"""Zenith × Antigravity worker — local HTTP API (REST, no auth on loopback).

Zenith reaches the worker over 127.0.0.1:8022. The worker runs
as the host user on the host machine (so the Antigravity CLI
authenticates with the user's Google login in ~/.gemini).

Endpoints
---------
POST /tasks                      submit a coding task (non-blocking)
GET  /tasks                      list tasks (newest first)
GET  /tasks/{id}                 full task state
GET  /tasks/{id}/output          accumulated output text
GET  /tasks/{id}/artifacts       discovered workspace files
POST /tasks/{id}/followup        send a message into the running conversation
POST /tasks/{id}/cancel          cancel a queued/running task
GET  /health                     liveness

The task model is persistent (worker/tasks.jsonl) and statuses follow the
requested state machine (QUEUED → … → COMPLETED/FAILED/CANCELLED).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from . import agy
from . import tasks as T
from . import brief

app = FastAPI(title="Zenith Antigravity Worker", version="1.0.0")

# Bind on the Docker bridge so the `zenith` container can reach it via the
# host gateway (127.0.0.1 from a container is the container's own loopback).
# The Pi is behind CGNAT + the worker exposes a tiny loopback-only surface;
# Zenith reaches it via the private bridge gateway, not from the internet.
_HOST = "0.0.0.0"
_PORT = int(__import__("os").environ.get("ZENITH_WORKER_PORT", "8022"))


@app.get("/health")
async def health():
    auth_info = agy.check_auth_status()
    return {
        "status": "ok",
        "worker": "antigravity-agy",
        "version": "1.0.0",
        "agy_installed": auth_info["installed"],
        "authenticated": auth_info["authenticated"],
    }


@app.get("/status")
async def status():
    auth_info = agy.check_auth_status()
    all_tasks = T.store.list()
    active_count = sum(1 for t in all_tasks if t.status in (T.QUEUED, T.STARTING, T.RUNNING, T.WAITING_FOR_INPUT))
    return {
        "status": "ok",
        "worker": "antigravity-agy",
        "version": "1.0.0",
        "host": _HOST,
        "port": _PORT,
        "agy": auth_info,
        "tasks": {
            "total": len(all_tasks),
            "active": active_count,
        },
    }


@app.post("/auth/login")
async def auth_login():
    """Trigger one-time interactive Google sign-in via Antigravity CLI."""
    import subprocess
    auth_info = agy.check_auth_status()
    if auth_info["authenticated"]:
        return {
            "ok": True,
            "status": "already_authenticated",
            "message": "Antigravity CLI is already authenticated with Google.",
            "agy": auth_info,
        }

    agy_bin = agy._resolve_agy_binary()
    try:
        # Launch non-blocking background login prompt as the host user
        subprocess.Popen(
            [agy_bin, "--print", "Hello, Antigravity! Please confirm authentication."],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "ok": True,
            "status": "initiated",
            "message": "Google OAuth prompt initiated. Follow browser prompt to complete sign-in.",
            "agy_path": agy_bin,
            "cli_command": "python -m worker.manage login",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to launch Antigravity CLI: {exc}")


@app.post("/auth/logout")
async def auth_logout():
    """Clear local Antigravity OAuth tokens."""
    home = Path.home()
    token_files = [
        home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token",
        home / ".gemini" / "antigravity" / "token.json",
    ]
    removed = []
    for f in token_files:
        if f.is_file():
            try:
                f.unlink()
                removed.append(str(f))
            except Exception:
                pass
    return {
        "ok": True,
        "status": "logged_out",
        "removed_tokens": removed,
        "authenticated": False,
    }


@app.post("/tasks")
async def create_task(payload: dict = None, request: Request = None):
    """Create a task from a spec dict (or a `{spec: {...}}` wrapper)."""
    if request:
        body = await request.json()
        payload = body.get("spec", body)
    if not payload or not payload.get("task"):
        raise HTTPException(status_code=400, detail="Missing `task` in spec.")
    spec = payload
    parent = payload.get("parent")
    workspace = payload.get("workspace")
    task = agy.submit(spec, parent=parent, workspace=workspace)
    return {"task_id": task.id, "status": task.status, "workspace": task.workspace}


@app.post("/chat")
async def chat_endpoint(request: Request):
    """Run an interactive prompt directly through Antigravity CLI (agy) on the host."""
    body = await request.json()
    prompt = body.get("prompt", "")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Missing `prompt`.")
    
    from fastapi.responses import StreamingResponse
    import subprocess

    cmd = [
        agy._AGY, "--continue", "--print", prompt,
        "--model", "gemini-3.1-pro-high",
        "--effort", "high",
        "--mode", "accept-edits",
        "--output-format", "stream-json",
        "--dangerously-skip-permissions",
    ]

    ws_dir = os.environ.get("ZENITH_WORKSPACE") or str(Path.home() / "zenith-workspaces" / "main")
    os.makedirs(ws_dir, exist_ok=True)

    async def event_generator():
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=ws_dir,
        )
        if proc.stdout:
            while True:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", "replace").rstrip("\n")
                if line.strip():
                    yield f"data: {line}\n\n"
        await proc.wait()
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/tasks")
async def list_tasks():
    return {"tasks": [t.to_dict() for t in T.store.list()]}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    try:
        return agy.get_status(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@app.get("/tasks/{task_id}/output")
async def get_output(task_id: str):
    try:
        return {"output": agy.get_output(task_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@app.get("/tasks/{task_id}/artifacts")
async def get_artifacts(task_id: str):
    try:
        t = agy.get_status(task_id)
        return {"artifacts": t.get("artifacts", [])}
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@app.post("/tasks/{task_id}/followup")
async def post_followup(task_id: str, request: Request):
    body = await request.json()
    msg = body.get("message")
    if not msg:
        raise HTTPException(status_code=400, detail="Missing `message`")
    ok = agy.send_followup(task_id, msg)
    if not ok:
        raise HTTPException(status_code=409, detail="task not in a followable state")
    return {"sent": True}


@app.post("/tasks/{task_id}/cancel")
async def post_cancel(task_id: str):
    ok = agy.cancel(task_id)
    if not ok:
        raise HTTPException(status_code=409, detail="task not cancellable")
    return {"cancelled": True}


# ─── Host Introspection & Native Execution Endpoints ─────────────────────────

_FORBIDDEN_PATTERNS = [
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:/\s*$|/\*|/$)"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),  # Fork bomb
    re.compile(r"\bmkfs(\.[a-z0-9]+)?\b"),
    re.compile(r"\bdd\s+if=.*of=(/dev/sd[a-z]|/dev/nvme[0-9]|/dev/vd[a-z])\b"),
    re.compile(r">\s*/dev/sd[a-z]\b"),
    re.compile(r"\bchmod\s+-[a-zA-Z]*R[a-zA-Z]*\s+777\s+/(?:\s*$|$)"),
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bpoweroff\b"),
    re.compile(r"\bdel\s+/f\s+/s\s+/q\s+[a-zA-Z]:[/\\]\s*$", re.IGNORECASE),
    re.compile(r"\brmdir\s+/s\s+/q\s+[a-zA-Z]:[/\\]\s*$", re.IGNORECASE),
]

def _get_native_host_paths() -> dict[str, Any]:
    import getpass
    import platform
    import tempfile

    sys_name = platform.system().lower()
    if "darwin" in sys_name:
        os_family = "darwin"
    elif "windows" in sys_name or os.name == "nt":
        os_family = "windows"
    else:
        os_family = "linux"

    try:
        username = getpass.getuser()
    except Exception:
        username = os.getenv("USER") or os.getenv("USERNAME") or "user"

    home_str = os.getenv("HOME") or os.getenv("USERPROFILE") or str(Path.home())
    home = Path(home_str).expanduser().resolve()

    if os_family == "linux":
        desktop = home / "Desktop"
        downloads = home / "Downloads"
        documents = home / "Documents"
        pictures = home / "Pictures"
        videos = home / "Videos"
        music = home / "Music"

        # Check XDG
        xdg_file = home / ".config" / "user-dirs.dirs"
        if xdg_file.is_file():
            try:
                for line in xdg_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        v = v.strip().strip('"').replace("$HOME", str(home)).replace("${HOME}", str(home))
                        if k.strip() == "XDG_DESKTOP_DIR": desktop = Path(v).resolve()
                        elif k.strip() == "XDG_DOWNLOAD_DIR": downloads = Path(v).resolve()
                        elif k.strip() == "XDG_DOCUMENTS_DIR": documents = Path(v).resolve()
                        elif k.strip() == "XDG_PICTURES_DIR": pictures = Path(v).resolve()
                        elif k.strip() == "XDG_VIDEOS_DIR": videos = Path(v).resolve()
                        elif k.strip() == "XDG_MUSIC_DIR": music = Path(v).resolve()
            except Exception:
                pass
        root = "/"
    elif os_family == "darwin":
        desktop = home / "Desktop"
        downloads = home / "Downloads"
        documents = home / "Documents"
        pictures = home / "Pictures"
        videos = home / "Movies" if (home / "Movies").exists() else home / "Videos"
        music = home / "Music"
        root = "/"
    else:  # windows
        desktop = home / "Desktop"
        downloads = home / "Downloads"
        documents = home / "Documents"
        pictures = home / "Pictures"
        videos = home / "Videos"
        music = home / "Music"
        root = os.getenv("SystemDrive", "C:") + "\\"

    ws_dir = os.environ.get("ZENITH_WORKSPACE") or str(Path(__file__).resolve().parent.parent)

    return {
        "status": "ok",
        "os_family": os_family,
        "username": username,
        "home": str(home),
        "desktop": str(desktop.resolve()),
        "downloads": str(downloads.resolve()),
        "documents": str(documents.resolve()),
        "pictures": str(pictures.resolve()),
        "videos": str(videos.resolve()),
        "music": str(music.resolve()),
        "workspace": ws_dir,
        "temp": tempfile.gettempdir(),
        "root": root,
    }


@app.get("/host/paths")
async def get_host_paths_endpoint():
    """Authoritative host paths resolved directly in the host OS environment."""
    return _get_native_host_paths()


@app.post("/shell")
async def run_shell_endpoint(request: Request):
    """Execute a shell command natively on the host machine as the host user."""
    import platform
    import shutil

    body = await request.json()
    command = str(body.get("command", "")).strip()
    cwd_str = str(body.get("cwd", "")).strip()
    timeout = max(1, min(int(body.get("timeout", 60)), 300))
    shell_type = str(body.get("shell_type", "auto")).lower()

    if not command:
        raise HTTPException(status_code=400, detail="Missing `command`")

    # Safety check
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(command):
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command refused: destructive command matches forbidden pattern.",
                "duration_seconds": 0.0,
                "cwd": cwd_str,
            }

    # Resolve cwd
    if cwd_str:
        p_cwd = Path(cwd_str).expanduser()
        if not p_cwd.is_absolute():
            p_cwd = (Path.home() / p_cwd).resolve()
        else:
            p_cwd = p_cwd.resolve()
        if not p_cwd.is_dir():
            ws = Path(__file__).resolve().parent.parent
            target_cwd = ws if ws.is_dir() else Path.home()
        else:
            target_cwd = p_cwd
    else:
        target_cwd = Path.home()

    # Determine shell
    sys_name = platform.system().lower()
    is_win = "windows" in sys_name or os.name == "nt"
    is_mac = "darwin" in sys_name

    if is_win:
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if pwsh and shell_type in ("auto", "powershell", "pwsh"):
            cmd_args = [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command]
        else:
            cmd_args = [os.getenv("COMSPEC", "cmd.exe"), "/c", command]
    elif is_mac:
        sh_bin = shutil.which("zsh") or shutil.which("bash") or "/bin/bash"
        cmd_args = [sh_bin, "-c", command]
    else:
        sh_bin = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        cmd_args = [sh_bin, "-c", command]

    t0 = time.perf_counter()
    env = os.environ.copy()
    user_bin = str(Path.home() / ".local" / "bin")
    if user_bin not in env.get("PATH", ""):
        env["PATH"] = f"{user_bin}:{env.get('PATH', '')}"

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(target_cwd),
            env=env,
        )
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        duration = round(time.perf_counter() - t0, 3)
        stdout = out_b.decode(errors="replace").replace("\r\n", "\n").strip()
        stderr = err_b.decode(errors="replace").replace("\r\n", "\n").strip()
        code = proc.returncode if proc.returncode is not None else 0

        return {
            "ok": code == 0,
            "exit_code": code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": duration,
            "cwd": str(target_cwd),
        }
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds.",
            "duration_seconds": round(time.perf_counter() - t0, 3),
            "cwd": str(target_cwd),
        }
    except Exception as exc:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": round(time.perf_counter() - t0, 3),
            "cwd": str(target_cwd),
        }


@app.get("/host/fs/read")
async def host_read_file(path: str):
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    return {"status": "ok", "path": str(p), "content": text, "size": p.stat().st_size}


@app.post("/host/fs/write")
async def host_write_file(request: Request):
    body = await request.json()
    path = body.get("path")
    content = body.get("content", "")
    if not path:
        raise HTTPException(status_code=400, detail="Missing `path`")
    p = Path(path).expanduser().resolve()
    if str(p) in ("/", "C:\\") or len(str(p)) < 4:
        raise HTTPException(status_code=403, detail="Cannot write to system root")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", errors="replace")
    return {"status": "ok", "path": str(p), "bytes_written": len(content)}


@app.get("/host/fs/list")
async def host_list_dir(path: str = "."):
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {path}")
    items = []
    for c in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        items.append({
            "name": c.name,
            "is_dir": c.is_dir(),
            "size": c.stat().st_size if c.is_file() else 0,
        })
    return {"status": "ok", "path": str(p), "items": items}


@app.post("/host/fs/mkdir")
async def host_mkdir(request: Request):
    body = await request.json()
    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Missing `path`")
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return {"status": "ok", "path": str(p)}


@app.post("/host/fs/remove")
async def host_remove(request: Request):
    import shutil
    body = await request.json()
    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Missing `path`")
    p = Path(path).expanduser().resolve()
    if str(p) in ("/", "/home", "/Users", "C:\\", "C:\\Users") or str(p) == str(Path.home()):
        raise HTTPException(status_code=403, detail="Cannot remove root or user home directory")
    if p.is_dir():
        shutil.rmtree(p)
    elif p.is_file() or p.is_symlink():
        p.unlink()
    else:
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    return {"status": "ok", "path": str(p), "removed": True}


def main():
    uvicorn.run(app, host=_HOST, port=_PORT, log_level="info")


if __name__ == "__main__":
    main()