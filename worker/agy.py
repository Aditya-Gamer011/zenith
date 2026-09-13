"""Antigravity CLI (agy) adapter — the actual worker transport.

Zenith doesn't care how a coding agent runs; this module is the one seam that
talks to Google's Antigravity CLI (`agy`). It exposes a small, task-oriented
API:

    submit(spec, workspace, parent) -> task_id        # spawn agy, stream JSONL
    get_status(task_id) -> dict
    get_output(task_id) -> str
    send_followup(task_id, message) -> bool           # continue conversation
    cancel(task_id) -> bool
    list_artifacts(task_id) -> list[str]
    wait_until(task_id, statuses, timeout) -> dict

Magic:
- Parses the `agy --output-format stream-json` lines into `current_activity`
  (step types + text deltas) and `output` (final result).
- Persists via TaskStore (worker/tasks.py), updates are reflected to Zenith
  through the REST API in peacant.py.
- The subprocess is detached: `agy` keeps running even if the HTTP API restarts.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
import uuid

from . import tasks as T  # worker/tasks.py

# Whether we've already surfaced the agent's clarifying question this session.
_seek_clarify: dict[str, bool] = {}


def _mark_waiting(task_id: str, on_update) -> None:
    """Mark a task WAITING_FOR_INPUT once (the monitor relays it to the user)."""
    if _seek_clarify.get(task_id):
        return
    _seek_clarify[task_id] = True
    if on_update:
        on_update(task_id, status=T.WAITING_FOR_INPUT)

_AGY = os.environ.get("AGY_BIN", shutil.which("agy") or shutil.which("antigravity") or "agy")
# The coding agent. Antigravity's own "low" effort is enough for most fixes;
# use "high" for planning-heavy tasks via agent flags below.
_MODEL = os.environ.get("AGY_MODEL", "gemini-3.1-pro-high")
_EFFORT = os.environ.get("AGY_EFFORT", "high")
# Long tasks shouldn't be cut short by agy's default 5m print timeout; Zenith
# runs tasks as background jobs so we set a generous outer bound.
_MAX_WAIT = int(os.environ.get("AGY_MAX_WAIT", str(60 * 60 * 4)))  # 4h default
_WS_ROOTS = ["/home/singh/zenith-workspaces", "/home/singh/peacos-workspaces", "/home/singh", "/workspace"]


def _pick(model: str) -> str:
    return model or _MODEL


def prompt_from_spec(spec: dict) -> str:
    """Build the exact Antigravity prompt from a structured engineering brief.

    `spec` fields (see brief.py for the full builder on the Zenith side):
      task, workspace, requirements[], constraints[], acceptanceCriteria[],
      autonomy ('high'|'medium'|'low'), destructive_allowed (bool),
      ask_for_clarification (bool), deliverables[], technologies[], context.
    """
    lines: list[str] = []
    lines.append("You are Google Antigravity, a senior engineer working a delegated task.")
    lines.append("")
    lines.append(f"## Task objective\n{spec.get('task') or '(unspecified)'}")
    if spec.get("context"):
        lines.append(f"\n## Context discovered by Zenith\n{spec['context']}")
    reqs = spec.get("requirements") or []
    if reqs:
        lines.append("\n## Requirements")
        for i, r in enumerate(reqs, 1):
            lines.append(f"{i}. {r}")
    cons = spec.get("constraints") or []
    if cons:
        lines.append("\n## Constraints")
        for i, c in enumerate(cons, 1):
            lines.append(f"{i}. {c}")
    woes = spec.get("acceptanceCriteria") or []
    if woes:
        lines.append("\n## Acceptance criteria")
        for i, a in enumerate(woes, 1):
            lines.append(f"{i}. {a}")
    tech = spec.get("technologies") or []
    if tech:
        lines.append(f"\n## Technologies to use\n{', '.join(tech)}")
    delivs = spec.get("deliverables") or []
    if delivs:
        lines.append("\n## Expected deliverables")
        for i, d in enumerate(delivs, 1):
            lines.append(f"{i}. {d}")
    workspace = spec.get("workspace") or ""
    lines.append(f"\n## Workspace\nWork inside: `{workspace}` (create it if missing, or clone the repo there as needed).")
    lines.append("\n## Working rules")
    autonomy = (spec.get("autonomy") or "high").lower()
    if autonomy == "high":
        lines.append("- You are autonomous: plan the work, do it, run tests/builds, and iterate without asking.")
    else:
        lines.append("- Work autonomously but keep the user informed at each meaningful step.")
    if spec.get("destructive_allowed"):
        lines.append("- Destructive changes are allowed when required; be careful and reversible where possible.")
    else:
        lines.append("- Do NOT make destructive changes (deletes, force-pushes, destructive DB/fs ops) unless:\n"
                     "    the task explicitly requires it AND the change is clearly scoped to the workspace.")
    if spec.get("ask_for_clarification", True) is not False:
        lines.append("- If a requirement is ambiguous or blockers appear, ask for clarification.\n"
                     "  Emit a single line starting with `CLARIFY:` followed by your question, then pause.\n"
                     "  Do not fabricate missing context.")
    else:
        lines.append("- Do not ask for clarification; make reasonable assumptions and proceed.")
    lines.append("- Do NOT push to production, deploy, or publish anything unless Zenith explicitly instructs it in this task.")
    lines.append("- Git: commit progress when the task reaches a working checkpoint, unless told otherwise. Never force-push to a shared branch.")
    lines.append("\n## Done"
                 "\nWhen completely done, summarize in 3-5 sentences: what you built/changed, how it was verified"
                 " (tests/build/cmd output), the files/artifacts created, and anything the user should know. Keep it clear and skimmable.")
    return "\n".join(lines)


def _ensure_workspace_rules(ws_path: str) -> None:
    """Save workspace tools/rules into .agents/rules so Antigravity automatically discovers them."""
    rules_dir = os.path.join(ws_path, ".agents", "rules")
    os.makedirs(rules_dir, exist_ok=True)
    rules_file = os.path.join(rules_dir, "environment_tools.md")
    if not os.path.exists(rules_file):
        content = """# Workspace Environment & Tool Guidelines

