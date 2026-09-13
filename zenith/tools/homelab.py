"""New capability modules: Docker, GitHub, system health, Minecraft, email.

Every capability is *derived* — the tool defines the operation precisely and the
LLM merely picks it. None of these hand the model a raw API/key or arbitrary
shell.

  docker.*    — speak to the local Docker daemon over the socket.
  system.*    — read pressure (uptime, memory, disk, cpu, processes).
  gh.*        — GitHub through the authenticated `gh` CLI.
  minecraft.* — start/stop/restart/players for the Twilight-MC compose project.
  email.*     — IMAP read + SMTP send.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path

import httpx

from ..core.config import settings

DOCKER_SOCKET = settings.docker_socket
GUARDED = set(settings.guarded_containers)
MC_DIR = settings.mc_compose_dir
_MC_COMPOSE = settings.mc_compose_files


# ─────────────────────────────────────────────────────── shared transport ─────


def _client() -> httpx.AsyncClient:
    """HTTPX client whose requests go to the Docker socket."""
    transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET)
    return httpx.AsyncClient(transport=transport, timeout=10)


async def _docker_json(path: str, method: str = "GET", body: dict | None = None) -> dict:
    async with _client() as client:
        resp = await client.request(method, f"http://docker{path}", json=body)
    resp.raise_for_status()
    return resp.json() if resp.content else {}


async def _docker_text(path: str) -> str:
    async with _client() as client:
        resp = await client.get(f"http://docker{path}")
    resp.raise_for_status()
    return resp.text


# ─────────────────────────────────────────────────────────────── docker ───────


async def docker_list() -> str:
    """All containers + one-line status."""
    try:
        rows = await _docker_json("/containers/json?all=1")
    except Exception as exc:
        return f"[docker error] {exc}"
    if not rows:
        return "No containers."
    return "\n".join(
        f"{(c.get('Names') or ['?'])[0].lstrip('/')}: {c.get('Status', c.get('State', '?'))}"
        for c in rows
    )


async def docker_table() -> str:
    """Compact fleet table for the UI status strip."""
    try:
        rows = await _docker_json("/containers/json?all=1&size=0")
    except Exception as exc:
        return f"[docker error] {exc}"
    if not rows:
        return "No containers."
    lines = []
    for c in rows:
        name = (c.get("Names") or ["?"])[0].lstrip("/")
        lines.append(f"{name}  {c.get('State', '?')}  {c.get('Image', '?')}")
    return "\n".join(lines)


async def docker_status(name: str) -> str:
    clean = _guarded(name)
    if clean is not None:
        return clean
    try:
        rows = await _docker_json(f"/containers/{name}/json")
        state = rows.get("State", {})
        cfg = rows.get("Config", {})
        up = "running" if state.get("Running") else "stopped"
        return f"{name}: {up} (started {state.get('StartedAt', '?')}, image {cfg.get('Image', '?')})"
    except Exception as exc:
        return f"[docker] {name}: {exc}"


def _guarded(name: str) -> str | None:
    """Return an error string if the container is not one Zenith may control."""
    if name not in GUARDED:
        return (f"[docker] {name} is not in the controlled set. "
                f"Allowed: {', '.join(sorted(GUARDED)) or '(none configured)'}")
    return None


async def docker_start(name: str) -> str:
    err = _guarded(name)
    if err:
        return err
    try:
        await _docker_json(f"/containers/{name}/start", method="POST")
    except Exception as exc:
        return f"[docker] {name}: couldn't start — {exc}"
    return f"Started {name}."


async def docker_stop(name: str) -> str:
    err = _guarded(name)
    if err:
        return err
    try:
        await _docker_json(f"/containers/{name}/stop?t=10", method="POST")
    except Exception as exc:
        return f"[docker] {name}: couldn't stop — {exc}"
    return f"Stopped {name}."


async def docker_restart(name: str) -> str:
    err = _guarded(name)
    if err:
        return err
    try:
        await _docker_json(f"/containers/{name}/restart?t=10", method="POST")
    except Exception as exc:
        return f"[docker] {name}: couldn't restart — {exc}"
    return f"Restarted {name}."


async def docker_logs(name: str, tail: int = 80) -> str:
    try:
        text = await _docker_text(
            f"/containers/{name}/logs?stdout=1&stderr=1&tail={tail}&timestamps=0"
        )
        return text[-6000:] or f"(no recent logs for {name})"
    except Exception as exc:
        return f"[docker] {name} logs: {exc}"


# ───────────────────────────────────────────────────────────────────── system ──


async def _run_blocking(cmd, *, timeout: int = 10, shell: bool = False, env=None, cwd=None):
    """Run a blocking subprocess OFF the event loop (the loop serves chat+voice
    +scheduler; a synchronous subprocess.run would freeze all of them)."""
    return await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True, timeout=timeout,
        shell=shell, env=env, cwd=cwd,
    )


async def system_status() -> str:
    """Host vitals: uptime, load, memory, disk / across Linux, macOS, and Windows."""
    try:
        from .system_info import cross_platform_system_status
        return await cross_platform_system_status()
    except Exception as exc:
        return f"[system] {exc}"


async def disk_usage() -> str:
    """Disk usage table across Linux, macOS, and Windows."""
    try:
        from .system_info import cross_platform_disk_usage
        return await cross_platform_disk_usage()
    except Exception as exc:
        return f"[disk] {exc}"


async def memory_usage() -> str:
    """Free/human memory table across Linux, macOS, and Windows."""
    try:
        from .system_info import cross_platform_memory_usage
        return await cross_platform_memory_usage()
    except Exception as exc:
        return f"[memory] {exc}"


async def cpu_usage() -> str:
    """CPU load average + top-ish process list across Linux, macOS, and Windows."""
    try:
        from .system_info import cross_platform_cpu_usage
        return await cross_platform_cpu_usage()
    except Exception as exc:
        return f"[cpu] {exc}"


async def top_processes(limit: int = 8) -> str:
    """Top CPU/memory processes across Linux, macOS, and Windows."""
    try:
        from .system_info import cross_platform_top_processes
        return await cross_platform_top_processes(limit=limit)
    except Exception as exc:
        return f"[ps] {exc}"


async def _read_proc(which: str) -> str:
    try:
        return Path(f"/proc/{which}").read_text(errors="replace").strip()
    except Exception as exc:
        return f"[proc] {exc}"


def _mem_parse(meminfo: str, key: str) -> int:
    m = re.search(rf"^{key}:\s+(\d+)", meminfo, re.M)
    return int(m.group(1)) if m else 0


# ──────────────────────────────────────────────────────────────────────── gh ──


async def _gh(args: list[str], timeout: int = 30) -> str:
    """Run the GitHub CLI; returns trimmed stdout or an error line.

    Async: a slow gh network call must not block the event loop.
    """
    env = dict(os.environ)
    # Allow GH_TOKEN to come from the container env (set via .env).
    if os.getenv("GH_TOKEN"):
        env["GH_TOKEN"] = os.getenv("GH_TOKEN")
    try:
        proc = await _run_blocking([settings.gh_bin, *args], timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return "[gh] timed out"
    except Exception as exc:
        return f"[gh] {exc}"
    combined = proc.stdout.strip()
    # Some gh commands return non-zero even on partial success (e.g. `auth
    # status` failing on the default account while GH_TOKEN works). If the
    # output carries useful content, prefer it over a bare error line.
    if proc.returncode != 0:
        if combined and "Logged in" in combined:
            return combined
        return f"[gh] {proc.stderr.strip()[:400]}"
    return combined


async def gh_whoami() -> str:
    out = await _gh(["auth", "status"])
    return out


def _default_gh_owner() -> str:
    return (
        getattr(settings, "github_user", "")
        or os.getenv("GITHUB_USER", "")
        or ""
    )


async def gh_list_repos(owner: str = "", limit: int = 20) -> str:
    if not owner:
        owner = _default_gh_owner()
    out = await _gh(["repo", "list", owner, "--limit", str(limit), "--json",
                     "name,description,visibility,updatedAt,defaultBranchRef"])
    if out.startswith("[gh"):
        return out
    try:
        rows = json.loads(out)
    except Exception:
        return out
    lines = []
    for r in rows:
        d = (r.get("description") or "")[:60]
        lines.append(f"{r.get('name')} — {d} ({r.get('visibility')}, default {r.get('defaultBranchRef', {}).get('name') or 'main'})")
    return "\n".join(lines) or f"No repos for {owner}."


def _repo_arg(owner: str, repo: str) -> tuple[str, str] | str:
    """Normalize owner/repo; returns (owner, repo) or an error string."""
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    if "/" in repo:
        owner, repo = repo.rsplit("/", 1)
    if not owner:
        owner = _default_gh_owner()
    if not owner or not repo:
        return f"Provide owner and repo (e.g. owner={owner or 'username'} repo=project)."
    return owner, repo


async def gh_issues(owner: str, repo: str, state: str = "open", limit: int = 10) -> str:
    r = _repo_arg(owner, repo)
    if isinstance(r, str):
        return r
    owner, repo = r
    out = await _gh(["issue", "list", "-R", f"{owner}/{repo}", "--state", state,
                     "--limit", str(limit), "--json", "number,title"])
    if out.startswith("[gh"):
        return out
    try:
        rows = json.loads(out)
    except Exception:
        return out
    if not rows:
        return f"No {state} issues in {owner}/{repo}."
    return "\n".join(f"#{row['number']} {row['title']}" for row in rows)


async def gh_pulls(owner: str, repo: str, state: str = "open") -> str:
    r = _repo_arg(owner, repo)
    if isinstance(r, str):
        return r
    owner, repo = r
    out = await _gh(["pr", "list", "-R", f"{owner}/{repo}", "--state", state,
                     "--limit", "10", "--json", "number,title,author{login}"])
    if out.startswith("[gh"):
        return out
    try:
        rows = json.loads(out)
    except Exception:
        return out
    if not rows:
        return f"No {state} PRs in {owner}/{repo}."
    return "\n".join(f"#{r['number']} {r['title']} (by {r.get('author', {}).get('login', '?')})" for r in rows)


async def gh_repo_status(owner: str, repo: str) -> str:
    r = _repo_arg(owner, repo)
    if isinstance(r, str):
        return r
    owner, repo = r
    view = await _gh(["repo", "view", f"{owner}/{repo}", "--json", "defaultBranchRef,description"])
    try:
        meta = json.loads(view) if not view.startswith("[gh") else {}
    except Exception:
        meta = {}
    branch = (meta.get("defaultBranchRef") or {}).get("name", "main")
    commits = await _gh(["api", f"/repos/{owner}/{repo}/commits?per_page=5",
                         "--jq", '.[] | "\\(.commit.author.date[0:10]) \\(.commit.message | split("\\n")[0])"'])
    if "error message" in commits.lower() or commits.startswith("[gh"):
        commits = "unavailable"
    return f"{owner}/{repo} — default {branch}\nRecent commits:\n{commits}"


async def gh_create_issue(owner: str, repo: str, title: str, body: str = "") -> str:
    r = _repo_arg(owner, repo)
    if isinstance(r, str):
        return r
    owner, repo = r
    out = await _gh(["issue", "create", "-R", f"{owner}/{repo}", "--title", title,
                     "--body", body or "Opened by Zenith."])
    return out  # returns the URL on success, [gh ...] on failure


async def gh_create_repo(name: str, private: bool = False, description: str = "") -> str:
    """Create a GitHub repo under the user's account. Returns the clone URL."""
    if not name or not re.match(r"^[A-Za-z0-9_.-]+$", name):
        return "Invalid repo name (letters/digits/-/_)."
    cmd = [
        "repo", "create", name,
        "--" + ("private" if private else "public"),
        "--confirm",
    ]
    if description:
        cmd += ["--description", description]
    out = await _gh(cmd)
    return out


