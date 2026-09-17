"""Tool registry: the single catalog of every capability Zenith can invoke.

Tools are declared with a name, description, JSON-schema input params, and an
async handler. The Orchestrator exposes this catalog to the LLM as a `tools` list,
validates calls against the schema, and executes them.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable


class ToolValidationError(Exception):
    """Raised when the model's arguments fail the tool's JSON-schema-ish check."""


# Pluggable confirmation hook, installed by main.py's WS receive-pump. When
# set, gated tools call it before executing; it emits a `confirm` event and
# waits (bounded) for the human. When unset (tests, non-WS contexts), gated
# tools execute immediately — the gate is a live-session affordance, not a
# hard fail-safe.
async def _ask_confirmation(name: str, arguments: dict[str, Any]) -> bool:
    return True


def set_confirmation_hook(hook) -> None:
    """Install the confirmation async callable (name, args) -> bool."""
    global _ask_confirmation
    _ask_confirmation = hook


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


TOOLS: dict[str, dict[str, Any]] = {}


def register(
    name: str,
    description: str,
    params: dict[str, Any],
    handler: Callable[..., Awaitable[Any]],
    hidden_from_catalog: bool = False,
) -> None:
    """Add a tool. `params` is a JSON Schema object."""
    TOOLS[name] = {
        "name": name,
        "description": description,
        "parameters": params,
        "handler": handler,
        "hidden_from_catalog": hidden_from_catalog,
    }


def catalog() -> list[dict[str, Any]]:
    """The tools list handed to the LLM (schema only, no handler/flags)."""
    from .config import settings
    user_name = settings.user_name or "Friend"

    def _personalize(val: Any) -> Any:
        if isinstance(val, str):
            return (val.replace("the user's", f"{user_name}'s")
                       .replace("the user", user_name)
                       .replace("user's", f"{user_name}'s")
                       .replace("The user's", f"{user_name}'s")
                       .replace("The user", user_name))
        if isinstance(val, dict):
            return {k: _personalize(v) for k, v in val.items()}
        if isinstance(val, list):
            return [_personalize(x) for x in val]
        return val

    out = []
    for t in TOOLS.values():
        if t.get("hidden_from_catalog"):
            continue
        desc = t["description"]
        desc = (desc.replace("the user's", f"{user_name}'s")
                    .replace("the user", user_name)
                    .replace("user's", f"{user_name}'s")
                    .replace("The user's", f"{user_name}'s")
                    .replace("The user", user_name))
        params = _personalize(t["parameters"])
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": desc,
                "parameters": params,
            },
        })
    return out


EXECUTIVE_TOOL_NAMES = [
    "delegate_task",
    "list_agents",
    "get_agent_status",
    "update_user_profile",
    "memory",
    "graph",
    "switch_mode",
    "get_mode",
    "setup_secret",
    "get_setup_status",
    "zenith_docs",
]


def executive_catalog() -> list[dict[str, Any]]:
    """Scoped tool specs for Zenith Orchestrator's executive chat turns."""
    from .config import settings
    user_name = settings.user_name or "Friend"

    def _personalize(val: Any) -> Any:
        if isinstance(val, str):
            return (val.replace("the user's", f"{user_name}'s")
                       .replace("the user", user_name)
                       .replace("user's", f"{user_name}'s")
                       .replace("The user's", f"{user_name}'s")
                       .replace("The user", user_name))
        if isinstance(val, dict):
            return {k: _personalize(v) for k, v in val.items()}
        if isinstance(val, list):
            return [_personalize(x) for x in val]
        return val

    out = []
    for name in EXECUTIVE_TOOL_NAMES:
        t = TOOLS.get(name)
        if not t:
            continue
        desc = t["description"]
        desc = (desc.replace("the user's", f"{user_name}'s")
                    .replace("the user", user_name)
                    .replace("user's", f"{user_name}'s")
                    .replace("The user's", f"{user_name}'s")
                    .replace("The user", user_name))
        params = _personalize(t["parameters"])
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": desc,
                "parameters": params,
            },
        })
    return out


async def call_tool(
    name: str,
    arguments: dict[str, Any],
    emit: Callable | None = None,
) -> dict[str, Any]:
    """Validate & execute a tool by name.

    Returns a normalized result dict: {"ok": bool, "result": str | "error": str}.
    """
    tool = TOOLS.get(name)
    if not tool:
        return {"ok": False, "error": f"Unknown tool '{name}'"}

    # Kill-switch guard for shell.
    try:
        from ..core.config import settings

        if name == "shell" and not settings.allow_shell:
            return {"ok": False, "error": "Shell is disabled (ALLOW_SHELL=no). "
                                          "Enable in .env to allow shell commands."}
    except Exception:
        pass

    try:
        validated = json_validate(tool["parameters"], arguments or {})
    except ToolValidationError as exc:
        return {"ok": False, "error": f"Invalid arguments: {exc}"}

    # Confirmation checkpoint for mutating tools (live sessions install the
    # hook; tests/non-WS contexts pass through). Auto-refuses on timeout so a
    # missed dock can never wedge the turn.
    from ..core.confirmation import confirm_tools

    if name in confirm_tools():
        approved = await _ask_confirmation(name, validated)
        if not approved:
            return {"ok": False, "cancelled": True,
                    "error": "Action cancelled — user didn't approve it."}

    try:
        if name == "delegate_task" and emit is not None:
            result = await tool["handler"](**validated, emit=emit)
        else:
            result = await tool["handler"](**validated)
    except Exception as exc:
        return {"ok": False, "error": f"Tool '{name}' raised: {exc}"}

    if result is None:
        result = ""
    if isinstance(result, (dict, list)):
        try:
            result = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        except TypeError:
            result = str(result)
    return {"ok": True, "result": str(result)}


