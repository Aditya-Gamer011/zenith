"""Local Git & Developer Suite tool — repository status, log, diff, branch management, and port inspection."""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from ..core.config import settings


def _resolve_repo(repo_path: str = "") -> Path:
    if not repo_path:
        return settings.workspace_dir if settings.workspace_dir.exists() else Path.cwd()
    p = Path(repo_path).expanduser().resolve()
    return p if p.is_dir() else settings.workspace_dir


_get_cwd = _resolve_repo


async def _run_blocking(cmd: list[str], *, timeout: int, cwd: Path | str | None = None, shell: bool = False) -> subprocess.CompletedProcess:
    """Run a blocking subprocess OFF the event loop.

    A synchronous subprocess.run in an async handler blocks the ENTIRE loop
    (chat, voice, scheduler). asyncio.to_thread keeps the loop free.
    """
    return await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True, timeout=timeout,
        cwd=cwd, shell=shell,
    )


async def _run_git(args: list[str], cwd: Path) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode(errors="replace").strip()
    except Exception as exc:
        return f"[git error] {exc}"



async def git_status(repo_path: str = "") -> str:
    """Git status + branch info for a repository directory."""
    path = _resolve_repo(repo_path)
    if not (path / ".git").exists():
        return f"[git] Not a git repository: {path}"
    try:
        proc = await _run_blocking(["git", "status", "-sb"], timeout=10, cwd=path)
        return proc.stdout.strip() or "(clean working tree)"
    except Exception as exc:
        return f"[git error] {exc}"


async def git_log(repo_path: str = "", limit: int = 10) -> str:
    """Recent commit history for a repository."""
    path = _resolve_repo(repo_path)
    if not (path / ".git").exists():
        return f"[git] Not a git repository: {path}"
    try:
        proc = await _run_blocking(
            ["git", "log", f"-n{min(limit, 30)}", "--pretty=format:%h - %an (%cr): %s"],
            timeout=10, cwd=path,
        )
        return proc.stdout.strip() or "(no commits)"
    except Exception as exc:
        return f"[git error] {exc}"


async def git_diff(repo_path: str = "", file_path: str = "") -> str:
    """Git diff for staged/unstaged changes."""
    path = _resolve_repo(repo_path)
    if not (path / ".git").exists():
        return f"[git] Not a git repository: {path}"
    cmd = ["git", "diff"]
    if file_path:
        cmd.append(file_path)
    try:
        proc = await _run_blocking(cmd, timeout=15, cwd=path)
        out = proc.stdout.strip()
        if not out:
            # Check staged diff
            proc_staged = await _run_blocking(
                ["git", "diff", "--staged", *( [file_path] if file_path else [] )],
                timeout=15, cwd=path,
            )
            out = proc_staged.stdout.strip()
        return out[:4000] if out else "(no uncommitted changes)"
    except Exception as exc:
        return f"[git error] {exc}"


async def git_branch(action: str, repo_path: str = "", branch_name: str = "") -> str:
    """Manage local git branches (action: 'list' | 'checkout' | 'create')."""
    path = _resolve_repo(repo_path)
    if not (path / ".git").exists():
        return f"[git] Not a git repository: {path}"
    act = (action or "list").lower()

    if act == "list":
        try:
            proc = await _run_blocking(["git", "branch", "-a"], timeout=10, cwd=path)
            return proc.stdout.strip() or "(no branches)"
        except Exception as exc:
            return f"[git error] {exc}"

    if act == "checkout":
        if not branch_name:
            return "[git] Provide a branch_name to checkout."
        try:
            proc = await _run_blocking(["git", "checkout", branch_name], timeout=15, cwd=path)
            return (proc.stdout + "\n" + proc.stderr).strip()
        except Exception as exc:
            return f"[git error] {exc}"

    if act == "create":
        if not branch_name:
            return "[git] Provide a branch_name to create."
        try:
            proc = await _run_blocking(["git", "checkout", "-b", branch_name], timeout=15, cwd=path)
            return (proc.stdout + "\n" + proc.stderr).strip()
        except Exception as exc:
            return f"[git error] {exc}"

    return "Unknown git_branch action. Use 'list', 'checkout', or 'create'."


async def port_inspector(port: int = 0) -> str:
    """Inspect listening ports or find which process is bound to a specific port."""
    try:
        if port > 0:
            cmd = f"ss -tulpn 'sport = :{port}' || lsof -i :{port}"
        else:
            cmd = "ss -tulpn | head -30"
        proc = await _run_blocking(cmd, timeout=10, shell=True)
        out = proc.stdout.strip()
        if not out or out.count("\n") == 0:
            return f"No listening process found on port {port}." if port > 0 else "No listening ports detected."
        return out[:3000]
    except Exception as exc:
        return f"[port inspector error] {exc}"