async def gh_create_branch(owner: str, repo: str, branch: str, base: str = "") -> str:
    """Create a branch in a local-ish copy? For remote-only: use gh api."""
    r = _repo_arg(owner, repo)
    if isinstance(r, str):
        return r
    owner, repo = r
    base = base or await _default_branch(owner, repo)
    out = await _gh(["api", "-X", "POST", f"/repos/{owner}/{repo}/git/refs",
                     "-f", f"ref=refs/heads/{branch}", "--field", f"sha={await _base_sha(owner, repo, base)}"])
    return out


async def _default_branch(owner: str, repo: str) -> str:
    out = await _gh(["repo", "view", f"{owner}/{repo}", "--json", "defaultBranchRef"])
    try:
        return (json.loads(out).get("defaultBranchRef") or {}).get("name", "main") if not out.startswith("[gh") else "main"
    except Exception:
        return "main"


async def _base_sha(owner: str, repo: str, branch: str) -> str:
    out = await _gh(["api", f"/repos/{owner}/{repo}/git/ref/heads/{branch}"])
    try:
        return json.loads(out)["object"]["sha"] if not out.startswith("[gh") else ""
    except Exception:
        return ""


# ────────────────────────────────────────────────────────────────── minecraft ──


async def mc_status() -> str:
    """Twilight stack status (server + tunnels)."""
    try:
        import urllib.parse
        resp = await _docker_json(
            "/containers/json?all=1&filters=" + urllib.parse.quote(json.dumps({"name": ["twilight"]}))
        )
    except Exception as exc:
        return f"[minecraft] {exc}"
    if not resp:
        return "twilight stack: no containers up."
    return "\n".join(
        f"{(c.get('Names') or ['?'])[0].lstrip('/')}: {c.get('State', '?')} ({c.get('Status', '')})"
        for c in resp
    )