def json_validate(schema: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    """Validate a plain dict against a JSON Schema subset (required + types).

    Kept intentionally small: checks required keys, adapts raw string inputs
    for single-parameter or email schemas, and enforces basic types/items.
    """
    value = dict(value or {})
    required = set(schema.get("required", []))

    # If args came as a raw unparsed string (e.g. {"raw": "..."}):
    if "raw" in value and isinstance(value["raw"], str):
        raw_text = value.pop("raw").strip()
        if len(required) == 1:
            value[list(required)[0]] = raw_text
        elif "to" in schema.get("properties", {}):
            import re
            m = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", raw_text)
            if m:
                value["to"] = m.group(1)
                value["body"] = raw_text
                value["subject"] = "Message from Zenith"

    # Fill defaults or sensible fallbacks for email send/draft if partially supplied
    if "to" in schema.get("properties", {}):
        if "to" in value and not value.get("subject"):
            value["subject"] = "Message from Zenith"
        if "to" in value and not value.get("body"):
            value["body"] = value.get("subject") or "Hello"

    missing = required - set(value.keys())
    if missing:
        raise ToolValidationError(f"missing: {sorted(missing)}")

    properties = schema.get("properties", {})
    for key, spec in properties.items():
        if key not in value:
            continue
        raw = value[key]
        kind = spec.get("type")
        if kind == "string" and not isinstance(raw, str):
            value[key] = str(raw)
        elif kind == "number" and not isinstance(raw, (int, float)):
            try:
                value[key] = float(raw)
            except (TypeError, ValueError):
                pass
        elif kind == "integer" and not isinstance(raw, int):
            try:
                value[key] = int(raw)
            except (TypeError, ValueError):
                pass
        elif kind == "boolean" and not isinstance(raw, bool):
            value[key] = str(raw).lower() in ("1", "true", "yes", "on")
    return value


# ─────────────────────────────────────────────────────── handlers ────────────


async def tool_shell(command: str, cwd: str = "", timeout: int = 60, shell_type: str = "auto") -> str:
    from zenith.tools.computer import run_shell
    timeout = 60 if not timeout else max(1, min(timeout, 300))
    return await run_shell(command, cwd=cwd, timeout=timeout, shell_type=shell_type, max_output=4000)


async def tool_get_command_history(limit: int = 10) -> str:
    """Return the recent command history executed in this session."""
    from zenith.tools.computer import format_command_history
    return format_command_history(limit=limit)


async def tool_get_system_info(detail_level: str = "summary") -> str:
    """Introspect the host, OS (Linux/macOS/Windows), container/server environment, and hardware vitals."""
    from zenith.tools.system_info import format_host_summary, format_host_details_markdown
    if str(detail_level).lower() in ("full", "detailed", "markdown", "all"):
        return format_host_details_markdown()
    return format_host_summary()


async def tool_get_available_tools(category: str = "", query: str = "") -> str:
    """Inspect all available tools Zenith can invoke, their schemas, parameters, and categories."""
    from zenith.tools.tool_explorer import get_available_tools
    return get_available_tools(category=category, query=query)


async def tool_get_configurable_tools() -> str:
    """List all tools and integrations that can be configured in Zenith and their credential requirements."""
    from zenith.tools.tool_explorer import get_configurable_tools
    return get_configurable_tools()


async def tool_time_now() -> str:
    """Explicit current wall-clock time so Zenith can answer 'what time is it?'."""
    from datetime import datetime
    import os
    from zoneinfo import ZoneInfo
    from .config import settings

    tz = getattr(settings, "user_timezone", "") or os.getenv("USER_TIMEZONE") or os.getenv("TZ", "Asia/Kolkata")
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception:
        now = datetime.now()
    return f"{now.strftime('%A, %d %B %Y, %I:%M %p')} ({tz})"


async def tool_git_commit(repo_path: str = "", message: str = "") -> str:
    """Stage all changes and commit in a repo directory (safe local)."""
    from zenith.tools.git_dev import _resolve_repo, _run_blocking

    if not message:
        return "[git] Provide a commit message."
    path = _resolve_repo(repo_path)
    if not (path / ".git").exists():
        return f"[git] Not a git repository: {path}"
    try:
        await _run_blocking(["git", "add", "-A"], timeout=20, cwd=path)
        proc = await _run_blocking(
            ["git", "commit", "-m", message], timeout=20, cwd=path,
        )
        if proc.returncode == 0:
            return f"Committed in {path}: {message}"
        # Nothing to commit (clean tree) or a validation failure:
        err = proc.stderr.strip() or proc.stdout.strip()
        if "nothing to commit" in err or "no changes" in err:
            return "Nothing to commit — working tree is clean."
        return f"[git] commit failed: {err[:300]}"
    except Exception as exc:
        return f"[git commit error] {exc}"


async def tool_read_file(path: str) -> str:
    from zenith.tools.computer import read_file
    return await read_file(path)


async def tool_write_file(path: str, content: str) -> str:
    from zenith.tools.computer import write_file
    return await write_file(path, content)


async def tool_list_dir(path: str) -> str:
    from zenith.tools.computer import list_dir
    return await list_dir(path)


async def tool_weather(location: str = "autodetect") -> str:
    from zenith.tools.web import get_weather
    return await get_weather(location)


async def tool_web_search(query: str) -> str:
    from zenith.tools.web import web_search
    return await web_search(query)


async def tool_read_url(url: str) -> str:
    from zenith.tools.web import read_url
    return await read_url(url)


# ── Maps ────────────────────────────────────────────────────────────────────
async def tool_maps_search(query: str, location: str = "") -> str:
    from zenith.tools.maps import maps_search
    return await maps_search(query, location)


async def tool_maps_directions(origin: str, destination: str, mode: str = "driving") -> str:
    from zenith.tools.maps import maps_directions
    return await maps_directions(origin, destination, mode)


async def tool_maps_commute(origin: str, destinations: Any = "", mode: str = "driving") -> str:
    from zenith.tools.maps import maps_commute
    return await maps_commute(origin, destinations, mode)


async def tool_maps_geocode(location: str) -> str:
    from zenith.tools.maps import maps_geocode
    return await maps_geocode(location)


async def tool_maps_embed(
    query_or_place: str = "",
    embed_type: str = "place",
    origin: str = "",
    destination: str = "",
    mode: str = "driving",
) -> str:
    from zenith.tools.maps import maps_embed
    return await maps_embed(query_or_place, embed_type, origin, destination, mode)


# ── God's Eye View (GEV) ─────────────────────────────────────────────────────
async def tool_gods_eye_view(
    location: str = "",
    lat: float | None = None,
    lon: float | None = None,
    alt: float | None = None,
    style: str = "normal",
    hud: str = "tactical",
    heading: float = 0,
    pitch: float = -35,
    map_layer: str = "photoreal",
) -> str:
    from zenith.tools.gods_eye_view import gods_eye_view
    return await gods_eye_view(
        location=location,
        lat=lat,
        lon=lon,
        alt=alt,
        style=style,
        hud=hud,
        heading=heading,
        pitch=pitch,
        map_layer=map_layer,
    )


async def tool_gods_eye_view_status() -> str:
    from zenith.tools.gods_eye_view import gods_eye_view_status
    return await gods_eye_view_status()


async def tool_browser(url: str, max_chars: int = 5000) -> str:
    from zenith.tools.browser import browse
    return await browse(url, max_chars=max_chars)


async def tool_browser_screenshot(url: str, full_page: bool = True) -> str:
    from zenith.tools.browser import browser_screenshot
    return await browser_screenshot(url, full_page=full_page)


async def tool_browser_click(url: str, selector: str) -> str:
    from zenith.tools.browser import browser_click
    return await browser_click(url, selector)


async def tool_browser_type(url: str, selector: str, text: str, submit: bool = False) -> str:
    from zenith.tools.browser import browser_type
    return await browser_type(url, selector, text, submit)


async def tool_notes(action: str, title: str = "", text: str = "") -> str:
    from zenith.tools.notes import notes
    return await notes(action, title, text)


async def tool_todo(action: str, title: str = "", text: str = "", todo_id: int | None = None) -> str:
    from zenith.tools.todo import todo
    title = title or text or ""
    # When the user says "remove X from my todos" the model may give the title
    # but not the id. Resolve by fuzzy title match so delete/done actually work.
    if (action in ("delete", "done")) and not todo_id and title:
        from zenith.tools.todo import all_todos
        try:
            matches = [t for t in all_todos() if title.lower() in (t.get("title") or "").lower()]
            if matches:
                if len(matches) == 1:
                    todo_id = matches[0]["id"]
                elif action == "delete":
                    # Multiple matches → delete all of them (a clear intent).
                    return " | ".join(todo("delete", "", m["id"]) for m in matches)
        except Exception:
            pass
    return await todo(action, title, todo_id)


async def tool_reminder(action: str, text: str = "", when: str = "", rid: int | None = None) -> str:
    from zenith.tools.reminders import reminder
    return await reminder(action, text, when, rid)


async def tool_email_reminder(task: str, when: str = "") -> str:
    """Email a one-off reminder to the user. Calendar events are separate; this is
    just the emailed reminder (opt-in, confirmation-gated)."""
    from zenith.tools.homelab import email_send

    target_email = settings.user_email or settings.gmail_user
    if not target_email:
        return "Email reminder failed: no user email configured (set USER_EMAIL or GMAIL_USER in settings)."

    body = (f"⏰ Reminder from Zenith:\n\n{task}\n\n"
            f"Scheduled for: {when or 'as set on your calendar'}.")
    return await email_send(target_email, f"⏰ {task}", body)


async def tool_memory(action: str, key: str = "", value: str = "", query: str = "") -> str:
    from zenith.tools.memory import memory
    return await memory(action, key, value, query)


async def tool_graph(query: str = "") -> str:
    from zenith.tools.memory import graph
    return await graph(query)


async def tool_agent(action: str, name: str = "", goal: str = "", context: str = "", agent_id: str = "") -> str:
    from zenith.tools.agent import agent
    return await agent(action, name, goal, context, agent_id)


async def tool_delegate_task(department: str, task: str, context: str = "", synchronous: bool = True, emit: Any = None) -> str:
    from zenith.tools.agent import delegate_task
    return await delegate_task(department, task, context, synchronous, emit=emit)



async def tool_list_agents() -> str:
    from zenith.tools.agent import list_agents
    return await list_agents()


async def tool_get_agent_status(run_id: str = "") -> str:
    from zenith.tools.agent import get_agent_status
    return await get_agent_status(run_id)


async def tool_hire_agent(
    agent_id: str,
    name: str = "",
    department: str = "",
    role_description: str = "",
    system_prompt: str = "",
    tool_names: list[str] | None = None,
) -> str:
    from zenith.tools.agent import hire_agent
    return await hire_agent(agent_id, name, department, role_description, system_prompt, tool_names)


async def tool_update_agent(
    agent_id: str,
    system_prompt: str = "",
    tool_names: list[str] | None = None,
    role_description: str = "",
) -> str:
    from zenith.tools.agent import update_agent
    return await update_agent(agent_id, system_prompt, tool_names, role_description)


async def tool_fire_agent(agent_id: str) -> str:
    from zenith.tools.agent import fire_agent
    return await fire_agent(agent_id)


async def tool_inspect_agent(agent_id: str) -> str:
    from zenith.tools.agent import inspect_agent
    return await inspect_agent(agent_id)


async def tool_list_available_tools(filter: str = "") -> str:
    from zenith.tools.agent import list_available_tools
    return await list_available_tools(filter)



async def tool_calendar(action: str, text: str = "", when: str = "", event_id: str = "") -> str:
    from zenith.tools.calendar import calendar
    return await calendar(action, text or event_id, when, event_id=event_id)


# Control-plane admin tools
async def tool_docker_list() -> str:
    from zenith.tools.homelab import docker_list
    return await docker_list()


async def tool_docker_table() -> str:
    from zenith.tools.homelab import docker_table
    return await docker_table()


async def tool_docker_status(container: str) -> str:
    from zenith.tools.homelab import docker_status
    return await docker_status(container)


async def tool_docker_logs(container: str, tail: int = 80) -> str:
    from zenith.tools.homelab import docker_logs
    return await docker_logs(container, tail)


async def tool_docker_start(container: str) -> str:
    from zenith.tools.homelab import docker_start
    return await docker_start(container)


async def tool_docker_stop(container: str) -> str:
    from zenith.tools.homelab import docker_stop
    return await docker_stop(container)


async def tool_docker_restart(container: str) -> str:
    from zenith.tools.homelab import docker_restart
    return await docker_restart(container)


async def tool_system_status() -> str:
    from zenith.tools.homelab import system_status
    return await system_status()


async def tool_disk_usage() -> str:
    from zenith.tools.homelab import disk_usage
    return await disk_usage()


async def tool_memory_usage() -> str:
    from zenith.tools.homelab import memory_usage
    return await memory_usage()


async def tool_top_processes() -> str:
    from zenith.tools.homelab import top_processes
    return await top_processes()


async def tool_gh_whoami() -> str:
    from zenith.tools.homelab import gh_whoami
    return await gh_whoami()


async def tool_gh_repos(owner: str = "") -> str:
    from ..core.config import settings
    owner = owner or getattr(settings, "github_user", "") or os.getenv("GITHUB_USER", "")
    from zenith.tools.homelab import gh_list_repos
    return await gh_list_repos(owner)


async def tool_gh_issues(owner: str, repo: str) -> str:
    from zenith.tools.homelab import gh_issues
    return await gh_issues(owner, repo)


async def tool_gh_pulls(owner: str, repo: str) -> str:
    from zenith.tools.homelab import gh_pulls
    return await gh_pulls(owner, repo)


async def tool_gh_repo_status(owner: str, repo: str) -> str:
    from zenith.tools.homelab import gh_repo_status
    return await gh_repo_status(owner, repo)


async def tool_gh_create_issue(owner: str, repo: str, title: str, body: str = "") -> str:
    from zenith.tools.homelab import gh_create_issue
    return await gh_create_issue(owner, repo, title, body)


async def tool_gh_create_repo(name: str, private: bool = False, description: str = "") -> str:
    from zenith.tools.homelab import gh_create_repo
    return await gh_create_repo(name, private, description)


async def tool_mc_status() -> str:
    from zenith.tools.homelab import mc_status
    return await mc_status()


async def tool_mc_players() -> str:
    from zenith.tools.homelab import mc_players
    return await mc_players()


async def tool_mc_admin(
    command: str = "list",
    player: str = "",
    item: str = "",
    count: str = "",
    x: str = "0",
    y: str = "64",
    z: str = "0",
    message: str = "",
    tick: str = "1000",
    weather: str = "clear",
) -> str:
    from zenith.tools.rcon import mc_admin
    return await mc_admin(command, player, item, count, x, y, z, message, tick, weather)


async def tool_mc_admin_help() -> str:
    from zenith.tools.rcon import mc_admin_help
    return await mc_admin_help()


async def tool_youtube_transcript(url: str = "") -> str:
    from zenith.tools.youtube import youtube_transcript
    return await youtube_transcript(url)


async def tool_youtube_search(query: str = "") -> str:
    from zenith.tools.youtube import youtube_search
    return await youtube_search(query)


async def tool_n8n_health() -> str:
    from zenith.tools.n8n import n8n_health
    return await n8n_health()


async def tool_n8n_workflows(limit: int = 20) -> str:
    from zenith.tools.n8n import n8n_workflows
    return await n8n_workflows(limit)


async def tool_n8n_execute(workflow_id: str = "", name: str = "", data: str = "{}") -> str:
    from zenith.tools.n8n import n8n_execute
    return await n8n_execute(workflow_id, name, data)


async def tool_mc_start() -> str:
    from zenith.tools.homelab import mc_start
    return await mc_start()


async def tool_mc_stop() -> str:
    from zenith.tools.homelab import mc_stop
    return await mc_stop()


async def tool_mc_restart() -> str:
    from zenith.tools.homelab import mc_restart
    return await mc_restart()


async def tool_email_search(query: str = "") -> str:
    from zenith.tools.homelab import email_search
    return await email_search(query)


async def tool_email_read(uid: str) -> str:
    from zenith.tools.homelab import email_read
    return await email_read(uid)


async def tool_email_draft(to: str, subject: str, body: str, attachment_path: str = "") -> str:
    # Direct execution policy — email_draft transmits immediately without draft hold
    return await tool_email_send(to, subject, body, attachment_path)


async def tool_email_send(to: str, subject: str, body: str, attachment_path: str = "", attachment_paths: list[str] | None = None) -> str:
    from zenith.tools import mail
    from pathlib import Path
    import re

    # The model sometimes hands us the literal characters "\n" instead of real
    # line breaks. Normalize once here; mail._normalize_body re-covers every
    # other send path (attachment, SMTP, gateways).
    if body:
        body = re.sub(r"\n\s*\n\s*\n+", "\n\n",
                      mail._normalize_body(body))

    # Collect requested attachments. Endorse explicit paths the model (or a
    # previous tool result) actually handed us — those win over any guessing.
    requested: list[str] = []
    if attachment_path:
        requested.append(attachment_path)
    if attachment_paths:
        requested.extend(a for a in attachment_paths if a)

    def clean_path(raw: str) -> Path:
        raw = (raw or "").strip().strip("'\"")
        m = re.search(r"(/tmp/zenith-files/[^\s)]+)", raw)
        if m:
            raw = m.group(1)
        return Path(raw).expanduser()

    outdir = Path("/tmp/zenith-files")
    text_check = (subject or "").lower() + " " + (body or "").lower()
    is_ppt_request = any(k in text_check for k in ["ppt", "presentation", "slide", "powerpoint"])

    resolved: list[str] = []
    seen = set()
    for raw in requested:
        p = clean_path(raw)
        if not p.is_file():
            cand = outdir / p.name
            if cand.is_file():
                p = cand
            else:
                # Even an explicit path can be a blob of text — try to resolve
                # the most recent file whose stem matches the given stem.
                stem = p.stem.split("_")[0]
                glob = outdir.glob(f"{stem}*")
                pool = sorted([f for f in glob if f.is_file()], key=lambda f: f.stat().st_mtime, reverse=True)
                if pool:
                    p = pool[0]
        if p.is_file() and p not in seen:
            resolved.append(str(p))
            seen.add(p)

    # Only when NOTHING was explicitly named do we pick for the user — and even
    # then, a PPT request must resolve to a pptx (never the wrong file type).
    if not resolved and outdir.exists():
        pool = [f for f in outdir.iterdir() if f.is_file()]
        if is_ppt_request:
            pool = [f for f in pool if f.suffix.lower() == ".pptx"]
        if not pool and is_ppt_request:
            pool = []  # no pptx available → no silent wrong-type attach
        words = [w for w in re.findall(r"\w+", text_check)
                 if len(w) > 3 and w not in {"make", "send", "generate", "create", "with",
                                             "from", "about", "presentation", "slide",
                                             "powerpoint", "email", "tmp", "zenith", "files"}]
        scored = sorted(pool, key=lambda f: (sum(w in f.name.lower() for w in words), f.stat().st_mtime), reverse=True)
        if scored:
            resolved = [str(scored[0])]

    return await mail.send(to, subject, body, attachment_paths=resolved)


# ── Charting & Research ───────────────────────────────────────────────────────
async def tool_generate_chart(
    title: str,
    chart_type: str = "bar",
    labels: Any = "",
    values: Any = "",
    series_names: Any = "",
    x_label: str = "",
    y_label: str = "",
    upload_to_cdn: bool = False,
) -> str:
    from zenith.tools.charts import generate_chart
    return await generate_chart(title, chart_type, labels, values, series_names, x_label, y_label, upload_to_cdn)


async def tool_deep_research(
    topic: str,
    extra_queries: list[str] | None = None,
    pdf_files: list[str] | None = None,
    max_sources: int = 6,
    generate_report_pdf: bool = True,
    create_chart: bool = True,
) -> str:
    from zenith.tools.research import deep_research
    return await deep_research(
        topic,
        extra_queries=extra_queries,
        pdf_files=pdf_files,
        max_sources=max_sources,
        generate_report_pdf=generate_report_pdf,
        create_chart=create_chart,
    )


async def tool_research_synthesis(
    topic: str,
    extra_queries: list[str] | None = None,
    pdf_files: list[str] | None = None,
    max_sources: int = 6,
    generate_pdf_report: bool = True,
) -> str:
    return await tool_deep_research(
        topic=topic,
        extra_queries=extra_queries,
        pdf_files=pdf_files,
        max_sources=max_sources,
        generate_report_pdf=generate_pdf_report,
    )


async def tool_generate_pptx(
    title: str,
    subtitle: str = "",
    slides: list[dict] | str = None,
    author: str = "",
    theme: str = "executive_dark",
    template: str = "",
    transition: str = "fade",
) -> str:
    from ..core.config import settings
    author = author or settings.user_name or "Zenith"
    from zenith.tools.presentation import generate_pptx
    return await generate_pptx(
        title=title,
        subtitle=subtitle,
        slides=slides,
        author=author,
        theme=theme,
        template=template,
        transition=transition,
    )


async def tool_list_pptx_themes() -> str:
    import json
    themes_info = {
        "executive_dark": "Midnight Obsidian Slate background (#0B0F19), Slate Cards, Violet & Cyan Accents (Default Executive)",
        "cyberpunk_neon": "Deep Black background (#08090C), Neon Cyan (#00F3FF) & Electric Pink (#FF007F) High-Contrast Accents",
        "corporate_light": "Crisp Platinum White background (#F8FAFC), Sapphire Blue (#1E40AF) & Sky Blue (#0284C7) Accents",
        "emerald_forest": "Obsidian Emerald Green background (#041E19), Mint & Teal Accents (#10B981)",
        "sunset_warm": "Warm Charcoal background (#1C1917), Amber Gold (#F59E0B) & Crimson (#E11D48) Accents",
        "midnight_violet": "Deep Velvet Purple background (#0F0C1B), Violet (#A855F7) & Hot Pink Accents",
    }
    return json.dumps(themes_info, indent=2)


async def tool_list_pptx_templates() -> str:
    import json
    templates_info = {
        "pitch_deck": "4-Slide Widescreen Pitch Deck (Opportunity Split, Core Solution Cards, Market TAM Stats, Roadmap Timeline)",
        "tech_overview": "3-Slide Technical Architecture Brief (Data Center Photo Hero, Latency & Uptime Stat Hero, Feature Cards)",
        "market_analysis": "3-Slide Financial & Market Brief (Global Market Photo Hero, Valuation Stat Hero, Competitive Matrix)",
    }
    return json.dumps(templates_info, indent=2)


async def tool_search_presentation_photos(query: str) -> str:
    from zenith.tools.presentation import fetch_web_image
    img_path = await fetch_web_image(query)
    if img_path:
        return f"SUCCESS: Downloaded and verified presentation photo for '{query}' at {img_path}"
    return f"FAILED: Could not locate web photo for '{query}'."


async def tool_fetch_stock_photo(query: str) -> str:
    from zenith.tools.presentation import fetch_web_image
    img_path = await fetch_web_image(query)
    if img_path:
        return f"SUCCESS: Downloaded high-resolution stock photo for '{query}' at {img_path}"
    return f"FAILED: Could not locate stock photo for '{query}'."




# ── Homelab Suite ────────────────────────────────────────────────────────────
async def tool_media_search(query: str, media_type: str = "all") -> str:
    from zenith.tools.homelab_suite import media_search
    return await media_search(query, media_type)


async def tool_media_add(title: str, media_type: str = "movie", search_now: bool = True) -> str:
    from zenith.tools.homelab_suite import media_add
    return await media_add(title, media_type, search_now)


async def tool_media_queue() -> str:
    from zenith.tools.homelab_suite import media_queue
    return await media_queue()


async def tool_torrent_control(action: str = "list", info_hash: str = "") -> str:
    from zenith.tools.homelab_suite import torrent_control
    return await torrent_control(action, info_hash)


async def tool_tunnel_status() -> str:
    from zenith.tools.homelab_suite import tunnel_status
    return await tunnel_status()


async def tool_tunnel_add_route(subdomain: str, local_port: int) -> str:
    from zenith.tools.homelab_suite import tunnel_add_route
    return await tunnel_add_route(subdomain, local_port)


async def tool_homelab_overview() -> str:
    from zenith.tools.homelab_suite import homelab_overview
    return await homelab_overview()


async def tool_ha_fan(action: str = "status", entity_id: str = "fan.fan_2", percentage: int | None = None) -> str:
    from zenith.tools.homeassistant import ha_fan
    return await ha_fan(action, entity_id, percentage)


async def tool_ha_ac(
    action: str = "status",
    temperature: float | None = None,
    mode: str | None = None,
    fan_mode: str | None = None,
) -> str:
    from zenith.tools.homeassistant import ha_ac
    return await ha_ac(action, temperature, mode, fan_mode)


async def tool_ha_climate(
    action: str = "status",
    entity_id: str = "climate.panasonic_ac_panasonic_ac",
    temperature: float | None = None,
    hvac_mode: str | None = None,
    fan_mode: str | None = None,
) -> str:
    from zenith.tools.homeassistant import ha_climate
    return await ha_climate(action, entity_id, temperature, hvac_mode, fan_mode)



async def tool_ha_soundbar(action: str = "status") -> str:
    from zenith.tools.homeassistant import ha_soundbar
    return await ha_soundbar(action)


async def tool_ha_switch(action: str = "status", device: str = "ac") -> str:
    from zenith.tools.homeassistant import ha_switch
    return await ha_switch(action, device)


async def tool_ha_smart_plug(action: str = "status") -> str:
    from zenith.tools.homeassistant import ha_smart_plug
    return await ha_smart_plug(action)


async def tool_ha_overview() -> str:
    from zenith.tools.homeassistant import ha_overview
    return await ha_overview()


async def tool_ha_entity(action: str = "status", domain: str = "homeassistant", service: str = "toggle", entity_id: str = "fan.fan_2") -> str:
    from zenith.tools.homeassistant import ha_entity
    return await ha_entity(action, domain, service, entity_id)



# ── File & Image Processing ───────────────────────────────────────────────────
async def tool_analyze_image(image_path: str, prompt: str = "") -> str:
    from zenith.tools.file_processor import analyze_image
    return await analyze_image(image_path, prompt)


async def tool_edit_image(
    image_path: str,
    action: str,
    width: int = 0,
    height: int = 0,
    angle: int = 0,
    target_format: str = "",
    watermark_text: str = "",
) -> str:
    from zenith.tools.file_processor import edit_image
    return await edit_image(image_path, action, width, height, angle, target_format, watermark_text)


async def tool_analyze_file(file_path: str) -> str:
    from zenith.tools.file_processor import analyze_file
    return await analyze_file(file_path)


async def tool_modify_file(file_path: str, new_content: str, output_filename: str = "") -> str:
    from zenith.tools.file_processor import modify_file
    return await modify_file(file_path, new_content, output_filename)


# ── GitHub Pro Suite ─────────────────────────────────────────────────────────
async def tool_gh_create_pr(
    title: str,
    body: str = "",
    head_branch: str = "",
    base_branch: str = "main",
    repo_path: str = "",
    draft: bool = False,
) -> str:
    from zenith.tools.gh_pro import gh_create_pr
    return await gh_create_pr(title, body, head_branch, base_branch, repo_path, draft)


async def tool_gh_code_review(base_branch: str = "main", repo_path: str = "") -> str:
    from zenith.tools.gh_pro import gh_code_review
    return await gh_code_review(base_branch, repo_path)


async def tool_gh_list_issues_prs(repo: str = "", state: str = "open") -> str:
    from zenith.tools.gh_pro import gh_list_issues_prs
    return await gh_list_issues_prs(repo, state)


async def tool_gh_release_create(
    tag: str,
    title: str = "",
    notes: str = "",
    asset_path: str = "",
    repo_path: str = "",
) -> str:
    from zenith.tools.gh_pro import gh_release_create
    return await gh_release_create(tag, title, notes, asset_path, repo_path)


# ── Network & HTTP Testing Suite ──────────────────────────────────────────────
async def tool_http_request(
    url: str,
    method: str = "GET",
    headers: Any = "",
    params: Any = "",
    data: Any = "",
    timeout: int = 15,
) -> str:
    from zenith.tools.net_tools import http_request
    return await http_request(url, method, headers, params, data, timeout)


async def tool_dns_lookup(domain: str, record_type: str = "A") -> str:
    from zenith.tools.net_tools import dns_lookup
    return await dns_lookup(domain, record_type)


# ── Advanced Web Suite ───────────────────────────────────────────────────────
async def tool_web_screenshot_full(url: str, full_page: bool = True) -> str:
    return await tool_browser_screenshot(url, full_page=full_page)


async def tool_web_extract_data(url: str, selector: str = "", extract_type: str = "text") -> str:
    from zenith.tools.web_pro import web_extract_data
    return await web_extract_data(url, selector, extract_type)


async def _auto_pptx_from_text(title: str, filename: str, content: str) -> str:
    from zenith.tools.presentation import generate_pptx

    clean_title = title or filename.replace("_", " ").replace("-", " ").title()
    slides = []
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    for line in lines:
        if line.startswith("#") or line.lower().startswith("slide") or (len(line) < 40 and line.endswith(":")):
            slide_title = line.lstrip("#").strip()
            slides.append({"title": slide_title, "bullets": [], "layout": "cards_grid"})
        else:
            if not slides:
                slides.append({"title": clean_title, "bullets": [], "layout": "cards_grid"})
            b = line.lstrip("*-•0123456789. ").strip()
            if b:
                slides[-1]["bullets"].append(b)

    if not slides:
        slides = [{"title": clean_title, "bullets": [content[:150]], "layout": "cards_grid"}]

    return await generate_pptx(title=clean_title, subtitle="Executive Presentation", slides=slides)


async def tool_generate_pdf(filename: str, content: str, title: str = "") -> str:
    check = (filename + " " + content + " " + title).lower()
    if any(k in check for k in ["ppt", "presentation", "slide", "powerpoint"]):
        return await _auto_pptx_from_text(title, filename, content)
    from zenith.tools.filegen import generate_pdf
    return await generate_pdf(filename, content, title)


async def tool_generate_docx(filename: str, content: str, title: str = "") -> str:
    check = (filename + " " + content + " " + title).lower()
    if any(k in check for k in ["ppt", "presentation", "slide", "powerpoint"]):
        return await _auto_pptx_from_text(title, filename, content)
    from zenith.tools.filegen import generate_docx
    return await generate_docx(filename, content, title)


async def tool_generate_xlsx(filename: str, data: str, sheet_name: str = "Sheet1") -> str:
    from zenith.tools.filegen import generate_xlsx
    return await generate_xlsx(filename, data, sheet_name)


async def tool_generate_code(filename: str, content: str) -> str:
    from zenith.tools.filegen import generate_code
    return await generate_code(filename, content)


async def tool_generate_csv(filename: str, data: str) -> str:
    from zenith.tools.filegen import generate_csv
    return await generate_csv(filename, data)


async def tool_generate_json(filename: str, data: str) -> str:
    from zenith.tools.filegen import generate_json
    return await generate_json(filename, data)


async def tool_list_generated_files() -> str:
    from zenith.tools.filegen import list_generated_files
    return await list_generated_files()


async def tool_delete_generated_file(filename: str) -> str:
    from zenith.tools.filegen import delete_generated_file
    return await delete_generated_file(filename)


# ── CDN (cdn.hackclub.com) ──────────────────────────────────────────────────
async def tool_cdn_upload(file_path: str) -> str:
    from zenith.tools.cdn import cdn_upload
    return await cdn_upload(file_path)


async def tool_cdn_upload_url(url: str, source_auth: str = "") -> str:
    from zenith.tools.cdn import cdn_upload_url
    return await cdn_upload_url(url, source_auth)


async def tool_cdn_delete(upload_id: str) -> str:
    from zenith.tools.cdn import cdn_delete
    return await cdn_delete(upload_id)


async def tool_cdn_quota() -> str:
    from zenith.tools.cdn import cdn_quota
    return await cdn_quota()


async def tool_mailbox_create() -> str:
    from zenith.tools.mailbox import create
    return await create()


async def tool_mailbox_messages(address: str, password: str, limit: int = 8) -> str:
    from zenith.tools.mailbox import messages
    return await messages(address, password, limit)


async def tool_mailbox_read(address: str, password: str) -> str:
    from zenith.tools.mailbox import read
    return await read(address, password)


async def tool_mailbox_delete(address: str, password: str) -> str:
    from zenith.tools.mailbox import delete
    return await delete(address, password)


# ── Cloudflare ───────────────────────────────────────────────────────────────
async def tool_cf_dns_list(zone: str = "") -> str:
    from zenith.tools.integrations import cf_dns_list
    return await cf_dns_list(zone)


async def tool_cf_dns_upsert(rec_type: str, name: str, content: str, proxied: bool = False, zone: str = "") -> str:
    from zenith.tools.integrations import cf_dns_upsert
    return await cf_dns_upsert(rec_type, name, content, proxied, zone)


async def tool_cf_email_routing(zone: str = "") -> str:
    from zenith.tools.integrations import cf_email_routing_rules
    return await cf_email_routing_rules(zone)


async def tool_cf_dns_status(zone: str = "") -> str:
    from zenith.tools.integrations import cf_dns_status
    return await cf_dns_status(zone)


# ── R2 object storage ────────────────────────────────────────────────────────
async def tool_r2_buckets() -> str:
    from zenith.tools.integrations import r2_buckets
    return await r2_buckets()


async def tool_r2_objects(bucket: str, prefix: str = "") -> str:
    from zenith.tools.integrations import r2_objects
    return await r2_objects(bucket, prefix)


async def tool_r2_put(bucket: str, key: str, content: str) -> str:
    from zenith.tools.integrations import r2_put
    return await r2_put(bucket, key, content)


async def tool_r2_get(bucket: str, key: str) -> str:
    from zenith.tools.integrations import r2_get
    return await r2_get(bucket, key)


async def tool_r2_delete(bucket: str, key: str) -> str:
    from zenith.tools.integrations import r2_delete
    return await r2_delete(bucket, key)


# ── Vercel ──────────────────────────────────────────────────────────────────
async def tool_vercel_projects() -> str:
    from zenith.tools.integrations import vercel_projects
    return await vercel_projects()


async def tool_vercel_deploy_status(project: str) -> str:
    from zenith.tools.integrations import vercel_deploy_status
    return await vercel_deploy_status(project)


async def tool_vercel_deploy(project: str, ref: str = "main") -> str:
    from zenith.tools.integrations import vercel_deploy
    return await vercel_deploy(project, ref)


async def tool_vercel_env_list(project: str) -> str:
    from zenith.tools.integrations import vercel_env_list
    return await vercel_env_list(project)


# ── Antigravity worker tools ──────────────────────────────────────────────────
# These proxy to the zenith-worker REST API on 127.0.0.1:8022 (a separate background
# service running on the host, which owns the Antigravity CLI auth). Non-blocking:
# submit returns immediately with a task id; the worker runs the long task in the
# background and Zenith polls it.

def _get_docker_gateway_ip() -> str | None:
    try:
        with open("/proc/net/route", "r") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    import socket, struct
                    return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    except Exception:
        pass
    return None


def _get_worker_url() -> str:
    val = os.environ.get("WORKER_URL", "").strip().rstrip("/")
    if val:
        return val
    if Path("/.dockerenv").is_file():
        gw = _get_docker_gateway_ip()
        if gw:
            return f"http://{gw}:8022"
        return "http://host.docker.internal:8022"
    return "http://127.0.0.1:8022"


async def _worker_get(path: str, timeout: float = 20) -> dict:
    import httpx
    worker_url = _get_worker_url()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{worker_url}{path}")
            return r.json()
    except Exception as exc:
        candidates = ["http://127.0.0.1:8022", "http://host.docker.internal:8022"]
        gw = _get_docker_gateway_ip()
        if gw:
            candidates.insert(0, f"http://{gw}:8022")
        for cand in candidates:
            if cand == worker_url:
                continue
            try:
                async with httpx.AsyncClient(timeout=min(timeout, 3.0)) as client:
                    r = await client.get(f"{cand}{path}")
                    return r.json()
            except Exception:
                continue
        raise exc


async def _worker_post(path: str, body: dict, timeout: float = 20) -> dict:
    import httpx
    worker_url = _get_worker_url()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{worker_url}{path}", json=body)
            return r.json()
    except Exception as exc:
        candidates = ["http://127.0.0.1:8022", "http://host.docker.internal:8022"]
        gw = _get_docker_gateway_ip()
        if gw:
            candidates.insert(0, f"http://{gw}:8022")
        for cand in candidates:
            if cand == worker_url:
                continue
            try:
                async with httpx.AsyncClient(timeout=min(timeout, 3.0)) as client:
                    r = await client.post(f"{cand}{path}", json=body)
                    return r.json()
            except Exception:
                continue
        raise exc


async def tool_worker_status() -> str:
    """Check health, responsiveness, agy CLI installation, and Google OAuth authentication status of the Antigravity Coding Worker."""
    worker_url = _get_worker_url()
    try:
        data = await _worker_get("/status", timeout=4.0)
        agy_info = data.get("agy") or {}
        tasks_info = data.get("tasks") or {}
        is_auth = agy_info.get("authenticated", False)
        installed = agy_info.get("installed", False)
        path = agy_info.get("path") or "(not found)"
        active_tasks = tasks_info.get("active", 0)
        total_tasks = tasks_info.get("total", 0)

        auth_str = "Authenticated (Autonomous background execution active)" if is_auth else "Sign-in Required (run 'agy' or './scripts/setup-worker.sh login' in terminal to link Google account)"
        return (
            f"Antigravity Coding Worker Status:\n"
            f"  • Daemon Status: ONLINE (HTTP 200 OK)\n"
            f"  • Worker URL:    {worker_url}\n"
            f"  • agy Binary:    {'Installed at ' + path if installed else 'Not Installed'}\n"
            f"  • Auth State:    {auth_str}\n"
            f"  • Task Activity: {active_tasks} active / {total_tasks} total tasks\n"
            f"  • Model/Effort:  {agy_info.get('model', 'gemini-3.1-pro-high')} (effort: {agy_info.get('effort', 'high')})"
        )
    except Exception as exc:
        return (
            f"Antigravity Coding Worker Status:\n"
            f"  • Daemon Status: OFFLINE or Unreachable ({exc})\n"
            f"  • Worker URL:    {worker_url}\n"
            f"  • Host Control:  Run './scripts/setup-worker.sh start' on host to ignite daemon.\n"
            f"  • Fallback:      Zenith Native Agent (agent tool) is active using configured GEMINI_API_KEY."
        )


async def tool_worker_control(action: str = "status") -> str:
    """Manage the Antigravity Coding Worker daemon on the host (actions: 'status', 'restart', 'start', 'stop', 'login')."""
    act = (action or "status").lower().strip()
    if act == "status":
        return await tool_worker_status()

    if act == "login":
        return (
            "To authenticate Google Antigravity CLI, open a host terminal and run:\n"
            "  ./scripts/setup-worker.sh login            (Linux / macOS)\n"
            "  .\\scripts\\setup-worker.ps1 -Action login    (Windows PowerShell)\n"
            "This will open a browser window for a one-time Google Sign-In."
        )
    if act in ("start", "restart", "stop"):
        return (
            f"Worker '{act}' signal noted. To manage the background daemon on the host:\n"
            f"  Linux/macOS: ./scripts/setup-worker.sh {act}\n"
            f"  Windows:     .\\scripts\\setup-worker.ps1 -Action {act}"
        )
    return f"Unknown worker action '{action}'. Available actions: status, restart, start, stop, login."


async def tool_agent_submit(
    task: str,
    workspace: str = "",
    requirements: str = "",
    constraints: str = "",
    acceptance: str = "",
    context: str = "",
    autonomy: str = "high",
    destructive: bool = False,
) -> str:
    """Delegate a substantial coding/engineering task to the Antigravity worker or native agent."""
    # Inspect worker availability and authentication state
    worker_online = False
    worker_auth = False
    try:
        health = await _worker_get("/health", timeout=2.5)
        worker_online = (health.get("status") == "ok")
        worker_auth = bool(health.get("authenticated", False))
    except Exception:
        pass

    # Zero-Blocker Fallback: If worker is not authenticated or not online, activate Zenith Native Coding Agent
    if not worker_online or not worker_auth:
        reason = "Worker daemon offline" if not worker_online else "Worker awaiting one-time Google Sign-In ('agy')"
        from zenith.tools.agent import agent as native_agent
        goal_summary = f"{task.strip()}."
        if requirements:
            goal_summary += f" Requirements: {requirements}."
        if constraints:
            goal_summary += f" Constraints: {constraints}."
        ctx = context or ""
        if workspace:
            ctx += f" Target workspace: {workspace}"

        native_res = await native_agent("start", name="coding", goal=goal_summary, context=ctx)
        return (
            f"[{reason}]\n"
            f"⚡ Seamlessly activated Zenith Native Coding Agent (powered by GEMINI_API_KEY).\n"
            f"  {native_res}\n"
            f"💡 Note: To enable the multi-file autonomous Antigravity CLI worker, run 'agy' once in a host terminal to sign in."
        )

    # Distill and dispatch to full autonomous Antigravity worker
    spec = {
        "task": task.strip(),
        "workspace": workspace.strip() or "",
        "requirements": [x.strip() for x in requirements.split("|") if x.strip()],
        "constraints": [x.strip() for x in constraints.split("|") if x.strip()],
        "acceptanceCriteria": [x.strip() for x in acceptance.split("|") if x.strip()],
        "context": context.strip(),
        "autonomy": autonomy,
        "destructive_allowed": bool(destructive),
        "ask_for_clarification": True,
        "parent": "",
    }
    try:
        data = await _worker_post("/tasks", {"spec": spec})
        tid = data.get("task_id")
        if not tid:
            return f"[antigravity] worker error: {data}"
        return (f"Delegated to Antigravity worker.\n"
                f"  task id: {tid}\n"
                f"  status:  {data.get('status')}\n"
                f"  workspace: {data.get('workspace')}\n"
                f"The worker is operating 100% autonomously in the background. Poll with agent_status or agent_output.")
    except Exception as exc:
        return f"[antigravity] submit failed: {exc}"


async def tool_agent_status(task_id: str) -> str:
    try:
        t = await _worker_get(f"/tasks/{task_id}")
        return (f"Status of {task_id}: {t['status']}\n"
                f"  activity: {t.get('current_activity') or '(idle)'}\n"
                f"  workspace: {t.get('workspace')}\n"
                f"  output: {(t.get('output') or '')[:400]}\n"
                f"  errors: {t.get('errors') or 'none'}")
    except Exception as exc:
        return f"[antigravity] status failed: {exc}"


async def tool_agent_output(task_id: str) -> str:
    try:
        data = await _worker_get(f"/tasks/{task_id}/output")
        return data.get("output") or "(no output yet)"
    except Exception as exc:
        return f"[antigravity] output failed: {exc}"


async def tool_agent_artifacts(task_id: str) -> str:
    try:
        data = await _worker_get(f"/tasks/{task_id}/artifacts")
        arts = data.get("artifacts") or []
        return "Artifacts:\n- " + "\n- ".join(arts) if arts else "(none yet)"
    except Exception as exc:
        return f"[antigravity] artifacts failed: {exc}"


async def tool_agent_followup(task_id: str, message: str) -> str:
    try:
        data = await _worker_post(f"/tasks/{task_id}/followup", {"message": message})
        return "Follow-up sent to the worker." if data.get("sent") else str(data)
    except Exception as exc:
        return f"[antigravity] followup failed: {exc}"


async def tool_agent_cancel(task_id: str) -> str:
    try:
        data = await _worker_post(f"/tasks/{task_id}/cancel", {})
        return "Cancelled." if data.get("cancelled") else str(data)
    except Exception as exc:
        return f"[antigravity] cancel failed: {exc}"


# ── Mode Management & UI Customizer Handlers ─────────────────────────────────
async def tool_switch_mode(mode: str, reason: str = "") -> str:
    from zenith.tools.ui_customizer import switch_mode
    return await switch_mode(mode, reason)


async def tool_get_mode() -> str:
    from zenith.tools.ui_customizer import get_current_mode
    import json
    return json.dumps(get_current_mode())


async def tool_update_user_profile(name: str = "", email: str = "", timezone: str = "", bio: str = "") -> str:
    from zenith.tools.ui_customizer import update_user_profile
    return await update_user_profile(name, email, timezone, bio)


async def tool_setup_secret(key: str, value: str) -> str:
    from zenith.tools.ui_customizer import setup_secret
    return await setup_secret(key, value)


async def tool_get_setup_status(category: str = "") -> str:
    from zenith.tools.ui_customizer import get_setup_status
    return await get_setup_status(category)


async def tool_ui_inspect(target: str = "theme") -> str:
    from zenith.tools.ui_customizer import ui_inspect
    return await ui_inspect(target)


async def tool_ui_customize_theme(accent_color: str = "", theme_mode: str = "", font: str = "", custom_css: str = "") -> str:
    from zenith.tools.ui_customizer import ui_customize_theme
    return await ui_customize_theme(accent_color, theme_mode, font, custom_css)


async def tool_ui_reset_theme() -> str:
    from zenith.tools.ui_customizer import ui_reset_theme
    return await ui_reset_theme()


# ───────────────────────────────────────────────────────────────────────── Catalog


# ── reads / info (never confirm) ──────────────────────────────────────────────
register("get_weather", "Get current weather for a city or 'auto' (geolocation defaults to Dehradun).", {
    "type": "object",
    "properties": {"location": {"type": "string"}},
}, tool_weather)

register("web_search", "Search the web for current information. Returns top snippets.", {
    "type": "object",
    "properties": {"query": {"type": "string", "description": "Search query."}},
    "required": ["query"],
}, tool_web_search)

register("read_url", "Read a web page / URL and return its readable text content (tries llmsolutions, falls back to the in-process browser).", {
    "type": "object",
    "properties": {"url": {"type": "string", "description": "Full URL (include https://)."}},
    "required": ["url"],
}, tool_read_url)

# ── Maps & Location ─────────────────────────────────────────────────────────
register("maps_search", "Search Google Maps for places, cafes, restaurants, landmarks, or addresses.", {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query or place type (e.g. 'cafes', 'Space Needle')."},
        "location": {"type": "string", "description": "Optional city/area bias (e.g. 'Dehradun', 'Seattle')."},
    },
    "required": ["query"],
}, tool_maps_search)

