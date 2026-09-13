"""Systemd & Network Health tool suite — service monitoring/control, ping, and endpoint health checks."""
from __future__ import annotations

import asyncio
import re
import subprocess
import time
import httpx

from ..core.config import settings


async def _run_blocking(cmd, *, timeout: int, shell: bool = False):
    """Run a blocking subprocess OFF the event loop (the loop serves chat+voice
    +scheduler; a synchronous subprocess.run would freeze all of them)."""
    return await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True, timeout=timeout, shell=shell,
    )


async def systemd_status(service: str = "") -> str:
    """List active systemd services or detailed status for a specific service."""
    try:
        if service:
            proc = await _run_blocking(
                ["systemctl", "status", service, "--no-pager"], timeout=10,
            )
            out = (proc.stdout or proc.stderr).strip()
            return out[:3000] if out else f"No status for service {service}."

        proc = await _run_blocking(
            ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager"],
            timeout=10,
        )
        out = proc.stdout.strip()
        lines = out.splitlines()[:25]
        return "\n".join(lines) if lines else "No running systemd services listed."
    except Exception as exc:
        return f"[systemd error] {exc}"


async def systemd_control(service: str, action: str) -> str:
    """Control a systemd service (start | stop | restart | reload). Confirmation-gated."""
    act = (action or "").lower()
    if act not in ("start", "stop", "restart", "reload"):
        return "Action must be one of: start, stop, restart, reload."
    if not service:
        return "Provide service name."
    try:
        proc = await _run_blocking(["systemctl", act, service], timeout=15)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            return f"[systemd] {act} {service} failed: {err}"
        return f"Systemd service '{service}' {act} succeeded."
    except Exception as exc:
        return f"[systemd error] {exc}"


async def ping_check(host: str, count: int = 3) -> str:
    """Ping a host and measure latency and packet loss."""
    clean_host = re.sub(r"[^a-zA-Z0-9.-]", "", host.strip())
    if not clean_host:
        return "[ping] Invalid host provided."
    cnt = max(1, min(count, 10))
    try:
        proc = await _run_blocking(
            ["ping", "-c", str(cnt), "-W", "3", clean_host], timeout=15,
        )
        out = proc.stdout.strip()
        if proc.returncode != 0 or not out:
            return f"[ping] {clean_host} unreachable (exit code {proc.returncode})."
        return out[:1500]
    except Exception as exc:
        return f"[ping error] {exc}"


async def endpoint_health(url: str) -> str:
    """Check HTTP health, latency, status code, and headers for an endpoint URL."""
    if not url:
        return "[health] Provide a URL."
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    start_ts = time.time()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
            elapsed_ms = round((time.time() - start_ts) * 1000, 1)
            server = resp.headers.get("server", "unknown")
            content_type = resp.headers.get("content-type", "unknown")
            
            return (
                f"Endpoint: {url}\n"
                f"Status: {resp.status_code} {resp.reason_phrase}\n"
                f"Latency: {elapsed_ms} ms\n"
                f"Server: {server}\n"
                f"Content-Type: {content_type}"
            )
    except Exception as exc:
        elapsed_ms = round((time.time() - start_ts) * 1000, 1)
        return f"[health error] {url} failed after {elapsed_ms} ms: {exc}"
