"""Cross-platform process manager and setup orchestrator for Zenith Antigravity Worker.

Usage:
    python -m worker.manage start
    python -m worker.manage stop
    python -m worker.manage restart
    python -m worker.manage status
    python -m worker.manage install-agy
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PID_FILE = DATA_DIR / "worker.pid"
LOG_FILE = DATA_DIR / "worker.log"
PORT = int(os.environ.get("ZENITH_WORKER_PORT", "8022"))
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"


def is_worker_alive() -> bool:
    """Check if the worker HTTP endpoint is actively responding."""
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "Zenith-Manager"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_pid_by_port(port: int = PORT) -> int | None:
    """Attempt to find PID of the process listening on the target port."""
    if os.name == "nt":
        try:
            out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    return int(parts[-1])
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True)
            for line in out.splitlines():
                if line.strip().isdigit():
                    return int(line.strip())
        except Exception:
            pass
    return None


def get_worker_pid() -> int | None:
    """Read saved PID from data/worker.pid or resolve by port."""
    if PID_FILE.is_file():
        try:
            content = PID_FILE.read_text(encoding="utf-8").strip()
            pid = int(content)
            if is_pid_running(pid):
                return pid
        except (ValueError, OSError):
            pass
    if is_worker_alive():
        return find_pid_by_port(PORT)
    return None


def is_pid_running(pid: int) -> bool:
    """Check if a process with given PID exists."""
    if pid <= 0:
        return False
    if os.name == "nt":
        # Windows tasklist check
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return str(pid) in out
        except Exception:
            return False
    else:
        # Unix kill 0 check
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def resolve_python() -> str:
    """Find the preferred Python binary (worker/.venv or sys.executable)."""
    is_win = os.name == "nt"
    venv_py = PROJECT_ROOT / "worker" / ".venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python")
    if venv_py.is_file() and os.access(venv_py, os.X_OK if not is_win else os.F_OK):
        return str(venv_py)
    
    root_venv_py = PROJECT_ROOT / ".venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python")
    if root_venv_py.is_file() and os.access(root_venv_py, os.X_OK if not is_win else os.F_OK):
        return str(root_venv_py)
        
    return sys.executable


def install_antigravity_cli() -> bool:
    """Automatically download and install Google Antigravity CLI (agy)."""
    print("[worker.manage] Checking for Antigravity CLI (agy)...")
    found = shutil.which("agy") or shutil.which("antigravity")
    if found:
        print(f"[worker.manage] Antigravity CLI already installed at: {found}")
        return True

    home = Path.home()
    is_win = os.name == "nt"
    
    # Check fallback paths
    candidates = [
        home / ".local" / "bin" / ("agy.exe" if is_win else "agy"),
        home / "AppData" / "Local" / "agy" / "bin" / "agy.exe",
    ]
    for c in candidates:
        if c.is_file():
            print(f"[worker.manage] Found Antigravity CLI at: {c}")
            return True

    print("[worker.manage] agy binary not found. Downloading official installer...")
    try:
        if is_win:
            # Windows PowerShell installation
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://antigravity.google/cli/install.ps1 | iex"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                print("[worker.manage] agy CLI installed successfully on Windows.")
                return True
            else:
                print(f"[worker.manage] Warning: PowerShell install returned {res.returncode}: {res.stderr.strip()[:200]}")
        else:
            # Linux / macOS bash installation
            sh_code = "curl -fsSL https://antigravity.google/cli/install.sh | bash"
            res = subprocess.run(["bash", "-c", sh_code], capture_output=True, text=True)
            if res.returncode == 0:
                print("[worker.manage] agy CLI installed successfully on Unix.")
                return True
            else:
                print(f"[worker.manage] Warning: Bash install returned {res.returncode}: {res.stderr.strip()[:200]}")
    except Exception as exc:
        print(f"[worker.manage] Installation attempt error: {exc}")

    return False


def start_worker() -> int:
    """Start the worker daemon in the background."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if is_worker_alive():
        pid = get_worker_pid()
        print(f"[worker.manage] Worker is already online on port {PORT}" + (f" (PID {pid})" if pid else ""))
        return 0

    py_exe = resolve_python()
    cmd = [py_exe, "-m", "worker.peacant"]
    print(f"[worker.manage] Spawning worker: {' '.join(cmd)} (logging to {LOG_FILE})")

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    # Ensure standard user bin path is in PATH
    home = str(Path.home())
    if os.name != "nt":
        user_bin = f"{home}/.local/bin"
        if user_bin not in env.get("PATH", ""):
            env["PATH"] = f"{user_bin}:{env.get('PATH', '')}"

    log_fh = open(LOG_FILE, "a", encoding="utf-8")
    
    creation_flags = 0
    start_new_session = True
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        start_new_session = False

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=creation_flags,
            start_new_session=start_new_session,
        )
        PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        print(f"[worker.manage] Process launched with PID {proc.pid}. Waiting for healthcheck...")
    except Exception as exc:
        print(f"[worker.manage] Failed to launch worker: {exc}")
        return 1

    # Wait up to 6 seconds for healthcheck
    deadline = time.time() + 6.0
    while time.time() < deadline:
        time.sleep(0.4)
        if is_worker_alive():
            print(f"[worker.manage] Worker is healthy and responsive at http://127.0.0.1:{PORT}/health")
            return 0
        if not is_pid_running(proc.pid):
            print(f"[worker.manage] Error: Worker process {proc.pid} exited prematurely. Check {LOG_FILE}:")
            try:
                log_lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-10:]
                print("\n".join(log_lines))
            except Exception:
                pass
            return 1

    print(f"[worker.manage] Notice: Worker started (PID {proc.pid}), but healthcheck timed out after 6s.")
    return 0


