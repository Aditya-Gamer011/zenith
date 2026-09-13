"""Canva integration service layer.

Business logic for Canva operations. Each method checks connection status
before making API calls and returns structured results.
"""
from __future__ import annotations

import logging
from typing import Any

from ...core.config import settings
from ..models import IntegrationDB

log = logging.getLogger("zenith.integrations.canva.service")


def _get_db() -> IntegrationDB:
    return IntegrationDB(settings.db_path)


def _get_client(user_id: str = "local"):
    """Get an authenticated CanvaClient or None if not connected."""
    from .client import CanvaClient

    db = _get_db()
    conn = db.get_connection("canva", user_id)
    if not conn or not conn.get("access_token"):
        return None
    return CanvaClient(
        access_token=conn["access_token"],
        db=db,
        user_id=user_id,
    )


async def get_user_info(user_id: str = "local") -> dict[str, Any]:
    """Get the connected Canva user's profile."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Canva is not connected. Please connect in Settings → Art & Design."}
    try:
        data = await client.get_user_profile()
        return {"ok": True, "result": data}
    except Exception as exc:
        log.error("Canva get_user_info failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def list_designs(
    query: str = "", user_id: str = "local"
) -> dict[str, Any]:
    """List the user's Canva designs."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Canva is not connected."}
    try:
        data = await client.list_designs(query=query)
        items = data.get("items", [])
        return {
            "ok": True,
            "result": {
                "count": len(items),
                "designs": [
                    {
                        "id": d.get("id", ""),
                        "title": d.get("title", ""),
                        "created_at": d.get("created_at", ""),
                        "updated_at": d.get("updated_at", ""),
                        "thumbnail": d.get("thumbnail", {}).get("url", ""),
                    }
                    for d in items[:50]
                ],
            },
        }
    except Exception as exc:
        log.error("Canva list_designs failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def create_design(
    design_type: str = "",
    title: str = "Untitled",
    width: int | None = None,
    height: int | None = None,
    user_id: str = "local",
) -> dict[str, Any]:
    """Create a new Canva design."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Canva is not connected."}
    try:
        data = await client.create_design(
            design_type=design_type, title=title, width=width, height=height
        )
        return {"ok": True, "result": data}
    except Exception as exc:
        log.error("Canva create_design failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def export_design(
    design_id: str,
    format: str = "png",
    user_id: str = "local",
) -> dict[str, Any]:
    """Export a Canva design."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Canva is not connected."}
    try:
        data = await client.create_export(design_id, format=format)
        return {"ok": True, "result": data}
    except Exception as exc:
        log.error("Canva export_design failed: %s", exc)
        return {"ok": False, "error": str(exc)}
