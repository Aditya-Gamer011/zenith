"""Real confirmation gate for mutating tools.

This is a lightweight, non-sticky consent layer (replaces the prompt-suggestion
"Direct Execution — ALWAYS" fiction). A small allowlist of genuinely risky tools
(upserting DNS, deleting from R2, adding routes that change ingress, mutating a
release/PR, controlling systemd) gains a one-ask checkpoint: the orchestrator
emits a `confirm` WS event carrying the tool + message + an id, and the browser
shows the confirm dock. The gate awaits the decision, auto-refusing after
CONFIRM_TIMEOUT so nothing hangs forever, and resolves to a normal
`{cancelled: true}` tool result the model can see.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

_DEFAULT_CONFIRM_TOOLS = (
    "cf_dns_upsert",   # real DNS
    "r2_delete",       # storage deletion
    "vercel_deploy",   # production deploy
    "gh_create_repo",  # creates public/private repos
    "gh_create_pr",
    "gh_release_create",  # publish a release with assets
    "tunnel_add_route",   # changes public ingress
    "media_add",          # downloads media
    "systemd_control",    # start/stop/restart host services
    "email_send",         # first-class checkpoint for anything outbound
    "mc_admin",           # mutates the Minecraft world (ban/give/tp/etc.)
)

# Map of tool-name -> human explanation shown in the dock.
# Auto-generated from a generic template when not present.
_CONFIRM_MESSAGES: dict[str, str] = {}


def confirm_tools() -> tuple[str, ...]:
    """Which tools require a confirmation checkpoint."""
    from .config import settings
    if not getattr(settings, "require_approvals", False):
        return ()
    return _DEFAULT_CONFIRM_TOOLS


class ConfirmGate:
    """Server-side ask/approve/deny with a timeout.

    One instance lives on the Orchestrator. `request()` returns an awaitable
    that resolves to True (approved) or False (denied / no one answered).
    The emit callback (set by main.py) delivers a `confirm` WS event to the
    UI before the gate starts waiting.
    """

    def __init__(self, timeout: float = 180.0, emit: Callable | None = None) -> None:
        self.timeout = timeout
        self.emit = emit
        self._pending: dict[int, dict[str, Any]] = {}
        self._seq = 0

    def needs_gate(self, tool: str) -> bool:
        return tool in confirm_tools()

    def describe(self, tool: str, arguments: dict[str, Any]) -> str:
        """Build a human message for the confirm dock from the tool + args."""
        if tool in _CONFIRM_MESSAGES:
            return _CONFIRM_MESSAGES[tool]
        args = arguments or {}
        summary = ", ".join(f"{k}={str(v)[:40]}" for k, v in list(args.items())[:3])
        return f"Zenith wants to run `{tool}`" + (f" — {summary}" if summary else "") + "."

    def get_pending(self) -> list[dict[str, Any]]:
        """Return all active uncompleted confirmations so reconnecting clients can render the dock."""
        out = []
        for cid, data in list(self._pending.items()):
            fut = data.get("future")
            if fut and not fut.done():
                out.append({
                    "id": cid,
                    "tool": data.get("tool", ""),
                    "message": data.get("message", ""),
                    "created_at": data.get("created_at", 0),
                })
        return out

    async def request(self, tool: str, arguments: dict[str, Any]) -> bool:
        """Create a pending confirmation, emit the dock event, await a decision.

        Auto-refuses (returns False) if nobody answers within `timeout`.
        """
        cid = self._next_id()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        desc = self.describe(tool, arguments)
        self._pending[cid] = {
            "future": fut,
            "tool": tool,
            "arguments": arguments,
            "message": desc,
            "created_at": time.time(),
        }
        try:
            if self.emit:
                try:
                    await self.emit({
                        "type": "confirm",
                        "id": cid,
                        "tool": tool,
                        "message": desc,
                    })
                except Exception:
                    pass
            try:
                approved = await asyncio.wait_for(fut, timeout=self.timeout)
            except asyncio.TimeoutError:
                approved = False
            return approved
        finally:
            self._pending.pop(cid, None)

    def _next_id(self) -> int:
        self._seq += 1
        return self._seq + id(self) * 1000  # process-unique, monotonic

    def resolve(self, cid: int, decision: bool) -> bool:
        """Satisfy a pending confirmation with a decision. False if unknown or expired."""
        data = self._pending.get(cid)
        if data is None:
            return False
        fut = data.get("future")
        if fut is None or fut.done():
            return False
        fut.set_result(decision)
        return True