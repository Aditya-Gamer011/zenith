"""Antigravity CLI (agy) adapter — cross-platform worker transport.

Zenith delegates engineering and coding tasks to Google's Antigravity CLI (`agy`).
This module provides the task-oriented adapter:

    submit(spec, workspace, parent) -> task_id        # spawn agy, stream JSONL
    get_status(task_id) -> dict
    get_output(task_id) -> str
    send_followup(task_id, message) -> bool           # continue conversation
    cancel(task_id) -> bool
    list_artifacts(task_id) -> list[str]
    wait_until(task_id, statuses, timeout) -> dict

Cross-platform design:
- OS-neutral: operates across Linux, macOS, and Windows.
- Dynamically resolves user home directories, workspace paths, and CLI binaries.
- Safe process lifecycle tracking with native platform termination fallbacks.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import tasks as T  # worker/tasks.py

# Whether we've already surfaced the agent's clarifying question this session.
_seek_clarify: dict[str, bool] = {}

# Active process tracking for robust cross-platform cancellation
_active_procs: dict[str, subprocess.Popen] = {}


def _mark_waiting(task_id: str, on_update) -> None:
    """Mark a task WAITING_FOR_INPUT once (the monitor relays it to the user)."""
    if _seek_clarify.get(task_id):
        return
    _seek_clarify[task_id] = True
    if on_update:
        on_update(task_id, status=T.WAITING_FOR_INPUT)


def _resolve_agy_binary() -> str:
    """Locate the Antigravity CLI executable across Linux, macOS, and Windows."""
    env_bin = os.environ.get("AGY_BIN")
    if env_bin and shutil.which(env_bin):
        return env_bin
    
    found = shutil.which("agy") or shutil.which("antigravity")
    if found:
        return found
    
    # Check standard per-user binary paths
    home = Path.home()
    is_win = os.name == "nt"
    candidates = [
        home / ".local" / "bin" / ("agy.exe" if is_win else "agy"),
        home / ".local" / "bin" / ("antigravity.exe" if is_win else "antigravity"),
        home / "AppData" / "Local" / "agy" / "bin" / "agy.exe",
        home / "AppData" / "Roaming" / "npm" / "agy.cmd",
        home / "AppData" / "Local" / "Programs" / "agy" / "agy.exe",
        Path("/usr/local/bin/agy"),
        Path("/usr/bin/agy"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return "agy"


def check_auth_status() -> dict[str, Any]:
    """Check whether Antigravity CLI binary is installed and authenticated."""
    bin_path = _resolve_agy_binary()
    is_installed = bool(shutil.which(bin_path) or Path(bin_path).is_file())

    home = Path.home()
    token_files = [
        home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token",
        home / ".gemini" / "antigravity" / "token.json",
        home / ".gemini" / "credentials.json",
    ]
    is_authenticated = any(f.is_file() and f.stat().st_size > 0 for f in token_files)

    return {
        "installed": is_installed,
        "path": bin_path if is_installed else None,
        "authenticated": is_authenticated,
        "model": _MODEL,
        "effort": _EFFORT,
    }


_AGY = _resolve_agy_binary()
# The coding agent. Antigravity's own "low" effort is enough for most fixes;
# use "high" for planning-heavy tasks via agent flags below.
_MODEL = os.environ.get("AGY_MODEL", "gemini-3.1-pro-high")
_EFFORT = os.environ.get("AGY_EFFORT", "high")
# Long tasks shouldn't be cut short by agy's default 5m print timeout; Zenith
# runs tasks as background jobs so we set a generous outer bound.
_MAX_WAIT = int(os.environ.get("AGY_MAX_WAIT", str(60 * 60 * 4)))  # 4h default

_DEFAULT_WORKSPACE_ROOT = os.environ.get(
    "ZENITH_WORKSPACES_DIR",
    str(Path.home() / "zenith-workspaces")
)
_WS_ROOTS = [
    _DEFAULT_WORKSPACE_ROOT,
    str(Path.home()),
    "/workspace",
]


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
    rules_dir = Path(ws_path) / ".agents" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "environment_tools.md"
    if not rules_file.exists():
        content = """# Workspace Environment & Tool Guidelines