register("maps_directions", "Get travel directions, route, distance, and duration between origin and destination using Google Maps.", {
    "type": "object",
    "properties": {
        "origin": {"type": "string", "description": "Starting address or place name."},
        "destination": {"type": "string", "description": "Destination address or place name."},
        "mode": {"type": "string", "enum": ["driving", "transit", "bicycling", "walking"], "default": "driving"},
    },
    "required": ["origin", "destination"],
}, tool_maps_directions)

register("maps_commute", "Calculate commute times and distance from an origin to one or more destinations.", {
    "type": "object",
    "properties": {
        "origin": {"type": "string", "description": "Origin location/address."},
        "destinations": {"description": "Single destination string or comma-separated list of destinations."},
        "mode": {"type": "string", "enum": ["driving", "transit", "bicycling", "walking"], "default": "driving"},
    },
    "required": ["origin", "destinations"],
}, tool_maps_commute)

register("maps_geocode", "Geocode an address or location to coordinates (lat/lng) and formatted address.", {
    "type": "object",
    "properties": {
        "location": {"type": "string", "description": "Address or location name."},
    },
    "required": ["location"],
}, tool_maps_geocode)

register("maps_embed", "Generate a Google Map iframe embed or interactive widget code for places, directions, or routes.", {
    "type": "object",
    "properties": {
        "query_or_place": {"type": "string", "description": "Place name or location query for embed."},
        "embed_type": {"type": "string", "enum": ["place", "directions", "search"], "default": "place"},
        "origin": {"type": "string", "description": "Origin address (for directions embed)."},
        "destination": {"type": "string", "description": "Destination address (for directions embed)."},
        "mode": {"type": "string", "enum": ["driving", "transit", "bicycling", "walking"], "default": "driving"},
    },
}, tool_maps_embed)

