"""Zenith — Figma Plugin Bridge (Server Side).

WebSocket server for bidirectional communication between Zenith's AI
and the Figma Plugin running in the user's Figma editor.

Architecture:
  Zenith AI → design_tools.py → plugin_bridge.py → WebSocket → Figma Plugin → Plugin API

The plugin bridge:
  - Authenticates plugin connections via one-time token
  - Validates command types and parameters against PLUGIN_COMMAND_TYPES
  - Queues design commands for the connected plugin
  - Returns structured results from plugin execution
  - Never executes arbitrary code
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from ..tools.design_schemas import PLUGIN_COMMAND_TYPES

log = logging.getLogger("zenith.integrations.plugin_bridge")

router = APIRouter(prefix="/api/integrations/figma-plugin", tags=["figma-plugin"])

# ── Connection State ─────────────────────────────────────────────────────────

# Active plugin connections (one per user)
_connections: dict[str, WebSocket] = {}

# Pending command futures: {command_id: asyncio.Future}
_pending: dict[str, asyncio.Future] = {}

# One-time connection tokens: {token: user_id}
_auth_tokens: dict[str, str] = {}


# ── Authentication ───────────────────────────────────────────────────────────

@router.post("/auth-token")
async def generate_auth_token():
    """Generate a one-time token for plugin authentication."""
    token = secrets.token_urlsafe(32)
    _auth_tokens[token] = "local"
    # Clean expired tokens (keep only last 10)
    while len(_auth_tokens) > 10:
        oldest = next(iter(_auth_tokens))
        del _auth_tokens[oldest]
    return JSONResponse({"token": token})


# ── WebSocket Endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws")
async def plugin_websocket(ws: WebSocket, token: str = ""):
    """WebSocket endpoint for Figma plugin connections."""
    # Validate token
    user_id = _auth_tokens.pop(token, None) if token else None
    if not user_id:
        await ws.close(code=4001, reason="Invalid or expired auth token")
        return

    await ws.accept()
    _connections[user_id] = ws
    log.info("Figma plugin connected for user=%s", user_id)

    try:
        # Send handshake
        await ws.send_json({
            "type": "handshake",
            "version": "1.0",
            "commands": list(PLUGIN_COMMAND_TYPES.keys()),
        })

        # Listen for results from the plugin
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "result":
                cmd_id = data.get("command_id", "")
                future = _pending.pop(cmd_id, None)
                if future and not future.done():
                    future.set_result(data)

            elif msg_type == "error":
                cmd_id = data.get("command_id", "")
                future = _pending.pop(cmd_id, None)
                if future and not future.done():
                    future.set_result({
                        "ok": False,
                        "error": data.get("message", "Plugin error"),
                    })

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        log.info("Figma plugin disconnected for user=%s", user_id)
    except Exception as exc:
        log.error("Plugin WebSocket error: %s", exc)
    finally:
        _connections.pop(user_id, None)
        # Fail any pending commands
        for cmd_id, future in list(_pending.items()):
            if not future.done():
                future.set_result({"ok": False, "error": "Plugin disconnected"})
            _pending.pop(cmd_id, None)


# ── Command Execution ────────────────────────────────────────────────────────

def is_plugin_connected(user_id: str = "local") -> bool:
    """Check if a Figma plugin is connected for the user."""
    return user_id in _connections


async def execute_command(
    command_type: str,
    params: dict[str, Any],
    user_id: str = "local",
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Send a validated command to the Figma plugin and wait for result.

    Returns:
        {"ok": True, "result": {...}} on success
        {"ok": False, "error": "..."} on failure
    """
    # Validate command type
    if command_type not in PLUGIN_COMMAND_TYPES:
        return {
            "ok": False,
            "error": f"Unknown command type: {command_type}. "
                     f"Available: {', '.join(PLUGIN_COMMAND_TYPES.keys())}",
        }

    # Validate required params
    spec = PLUGIN_COMMAND_TYPES[command_type]
    spec_params = spec.get("params", {})
    for param_name, param_spec in spec_params.items():
        if param_spec.get("required") and param_name not in params:
            return {
                "ok": False,
                "error": f"Missing required parameter '{param_name}' for {command_type}",
            }

    # Check connection
    ws = _connections.get(user_id)
    if not ws:
        return {
            "ok": False,
            "error": "No Figma plugin connected. Please open Figma and run the Zenith plugin.",
        }

    # Generate command ID and send
    cmd_id = secrets.token_hex(8)
    future: asyncio.Future = asyncio.get_event_loop().create_future()
    _pending[cmd_id] = future

    try:
        await ws.send_json({
            "type": "command",
            "command_id": cmd_id,
            "command_type": command_type,
            "params": params,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        _pending.pop(cmd_id, None)
        return {"ok": False, "error": f"Failed to send command to plugin: {exc}"}

    # Wait for result with timeout
    try:
        result = await asyncio.wait_for(future, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        _pending.pop(cmd_id, None)
        return {"ok": False, "error": f"Plugin did not respond within {timeout}s"}


# ── Plugin Bridge Status ─────────────────────────────────────────────────────

@router.get("/status")
async def plugin_status():
    """Check if the Figma plugin is connected."""
    return {
        "connected": is_plugin_connected(),
        "available_commands": list(PLUGIN_COMMAND_TYPES.keys()),
    }


# ── Landing Page Demo ────────────────────────────────────────────────────────
# Pre-built design action sequences for common tasks

LANDING_PAGE_ACTIONS = [
    {
        "command_type": "create_frame",
        "params": {
            "name": "Landing Page",
            "width": 1440,
            "height": 900,
            "x": 0,
            "y": 0,
            "fill_color": "#0a0a0f",
        },
    },
    {
        "command_type": "create_text",
        "params": {
            "text": "Welcome to Zenith",
            "x": 200,
            "y": 200,
            "width": 1040,
            "font_size": 64,
            "font_family": "Inter",
            "font_weight": "Bold",
            "fill_color": "#e4e4e7",
        },
    },
    {
        "command_type": "create_text",
        "params": {
            "text": "Your autonomous AI companion for everything.",
            "x": 200,
            "y": 300,
            "width": 1040,
            "font_size": 24,
            "font_family": "Inter",
            "font_weight": "Regular",
            "fill_color": "#a1a1aa",
        },
    },
    {
        "command_type": "create_rectangle",
        "params": {
            "x": 200,
            "y": 400,
            "width": 240,
            "height": 56,
            "fill_color": "#6366f1",
            "corner_radius": 12,
            "name": "CTA Button",
        },
    },
    {
        "command_type": "create_text",
        "params": {
            "text": "Get Started",
            "x": 232,
            "y": 414,
            "font_size": 18,
            "font_family": "Inter",
            "font_weight": "SemiBold",
            "fill_color": "#ffffff",
        },
    },
]


async def create_landing_page(user_id: str = "local") -> dict[str, Any]:
    """Execute the pre-built landing page design flow.

    This is the working vertical slice: creates a 1440×900 frame with
    headline, subtitle, and CTA button.
    """
    if not is_plugin_connected(user_id):
        return {
            "ok": False,
            "error": "Figma plugin not connected. Open Figma and run the Zenith plugin first.",
        }

    results = []
    for i, action in enumerate(LANDING_PAGE_ACTIONS):
        result = await execute_command(
            action["command_type"],
            action["params"],
            user_id=user_id,
        )
        results.append({
            "step": i + 1,
            "command": action["command_type"],
            "ok": result.get("ok", False),
            "error": result.get("error", ""),
        })
        if not result.get("ok"):
            return {
                "ok": False,
                "error": f"Step {i + 1} ({action['command_type']}) failed: {result.get('error', 'Unknown')}",
                "completed_steps": results,
            }

    return {
        "ok": True,
        "result": {
            "message": "Landing page created successfully in Figma",
            "steps_completed": len(results),
            "elements": [
                "1440×900 dark frame",
                "Headline: 'Welcome to Zenith'",
                "Subtitle: 'Your autonomous AI companion'",
                "CTA Button: 'Get Started'",
            ],
        },
    }