def stop_worker() -> int:
    """Stop the running worker daemon."""
    pid = get_worker_pid()
    stopped = False

    if pid and is_pid_running(pid):
        print(f"[worker.manage] Stopping worker process PID {pid}...")
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
                # Give it up to 2 seconds to terminate gracefully
                for _ in range(20):
                    time.sleep(0.1)
                    if not is_pid_running(pid):
                        break
                else:
                    os.kill(pid, signal.SIGKILL)
            stopped = True
        except Exception as exc:
            print(f"[worker.manage] Error stopping PID {pid}: {exc}")

    if PID_FILE.is_file():
        try:
            PID_FILE.unlink()
        except Exception:
            pass

    if is_worker_alive():
        port_pid = find_pid_by_port(PORT)
        if port_pid and is_pid_running(port_pid):
            print(f"[worker.manage] Reclaiming port {PORT} by terminating process PID {port_pid}...")
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(port_pid)], capture_output=True)
                else:
                    os.kill(port_pid, signal.SIGKILL)
                time.sleep(0.5)
            except Exception:
                pass

    if is_worker_alive():
        print(f"[worker.manage] Warning: Port {PORT} is still occupied by an active process.")
        return 1

    print("[worker.manage] Worker stopped successfully.")
    return 0


def status_worker() -> int:
    """Inspect and report worker status."""
    alive = is_worker_alive()
    pid = get_worker_pid()
    pid_running = is_pid_running(pid) if pid else False

    home = Path.home()
    token_files = [
        home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token",
        home / ".gemini" / "antigravity" / "token.json",
        home / ".gemini" / "credentials.json",
    ]
    is_auth = any(f.is_file() and f.stat().st_size > 0 for f in token_files)

    data = {
        "online": alive,
        "port": PORT,
        "pid": pid if pid_running else None,
        "health_url": HEALTH_URL,
        "agy_installed": bool(shutil.which("agy") or shutil.which("antigravity")),
        "authenticated": is_auth,
    }
    print(json.dumps(data, indent=2))
    return 0 if alive else 3


def login_worker() -> int:
    """Trigger one-time interactive Google sign-in with Antigravity CLI."""
    agy_path = shutil.which("agy") or shutil.which("antigravity")
    if not agy_path:
        home = Path.home()
        is_win = os.name == "nt"
        candidates = [
            home / ".local" / "bin" / ("agy.exe" if is_win else "agy"),
            home / "AppData" / "Local" / "agy" / "bin" / "agy.exe",
        ]
        for c in candidates:
            if c.is_file():
                agy_path = str(c)
                break

    if not agy_path:
        print("[worker.manage] Antigravity CLI is not installed yet. Installing...")
        if not install_antigravity_cli():
            print("[worker.manage] Failed to install Antigravity CLI.")
            return 1
        agy_path = shutil.which("agy") or shutil.which("antigravity") or "agy"

    print(f"[worker.manage] Launching Antigravity CLI for interactive Google sign-in...")
    print("Please follow the on-screen browser prompt to sign in with your Google account.\n")
    try:
        res = subprocess.run([agy_path, "--print", "Hello, Antigravity! Please confirm authentication."], check=False)
        return res.returncode
    except Exception as exc:
        print(f"[worker.manage] Error running agy: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Zenith Antigravity Worker Manager")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "install-agy", "login"], help="Action to perform")
    args = parser.parse_args()

    if args.action == "start":
        return start_worker()
    elif args.action == "stop":
        return stop_worker()
    elif args.action == "restart":
        stop_worker()
        time.sleep(0.5)
        return start_worker()
    elif args.action == "status":
        return status_worker()
    elif args.action == "install-agy":
        return 0 if install_antigravity_cli() else 1
    elif args.action == "login":
        return login_worker()
    return 0


if __name__ == "__main__":
    sys.exit(main())