register("gods_eye_view", "Open God's Eye View (GEV) 3D satellite simulator, live global intelligence console, and interactive HUD globe embed for any location on Earth or in orbit.", {
    "type": "object",
    "properties": {
        "location": {"type": "string", "description": "City, country, landmark, address, coordinates, or preset name (e.g. 'Pentagon', 'White House', 'Area 51', 'Pyramids of Giza', 'Eiffel Tower', 'Tokyo Tower', 'Burj Khalifa', 'Everest', 'Orbit')."},
        "lat": {"type": "number", "description": "Optional explicit target latitude (-90 to 90)."},
        "lon": {"type": "number", "description": "Optional explicit target longitude (-180 to 180)."},
        "alt": {"type": "number", "description": "Camera altitude in meters (e.g. 500 for street view, 1200 for landmark, 9000 for mountains, 2000000 for space orbit). Default is 800."},
        "style": {
            "type": "string",
            "enum": ["normal", "nvg", "flir", "crt", "anime", "noir", "snow"],
            "default": "normal",
            "description": "Satellite sensor visualization mode: 'normal' (photoreal optical), 'nvg' (night vision surveillance green), 'flir' (thermal infrared heat signature), 'crt' (tactical terminal scanlines), 'anime' (cel-shaded), 'noir' (monochrome high contrast), 'snow' (blizzard/winter overlay)."
        },
        "hud": {
            "type": "string",
            "enum": ["tactical", "standard", "minimal", "off"],
            "default": "tactical",
            "description": "HUD overlay mode: 'tactical' (military target telemetry and tracking brackets), 'standard', 'minimal', or 'off'."
        },
        "heading": {"type": "number", "description": "Camera compass heading in degrees (0 = North, 90 = East, 180 = South, 270 = West). Default is 0."},
        "pitch": {"type": "number", "description": "Camera pitch angle in degrees (-90 = straight down, -35 = angled perspective). Default is -35."},
        "map_layer": {
            "type": "string",
            "enum": ["photoreal", "bing", "osm", "esri"],
            "default": "photoreal",
            "description": "Base map tile layer: 'photoreal' (Google 3D Tiles / Photorealistic 3D), 'esri' (Esri World Imagery satellite), 'osm' (OpenStreetMap), or 'bing'."
        },
    },
}, tool_gods_eye_view)

register("gods_eye_view_status", "Check God's Eye View 3D Earth Observation console status, active port, live data feeds, and configured tokens (Cesium Ion, Google Maps, OpenSky).", {
    "type": "object",
    "properties": {},
}, tool_gods_eye_view_status)


register("browser", "Open a URL in headless Chromium/Playwright, wait for page load, and extract clean readable text content and page title. Governed by Privacy Guard.", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Full URL (include https://)."},
        "max_chars": {"type": "integer", "default": 5000, "description": "Maximum characters of readable text to extract."},
    },
    "required": ["url"],
}, tool_browser)

register("browser_screenshot", "Capture a rendered screenshot of any webpage using headless Chromium/Playwright and embed the image preview directly in chat.", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Full webpage URL to capture."},
        "full_page": {"type": "boolean", "default": True, "description": "Whether to capture the entire scrollable page height or just viewport."},
    },
    "required": ["url"],
}, tool_browser_screenshot)

register("browser_click", "Open a page and click the first element matching a CSS selector.", {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "selector": {"type": "string", "description": "CSS selector, e.g. '#submit' or 'button:text(\"Save\")'."},
    },
    "required": ["url", "selector"],
}, tool_browser_click)

register("browser_type", "Type text into a field (CSS selector) and optionally press Enter (submit).", {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "selector": {"type": "string"},
        "text": {"type": "string"},
        "submit": {"type": "boolean", "description": "Press Enter after typing."},
    },
    "required": ["url", "selector", "text"],
}, tool_browser_type)

register("notes", "Manage personal notes. action: 'create' | 'list' | 'get' | 'delete'. Create with title+text.",
         {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["create", "list", "get", "delete"]},
        "title": {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["action"],
}, tool_notes)

register("todo", "Manage to-dos. action: 'add' | 'list' | 'done' | 'delete'. 'add' takes a title.", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["add", "list", "done", "delete"]},
        "title": {"type": "string"},
        "todo_id": {"type": "integer"},
    },
    "required": ["action"],
}, tool_todo)

# Reminders are now Google Calendar events. "remind me to X at HH:MM" → calendar
# with a title like "⏰ Reminder: X", a real date/time, and (only if user wants
# it) an email notification. This is the sole scheduling surface.
register("calendar", "Manage user's calendar. 'add' creates a real event with a title and when (natural language, e.g. 'tomorrow 4pm', 'today 21:30' — used for reminders too); 'list' shows upcoming; 'delete' removes event(s) matching the title in 'text' (or a specific event_id).", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["add", "list", "delete"]},
        "text": {"type": "string", "description": "Event/reminder title. For 'delete', a title words to match — e.g. 'remove the 4pm jog reminder' passes text='jog'."},
        "when": {"type": "string", "description": "When, as natural language ('tomorrow 4pm', 'today 21:30')."},
        "event_id": {"type": "string", "description": "Google Calendar event id — only needed to delete a SPECIFIC event. Prefer passing a matching title in text."},
    },
    "required": ["action"],
}, tool_calendar)