async def _mc_compose_cmd(action: str, timeout: int = 45) -> str:
    """Run `docker compose <action>` in the Twilight-MC directory (off the loop)."""
    if not MC_DIR.exists():
        return f"[minecraft] Compose dir not found: {MC_DIR} (set MC_COMPOSE_DIR in .env)."
    try:
        proc = await _run_blocking(
            ["docker", "compose", *_MC_COMPOSE.split(), action],
            timeout=timeout, cwd=str(MC_DIR),
        )
    except subprocess.TimeoutExpired:
        return f"[minecraft] {action} timed out."
    except FileNotFoundError:
        return "[minecraft] docker binary not found in Zenith's container."
    except Exception as exc:
        return f"[minecraft] {exc}"
    if proc.returncode != 0:
        return f"[minecraft] {action} failed: {(proc.stderr or proc.stdout).strip()[-300:]}"
    out = proc.stdout.strip()
    return f"{action} ok." + (f"\n{out[-300:]}" if out else "")


async def mc_start() -> str:
    return await _mc_compose_cmd("up")


async def _mc_up() -> str:
    if not MC_DIR.exists():
        return f"[minecraft] Compose dir not found: {MC_DIR}."
    try:
        await asyncio.create_subprocess_exec(  # "docker compose up -d"
            "docker", "compose", *_MC_COMPOSE.split(), "up", "-d",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(MC_DIR),
        )
    except Exception as exc:
        return f"[minecraft] {exc}"
    return f"Twilight-MC is starting (compose up -d in {MC_DIR})."


