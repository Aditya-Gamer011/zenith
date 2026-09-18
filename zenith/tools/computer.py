"""Computer control: safe cross-platform shell execution (opt-in via ALLOW_SHELL), file IO, dir listing.

Operates as a full AI coding agent execution engine:
- Cross-platform command execution across Linux (bash/sh), macOS (zsh/bash), and Windows (PowerShell/cmd).
- Stateful working directory (cwd) tracking across commands and cd navigation.
- Structured execution feedback: command, cwd, shell used, exit code, execution time, stdout, stderr.
- Session command history buffer so the agent knows what commands it ran, what happened, and what to run next.
- Safe defaults and refusal for destructive commands across all supported operating systems.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import shutil
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.config import settings
from ..core.sandbox import sandbox

MAX_READ = 20_000
MAX_WRITE = 40_000

# Commands Zenith must never run, even with ALLOW_SHELL=yes (Linux, macOS, Windows).
FORBIDDEN_PATTERNS = [
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:/(?:\s|$|\*|;)|~(?:\s|$|\*|;)|\$HOME(?:\s|$|/\*|;))"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
    re.compile(r"\bmkfs(\.[a-z0-9]+)?\b"),
    re.compile(r"\bdd\s+if=.*of=(/dev/sd[a-z]|/dev/nvme[0-9]|/dev/vd[a-z])\b"),
    re.compile(r">\s*/dev/sd[a-z]\b"),
    re.compile(r"\bchmod\s+-[a-zA-Z]*R[a-zA-Z]*\s+777\s+(?:/(?:\s|$|\*|;)|~(?:\s|$|\*|;))"),
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bpoweroff\b"),
    re.compile(r"\bdel\s+/f\s+/s\s+/q\s+[a-zA-Z]:[/\\]\s*$", re.IGNORECASE),
    re.compile(r"\brmdir\s+/s\s+/q\s+[a-zA-Z]:[/\\]\s*$", re.IGNORECASE),
    re.compile(r"\bremove-item\s+-recurse\s+-force\s+[a-zA-Z]:[/\\]\s*$", re.IGNORECASE),
]

# Stateful working directory tracked across commands in the active session
_ACTIVE_CWD: Path = (
    settings.workspace_dir.resolve()
    if settings.workspace_dir.exists()
    else Path.cwd().resolve()
)

# Session command history buffer (keeps the last 50 executed commands)
@dataclass
class CommandEntry:
    command: str
    cwd: str
    os_family: str
    shell_name: str
    exit_code: int
    status: str
    duration_seconds: float
    timestamp: str
    stdout_preview: str
    stderr_preview: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "os": self.os_family,
            "shell": self.shell_name,
            "exit_code": self.exit_code,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "stdout_preview": self.stdout_preview,
            "stderr_preview": self.stderr_preview,
        }


_COMMAND_HISTORY: deque[CommandEntry] = deque(maxlen=50)


def _unsafe(command: str) -> bool:
    for pat in FORBIDDEN_PATTERNS:
        if pat.search(command):
            return True
    safe, _ = sandbox.is_command_safe(command)
    return not safe


def get_active_cwd() -> Path:
    """Get the current tracked working directory."""
    global _ACTIVE_CWD
    if not _ACTIVE_CWD.exists():
        _ACTIVE_CWD = settings.workspace_dir if settings.workspace_dir.exists() else Path.cwd()
    return _ACTIVE_CWD


def set_active_cwd(path: str | Path) -> str:
    """Set the active working directory for future commands."""
    global _ACTIVE_CWD
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (_ACTIVE_CWD / p).resolve()
    else:
        p = p.resolve()

    if not p.is_dir():
        return f"[error] Not a directory: {path}"
    _ACTIVE_CWD = p
    return f"Working directory set to: {_ACTIVE_CWD}"


def get_command_history(limit: int = 10) -> list[dict[str, Any]]:
    """Return the recent command history list."""
    history = list(_COMMAND_HISTORY)
    limit = max(1, min(limit, len(history)))
    return [entry.to_dict() for entry in history[-limit:]]


def format_command_history(limit: int = 10) -> str:
    """Format recent commands for display or prompt injection."""
    history = list(_COMMAND_HISTORY)
    if not history:
        return "No commands executed in this session yet."
    limit = max(1, min(limit, len(history)))
    items = history[-limit:]
    lines = [f"# Recent Command History ({len(items)} commands):"]
    for idx, entry in enumerate(items, 1):
        status_label = "SUCCESS" if entry.exit_code == 0 else f"FAILED ({entry.exit_code})"
        lines.append(
            f"{idx}. [{entry.timestamp}] $ {entry.command} -> {status_label} "
            f"({entry.duration_seconds:.2f}s, cwd: {entry.cwd})"
        )
        if entry.stderr_preview:
            lines.append(f"   [stderr preview] {entry.stderr_preview.splitlines()[0][:100]}")
    return "\n".join(lines)


def _resolve_shell_for_os(shell_type: str = "auto") -> tuple[str, list[str]]:
    """Determine executable and prefix arguments based on OS and shell preference.

    Returns:
        (shell_name, [executable, ...flags])
    """
    sys_name = platform.system().lower()
    is_win = "windows" in sys_name
    is_mac = "darwin" in sys_name

    shell_type = (shell_type or "auto").strip().lower()

    if shell_type == "powershell" or shell_type == "pwsh":
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        return "powershell", [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]

    if shell_type == "cmd":
        cmd_exe = os.getenv("COMSPEC", "cmd.exe")
        return "cmd", [cmd_exe, "/c"]

    if shell_type == "zsh":
        zsh = shutil.which("zsh") or "/bin/zsh"
        return "zsh", [zsh, "-c"]

    if shell_type == "bash":
        bash = shutil.which("bash") or "/bin/bash"
        return "bash", [bash, "-c"]

    if shell_type == "sh":
        sh = shutil.which("sh") or "/bin/sh"
        return "sh", [sh, "-c"]

    # Auto-detection
    if is_win:
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if pwsh:
            return "powershell", [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]
        cmd_exe = os.getenv("COMSPEC", "cmd.exe")
        return "cmd", [cmd_exe, "/c"]

    if is_mac:
        zsh = shutil.which("zsh") or "/bin/zsh"
        if Path(zsh).exists() or shutil.which("zsh"):
            return "zsh", [zsh, "-c"]
        bash = shutil.which("bash") or "/bin/bash"
        return "bash", [bash, "-c"]

    # Linux / other Unix
    bash = shutil.which("bash") or "/bin/bash"
    if Path(bash).exists() or shutil.which("bash"):
        return "bash", [bash, "-c"]
    return "sh", [shutil.which("sh") or "/bin/sh", "-c"]


async def run_shell(
    command: str,
    cwd: str = "",
    timeout: int = 60,
    shell_type: str = "auto",
    max_output: int = 4000,
) -> str:
    """Run a shell command with full cross-platform support (Linux, macOS, Windows).

    Returns structured agentic feedback:
    - Command executed
    - Active working directory (cwd)
    - Operating system and shell used
    - Exit code (SUCCESS / FAILED)
    - Execution duration
    - Standard Output (stdout)
    - Standard Error (stderr)
    - Records the command in session history
    """
    global _ACTIVE_CWD

    if not settings.allow_shell:
        return "Shell is disabled (ALLOW_SHELL=no). Enable in .env to allow shell commands."

    if _unsafe(command):
        record = CommandEntry(
            command=command,
            cwd=str(get_active_cwd()),
            os_family=platform.system().lower(),
            shell_name="refused",
            exit_code=-1,
            status="REFUSED",
            duration_seconds=0.0,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            stdout_preview="",
            stderr_preview="Command is on Zenith's no-go list.",
        )
        _COMMAND_HISTORY.append(record)
        return (
            f"$ {command}\n"
            f"[cwd: {get_active_cwd()}] [os: {platform.system().lower()}] [exit: -1 (REFUSED)]\n"
            f"[refused: that command is on Zenith's no-go safety list.]"
        )

    # Resolve working directory with host path expansion
    from .host_paths import is_container, _get_worker_url, resolve_host_path

    target_cwd = get_active_cwd()
    if cwd and cwd.strip():
        resolved_cwd = resolve_host_path(cwd.strip())
        p = Path(resolved_cwd).expanduser()
        if not p.is_absolute():
            p = (target_cwd / p).resolve()
        else:
            p = p.resolve()
        target_cwd = p

    # Handle pure cd commands: update _ACTIVE_CWD statefully
    clean_cmd = command.strip()
    cd_match = re.match(r"^cd\s+(.+)$", clean_cmd)
    if cd_match:
        target_dir = cd_match.group(1).strip().strip('"').strip("'")
        resolved_target = resolve_host_path(target_dir) if target_dir != "~" else str(Path.home())
        if resolved_target == "~":
            new_path = Path.home()
        elif resolved_target.startswith("~/"):
            new_path = Path.home() / resolved_target[2:]
        else:
            p_target = Path(resolved_target)
            new_path = p_target if p_target.is_absolute() else (target_cwd / p_target).resolve()

        t0 = time.perf_counter()
        if new_path.is_dir():
            _ACTIVE_CWD = new_path
            dur = time.perf_counter() - t0
            record = CommandEntry(
                command=command,
                cwd=str(_ACTIVE_CWD),
                os_family=platform.system().lower(),
                shell_name="builtin_cd",
                exit_code=0,
                status="SUCCESS",
                duration_seconds=round(dur, 4),
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                stdout_preview=f"Changed directory to {_ACTIVE_CWD}",
                stderr_preview="",
            )
            _COMMAND_HISTORY.append(record)
            return (
                f"$ {command}\n"
                f"[cwd: {_ACTIVE_CWD}] [os: {platform.system().lower()}] [exit: 0 (SUCCESS)] [duration: {dur:.2f}s]\n"
                f"Changed active working directory to {_ACTIVE_CWD}"
            )
        else:
            dur = time.perf_counter() - t0
            record = CommandEntry(
                command=command,
                cwd=str(target_cwd),
                os_family=platform.system().lower(),
                shell_name="builtin_cd",
                exit_code=1,
                status="FAILED",
                duration_seconds=round(dur, 4),
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                stdout_preview="",
                stderr_preview=f"Directory not found: {target_dir}",
            )
            _COMMAND_HISTORY.append(record)
            return (
                f"$ {command}\n"
                f"[cwd: {target_cwd}] [os: {platform.system().lower()}] [exit: 1 (FAILED)] [duration: {dur:.2f}s]\n"
                f"[stderr]\nDirectory not found: {target_dir}"
            )

    # When running inside a container, delegate directly to the host worker
    # so commands execute on the real host machine with the user's real environment.
    if is_container():
        worker_url = _get_worker_url()
        try:
            from .host_paths import get_host_paths
            hp = get_host_paths()
            host_workspace = hp.get("workspace", "")
            host_home = hp.get("home", "")
            host_cwd_str = str(target_cwd) if target_cwd else ""
            if host_cwd_str.startswith("/app"):
                host_cwd_str = host_cwd_str.replace("/app", host_workspace) if host_workspace else ""
            elif host_cwd_str.startswith("/home/zenith"):
                host_cwd_str = host_cwd_str.replace("/home/zenith", host_home) if host_home else ""

            payload = json.dumps({
                "command": command,
                "cwd": host_cwd_str,
                "timeout": timeout,
                "shell_type": shell_type,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{worker_url}/shell",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Zenith-Computer"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout + 5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    code = data.get("exit_code", 0)
                    out = data.get("stdout", "")
                    err = data.get("stderr", "")
                    dur = data.get("duration_seconds", 0.0)
                    host_cwd = data.get("cwd", str(target_cwd))
                    if host_cwd:
                        try:
                            _ACTIVE_CWD = Path(host_cwd)
                        except Exception:
                            pass
                    out = sandbox.redact_secrets(out)
                    err = sandbox.redact_secrets(err)
                    status_text = "SUCCESS" if code == 0 else "FAILED"

                    # Handle output truncation cleanly
                    raw_out_len = len(out)
                    raw_err_len = len(err)
                    if raw_out_len > max_output:
                        out = out[-max_output:] + f"\n... [stdout truncated: showing last {max_output} characters of {raw_out_len} total]"
                    if raw_err_len > max_output:
                        err = err[-max_output:] + f"\n... [stderr truncated: showing last {max_output} characters of {raw_err_len} total]"

                    os_family_label = hp.get("os_family", "linux")
                    record = CommandEntry(
                        command=command,
                        cwd=str(host_cwd),
                        os_family=os_family_label,
                        shell_name="host_worker",
                        exit_code=code,
                        status=status_text,
                        duration_seconds=round(dur, 3),
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                        stdout_preview=out[:200] if out else "",
                        stderr_preview=err[:200] if err else "",
                    )
                    _COMMAND_HISTORY.append(record)

                    lines = [
                        f"$ {command}",
                        f"[cwd: {host_cwd}] [os: {os_family_label} (host_worker)] [host execution: SUCCESS] [exit: {code} ({status_text})] [duration: {dur:.2f}s]",
                    ]
                    if out:
                        lines.append("--- stdout ---")
                        lines.append(out)
                    if err:
                        lines.append("--- stderr ---")
                        lines.append(err)
                    if not out and not err:
                        lines.append("[no output produced]")
                    return "\n".join(lines)
        except Exception as w_exc:
            log.warning("Host worker shell execution failed: %s", w_exc)

    # Timebox: allow up to 300 seconds for builds, installs, or test suites
    timeout = max(1, min(timeout or 60, 300))
    shell_name, shell_args = _resolve_shell_for_os(shell_type)
    full_args = shell_args + [command]

    os_family = platform.system().lower()
    t0 = time.perf_counter()

    try:
        # Cross-platform environment with PATH preserved
        env = os.environ.copy()

        try:
            proc = await asyncio.create_subprocess_exec(
                *full_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(target_cwd),
                env=env,
            )
        except (FileNotFoundError, PermissionError):
            # Fallback to asyncio.create_subprocess_shell if direct shell exec fails
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(target_cwd),
                env=env,
            )

        out_bytes, err_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        duration = time.perf_counter() - t0

        out = out_bytes.decode(errors="replace").replace("\r\n", "\n").strip()
        err = err_bytes.decode(errors="replace").replace("\r\n", "\n").strip()
        out = sandbox.redact_secrets(out)
        err = sandbox.redact_secrets(err)
        code = proc.returncode if proc.returncode is not None else 0

        # Handle output truncation cleanly
        raw_out_len = len(out)
        raw_err_len = len(err)
        if raw_out_len > max_output:
            out = out[-max_output:] + f"\n... [stdout truncated: showing last {max_output} characters of {raw_out_len} total]"
        if raw_err_len > max_output:
            err = err[-max_output:] + f"\n... [stderr truncated: showing last {max_output} characters of {raw_err_len} total]"

        status_text = "SUCCESS" if code == 0 else "FAILED"

        # Record in history
        record = CommandEntry(
            command=command,
            cwd=str(target_cwd),
            os_family=os_family,
            shell_name=shell_name,
            exit_code=code,
            status=status_text,
            duration_seconds=round(duration, 3),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            stdout_preview=out[:200] if out else "",
            stderr_preview=err[:200] if err else "",
        )
        _COMMAND_HISTORY.append(record)

        # Build clean structured output
        lines = [
            f"$ {command}",
            f"[cwd: {target_cwd}] [os: {os_family} ({shell_name})] [exit: {code} ({status_text})] [duration: {duration:.2f}s]",
        ]
        if out:
            lines.append("--- stdout ---")
            lines.append(out)
        if err:
            lines.append("--- stderr ---")
            lines.append(err)
        if not out and not err:
            lines.append("[no output produced]")

        return "\n".join(lines)

    except asyncio.TimeoutError:
        duration = time.perf_counter() - t0
        try:
            proc.kill()
        except Exception:
            pass

        record = CommandEntry(
            command=command,
            cwd=str(target_cwd),
            os_family=os_family,
            shell_name=shell_name,
            exit_code=-1,
            status="TIMEOUT",
            duration_seconds=round(duration, 3),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            stdout_preview="",
            stderr_preview=f"Command timed out after {timeout}s",
        )
        _COMMAND_HISTORY.append(record)

        return (
            f"$ {command}\n"
            f"[cwd: {target_cwd}] [os: {os_family} ({shell_name})] [exit: -1 (TIMEOUT)] [duration: {duration:.2f}s]\n"
            f"[error: command timed out after {timeout} seconds]"
        )

    except Exception as exc:
        duration = time.perf_counter() - t0
        record = CommandEntry(
            command=command,
            cwd=str(target_cwd),
            os_family=os_family,
            shell_name=shell_name,
            exit_code=-1,
            status="ERROR",
            duration_seconds=round(duration, 3),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            stdout_preview="",
            stderr_preview=str(exc),
        )
        _COMMAND_HISTORY.append(record)

        return (
            f"$ {command}\n"
            f"[cwd: {target_cwd}] [os: {os_family} ({shell_name})] [exit: -1 (ERROR)] [duration: {duration:.2f}s]\n"
            f"[error: {exc}]"
        )


async def read_file(path: str, raw: bool = False) -> str:
    """Read a text file (supports absolute or cwd-relative paths). Wrapped in untrusted_content tags for injection safety unless raw=True."""
    try:
        from .host_paths import is_container, _get_worker_url, resolve_host_path, is_host_path
        resolved_path = resolve_host_path(path)
        p = Path(resolved_path).expanduser()
        if not p.is_absolute():
            p = (get_active_cwd() / p).resolve()
        else:
            p = p.resolve()

        # Sovereign Sandbox protection (MUST run before reading)
        blocked, reason = sandbox.is_path_protected(p, operation="read")
        if blocked:
            return f"[sandbox violation] Access to protected path is blocked: {reason}"
        sym_safe, sym_reason = sandbox.is_symlink_safe(p)
        if not sym_safe:
            return f"[sandbox violation] {sym_reason}"

        # If in container and file targets host (or does not exist locally), try reading via host worker
        if is_container() and (is_host_path(p) or not p.is_file()):
            try:
                import urllib.request
                import urllib.parse
                url = f"{_get_worker_url()}/host/fs/read?path={urllib.parse.quote(str(p))}"
                req = urllib.request.Request(url, headers={"User-Agent": "Zenith-Computer"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        text = data.get("content", "")
                        if len(text) > MAX_READ:
                            text = text[:MAX_READ] + f"\n... [truncated, file is {data.get('size', len(text))} bytes]"
                        if not raw:
                            from .swe_engine import wrap_untrusted_content
                            return wrap_untrusted_content(text, source=Path(path).name)
                        return text
            except Exception:
                pass

        if not p.is_file():
            return f"[error] Not a file: {path} (resolved: {p})"
        text = p.read_text(errors="replace")
        if len(text) > MAX_READ:
            text = text[:MAX_READ] + f"\n... [truncated, file is {p.stat().st_size} bytes]"
        if not raw:
            from .swe_engine import wrap_untrusted_content
            return wrap_untrusted_content(text, source=p.name)
        return text
    except Exception as exc:
        return f"[error] {exc}"


async def write_file(path: str, content: str) -> str:
    """Write (or overwrite) a text file at a specified path."""
    try:
        from .host_paths import is_container, _get_worker_url, resolve_host_path, is_host_path
        resolved_path = resolve_host_path(path)
        p = Path(resolved_path).expanduser()
        if not p.is_absolute():
            p = (get_active_cwd() / p).resolve()
        else:
            p = p.resolve()

        # Sovereign Sandbox protection (MUST run before writing)
        blocked, reason = sandbox.is_path_protected(p, operation="write")
        if blocked:
            return f"[sandbox violation] Write to protected path is blocked: {reason}"
        sym_safe, sym_reason = sandbox.is_symlink_safe(p)
        if not sym_safe:
            return f"[sandbox violation] {sym_reason}"

        # If running in container and path targets host, write via worker so host desktop/documents are written natively
        if is_container() and is_host_path(p):
            try:
                import urllib.request
                payload = json.dumps({"path": str(p), "content": content}).encode("utf-8")
                req = urllib.request.Request(
                    f"{_get_worker_url()}/host/fs/write",
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "Zenith-Computer"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    if resp.status == 200:
                        return f"Wrote {len(content)} bytes to host path: {p}"
            except Exception:
                pass

        if len(content) > MAX_WRITE:
            content = content[:MAX_WRITE]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, errors="replace")
        return f"Wrote {len(content)} bytes to {p}"
    except Exception as exc:
        return f"[error] {exc}"


async def list_dir(path: str = ".") -> str:
    """List directory contents with sizes and type annotations."""
    try:
        from .host_paths import is_container, _get_worker_url, resolve_host_path, is_host_path
        resolved_path = resolve_host_path(path) if path != "." else "."
        p = Path(resolved_path).expanduser()
        if not p.is_absolute():
            p = (get_active_cwd() / p).resolve()
        else:
            p = p.resolve()

        # Sovereign Sandbox protection (MUST run before listing)
        blocked, reason = sandbox.is_path_protected(p, operation="read")
        if blocked:
            return f"[sandbox violation] Access to protected path is blocked: {reason}"
        sym_safe, sym_reason = sandbox.is_symlink_safe(p)
        if not sym_safe:
            return f"[sandbox violation] {sym_reason}"

        # If in container and path targets host (or directory does not exist locally), query host worker
        if is_container() and (is_host_path(p) or not p.is_dir()):
            try:
                import urllib.request
                import urllib.parse
                url = f"{_get_worker_url()}/host/fs/list?path={urllib.parse.quote(str(p))}"
                req = urllib.request.Request(url, headers={"User-Agent": "Zenith-Computer"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        items = data.get("items", [])
                        lines = [f"Directory listing for host path: {p}"]
                        for it in items:
                            if it.get("is_dir"):
                                lines.append(f"  [dir]  {it['name']}/")
                            else:
                                lines.append(f"         {it['name']}  ({it.get('size', 0)} B)")
                        if len(lines) == 1:
                            return f"Directory listing for host path: {p}\n(empty directory)"
                        return "\n".join(lines)
            except Exception:
                pass

        if not p.is_dir():
            return f"[error] Not a directory: {path} (resolved: {p})"
        lines = [f"Directory listing for: {p}"]
        for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
            if child.is_dir():
                lines.append(f"  [dir]  {child.name}/")
            elif child.is_file():
                lines.append(f"         {child.name}  ({child.stat().st_size} B)")
            else:
                lines.append(f"  [sym]  {child.name}")
        if len(lines) == 1:
            return f"Directory listing for: {p}\n(empty directory)"
        return "\n".join(lines)
    except Exception as exc:
        return f"[error] {exc}"


async def get_cwd() -> str:
    """Get active working directory string."""
    return str(get_active_cwd())