register("email_reminder", "Email the user a reminder — used when they opt into an emailed reminder after setting one. Sends a confirmation now; no event is created. Confirmation required.", {
    "type": "object",
    "properties": {
        "task": {"type": "string", "description": "What the reminder is about."},
        "when": {"type": "string", "description": "When it's scheduled for (freeform)."},
    },
    "required": ["task", "when"],
}, tool_email_reminder)

register("memory", "Store or recall long-term facts. action: 'save' | 'recall' | 'all'.", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["save", "recall", "all"]},
        "key": {"type": "string", "description": "For save: category::fact key, e.g. projects::CodeDraw."},
        "value": {"type": "string", "description": "For save: the fact value."},
        "query": {"type": "string", "description": "For recall: term to search."},
    },
    "required": ["action"],
}, tool_memory)

register("graph", "Query the knowledge graph (entities & relationships) for a term.", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}, tool_graph)

register("agent", "Manage specialist sub-agents for deep work. action 'start' launches an agent (coding|research); 'status' polls; 'result' fetches.", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["start", "status", "result", "list"]},
        "name": {"type": "string", "description": "Agent type ('coding'|'research'|'general') or agent ID for result."},
        "agent_id": {"type": "string", "description": "Hex ID of the agent for action 'result'."},
        "goal": {"type": "string"},
        "context": {"type": "string"},
    },
    "required": ["action"],
}, tool_agent)

register("delegate_task", "Delegate a mission or specialized task to a departmental specialist agent (communication, coding, hr, research, operations, productivity, creative, utility) or custom hired agent. The agent executes autonomously using its scoped departmental toolset and returns a concise, structured report.", {
    "type": "object",
    "properties": {
        "department": {"type": "string", "description": "Target department or custom agent ID ('communication', 'coding', 'hr', 'research', 'operations', 'productivity', 'creative', 'utility')."},
        "task": {"type": "string", "description": "Clear, actionable task description or instructions for the specialist agent."},
        "context": {"type": "string", "description": "Relevant background context, constraints, user preferences, or details needed to complete the task."},
        "synchronous": {"type": "boolean", "description": "Whether to wait for the agent to finish and return its findings immediately (default true). Set to false for long-running background tasks."},
    },
    "required": ["department", "task"],
}, tool_delegate_task)

register("list_agents", "List all active agents in the organization, including built-in departments and custom hired agents, their roles, descriptions, and tool counts.", {
    "type": "object",
    "properties": {},
}, tool_list_agents)

register("get_agent_status", "Check the status and fetch results of a delegated agent run.", {
    "type": "object",
    "properties": {
        "run_id": {"type": "string", "description": "Hex ID of the agent run (optional, leave blank to list all recent runs)."},
    },
}, tool_get_agent_status)

register("hire_agent", "Hire, configure, and register a new specialized autonomous agent with a custom system prompt and allocated toolset. Persisted in SQLite across restarts.", {
    "type": "object",
    "properties": {
        "agent_id": {"type": "string", "description": "Unique identifier slug for the agent (e.g. 'security_auditor', 'astro_tracker')."},
        "name": {"type": "string", "description": "Human-friendly display name for the agent (e.g. 'Security Auditor')."},
        "department": {"type": "string", "description": "Department name or division (e.g. 'Security & Compliance')."},
        "role_description": {"type": "string", "description": "Brief description of the agent's primary role and duties."},
        "system_prompt": {"type": "string", "description": "Domain-tailored system prompt defining the agent's behavior, instructions, and constraints."},
        "tool_names": {"type": "array", "items": {"type": "string"}, "description": "List of system tool names to allocate to this agent."},
    },
    "required": ["agent_id", "system_prompt"],
}, tool_hire_agent)

register("update_agent", "Update the system prompt, tool allocation, or description of an existing custom agent.", {
    "type": "object",
    "properties": {
        "agent_id": {"type": "string", "description": "Unique identifier slug of the agent to update."},
        "system_prompt": {"type": "string", "description": "Updated system prompt instructions."},
        "tool_names": {"type": "array", "items": {"type": "string"}, "description": "Updated list of tool names allocated to this agent."},
        "role_description": {"type": "string", "description": "Updated brief role description."},
    },
    "required": ["agent_id"],
}, tool_update_agent)

register("fire_agent", "Retire and remove a custom agent from the active organization roster.", {
    "type": "object",
    "properties": {
        "agent_id": {"type": "string", "description": "Unique identifier slug of the custom agent to retire."},
    },
    "required": ["agent_id"],
}, tool_fire_agent)

register("inspect_agent", "Inspect the full profile, system prompt, and allocated tools of any agent in the organization.", {
    "type": "object",
    "properties": {
        "agent_id": {"type": "string", "description": "Unique identifier slug of the agent to inspect."},
    },
    "required": ["agent_id"],
}, tool_inspect_agent)

register("list_available_tools", "List all system tools available in Zenith with descriptions to help People Operations / HR allocate tools to new agents.", {
    "type": "object",
    "properties": {
        "filter": {"type": "string", "description": "Optional keyword to filter tools by name or description."},
    },
}, tool_list_available_tools)


register("agent_submit", "Delegate a substantial coding/engineering task to the Antigravity worker (a full coding agent on the Pi). Use for 'build', 'create', 'implement', 'refactor', 'port', 'fix a bug across files', 'docker set up', 'web app/service/project', etc. The worker runs in the background and you can poll agent_status / agent_output / agent_artifacts and send agent_followup. Distill the user's intent into a tight brief (task, workspace, requirements|constraints|acceptance separated by '|').", {
    "type": "object",
    "properties": {
        "task": {"type": "string", "description": "Concise coding/engineering objective."},
        "workspace": {"type": "string", "description": "Absolute path on the Pi (default: ~/peacos-workspaces/<slug>)."},
        "requirements": {"type": "string", "description": "Pipe-separated list of requirements."},
        "constraints": {"type": "string", "description": "Pipe-separated constraints (e.g. 'don't deploy')."},
        "acceptance": {"type": "string", "description": "Pipe-separated acceptance criteria."},
        "context": {"type": "string", "description": "Important context Zenith discovered."},
        "autonomy": {"type": "string", "enum": ["high", "medium", "low"]},
        "destructive": {"type": "boolean", "description": "Allow destructive changes (default false)."},
    },
    "required": ["task"],
}, tool_agent_submit)

register("agent_status", "Check the status of an Antigravity worker task by id.", {
    "type": "object",
    "properties": {"task_id": {"type": "string"}},
    "required": ["task_id"],
}, tool_agent_status)

register("agent_output", "Fetch the current output text of an Antigravity worker task.", {
    "type": "object",
    "properties": {"task_id": {"type": "string"}},
    "required": ["task_id"],
}, tool_agent_output)

register("agent_artifacts", "List files/artifacts an Antigravity worker task has produced.", {
    "type": "object",
    "properties": {"task_id": {"type": "string"}},
    "required": ["task_id"],
}, tool_agent_artifacts)

register("agent_followup", "Send a follow-up message into an ongoing Antigravity worker task's conversation.", {
    "type": "object",
    "properties": {
        "task_id": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["task_id", "message"],
}, tool_agent_followup)

register("agent_cancel", "Cancel a queued/running Antigravity worker task.", {
    "type": "object",
    "properties": {"task_id": {"type": "string"}},
    "required": ["task_id"],
}, tool_agent_cancel)

register("worker_status", "Check health, responsiveness, agy CLI installation, and Google OAuth authentication status of the Antigravity Coding Worker.", {
    "type": "object",
    "properties": {},
}, tool_worker_status)

register("worker_control", "Manage the Antigravity Coding Worker daemon on the host (actions: 'status', 'restart', 'start', 'stop', 'login').", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["status", "restart", "start", "stop", "login"], "description": "Worker management action."}
    },
    "required": ["action"],
}, tool_worker_control)

# ── read-only admin ────────────────────────────────────────────────────────────
register("docker_list", "List all Docker containers and their status.", {
    "type": "object",
    "properties": {},
}, tool_docker_list)

register("docker_table", "Compact table of containers for UI rendering.", {
    "type": "object",
    "properties": {},
}, tool_docker_table)

register("docker_status", "Get status (running/stopped, started time, image) for one container.", {
    "type": "object",
    "properties": {"container": {"type": "string", "description": "Container name, e.g. jellyfin."}},
    "required": ["container"],
}, tool_docker_status)

register("docker_logs", "Tail recent logs for one container (read-only).", {
    "type": "object",
    "properties": {"container": {"type": "string"}, "tail": {"type": "integer", "default": 80}},
    "required": ["container"],
}, tool_docker_logs)

register("docker_start", "Start a controlled container (from the guarded set).", {
    "type": "object",
    "properties": {"container": {"type": "string"}},
    "required": ["container"],
}, tool_docker_start)

register("docker_stop", "Stop a controlled container (guarded set).", {
    "type": "object",
    "properties": {"container": {"type": "string"}},
    "required": ["container"],
}, tool_docker_stop)

register("docker_restart", "Restart a controlled container (guarded set).", {
    "type": "object",
    "properties": {"container": {"type": "string"}},
    "required": ["container"],
}, tool_docker_restart)

register("system_status", "Host vitals: uptime, load, memory, disk.", {
    "type": "object",
    "properties": {},
}, tool_system_status)

register("disk_usage", "Disk usage table for / and /home.", {
    "type": "object",
    "properties": {},
}, tool_disk_usage)

register("memory_usage", "Memory summary (free -h).", {
    "type": "object",
    "properties": {},
}, tool_memory_usage)

register("top_processes", "Top CPU processes on the host.", {
    "type": "object",
    "properties": {},
}, tool_top_processes)

register("gh_whoami", "Check GitHub CLI account + auth.", {
    "type": "object",
    "properties": {},
}, tool_gh_whoami)

register("gh_list_repos", "List repos for an owner.", {
    "type": "object",
    "properties": {"owner": {"type": "string", "default": ""}},
}, tool_gh_repos)

register("gh_issues", "List open issues for a repo.", {
    "type": "object",
    "properties": {
        "owner": {"type": "string", "default": ""},
        "repo": {"type": "string", "description": "e.g. coding or owner/repo."},
    },
    "required": ["repo"],
}, tool_gh_issues)

register("gh_pulls", "List open pull requests for a repo.", {
    "type": "object",
    "properties": {
        "owner": {"type": "string", "default": ""},
        "repo": {"type": "string"},
    },
    "required": ["repo"],
}, tool_gh_pulls)

register("gh_repo_status", "Repo metadata + recent commits.", {
    "type": "object",
    "properties": {
        "owner": {"type": "string", "default": ""},
        "repo": {"type": "string"},
    },
    "required": ["repo"],
}, tool_gh_repo_status)

register("gh_create_issue", "Create a GitHub issue on a repo.", {
    "type": "object",
    "properties": {
        "owner": {"type": "string", "default": ""},
        "repo": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["repo", "title"],
}, tool_gh_create_issue)

register("gh_create_repo", "Create a GitHub repo under the user's account. Mutates GitHub — confirm first.", {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "private": {"type": "boolean", "default": False},
        "description": {"type": "string", "default": ""},
    },
    "required": ["name"],
}, tool_gh_create_repo)

register("mc_status", "Status of the Twilight-MC stack (server + tunnels).", {
    "type": "object",
    "properties": {},
}, tool_mc_status)

register("mc_players", "How many players are on the MC server right now.", {
    "type": "object",
    "properties": {},
}, tool_mc_players)

register("mc_start", "Start the Twilight-MC composition (server + tunnels).", {
    "type": "object",
    "properties": {},
}, tool_mc_start)

register("mc_stop", "Stop the Twilight-MC composition.", {
    "type": "object",
    "properties": {},
}, tool_mc_stop)

register("mc_restart", "Restart the Twilight-MC composition.", {
    "type": "object",
    "properties": {},
}, tool_mc_restart)

register("email_search", "Search the connected mailbox. Returns uid · From · Subject.", {
    "type": "object",
    "properties": {"query": {"type": "string", "default": ""}},
}, tool_email_search)

register("email_read", "Fetch one email by uid.", {
    "type": "object",
    "properties": {"uid": {"type": "string"}},
    "required": ["uid"],
}, tool_email_read)

register("email_draft", "Send an email immediately to a recipient (to, subject, body, optional attachment_path/attachment_paths). Sends directly without preview or confirmation. Supports one or more file attachments.", {
    "type": "object",
    "properties": {
        "to": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "attachment_path": {"type": "string", "description": "Absolute path to a file to attach (e.g. a generated PDF, spreadsheet, code file). Optional."},
        "attachment_paths": {"type": "array", "items": {"type": "string"}, "description": "Absolute paths of multiple files to attach. Optional."},
    },
    "required": ["to", "subject", "body"],
}, tool_email_draft)

register("email_send", "Send an email (to, subject, body) with one or more file attachments. Sends via Resend/SMTP. Supports PDFs, Word docs, spreadsheets, code, images — any file up to 25MB each. Pass the EXACT path(s) returned by generate_* to attachment_path (singular) or attachment_paths (multiple, for sending several files in one email).", {
    "type": "object",
    "properties": {
        "to": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "attachment_path": {"type": "string", "description": "Absolute path to a single file to attach. Optional. Copy it verbatim from the generate_* tool result."},
        "attachment_paths": {"type": "array", "items": {"type": "string"}, "description": "Absolute paths of MULTIPLE files to attach in the same email. Optional. Use when the user asks for several files together."},
    },
    "required": ["to", "subject", "body"],
}, tool_email_send)

register("mailbox_create", "Create a throwaway disposable inbox (no account needed) — for signups, verification links, one-time addresses. Returns address + password.", {
    "type": "object",
    "properties": {},
}, tool_mailbox_create)

register("mailbox_messages", "List messages in a disposable inbox created by mailbox_create (address + password).", {
    "type": "object",
    "properties": {
        "address": {"type": "string"},
        "password": {"type": "string"},
        "limit": {"type": "integer", "default": 8},
    },
    "required": ["address", "password"],
}, tool_mailbox_messages)

register("mailbox_read", "Read the newest message body in a disposable inbox (address + password).", {
    "type": "object",
    "properties": {
        "address": {"type": "string"},
        "password": {"type": "string"},
    },
    "required": ["address", "password"],
}, tool_mailbox_read)

register("mailbox_delete", "Delete a disposable inbox (address + password). It self-destructs anyway.", {
    "type": "object",
    "properties": {
        "address": {"type": "string"},
        "password": {"type": "string"},
    },
    "required": ["address", "password"],
}, tool_mailbox_delete)

# ── Cloudflare (DNS + Email Routing) ────────────────────────────────────────────
register("cf_dns_list", "List DNS records for a Cloudflare zone.", {
    "type": "object",
    "properties": {"zone": {"type": "string", "description": "Zone name, e.g. example.com."}},
}, tool_cf_dns_list)