async def mc_stop() -> str:
    if not MC_DIR.exists():
        return f"[minecraft] Compose dir not found at {MC_DIR}."
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", *_MC_COMPOSE.split(), "stop",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(MC_DIR),
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=45)
        code = proc.returncode
        if code != 0:
            return f"[minecraft] stop failed: {(err or out).decode(errors='replace')[-400:]}"
        return "Twilight-MC stopped."
    except asyncio.TimeoutError:
        return "[minecraft] stop timed out."
    except Exception as exc:
        return f"[minecraft] {exc}"


async def mc_restart() -> str:
    first = await mc_stop()
    if first.startswith("[minecraft]") and "stopped" not in first:
        return first
    return await mc_start()


async def mc_players() -> str:
    """Players right now. Uses the itzg image's own rcon-cli helper inside the
    container (via the Docker socket — Zenith has no docker CLI, only the
    socket, so `docker exec` via subprocess would fail)."""
    from ..tools.rcon import _docker_exec, _SERVER
    try:
        code, out, err = await _docker_exec(["list"])
    except (asyncio.TimeoutError, FileNotFoundError):
        return "Couldn't reach the Minecraft server (server likely stopped)."
    except Exception as exc:
        return f"[minecraft] {exc}"
    if code != 0 and not out:
        return "Couldn't reach the Minecraft server (server likely stopped)."
    return out.strip() or "No players online."


# ────────────────────────────────────────────────────────────────────── email ──


async def email_search(query: str = "", n: int = 5) -> str:
    """Search the configured mailbox; returns From/Subject/date lines."""
    from . import mail
    return await mail.search(query, n)


async def email_read(uid: str) -> str:
    from . import mail
    return await mail.read(uid)


def _normalize_email_args(to: str, subject: str, body: str) -> tuple[str, str, str]:
    import re
    email_regex = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
    all_text = f"{to or ''} {subject or ''} {body or ''}"
    matches = email_regex.findall(all_text)
    recipient = matches[0] if matches else ""

    to_clean = email_regex.sub("", to or "").strip()
    if to_clean and len(to_clean) > 5:
        if not body or body == to:
            body = to
        elif not subject:
            subject = to_clean[:50]

    if not subject:
        if body:
            subject = body.split("\n")[0][:60]
        else:
            subject = "Message from Zenith"

    if not body:
        body = subject or "Hello"

    return recipient or to or "", subject, body


async def email_send(to: str, subject: str, body: str) -> str:
    """Send email via Resend/SMTP."""
    from . import mail
    to, subject, body = _normalize_email_args(to, subject, body)
    if not (to and subject and body):
        return "Provide to, subject and body."
    if not (settings.resend_api_key or settings.mail_smtp_host):
        return ("Email isn't configured for sending (set RESEND_API_KEY for "
                "zenith@agm.quest, or MAIL_SMTP_*). Draft it and send manually.")
    return await mail.send(to, subject, body)


async def email_draft(to: str, subject: str, body: str) -> str:
    """Draft an email for user review."""
    to, subject, body = _normalize_email_args(to, subject, body)
    if not (to and subject and body):
        return "Provide to, subject and body."
    return f"to: {to}\nsubject: {subject}\n\n{body}"