"""n8n workflow integration — trigger, read, and inspect workflows.

n8n runs at https://n8n.agm.quest (container on :5678). The public REST API
needs an API key (n8n → Settings → API → Generate). Reads N8N_API_KEY from
.env; with no key the health/probe tool still works, and the rest degrade
to a clear "generate a key" message.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

from ..core.config import settings

log = logging.getLogger("zenith.n8n")

_BASE = (getattr(settings, "n8n_url", "") or
         os.environ.get("N8N_URL", "http://127.0.0.1:5678")).rstrip("/")


def api_key() -> str:
    return (getattr(settings, "n8n_api_key", "") or
            os.environ.get("N8N_API_KEY", "")).strip()


async def _get(path: str, timeout: float = 12.0) -> dict[str, Any]:
    key = api_key()
    headers = {"X-N8N-API-KEY": key} if key else {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{_BASE}{path}", headers=headers)
    except Exception as exc:
        return {"error": f"[n8n] {exc}"}
    if resp.status_code == 401:
        return {"error": ("[n8n] needs an API key. In n8n go to "
                          "Settings → API → Generate, then set N8N_API_KEY in .env "
                          "and restart Zenith.")}
    if resp.status_code >= 400:
        return {"error": f"[n8n] HTTP {resp.status_code}: {resp.text[:200]}"}
    try:
        return resp.json()
    except Exception:
        return {"error": "[n8n] non-JSON response."}


async def n8n_health() -> str:
    """Probe n8n's health/liveness (works without an API key)."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(f"{_BASE}/healthz")
            if resp.status_code == 200 and resp.text.strip() == "ok":
                return "n8n is running and healthy."
            return f"n8n responded {resp.status_code}."
    except Exception as exc:
        return f"[n8n] health probe failed: {exc}"


async def n8n_workflows(limit: int = 20) -> str:
    """List workflows (name, id, active) via the public API."""
    data = await _get(f"/api/v1/workflows?limit={max(1, min(limit, 50))}")
    if "error" in data:
        return data["error"]
    flows = data.get("data", [])
    if not flows:
        return "No workflows in n8n yet."
    lines = []
    for f in flows:
        name = f.get("name", "?")
        wid = f.get("id", "?")
        active = f.get("active", False)
        lines.append(f"{name} (id {wid}, {'active' if active else 'paused'})")
    return "\n".join(lines)


async def n8n_execute(workflow_id: str = "", name: str = "",
                      data: str = "{}") -> str:
    """Trigger a workflow execution with an optional JSON payload body.

    Must match an n8n public-API workflow (id). Returns execution id / result.
    """
    if not workflow_id and not name:
        return "[n8n] Provide a workflow_id (or name to look it up)."
    if workflow_id and not workflow_id.isdigit():
        return "[n8n] workflow_id must be the numeric n8n id."
    try:
        payload = json.loads(data or "{}")
    except Exception:
        return "[n8n] 'data' must be a JSON object string (e.g. {\"subject\": \"hi\"})."

    key = api_key()
    if not key:
        return ("[n8n] needs an API key (Settings → API → Generate), then set "
                "N8N_API_KEY in .env.")

    # Resolve by name if only a name was given.
    if not workflow_id:
        flows = await _get("/api/v1/workflows?limit=50")
        match = next((f for f in flows.get("data", [])
                      if (f.get("name") or "").lower() == (name or "").lower()), None)
        if not match:
            return f"[n8n] No workflow named '{name}'."
        workflow_id = match["id"]

    headers = {"X-N8N-API-KEY": key}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_BASE}/api/v1/workflows/{workflow_id}/run",
                headers=headers, json={"data": payload},
            )
    except Exception as exc:
        return f"[n8n] {exc}"
    if resp.status_code >= 400:
        return f"[n8n] trigger failed: HTTP {resp.status_code} {resp.text[:200]}"
    res = resp.json()
    exec_id = (res.get("data") or {}).get("executionId") or res.get("id") or "?"
    return f"n8n workflow fired (execution {exec_id})."