register("cf_dns_upsert", "Add or update a DNS record (A/AAAA/MX/TXT/CNAME). Mutates real DNS — confirm first.", {
    "type": "object",
    "properties": {
        "rec_type": {"type": "string", "enum": ["A", "AAAA", "CNAME", "MX", "TXT", "SRV"]},
        "name": {"type": "string", "description": "Host, e.g. '@' for root or 'mail'."},
        "content": {"type": "string", "description": "Value, e.g. IP address or target."},
        "proxied": {"type": "boolean", "default": False},
        "zone": {"type": "string", "default": ""},
    },
    "required": ["rec_type", "name", "content"],
}, tool_cf_dns_upsert)

register("cf_email_routing", "List Cloudflare Email Routing rules (catch-all → destination).", {
    "type": "object",
    "properties": {"zone": {"type": "string", "default": ""}},
}, tool_cf_email_routing)

register("cf_email_status", "Check SPF/DKIM/DMARC + MX presence for email deliverability.", {
    "type": "object",
    "properties": {"zone": {"type": "string", "default": ""}},
}, tool_cf_dns_status)

# ── Vercel ──────────────────────────────────────────────────────────────────────
register("vercel_projects", "List Vercel projects Zenith can deploy.", {
    "type": "object",
    "properties": {},
}, tool_vercel_projects)

register("vercel_deploy_status", "Latest deployment status for a Vercel project.", {
    "type": "object",
    "properties": {"project": {"type": "string"}},
    "required": ["project"],
}, tool_vercel_deploy_status)

register("vercel_deploy", "Trigger a production deploy of a Vercel project. Mutates — confirm first.", {
    "type": "object",
    "properties": {
        "project": {"type": "string"},
        "ref": {"type": "string", "default": "main"},
    },
    "required": ["project"],
}, tool_vercel_deploy)

register("vercel_env_list", "List env var names (values redacted) on a Vercel project.", {
    "type": "object",
    "properties": {"project": {"type": "string"}},
    "required": ["project"],
}, tool_vercel_env_list)

# ── R2 object storage ───────────────────────────────────────────────────────────
register("r2_buckets", "List R2 buckets on the Cloudflare account.", {
    "type": "object",
    "properties": {},
}, tool_r2_buckets)

register("r2_objects", "List objects in an R2 bucket (optional prefix filter).", {
    "type": "object",
    "properties": {
        "bucket": {"type": "string"},
        "prefix": {"type": "string", "default": ""},
    },
    "required": ["bucket"],
}, tool_r2_objects)

register("r2_put", "Store a text object in an R2 bucket.", {
    "type": "object",
    "properties": {
        "bucket": {"type": "string"},
        "key": {"type": "string", "description": "Object key/path, e.g. notes/hello.txt"},
        "content": {"type": "string"},
    },
    "required": ["bucket", "key", "content"],
}, tool_r2_put)

register("r2_get", "Fetch a text object from an R2 bucket by key.", {
    "type": "object",
    "properties": {
        "bucket": {"type": "string"},
        "key": {"type": "string"},
    },
    "required": ["bucket", "key"],
}, tool_r2_get)

register("r2_delete", "Delete an object from an R2 bucket. Mutates storage — confirm first.", {
    "type": "object",
    "properties": {
        "bucket": {"type": "string"},
        "key": {"type": "string"},
    },
    "required": ["bucket", "key"],
}, tool_r2_delete)

# ── computer / filesystem ──────────────────────────────────────────────────────
register("shell", "Run a shell command on the host machine across Linux, macOS, or Windows (only if ALLOW_SHELL=yes). Supports cwd tracking, multi-OS execution (bash/zsh/powershell/cmd), timeout up to 300s, and detailed exit/stdout/stderr feedback.", {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Command line string to execute."},
        "cwd": {"type": "string", "default": "", "description": "Optional working directory to run the command in. Defaults to active session directory."},
        "timeout": {"type": "integer", "default": 60, "description": "Seconds to allow before timing out (max 300)."},
        "shell_type": {"type": "string", "default": "auto", "description": "Shell type: 'auto', 'bash', 'zsh', 'powershell', 'cmd', or 'sh'."},
    },
    "required": ["command"],
}, tool_shell)

register("get_command_history", "View recent commands executed in this session, their exit codes, durations, and output previews.", {
    "type": "object",
    "properties": {
        "limit": {"type": "integer", "default": 10, "description": "Maximum number of recent commands to return (default 10)."},
    },
}, tool_get_command_history)

register("get_system_info", "Grab detailed info about the host machine, server, or container Zenith is running on (OS, Linux distro/macOS/Windows, Docker/WSL/Cloud VM, CPU cores, RAM, Disk, uptime, network IPs).", {
    "type": "object",
    "properties": {
        "detail_level": {"type": "string", "default": "summary", "description": "'summary' for concise overview, 'full' for detailed markdown report."},
    },
}, tool_get_system_info)

register("get_available_tools", "List and explore all tools available in Zenith, their parameters, descriptions, and categories. Useful for self-introspection and discovering capabilities.", {
    "type": "object",
    "properties": {
        "category": {"type": "string", "default": "", "description": "Optional category filter (e.g. 'system_shell', 'developer_git', 'web_browser', 'multimedia_design', 'smart_home_homelab', 'communication', 'ai_memory', 'configuration')."},
        "query": {"type": "string", "default": "", "description": "Optional search query to filter tool names and descriptions."},
    },
}, tool_get_available_tools)

register("get_configurable_tools", "List all tools, integrations, and services that can be configured in Zenith (e.g. Gemini, Resend, Groq, GitHub, Maps, Home Assistant, Cloudflare), what credentials they require, and their live configuration status.", {
    "type": "object",
    "properties": {},
}, tool_get_configurable_tools)

register("time_now", "Get the current wall-clock date/time (Asia/Kolkata by default). Use instead of guessing the time.", {
    "type": "object",
    "properties": {},
}, tool_time_now)

register("git_commit", "Stage all changes and commit them in a local git repo. Safe/local; returns 'nothing to commit' on a clean tree.", {
    "type": "object",
    "properties": {
        "repo_path": {"type": "string", "default": "", "description": "Optional repo directory (defaults to workspace)."},
        "message": {"type": "string", "description": "Commit message."},
    },
    "required": ["message"],
}, tool_git_commit)

register("read_file", "Read a text file. Returns content (truncated to 20k chars).", {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}, tool_read_file)

register("write_file", "Write (or overwrite) a text file at an absolute path.", {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["path", "content"],
}, tool_write_file)

register("list_dir", "List directory contents with sizes.", {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}, tool_list_dir)

# ── File Generation ───────────────────────────────────────────────────────────
register("generate_pdf", "Generate a PDF document from text content. Returns the file path. Use for reports, study notes, letters. Write SUBSTANTIAL 3-5 page documents by default (unless the user explicitly asked for short/brief). NEVER use when a presentation, slides, PPT, or PowerPoint deck is requested — use generate_pptx instead.", {
    "type": "object",
    "properties": {
        "filename": {"type": "string", "description": "Output filename (e.g. 'notes', 'report')."},
        "content": {"type": "string", "description": "Markdown content for the PDF. IMPORTANT: unless the user explicitly asked for a short note, write a SUBSTANTIAL 3-5 page document — multiple #/## sections, several solid paragraphs per section, real detail and depth (context, breakdowns, examples, tables where useful). Aim for roughly 1,200-2,000+ words. A 1-2 page skim is a failure unless asked for."},
        "title": {"type": "string", "description": "Optional title displayed at the top of the PDF."},
    },
    "required": ["filename", "content"],
}, tool_generate_pdf)

register("generate_docx", "Generate a Word (.docx) document. Returns the file path. Use for formatted documents, essays, project docs. Write SUBSTANTIAL 3-5 page documents by default (unless the user explicitly asked for short/brief). NEVER use when a presentation, slides, PPT, or PowerPoint deck is requested — use generate_pptx instead.", {
    "type": "object",
    "properties": {
        "filename": {"type": "string", "description": "Output filename (e.g. 'project_brief')."},
        "content": {"type": "string", "description": "Markdown content. Lines starting with # become headings. IMPORTANT: unless the user explicitly asked for a short note, write a SUBSTANTIAL 3-5 page document — multiple #/## sections, several solid paragraphs per section, real depth (context, breakdowns, examples, tables where useful). Aim for roughly 1,200-2,000+ words. A 1-2 page skim is a failure unless asked for."},
        "title": {"type": "string", "description": "Optional document title."},
    },
    "required": ["filename", "content"],
}, tool_generate_docx)

register("generate_xlsx", "Generate an Excel (.xlsx) spreadsheet from tabular data. Returns the file path. Use for tables, expense tracking, data.", {
    "type": "object",
    "properties": {
        "filename": {"type": "string", "description": "Output filename (e.g. 'expenses')."},
        "data": {"type": "string", "description": "CSV-like data: rows separated by newlines, columns by comma or pipe (|). First row becomes header."},
        "sheet_name": {"type": "string", "default": "Sheet1"},
    },
    "required": ["filename", "data"],
}, tool_generate_xlsx)

register("generate_code", "Generate a code or text file (any extension: .py, .js, .html, .css, .sh, .md, etc.). Returns the file path.", {
    "type": "object",
    "properties": {
        "filename": {"type": "string", "description": "Output filename with extension (e.g. 'server.py', 'index.html')."},
        "content": {"type": "string", "description": "File content."},
    },
    "required": ["filename", "content"],
}, tool_generate_code)

register("generate_csv", "Generate a CSV file from raw CSV text. Returns the file path.", {
    "type": "object",
    "properties": {
        "filename": {"type": "string", "description": "Output filename (e.g. 'data')."},
        "data": {"type": "string", "description": "Raw CSV content."},
    },
    "required": ["filename", "data"],
}, tool_generate_csv)

register("generate_json", "Generate a formatted JSON file. Returns the file path.", {
    "type": "object",
    "properties": {
        "filename": {"type": "string", "description": "Output filename (e.g. 'config')."},
        "data": {"type": "string", "description": "JSON string to format and write."},
    },
    "required": ["filename", "data"],
}, tool_generate_json)

register("list_generated_files", "List all files Zenith has generated (PDFs, docs, spreadsheets, code, etc.).", {
    "type": "object",
    "properties": {},
}, tool_list_generated_files)

register("delete_generated_file", "Delete a generated file by filename.", {
    "type": "object",
    "properties": {"filename": {"type": "string"}},
    "required": ["filename"],
}, tool_delete_generated_file)

# ── Hack Club CDN ────────────────────────────────────────────────────────────
register("cdn_upload", "Upload a local file to cdn.hackclub.com. Returns a permanent public CDN URL. Use for sharing generated files, hosting project assets, or when a response needs a downloadable file.", {
    "type": "object",
    "properties": {"file_path": {"type": "string", "description": "Absolute path to the file to upload."}},
    "required": ["file_path"],
}, tool_cdn_upload)

register("cdn_upload_url", "Upload a file from a URL to cdn.hackclub.com (re-host an image/file). Returns the CDN URL.", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Source URL of the file to upload."},
        "source_auth": {"type": "string", "description": "Optional auth header for fetching the source URL."},
    },
    "required": ["url"],
}, tool_cdn_upload_url)

register("cdn_delete", "Delete a file from cdn.hackclub.com by upload ID.", {
    "type": "object",
    "properties": {"upload_id": {"type": "string"}},
    "required": ["upload_id"],
}, tool_cdn_delete)

register("cdn_quota", "Check CDN storage quota and usage on cdn.hackclub.com.", {
    "type": "object",
    "properties": {},
}, tool_cdn_quota)

# ── Data Visualization & Deep Research ───────────────────────────────────────
register("generate_chart", "Generate visual data charts (bar, line, pie, donut, scatter, area). Returns image path + markdown embed code to show graphs directly in chat responses. Supports dark mode styling.", {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Title of the chart."},
        "chart_type": {"type": "string", "enum": ["bar", "line", "pie", "donut", "scatter", "area"], "default": "bar"},
        "labels": {"description": "Comma-separated list or array of category labels (e.g. 'Q1, Q2, Q3, Q4' or ['Jan', 'Feb'])."},
        "values": {"description": "Comma-separated list or array of numerical values (e.g. '15, 25, 40, 30')."},
        "series_names": {"description": "Optional legend / series label."},
        "x_label": {"type": "string", "description": "Label for the X axis."},
        "y_label": {"type": "string", "description": "Label for the Y axis."},
        "upload_to_cdn": {"type": "boolean", "default": False, "description": "Optionally upload chart image to Hack Club CDN for public sharing."},
    },
    "required": ["title", "labels", "values"],
}, tool_generate_chart)

register("deep_research", "Run autonomous multi-source deep research on any topic. Crawls web pages, parses local PDFs, executes multi-angle queries, synthesizes findings, auto-generates visual data charts, and creates a downloadable PDF research briefing.", {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "The research topic or question."},
        "extra_queries": {"type": "array", "items": {"type": "string"}, "description": "Additional search query angles to execute concurrently."},
        "pdf_files": {"type": "array", "items": {"type": "string"}, "description": "Local or uploaded PDF file paths to parse and synthesize."},
        "max_sources": {"type": "integer", "default": 6, "description": "Number of web sources to crawl & analyze."},
        "generate_report_pdf": {"type": "boolean", "default": True, "description": "Generate a downloadable PDF research briefing file."},
        "create_chart": {"type": "boolean", "default": True, "description": "Auto-extract numerical data and create a visual chart."},
    },
    "required": ["topic"],
}, tool_deep_research)

register("research_synthesis", "[Alias for 'deep_research'] Multi-query search aggregator, PDF parser & AI synthesis engine.", {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "Primary research topic or question."},
        "extra_queries": {"type": "array", "items": {"type": "string"}, "description": "Additional search query angles to execute concurrently."},
        "pdf_files": {"type": "array", "items": {"type": "string"}, "description": "Local or uploaded PDF file paths to parse and synthesize."},
        "max_sources": {"type": "integer", "default": 6, "description": "Maximum web sources to crawl."},
        "generate_pdf_report": {"type": "boolean", "default": True, "description": "Generate downloadable PDF synthesis briefing."},
    },
    "required": ["topic"],
}, tool_research_synthesis, hidden_from_catalog=True)

