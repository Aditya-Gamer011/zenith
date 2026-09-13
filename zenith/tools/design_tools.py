"""Zenith — AI Design Tools.

Registers design-related tools with Zenith's tool system. These tools
let the AI interact with Figma and Canva through structured, validated
operations — never arbitrary code execution.
"""
from __future__ import annotations

import json
import logging

from ..core.tools import register

log = logging.getLogger("zenith.tools.design_tools")


# ── Integration Status Tool ──────────────────────────────────────────────────

async def _design_integration_status(arguments: dict) -> dict:
    """Check which design integrations are connected and available."""
    from ..integrations.models import IntegrationDB
    from ..core.config import settings

    db = IntegrationDB(settings.db_path)
    connections = db.list_connections()

    result = {
        "integrations": [],
        "summary": "",
    }
    connected = []
    for conn in connections:
        status_info = {
            "provider": conn["provider"],
            "status": conn["status"],
            "connected": conn.get("connected", False),
            "user": conn.get("provider_user_name", ""),
            "last_sync": conn.get("last_sync_at", ""),
        }
        result["integrations"].append(status_info)
        if conn.get("connected"):
            connected.append(conn["provider"].title())

    if connected:
        result["summary"] = f"Connected: {', '.join(connected)}. You can use design tools for these platforms."
    else:
        result["summary"] = "No design integrations connected. Ask the user to connect Figma or Canva in Settings → Art & Design."

    return {"ok": True, "result": result}


register(
    "design_integration_status",
    "Check which design integrations (Figma, Canva) are currently connected and available for use.",
    {
        "type": "object",
        "properties": {},
    },
    _design_integration_status,
)


# ── Figma Tools ──────────────────────────────────────────────────────────────

async def _figma_get_user(arguments: dict) -> dict:
    """Get the connected Figma user's profile."""
    from ..integrations.figma.service import get_user_info
    return await get_user_info()


register(
    "figma_get_user",
    "Get the connected Figma user's profile information (name, email, avatar). Requires Figma integration to be connected.",
    {
        "type": "object",
        "properties": {},
    },
    _figma_get_user,
)


async def _figma_read_file(arguments: dict) -> dict:
    """Read a Figma file's metadata and page structure."""
    file_key = arguments.get("file_key", "").strip()
    if not file_key:
        return {"ok": False, "error": "file_key is required. This is the key from the Figma file URL (e.g. figma.com/file/FILE_KEY/...)."}
    from ..integrations.figma.service import read_file_metadata
    return await read_file_metadata(file_key)


register(
    "figma_read_file",
    "Read a Figma file's metadata including name, pages, version, and top-level structure. Provide the file_key from the Figma URL.",
    {
        "type": "object",
        "properties": {
            "file_key": {
                "type": "string",
                "description": "The Figma file key (from URL: figma.com/file/FILE_KEY/...)",
            },
        },
        "required": ["file_key"],
    },
    _figma_read_file,
)


async def _figma_inspect_nodes(arguments: dict) -> dict:
    """Inspect specific nodes in a Figma file."""
    file_key = arguments.get("file_key", "").strip()
    node_ids = arguments.get("node_ids", [])
    if not file_key:
        return {"ok": False, "error": "file_key is required."}
    if not node_ids:
        return {"ok": False, "error": "node_ids is required (list of node IDs like '1:2')."}
    if isinstance(node_ids, str):
        node_ids = [n.strip() for n in node_ids.split(",") if n.strip()]
    from ..integrations.figma.service import read_file_nodes
    return await read_file_nodes(file_key, node_ids)


register(
    "figma_inspect_nodes",
    "Inspect specific design nodes in a Figma file to see their properties (type, size, colors, text content, etc.).",
    {
        "type": "object",
        "properties": {
            "file_key": {
                "type": "string",
                "description": "The Figma file key",
            },
            "node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of node IDs to inspect (e.g. ['1:2', '1:3'])",
            },
        },
        "required": ["file_key", "node_ids"],
    },
    _figma_inspect_nodes,
)


