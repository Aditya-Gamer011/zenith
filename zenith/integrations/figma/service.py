"""Figma integration service layer.

Business logic for Figma operations. Each method checks connection status
before making API calls and returns structured results.
"""
from __future__ import annotations

import logging
from typing import Any

from ...core.config import settings
from ..models import IntegrationDB

log = logging.getLogger("zenith.integrations.figma.service")


def _get_db() -> IntegrationDB:
    return IntegrationDB(settings.db_path)


def _get_client(user_id: str = "local"):
    """Get an authenticated FigmaClient or None if not connected."""
    from .client import FigmaClient

    db = _get_db()
    conn = db.get_connection("figma", user_id)
    if not conn or not conn.get("access_token"):
        return None
    return FigmaClient(
        access_token=conn["access_token"],
        db=db,
        user_id=user_id,
    )


async def get_user_info(user_id: str = "local") -> dict[str, Any]:
    """Get the connected Figma user's profile."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Figma is not connected. Please connect in Settings → Art & Design."}
    try:
        data = await client.get_me()
        return {"ok": True, "result": data}
    except Exception as exc:
        log.error("Figma get_user_info failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def read_file_metadata(file_key: str, user_id: str = "local") -> dict[str, Any]:
    """Read a Figma file's metadata and top-level structure."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Figma is not connected."}
    try:
        data = await client.get_file(file_key)
        # Return a summary rather than the full tree
        result = {
            "name": data.get("name", ""),
            "lastModified": data.get("lastModified", ""),
            "version": data.get("version", ""),
            "role": data.get("role", ""),
            "pages": [],
        }
        doc = data.get("document", {})
        for child in doc.get("children", []):
            result["pages"].append({
                "id": child.get("id", ""),
                "name": child.get("name", ""),
                "type": child.get("type", ""),
                "childCount": len(child.get("children", [])),
            })
        return {"ok": True, "result": result}
    except Exception as exc:
        log.error("Figma read_file_metadata failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def read_file_nodes(
    file_key: str, node_ids: list[str], user_id: str = "local"
) -> dict[str, Any]:
    """Read specific nodes from a Figma file."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Figma is not connected."}
    if not node_ids:
        return {"ok": False, "error": "No node IDs provided."}
    try:
        data = await client.get_file_nodes(file_key, node_ids)
        return {"ok": True, "result": data.get("nodes", {})}
    except Exception as exc:
        log.error("Figma read_file_nodes failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def export_assets(
    file_key: str,
    node_ids: list[str],
    format: str = "png",
    user_id: str = "local",
) -> dict[str, Any]:
    """Export Figma nodes as images."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Figma is not connected."}
    if not node_ids:
        return {"ok": False, "error": "No node IDs provided."}
    try:
        data = await client.get_images(file_key, node_ids, format=format)
        return {"ok": True, "result": data.get("images", {})}
    except Exception as exc:
        log.error("Figma export_assets failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def list_comments(
    file_key: str, user_id: str = "local"
) -> dict[str, Any]:
    """Get comments on a Figma file."""
    client = _get_client(user_id)
    if not client:
        return {"ok": False, "error": "Figma is not connected."}
    try:
        data = await client.get_comments(file_key)
        comments = data.get("comments", [])
        return {
            "ok": True,
            "result": {
                "count": len(comments),
                "comments": [
                    {
                        "id": c.get("id", ""),
                        "message": c.get("message", ""),
                        "user": c.get("user", {}).get("handle", ""),
                        "created_at": c.get("created_at", ""),
                        "resolved_at": c.get("resolved_at", ""),
                    }
                    for c in comments[:50]
                ],
            },
        }
    except Exception as exc:
        log.error("Figma list_comments failed: %s", exc)
        return {"ok": False, "error": str(exc)}