register("generate_pptx", "Generate a PowerPoint presentation (.pptx) file. ALWAYS use this tool whenever the user asks for a presentation, slides, PPT, or PowerPoint deck. IMPORTANT: build a topical `slides` array from the actual topic (e.g. for 'lions' every slide must be about lions — habitat, diet, behaviour, species, conservation), each slide with a descriptive `image_query` for its web photo. Do NOT use the `template` parameter for a topic deck — `template` is ONLY for when the user explicitly requests a pitch_deck / tech_overview / market_analysis structure. If you supply `slides`, it completely defines the deck; `template` is ignored when slides are given. Supports visual themes (executive_dark, cyberpunk_neon, corporate_light, emerald_forest, sunset_warm, midnight_violet), transitions (fade, push, wipe, zoom), visual layout primitives (photo_hero, stat_hero, timeline, cards_grid, split_hero, comparison, quote, chapter_divider), and embedded web photos.", {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Presentation main title."},
        "subtitle": {"type": "string", "description": "Optional presentation subtitle."},
        "slides": {
            "type": "array",
            "description": "List of slide objects, each containing title, layout (photo_hero, stat_hero, timeline, cards_grid, split_hero, comparison, quote, chapter_divider), bullets, stats, cards, steps, columns, image_query.",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "layout": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                    "image_query": {"type": "string"},
                    "stats": {"type": "array"},
                    "cards": {"type": "array"},
                    "steps": {"type": "array"},
                    "columns": {"type": "array"}
                },
                "required": ["title"]
            }
        },
        "author": {"type": "string", "default": "Zenith User"},
        "theme": {"type": "string", "enum": ["executive_dark", "cyberpunk_neon", "corporate_light", "emerald_forest", "sunset_warm", "midnight_violet", "dark", "light"], "default": "executive_dark"},
        "template": {"type": "string", "enum": ["pitch_deck", "tech_overview", "market_analysis"], "description": "Optional pre-designed slide template structure."},
        "transition": {"type": "string", "enum": ["fade", "push", "wipe", "zoom"], "default": "fade", "description": "Slide entry animation / transition effect."}
    },
    "required": ["title"]
}, tool_generate_pptx)

register("list_pptx_themes", "List available PowerPoint color palettes and visual themes (executive_dark, cyberpunk_neon, corporate_light, emerald_forest, sunset_warm, midnight_violet).", {
    "type": "object",
    "properties": {}
}, tool_list_pptx_themes)

register("list_pptx_templates", "List pre-designed presentation templates (pitch_deck, tech_overview, market_analysis) with pre-configured layout structures.", {
    "type": "object",
    "properties": {}
}, tool_list_pptx_templates)

register("search_presentation_photos", "Search, download, and crop high-resolution web photos for embedding into presentation slides.", {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query for the web photo (e.g. 'Cybersecurity Data Center Server')."}
    },
    "required": ["query"]
}, tool_search_presentation_photos)

register("fetch_stock_photo", "Search, download, and crop high-resolution stock photos from Unsplash, Pexels, Pixabay, and Wikimedia Commons for use anywhere (presentations, documents, web apps, emails, or CDN uploads).", {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query for high-res stock photo (e.g. 'futuristic robotics lab', 'sunset over mountains', 'cybersecurity server')."}
    },
    "required": ["query"]
}, tool_fetch_stock_photo)



# ── Complete Homelab Control Suite ───────────────────────────────────────────
register("media_search", "Search for movies or TV shows across Sonarr, Radarr, and Jellyseerr. Returns library status, year, and TMDB/TVDB IDs.", {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Movie or TV show title."},
        "media_type": {"type": "string", "enum": ["all", "movie", "series"], "default": "all"},
    },
    "required": ["query"],
}, tool_media_search)

register("media_add", "Add a movie to Radarr or TV show to Sonarr and trigger immediate automatic download. Confirmation required.", {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Movie or TV show title."},
        "media_type": {"type": "string", "enum": ["movie", "series"], "default": "movie"},
        "search_now": {"type": "boolean", "default": True},
    },
    "required": ["title"],
}, tool_media_add)

register("media_queue", "Check active media download queue across Sonarr, Radarr, and qBittorrent (shows download speed, progress %, and state).", {
    "type": "object",
    "properties": {},
}, tool_media_queue)

register("torrent_control", "Manage qBittorrent downloads (action: 'list' | 'pause' | 'resume' | 'delete').", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "pause", "resume", "delete"], "default": "list"},
        "info_hash": {"type": "string", "description": "Torrent hash (or 'all')."},
    },
}, tool_torrent_control)

register("tunnel_status", "Check Cloudflare Tunnel ingress routes, active subdomains, and connectivity.", {
    "type": "object",
    "properties": {},
}, tool_tunnel_status)

register("tunnel_add_route", "Add a new public ingress subdomain route to Cloudflare Tunnel (e.g. app.yourdomain.com -> local port) and restart cloudflared. Confirmation required.", {
    "type": "object",
    "properties": {
        "subdomain": {"type": "string", "description": "Subdomain name (e.g. 'grafana' or 'app.yourdomain.com')."},
        "local_port": {"type": "integer", "description": "Local HTTP port bound on 127.0.0.1."},
    },
    "required": ["subdomain", "local_port"],
}, tool_tunnel_add_route)

register("homelab_overview", "Full scan of Homelab containers, system vitals, disk storage, and services.", {
    "type": "object",
    "properties": {},
}, tool_homelab_overview)

# ── GitHub Pro Suite ─────────────────────────────────────────────────────────
register("gh_create_pr", "Create a Pull Request on GitHub with automated summary of commits and diff. Confirmation required.", {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "PR title."},
        "body": {"type": "string", "description": "PR description body. Auto-generated if left empty."},
        "head_branch": {"type": "string", "description": "Source branch (defaults to current branch)."},
        "base_branch": {"type": "string", "default": "main", "description": "Target branch."},
        "repo_path": {"type": "string", "description": "Path to local repository."},
        "draft": {"type": "boolean", "default": False},
    },
    "required": ["title"],
}, tool_gh_create_pr)

register("gh_code_review", "Perform an AI code review on current git diff or branch against main. Analyzes bugs, security, performance, and architecture.", {
    "type": "object",
    "properties": {
        "base_branch": {"type": "string", "default": "main"},
        "repo_path": {"type": "string", "description": "Path to local repository."},
    },
}, tool_gh_code_review)

register("gh_list_issues_prs", "List open or closed Issues and PRs for a repository.", {
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "Target repository (e.g. 'owner/repo'). Defaults to current repo."},
        "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
    },
}, tool_gh_list_issues_prs)

register("gh_release_create", "Create a GitHub Release with optional attached asset binary/file. Confirmation required.", {
    "type": "object",
    "properties": {
        "tag": {"type": "string", "description": "Release tag (e.g. 'v1.0.0')."},
        "title": {"type": "string", "description": "Release title."},
        "notes": {"type": "string", "description": "Release notes. Auto-generated if empty."},
        "asset_path": {"type": "string", "description": "Path to binary or asset file to upload."},
        "repo_path": {"type": "string"},
    },
    "required": ["tag"],
}, tool_gh_release_create)

# ── Network & HTTP Testing Suite ──────────────────────────────────────────────
register("http_request", "Send custom HTTP requests (GET, POST, PUT, DELETE, PATCH, HEAD) to test REST/GraphQL APIs. Supports JSON payloads, custom headers, status codes, and latency benchmarks.", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Target endpoint URL."},
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"], "default": "GET"},
        "headers": {"description": "Custom headers as JSON string or dict."},
        "params": {"description": "Query parameters."},
        "data": {"description": "Request body payload (JSON or string)."},
        "timeout": {"type": "integer", "default": 15},
    },
    "required": ["url"],
}, tool_http_request)

register("dns_lookup", "Query DNS records (A, AAAA, MX, TXT, CNAME, NS, SOA) for any domain.", {
    "type": "object",
    "properties": {
        "domain": {"type": "string", "description": "Domain name (e.g. 'example.com')."},
        "record_type": {"type": "string", "enum": ["A", "AAAA", "MX", "TXT", "CNAME", "NS", "SOA"], "default": "A"},
    },
    "required": ["domain"],
}, tool_dns_lookup)

# ── Advanced Web Suite ───────────────────────────────────────────────────────
register("web_screenshot_full", "[Alias for 'browser_screenshot'] Capture a full-page high-resolution screenshot of any webpage and embed it directly in chat.", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Webpage URL to capture."},
        "full_page": {"type": "boolean", "default": True},
    },
    "required": ["url"],
}, tool_web_screenshot_full, hidden_from_catalog=True)

register("web_extract_data", "Extract structured content from a webpage (text, emails, links, headings).", {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Webpage URL."},
        "extract_type": {"type": "string", "enum": ["text", "emails", "links", "headings"], "default": "text"},
    },
    "required": ["url"],
}, tool_web_extract_data)

# ── File & Image Processing ───────────────────────────────────────────────────
register("analyze_image", "Inspect an image file (PNG, JPG, WEBP, SVG, GIF). Returns image dimensions, filesize, format, and AI vision description/OCR.", {
    "type": "object",
    "properties": {
        "image_path": {"type": "string", "description": "Path to the uploaded or local image file."},
        "prompt": {"type": "string", "description": "Optional question or instruction about the image."},
    },
    "required": ["image_path"],
}, tool_analyze_image)

register("edit_image", "Edit, transform, or convert an image (action: 'resize', 'grayscale', 'rotate', 'flip', 'blur', 'watermark'). Returns edited image embedded in chat.", {
    "type": "object",
    "properties": {
        "image_path": {"type": "string", "description": "Path to the image file to edit."},
        "action": {"type": "string", "enum": ["resize", "grayscale", "rotate", "flip", "blur", "watermark"], "default": "resize"},
        "width": {"type": "integer", "description": "Target width for resize."},
        "height": {"type": "integer", "description": "Target height for resize."},
        "angle": {"type": "integer", "description": "Rotation angle in degrees (e.g. 90, 180, 270)."},
        "target_format": {"type": "string", "description": "Target format extension (e.g. 'png', 'jpg', 'webp')."},
        "watermark_text": {"type": "string", "description": "Text to watermark on image."},
    },
    "required": ["image_path", "action"],
}, tool_edit_image)

register("analyze_file", "Inspect and extract content/structure from a user-uploaded file (PDF, Word doc, Excel sheet, CSV, JSON, code file).", {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the uploaded or local file."},
    },
    "required": ["file_path"],
}, tool_analyze_file)

register("modify_file", "Modify or re-export an existing file with new content or requested changes.", {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to modify."},
        "new_content": {"type": "string", "description": "New content or code for the file."},
        "output_filename": {"type": "string", "description": "Optional custom output filename."},
    },
    "required": ["file_path", "new_content"],
}, tool_modify_file)

# ───────────────────────────────────────────────────────────── git_dev handlers
async def tool_git_status(repo_path: str = "") -> str:
    from zenith.tools.git_dev import git_status
    return await git_status(repo_path)


async def tool_git_log(repo_path: str = "", limit: int = 10) -> str:
    from zenith.tools.git_dev import git_log
    return await git_log(repo_path, limit)


async def tool_git_diff(repo_path: str = "", file_path: str = "") -> str:
    from zenith.tools.git_dev import git_diff
    return await git_diff(repo_path, file_path)


async def tool_git_branch(action: str = "list", repo_path: str = "", branch_name: str = "") -> str:
    from zenith.tools.git_dev import git_branch
    return await git_branch(action, repo_path, branch_name)


async def tool_port_inspector(port: int = 0) -> str:
    from zenith.tools.git_dev import port_inspector
    return await port_inspector(port)


# ───────────────────────────────────────────────────────── systemd_net handlers
async def tool_systemd_status(service: str = "") -> str:
    from zenith.tools.systemd_net import systemd_status
    return await systemd_status(service)


async def tool_systemd_control(service: str, action: str) -> str:
    from zenith.tools.systemd_net import systemd_control
    return await systemd_control(service, action)


async def tool_ping_check(host: str, count: int = 3) -> str:
    from zenith.tools.systemd_net import ping_check
    return await ping_check(host, count)


async def tool_endpoint_health(url: str) -> str:
    from zenith.tools.systemd_net import endpoint_health
    return await endpoint_health(url)


# ──────────────────────────────────────────────────────────── jellyfin handlers
async def tool_jellyfin_status() -> str:
    from zenith.tools.jellyfin import jellyfin_status
    return await jellyfin_status()


async def tool_jellyfin_search(query: str, media_type: str = "") -> str:
    from zenith.tools.jellyfin import jellyfin_search
    return await jellyfin_search(query, media_type)


async def tool_jellyfin_recent(limit: int = 8) -> str:
    from zenith.tools.jellyfin import jellyfin_recent
    return await jellyfin_recent(limit)


# ── Local Git & Developer Suite ────────────────────────────────────────────────
register("git_status", "Check git status (branch, staged/unstaged changes) for a repo directory.", {
    "type": "object",
    "properties": {"repo_path": {"type": "string", "description": "Absolute path to repository (default: current workspace)."}},
}, tool_git_status)

register("git_log", "List recent commits for a local repository.", {
    "type": "object",
    "properties": {
        "repo_path": {"type": "string"},
        "limit": {"type": "integer", "default": 10},
    },
}, tool_git_log)

register("git_diff", "View git diff for uncommitted or staged changes.", {
    "type": "object",
    "properties": {
        "repo_path": {"type": "string"},
        "file_path": {"type": "string"},
    },
}, tool_git_diff)

register("git_branch", "Manage git branches (action: 'list' | 'checkout' | 'create').", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "checkout", "create"]},
        "repo_path": {"type": "string"},
        "branch_name": {"type": "string"},
    },
    "required": ["action"],
}, tool_git_branch)

register("port_inspector", "Inspect listening network ports or check which process is bound to a port.", {
    "type": "object",
    "properties": {"port": {"type": "integer", "default": 0}},
}, tool_port_inspector)

# ── Systemd & Network Health ──────────────────────────────────────────────────
register("systemd_status", "List active systemd services or detailed status of a unit.", {
    "type": "object",
    "properties": {"service": {"type": "string"}},
}, tool_systemd_status)

register("systemd_control", "Control a systemd service (start | stop | restart | reload). Confirmation required.", {
    "type": "object",
    "properties": {
        "service": {"type": "string"},
        "action": {"type": "string", "enum": ["start", "stop", "restart", "reload"]},
    },
    "required": ["service", "action"],
}, tool_systemd_control)

register("ping_check", "Ping a host to measure latency and packet loss.", {
    "type": "object",
    "properties": {
        "host": {"type": "string"},
        "count": {"type": "integer", "default": 3},
    },
    "required": ["host"],
}, tool_ping_check)

register("endpoint_health", "Check HTTP status code, latency, server and content-type for a URL.", {
    "type": "object",
    "properties": {"url": {"type": "string"}},
    "required": ["url"],
}, tool_endpoint_health)

# ── Jellyfin Media Manager ────────────────────────────────────────────────────
register("jellyfin_status", "Check Jellyfin server status and active playback sessions (Now Playing).", {
    "type": "object",
    "properties": {},
}, tool_jellyfin_status)

register("jellyfin_search", "Search Jellyfin media library for movies, TV shows, episodes, or music.", {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "media_type": {"type": "string", "description": "Optional filter e.g. Movie, Series, Episode"},
    },
    "required": ["query"],
}, tool_jellyfin_search)

register("jellyfin_recent", "List recently added items in the Jellyfin library.", {
    "type": "object",
    "properties": {"limit": {"type": "integer", "default": 8}},
}, tool_jellyfin_recent)