## Native Capability Discovery
- You are Google Antigravity, running autonomously within this workspace.
- Check workspace files, documentation, package manifests, and codebase structure first before making assumptions.
- Run tests and verification commands (`npm test`, `pytest`, `docker`, etc.) directly using bash execution.
- Maintain git commits for meaningful task milestones.
- Keep output concise and skimmable.
"""
        with open(rules_file, "w", encoding="utf-8") as f:
            f.write(content)


def _workspace_dir(spec: dict, default_root: str = None) -> str:
    """Resolve a workspace path, creating it if needed."""
    root = default_root or "/home/singh/peacos-workspaces"
    raw = (spec.get("workspace") or "").strip()
    if raw:
        # allow absolute or relative under root
        p = os.path.abspath(os.path.expanduser(raw))
        # only allow under the trusted root or an existing dir the user cares about
        if p != "/" and not p.startswith("/proc") and not p.startswith("/sys"):
            os.makedirs(p, exist_ok=True)
            _ensure_workspace_rules(p)
            return p
    # fall back to a slug under root
    slug = re.sub(r"[^a-z0-9_-]+", "-", (spec.get("task") or "task").lower())[:60] or "task"
    p = os.path.join(root, slug)
    os.makedirs(p, exist_ok=True)
    _ensure_workspace_rules(p)
    return p


def _list_artifacts(path: str) -> list[str]:
    """Cheap artifact scan: top-level files + any README/manifests deeper."""
    found: list[str] = []
    if not path or not os.path.isdir(path):
        return found
    try:
        for root, dirs, files in os.walk(path):
            depth = root[len(path):].count(os.sep)
            if depth > 3:
                dirs[:] = []
                continue
            if any(x in root for x in ("node_modules", ".git", "__pycache__", ".venv")):
                continue
            for fn in files:
                if fn in ("README.md", "package.json", "pyproject.toml", "Cargo.toml", "go.mod", "requirements.txt", "Dockerfile") or depth <= 1:
                    rel = os.path.relpath(os.path.join(root, fn), path)
                    found.append(rel)
        return sorted(set(found))
    except OSError:
        return found


def _stream_lines(proc, task_id: str, on_update) -> None:
    """Read agy stream-json stdout, update task.activity/output live."""
    if not proc.stdout:
        return
    result_text: list[str] = []
    last_activity = ""
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev = obj.get("event")
        if ev == "init":
            cid = obj.get("conversation_id") or obj.get("init", {}).get("conversation_id")
            if cid:
                on_update(task_id, conversation_id=str(cid))
        elif ev == "step_update":
            su = obj.get("step_update", {})
            st = su.get("step_type")
            state = su.get("state")
            delta = su.get("text_delta") or ""
            frag = ""
            if st:
                frag = f"[{st}:{state}]"
                if delta:
                    frag += f" {delta.strip()}"
                if frag.strip() != last_activity:
                    on_update(task_id, current_activity=frag)
                    last_activity = frag
            if delta:
                result_text.append(delta)
            # An agent blocked on a question pauses instead of finishing: mark
            # the task WAITING_FOR_INPUT so the monitor relays it to the user.
            if "CLARIFY:" in (frag or ""):
                _mark_waiting(task_id, on_update)
        elif ev == "result":
            res = obj.get("result", {})
            if res.get("response"):
                on_update(task_id, output=res["response"].strip())
            if res.get("status"):
                on_update(task_id, current_activity=f"[result:{res['status']}]")
    # final catch-all
    if result_text and not (on_update):
        pass  # keep; the per-line on_update() already stored output


def submit(spec: dict, parent: str | None = None, workspace: str | None = None) -> T.Task:
    """Create + start a task. Non-blocking: returns immediately with a Task."""
    prompt = prompt_from_spec(spec)
    # Always resolve through the same expander so ~/ and relative paths become
    # absolute, the dir is created, and the ledger stores the real path.
    if workspace:
        spec = dict(spec); spec["workspace"] = workspace
    ws = _workspace_dir(spec)
    os.makedirs(ws, exist_ok=True)  # ensure the workspace exists before agy cd's into it
    task = T.store.create(spec, ws, prompt, parent)
    T.store.set_status(task.id, T.RUNNING, started=True)
    _spawn(task.id)
    return task


def _spawn(task_id: str) -> None:
    """Launch agy for a task in a detached process thread."""
    task = T.store.get(task_id)
    if not task:
        return
    pr = prompt_from_spec(task.spec)
    cmd = [
        _AGY, "--print", pr,
        "--model", _pick(task.spec.get("model") or _MODEL),
        "--effort", _EFFORT,
        "--output-format", "stream-json",
        "--print-timeout", f"{_MAX_WAIT}s",
        "--add-dir", task.workspace,
        # Headless print mode can't prompt for permissions; auto-approve so the
        # coding agent can write files / run commands inside the workspace.
        # Safety is layered: task briefs forbid destructive/publish unless told,
        # and config keeps destructive_allowed=False by default.
        "--dangerously-skip-permissions",
    ]
    env = dict(os.environ)
    # Run under the user (must own ~/.gemini auth): this process is already
    # running as singh via the systemd unit.
    env.pop("AGY_DISABLE", None)

    def _run():
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=task.workspace or "/home/singh",
            )
            _stream_lines(proc, task_id, T.store.update)
            out, err = proc.communicate(timeout=_MAX_WAIT + 60)
        except Exception as exc:
            T.store.set_status(task_id, T.FAILED, error=str(exc))
            return
        if proc.returncode == 0:
            T.store.update(task_id, status=T.COMPLETED)
        elif proc.returncode == -signal.SIGKILL or proc.returncode == -signal.SIGTERM:
            T.store.update(task_id, status=T.CANCELLED)
        else:
            T.store.update(task_id, status=T.FAILED, errors=[err.decode("utf-8", "replace")[:2000]])

    import threading
    th = threading.Thread(target=_run, daemon=True, name=f"agy-{task_id}")
    th.start()


def _get(task_id: str) -> T.Task:
    t = T.store.get(task_id)
    if not t:
        raise KeyError(task_id)
    return t


def get_status(task_id: str) -> dict:
    t = _get(task_id)
    # discover artifacts lazily on completed tasks
    if t.status == T.COMPLETED and not t.artifacts:
        arts = _list_artifacts(t.workspace)
        if arts:
            T.store.update(task_id, artifacts=arts)
            t = _get(task_id)
    return t.to_dict()


def get_output(task_id: str) -> str:
    return _get(task_id).output or _get(task_id).current_activity or ""


def send_followup(task_id: str, message: str) -> bool:
    """Send a message into the ongoing agent conversation (new CLI turn)."""
    t = _get(task_id)
    if t.status not in (T.RUNNING, T.WAITING_FOR_INPUT, T.COMPLETED):
        return False
    if not t.conversation_id:
        # no running conversation id yet; can't continue a corpse
        t = T.store.update(task_id, status=T.WAITING_FOR_INPUT)
        return False
    # If the underlying agy run already finished, resume via --conversation.
    cmd = [
        _AGY, "--print", message,
        "--conversation", t.conversation_id,
        "--model", _pick(t.spec.get("model") or _MODEL),
        "--effort", _EFFORT,
        "--output-format", "stream-json",
        "--print-timeout", f"{_MAX_WAIT}s",
        "--dangerously-skip-permissions",
    ]
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ), cwd=t.workspace or "/home/singh",
        )
    except Exception:
        return False
    # We don't block; fire-and-forget is fine — the followup turn updates the
    # conversation. (Real wait + per-turn output can be added later.)
    return True


def cancel(task_id: str) -> bool:
    t = _get(task_id)
    if t.status not in (T.QUEUED, T.STARTING, T.RUNNING, T.WAITING_FOR_INPUT):
        return False
    # kill the agy subprocess if still alive (best-effort by pattern)
    for pid in _agy_pids(task_id):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    T.store.update(task_id, status=T.CANCELLED, completed_at=T._now())
    return True


def _agy_pids(task_id: str) -> list[int]:
    pids = []
    try:
        out = subprocess.check_output(["pgrep", "-f", f"agy.*{task_id}"], text=True, timeout=3)
        pids = [int(x) for x in out.split() if x.strip()]
    except Exception:
        pass
    return pids


def wait_until(task_id: str, statuses: tuple, timeout: int = 300) -> dict:
    t = _get(task_id)
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = _get(task_id)
        if t.status in statuses:
            return t.to_dict()
        time.sleep(1)
    return t.to_dict()