## Native Capability Discovery
- You are Google Antigravity, running autonomously within this workspace.
- Check workspace files, documentation, package manifests, and codebase structure first before making assumptions.
- Run tests and verification commands (`npm test`, `pytest`, `docker`, etc.) directly using command execution.
- Maintain git commits for meaningful task milestones.
- Keep output concise and skimmable.
"""
        rules_file.write_text(content, encoding="utf-8")


def _is_safe_workspace_path(p: str) -> bool:
    """Validate that a workspace path does not target sensitive system roots."""
    try:
        p_obj = Path(p).resolve()
        if p_obj == Path(p_obj.anchor):
            return False
        parts = {part.lower() for part in p_obj.parts}
        disallowed = {"proc", "sys", "windows", "system32", "etc"}
        if parts & disallowed:
            return False
        return True
    except Exception:
        return False


def _workspace_dir(spec: dict, default_root: str = None) -> str:
    """Resolve a workspace path, creating it if needed."""
    root = default_root or _DEFAULT_WORKSPACE_ROOT
    raw = (spec.get("workspace") or "").strip()
    if raw:
        p = os.path.abspath(os.path.expanduser(raw))
        if _is_safe_workspace_path(p):
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
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
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
            if "CLARIFY:" in (frag or ""):
                _mark_waiting(task_id, on_update)
        elif ev == "result":
            res = obj.get("result", {})
            if res.get("response"):
                on_update(task_id, output=res["response"].strip())
            if res.get("status"):
                on_update(task_id, current_activity=f"[result:{res['status']}]")


def submit(spec: dict, parent: str | None = None, workspace: str | None = None) -> T.Task:
    """Create + start a task. Non-blocking: returns immediately with a Task."""
    prompt = prompt_from_spec(spec)
    if workspace:
        spec = dict(spec)
        spec["workspace"] = workspace
    ws = _workspace_dir(spec)
    os.makedirs(ws, exist_ok=True)
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
        "--dangerously-skip-permissions",
    ]
    env = dict(os.environ)
    env.pop("AGY_DISABLE", None)
    fallback_cwd = str(Path.home())

    def _run():
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=task.workspace or fallback_cwd,
            )
            _active_procs[task_id] = proc
            _stream_lines(proc, task_id, T.store.update)
            out, err = proc.communicate(timeout=_MAX_WAIT + 60)
        except Exception as exc:
            T.store.set_status(task_id, T.FAILED, error=str(exc))
            return
        finally:
            _active_procs.pop(task_id, None)

        sig_term = getattr(signal, "SIGTERM", 15)
        sig_kill = getattr(signal, "SIGKILL", None)

        if proc.returncode == 0:
            T.store.update(task_id, status=T.COMPLETED)
        elif (sig_kill and proc.returncode == -sig_kill) or proc.returncode == -sig_term:
            T.store.update(task_id, status=T.CANCELLED)
        else:
            T.store.update(task_id, status=T.FAILED, errors=[err.decode("utf-8", "replace")[:2000]])

    th = threading.Thread(target=_run, daemon=True, name=f"agy-{task_id}")
    th.start()


def _get(task_id: str) -> T.Task:
    t = T.store.get(task_id)
    if not t:
        raise KeyError(task_id)
    return t


def get_status(task_id: str) -> dict:
    t = _get(task_id)
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
        t = T.store.update(task_id, status=T.WAITING_FOR_INPUT)
        return False
    cmd = [
        _AGY, "--print", message,
        "--conversation", t.conversation_id,
        "--model", _pick(t.spec.get("model") or _MODEL),
        "--effort", _EFFORT,
        "--output-format", "stream-json",
        "--print-timeout", f"{_MAX_WAIT}s",
        "--dangerously-skip-permissions",
    ]
    fallback_cwd = str(Path.home())
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(os.environ),
            cwd=t.workspace or fallback_cwd,
        )
    except Exception:
        return False
    return True


def cancel(task_id: str) -> bool:
    """Cancel a running task safely across Linux, macOS, and Windows."""
    t = _get(task_id)
    if t.status not in (T.QUEUED, T.STARTING, T.RUNNING, T.WAITING_FOR_INPUT):
        return False

    # 1. Terminate tracked subprocess directly
    proc = _active_procs.get(task_id)
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # 2. Process query fallback
    for pid in _agy_pids(task_id):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    T.store.update(task_id, status=T.CANCELLED, completed_at=T._now())
    return True


def _agy_pids(task_id: str) -> list[int]:
    """Find orphaned agy processes for a task across platforms."""
    pids = []
    try:
        if os.name == "nt":
            cmd = ["powershell", "-NoProfile", "-Command",
                   f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*agy*{task_id}*' }} | Select-Object -ExpandProperty ProcessId"]
            out = subprocess.check_output(cmd, text=True, timeout=4)
            pids = [int(x.strip()) for x in out.splitlines() if x.strip().isdigit()]
        elif shutil.which("pgrep"):
            out = subprocess.check_output(["pgrep", "-f", f"agy.*{task_id}"], text=True, timeout=3)
            pids = [int(x) for x in out.split() if x.strip().isdigit()]
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