# ── Home Assistant / Smart Home Suite ─────────────────────────────────────────
register("ha_fan", "Control smart fans (FAN 1 / fan.fan_1, FAN 2 / fan.fan_2). Actions: 'on', 'off', 'toggle', 'speed' (requires percentage 0-100), 'status'.", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["on", "off", "toggle", "speed", "status"], "default": "status"},
        "entity_id": {"type": "string", "default": "fan.fan_2", "description": "Fan entity ID (e.g. 'fan.fan_1', 'fan 1', 'fan.fan_2', 'fan 2')."},
        "percentage": {"type": "integer", "description": "Fan speed percentage (0 to 100). Required for speed action."},
    },
}, tool_ha_fan)

register("ha_ac", "Control Air Conditioner (power switch + Panasonic AC climate unit). Automatically turns on power switch + climate unit when requested. Actions: 'on', 'off', 'temp', 'mode', 'fan', 'toggle', 'status'. Allows setting temperature (°C), mode ('cool', 'heat', 'auto', 'dry', 'fan_only', 'off'), and fan_mode ('auto', 'diffuse', 'low', 'medium', 'high').", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["on", "off", "temp", "mode", "fan", "toggle", "status"], "default": "status"},
        "temperature": {"type": "number", "description": "Target temperature in °C (e.g. 23.0, 16.0 - 30.0 range)."},
        "mode": {"type": "string", "enum": ["cool", "heat", "auto", "dry", "fan_only", "off"], "description": "HVAC mode."},
        "fan_mode": {"type": "string", "enum": ["auto", "diffuse", "low", "medium", "high"], "description": "AC internal fan speed mode."},
    },
}, tool_ha_ac)

register("ha_climate", "Control any Home Assistant climate/thermostat device (Panasonic AC). Actions: 'status', 'on', 'off', 'temp', 'mode', 'fan'. Set temperature (°C), hvac_mode ('cool', 'heat', 'auto', 'dry', 'fan_only', 'off'), and fan_mode ('auto', 'diffuse', 'low', 'medium', 'high').", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["status", "on", "off", "temp", "mode", "fan"], "default": "status"},
        "entity_id": {"type": "string", "default": "climate.panasonic_ac_panasonic_ac"},
        "temperature": {"type": "number", "description": "Target temperature in °C."},
        "hvac_mode": {"type": "string", "description": "HVAC mode."},
        "fan_mode": {"type": "string", "description": "AC internal fan speed mode."},
    },
}, tool_ha_climate)

register("ha_soundbar", "Control Soundbar (POWER SWITCH Switch 1). Actions: 'on', 'off', 'toggle', 'status'.", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["on", "off", "toggle", "status"], "default": "status"},
    },
}, tool_ha_soundbar)

register("ha_switch", "Control any Home Assistant smart switch or socket by alias ('ac', 'soundbar', 'power_switch', 'plug', or custom switch entity ID). Actions: 'on', 'off', 'toggle', 'status'.", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["on", "off", "toggle", "status"], "default": "status"},
        "device": {"type": "string", "default": "ac", "description": "Device name/alias ('ac', 'soundbar', 'power_switch', 'plug', 'switch 1', 'switch 2')."},
    },
}, tool_ha_switch)

register("ha_smart_plug", "Control and inspect Smart Plug 10A socket & energy telemetry (voltage, power, current, energy). Actions: 'status', 'on', 'off', 'toggle', 'energy'.", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["status", "on", "off", "toggle", "energy"], "default": "status"},
    },
}, tool_ha_smart_plug)

register("ha_overview", "Get live status overview of all smart home devices in Home Assistant (AC, Soundbar, Fan 1, Fan 2, Main Switch, Smart Plug).", {
    "type": "object",
    "properties": {},
}, tool_ha_overview)

register("ha_entity", "Control or check state of any Home Assistant smart home device (switches, lights, fans, climate, sensors, automations).", {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["status", "call", "on", "off", "toggle"], "default": "status"},
        "domain": {"type": "string", "default": "homeassistant", "description": "HA domain (e.g. 'fan', 'light', 'switch')."},
        "service": {"type": "string", "default": "toggle", "description": "HA service (e.g. 'turn_on', 'turn_off', 'toggle')."},
        "entity_id": {"type": "string", "default": "fan.fan_2", "description": "Home Assistant entity ID."},
    },
}, tool_ha_entity)


# ── Minecraft RCON admin ─────────────────────────────────────────────────────
# Server must be RUNNING. These are confirmation-gated (mutating the world).
register("mc_admin", "Administer the Twilight-MC Minecraft server via RCON (server must be running). Actions: list, seed, save_all, whitelist_add/remove/list, ban, pardon, kick, op, deop, tp, give (e.g. 'give Aryan diamond 64'), say, time_set, weather. Player names 1-16 chars.", {
    "type": "object",
    "properties": {
        "command": {"type": "string", "enum": ["list", "seed", "save_all", "whitelist_add", "whitelist_remove", "whitelist_list", "ban", "pardon", "kick", "op", "deop", "tp", "give", "say", "time_set", "weather"], "default": "list"},
        "player": {"type": "string", "default": "", "description": "Player name for whitelist/ban/pardon/kick/op/deop/give."},
        "item": {"type": "string", "default": "", "description": "Item id for 'give' (e.g. diamond, oak_log)."},
        "count": {"type": "string", "default": "", "description": "Count for 'give'."},
        "x": {"type": "string", "default": "0", "description": "X for tp."},
        "y": {"type": "string", "default": "64", "description": "Y for tp."},
        "z": {"type": "string", "default": "0", "description": "Z for tp."}
    },
    "required": [],
}, tool_mc_admin)

register("mc_admin_help", "List what the Minecraft admin tool can do (commands + examples).", {
    "type": "object",
    "properties": {},
}, tool_mc_admin_help)


# ── YouTube transcript ──────────────────────────────────────────────────────
register("youtube_transcript", "Fetch the transcript (captions) of a YouTube video as clean text, for summarizing or taking notes. Pass a full watch/share/shorts URL.", {
    "type": "object",
    "properties": {"url": {"type": "string", "description": "YouTube URL (youtube.com/watch?v=…, youtu.be/…, shorts, live)."}},
    "required": ["url"],
}, tool_youtube_transcript)

register("youtube_search", "Search YouTube for video titles + URLs (no API key needed).", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}, tool_youtube_search)


# ── n8n workflow automation ────────────────────────────────────────────────
register("n8n_health", "Check if n8n is running and healthy (works without an API key).", {
    "type": "object",
    "properties": {},
}, tool_n8n_health)

register("n8n_workflows", "List n8n workflows (name/id/active). Needs N8N_API_KEY in .env.", {
    "type": "object",
    "properties": {"limit": {"type": "integer", "default": 20}},
}, tool_n8n_workflows)

register("n8n_execute", "Trigger an n8n workflow execution with an optional JSON payload ({\"data\": …}). Needs N8N_API_KEY in .env; pass the numeric workflow id or a name.", {
    "type": "object",
    "properties": {
        "workflow_id": {"type": "string", "default": "", "description": "Numeric n8n workflow id (or empty to match by name)."},
        "name": {"type": "string", "default": "", "description": "Workflow name when workflow_id is empty."},
        "data": {"type": "string", "default": "{}", "description": "JSON object payload for the workflow."},
    },
}, tool_n8n_execute)


# ── Mode Management & UI Customizer Tools ────────────────────────────────────
register("switch_mode", "Switch Zenith's operating mode between 'setup' (starter setup companion) and 'sovereign' (full autonomous normal mode). Use when user asks to switch modes or wants to skip onboarding.", {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "description": "Target mode: 'setup' (starter setup companion) or 'sovereign' (full autonomous).", "enum": ["setup", "sovereign", "genesis"]},
        "reason": {"type": "string", "default": "", "description": "Optional brief reason for the switch."}
    },
    "required": ["mode"],
}, tool_switch_mode)

register("get_mode", "Get Zenith's current operating mode (setup vs sovereign) and status.", {
    "type": "object",
    "properties": {},
}, tool_get_mode)

register("update_user_profile", "Update user identity and starter profile: name, email, timezone, bio/background. Call this tool immediately whenever the user provides, corrects, or asks to change/fix their name or dashboard identity (e.g. 'call me Aditya', 'my name is X', 'the dashboard still says Maya... pls fix'). Persists to .env, runtime settings, and long-term memory.", {
    "type": "object",
    "properties": {
        "name": {"type": "string", "default": "", "description": "User's display name or preferred name (e.g. 'Aditya')."},
        "email": {"type": "string", "default": "", "description": "User's primary email address."},
        "timezone": {"type": "string", "default": "", "description": "User's local timezone (e.g. Asia/Kolkata, America/New_York)."},
        "bio": {"type": "string", "default": "", "description": "Background, projects, preferences, or workflow details."}
    },
}, tool_update_user_profile)

register("setup_secret", "Store or update an API key/secret in Zenith's configuration (e.g. GEMINI_API_KEY, RESEND_API_KEY, GROQ_API_KEY, GITHUB_TOKEN, HOME_ASSISTANT_TOKEN, OPENWEATHER_API_KEY). Masked safely.", {
    "type": "object",
    "properties": {
        "key": {"type": "string", "description": "Environment variable key name in UPPERCASE (e.g. RESEND_API_KEY, GROQ_API_KEY, HOME_ASSISTANT_TOKEN)."},
        "value": {"type": "string", "description": "The secret key or token value to save."}
    },
    "required": ["key", "value"],
}, tool_setup_secret)

register("get_setup_status", "Inspect which integrations, API keys, and secrets are configured vs missing in Zenith (e.g. brain, email, voice, developer, smart_home, search). Shows where to get missing keys.", {
    "type": "object",
    "properties": {
        "category": {"type": "string", "default": "", "description": "Optional filter category (e.g. 'brain', 'email', 'voice', 'developer', 'smart_home', 'search') or leave empty for all."}
    },
}, tool_get_setup_status)

register("ui_inspect", "Inspect the current UI theme, CSS variables, accent colors, and custom CSS rules.", {
    "type": "object",
    "properties": {
        "target": {"type": "string", "default": "theme", "description": "What part of the UI to inspect (theme, colors, css)."}
    },
}, tool_ui_inspect)

register("ui_customize_theme", "Live-customize Zenith's UI appearance. Changes apply instantly in the connected browser without reloading the page. Can set accent_color (e.g. '#10b981', '#6366f1', '#ec4899', '#f59e0b', '#3b82f6'), font, or inject arbitrary custom CSS.", {
    "type": "object",
    "properties": {
        "accent_color": {"type": "string", "default": "", "description": "Hex, rgb, or color name for the UI primary accent color (e.g. '#10b981', '#6366f1', '#f59e0b')."},
        "theme_mode": {"type": "string", "default": "", "description": "Optional theme mode ('dark' or 'light')."},
        "font": {"type": "string", "default": "", "description": "Font family name for UI typography."},
        "custom_css": {"type": "string", "default": "", "description": "Arbitrary CSS rules to inject and apply live to the UI."}
    },
}, tool_ui_customize_theme)

register("ui_reset_theme", "Reset all UI customizations back to Zenith's default theme.", {
    "type": "object",
    "properties": {},
}, tool_ui_reset_theme)


async def tool_zenith_docs(topic: str = "all") -> str:
    """Read Zenith's self-knowledge documentation, tools reference, deployment guides, or architecture."""
    import pathlib

    current_file = pathlib.Path(__file__).resolve()
    repo_root = current_file.parents[2]  # zenith/zenith/core/tools.py -> repo root
    docs_dir = repo_root / "docs"

    topic_clean = (topic or "all").strip().lower()

    doc_map = {
        "overview": docs_dir / "SYSTEM_OVERVIEW.md",
        "system": docs_dir / "SYSTEM_OVERVIEW.md",
        "architecture": docs_dir / "SYSTEM_OVERVIEW.md",
        "tools": docs_dir / "TOOLS_REFERENCE.md",
        "capabilities": docs_dir / "TOOLS_REFERENCE.md",
        "deploy": docs_dir / "DEPLOYMENT_AND_SETUP.md",
        "deployment": docs_dir / "DEPLOYMENT_AND_SETUP.md",
        "setup": docs_dir / "DEPLOYMENT_AND_SETUP.md",
        "live": docs_dir / "DEPLOYMENT_AND_SETUP.md",
        "agent": docs_dir / "AGENT_GUIDE.md",
        "guide": docs_dir / "AGENT_GUIDE.md",
        "manual": docs_dir / "AGENT_GUIDE.md",
    }

    if topic_clean in doc_map and doc_map[topic_clean].exists():
        try:
            return doc_map[topic_clean].read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading {doc_map[topic_clean].name}: {e}"

    if docs_dir.exists():
        tools_file = docs_dir / "TOOLS_REFERENCE.md"
        if tools_file.exists() and topic_clean not in {"all", "help", "index"}:
            try:
                content = tools_file.read_text(encoding="utf-8")
                matches = []
                for line in content.splitlines():
                    if topic_clean in line.lower():
                        matches.append(line)
                if matches:
                    return f"### Tools matching '{topic_clean}':\n\n" + "\n".join(matches[:20])
            except Exception:
                pass

    return (
        "## Zenith System Documentation Index\n\n"
        "Zenith is an autonomous, open-source AI companion and sovereign control plane designed for general use.\n\n"
        "Available Documentation Modules (pass topic to zenith_docs):\n"
        "- **overview** / **system**: System architecture, core loops, memory engine, and intelligence layers (`docs/SYSTEM_OVERVIEW.md`).\n"
        "- **tools** / **capabilities**: Complete catalogue of all 60+ tools across 12 domains (`docs/TOOLS_REFERENCE.md`).\n"
        "- **deployment** / **setup** / **live**: Guide on running Zenith via Docker or Python, tunnels, ports, and `.env` keys (`docs/DEPLOYMENT_AND_SETUP.md`).\n"
        "- **agent** / **manual**: Zenith's operational handbook, direct execution rules, and self-healing procedures (`docs/AGENT_GUIDE.md`).\n\n"
        "You can also query specific tools like `zenith_docs('docker')`, `zenith_docs('github')`, or `zenith_docs('maps')`."
    )


register("zenith_docs", "Look up Zenith's internal documentation, tool specifications, system architecture, operational manual, or deployment guides. Topics: 'overview', 'tools', 'deployment', 'agent', 'all', or any specific tool name (e.g. 'docker', 'maps', 'email').", {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "default": "all", "description": "Documentation topic ('overview', 'tools', 'deployment', 'agent', 'all', or tool keyword)."}
    },
}, tool_zenith_docs)


AGENT_SYSTEM_SUFFIX = "\nWhen you plan to act, prefer the smallest tool that satisfies it. You are Zenith's delegation layer."

# ── Self-registering tool modules ────────────────────────────────────────────
# These modules call register() at import time to add their tools to TOOLS.
try:
    from ..tools import design_tools as _design_tools  # noqa: F401
except Exception:
    pass  # graceful: design tools optional if deps missing

try:
    from ..tools import context_suite as _context_suite  # noqa: F401
except Exception:
    pass  # graceful: context suite tools optional if deps missing