async def _figma_export_assets(arguments: dict) -> dict:
    """Export Figma nodes as images."""
    file_key = arguments.get("file_key", "").strip()
    node_ids = arguments.get("node_ids", [])
    fmt = arguments.get("format", "png")
    if not file_key:
        return {"ok": False, "error": "file_key is required."}
    if not node_ids:
        return {"ok": False, "error": "node_ids is required."}
    if isinstance(node_ids, str):
        node_ids = [n.strip() for n in node_ids.split(",") if n.strip()]
    from ..integrations.figma.service import export_assets
    return await export_assets(file_key, node_ids, format=fmt)


register(
    "figma_export_assets",
    "Export Figma design nodes as images. Supports PNG, SVG, JPG, and PDF formats.",
    {
        "type": "object",
        "properties": {
            "file_key": {
                "type": "string",
                "description": "The Figma file key",
            },
            "node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of node IDs to export",
            },
            "format": {
                "type": "string",
                "enum": ["png", "svg", "jpg", "pdf"],
                "description": "Export format (default: png)",
            },
        },
        "required": ["file_key", "node_ids"],
    },
    _figma_export_assets,
)


async def _figma_read_comments(arguments: dict) -> dict:
    """Read comments on a Figma file."""
    file_key = arguments.get("file_key", "").strip()
    if not file_key:
        return {"ok": False, "error": "file_key is required."}
    from ..integrations.figma.service import list_comments
    return await list_comments(file_key)


register(
    "figma_read_comments",
    "Read comments and feedback on a Figma design file.",
    {
        "type": "object",
        "properties": {
            "file_key": {
                "type": "string",
                "description": "The Figma file key",
            },
        },
        "required": ["file_key"],
    },
    _figma_read_comments,
)


# ── Canva Tools ──────────────────────────────────────────────────────────────

async def _canva_get_profile(arguments: dict) -> dict:
    """Get the connected Canva user's profile."""
    from ..integrations.canva.service import get_user_info
    return await get_user_info()


register(
    "canva_get_profile",
    "Get the connected Canva user's profile information. Requires Canva integration to be connected.",
    {
        "type": "object",
        "properties": {},
    },
    _canva_get_profile,
)


async def _canva_list_designs(arguments: dict) -> dict:
    """List the user's Canva designs."""
    query = arguments.get("query", "")
    from ..integrations.canva.service import list_designs
    return await list_designs(query=query)


register(
    "canva_list_designs",
    "List and search the user's Canva designs. Optionally filter by search query.",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional search query to filter designs",
            },
        },
    },
    _canva_list_designs,
)


async def _canva_create_design(arguments: dict) -> dict:
    """Create a new Canva design."""
    title = arguments.get("title", "Untitled")
    design_type = arguments.get("design_type", "")
    width = arguments.get("width")
    height = arguments.get("height")
    from ..integrations.canva.service import create_design
    return await create_design(
        design_type=design_type, title=title, width=width, height=height
    )


register(
    "canva_create_design",
    "Create a new Canva design with a specified title and dimensions. Note: this creates an empty design that opens in Canva's editor.",
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title for the new design",
            },
            "design_type": {
                "type": "string",
                "description": "Design type (e.g. 'Presentation', 'Poster', 'Instagram Post')",
            },
            "width": {
                "type": "integer",
                "description": "Width in pixels (for custom dimensions)",
            },
            "height": {
                "type": "integer",
                "description": "Height in pixels (for custom dimensions)",
            },
        },
        "required": ["title"],
    },
    _canva_create_design,
)


async def _canva_export_design(arguments: dict) -> dict:
    """Export a Canva design."""
    design_id = arguments.get("design_id", "").strip()
    fmt = arguments.get("format", "png")
    if not design_id:
        return {"ok": False, "error": "design_id is required."}
    from ..integrations.canva.service import export_design
    return await export_design(design_id, format=fmt)


register(
    "canva_export_design",
    "Export a Canva design as an image or PDF. Returns an export job that can be checked for completion.",
    {
        "type": "object",
        "properties": {
            "design_id": {
                "type": "string",
                "description": "The Canva design ID to export",
            },
            "format": {
                "type": "string",
                "enum": ["png", "jpg", "pdf"],
                "description": "Export format (default: png)",
            },
        },
        "required": ["design_id"],
    },
    _canva_export_design,
)


log.info("Design tools registered: 8 tools (Figma: 5, Canva: 4, Status: 1)")
