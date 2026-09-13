"""CDN upload — Hack Club CDN (cdn.hackclub.com).

Zenith can upload local files or remote URLs to Hack Club CDN,
returning permanent public URLs. Useful for sharing generated files (PDFs, images,
code) in chat, email attachments, or project assets.

Uses the v4 API with Bearer token auth.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

import httpx

from ..core.config import settings

_BASE = "https://cdn.hackclub.com"
_MAX_SIZE = 50 * 1024 * 1024  # 50 MB safety limit


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.hackclub_cdn_key}"}


async def cdn_upload(file_path: str) -> str:
    """Upload a local file to cdn.hackclub.com. Returns the public CDN URL."""
    if not settings.hackclub_cdn_key:
        return "[cdn] HACKCLUB_CDN_KEY is not set in .env."

    p = Path(file_path).expanduser()
    if not p.is_file():
        return f"[cdn] File not found: {file_path}"

    size = p.stat().st_size
    if size > _MAX_SIZE:
        return f"[cdn] File too large ({size / 1024 / 1024:.1f} MB). Max is 50 MB."
    if size == 0:
        return "[cdn] File is empty."

    mime, _ = mimetypes.guess_type(p.name)
    try:
        data = p.read_bytes()
        async with httpx.AsyncClient(timeout=60) as client:
            files = {"file": (p.name, data, mime or "application/octet-stream")}
            resp = await client.post(
                f"{_BASE}/api/v4/upload",
                headers=_headers(),
                files=files,
            )
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err = body.get("error", resp.text[:200])
            return f"[cdn] Upload failed ({resp.status_code}): {err}"

        result = resp.json()
        url = result.get("url", "")
        fname = result.get("filename", p.name)
        fid = result.get("id", "")
        return (f"Uploaded to CDN.\n"
                f"  url: {url}\n"
                f"  filename: {fname}\n"
                f"  id: {fid}\n"
                f"  size: {result.get('size', size)} bytes")
    except Exception as exc:
        return f"[cdn] Upload error: {exc}"


async def cdn_upload_url(url: str, source_auth: str = "") -> str:
    """Upload a file from a remote URL to the CDN. Returns the public CDN URL."""
    if not settings.hackclub_cdn_key:
        return "[cdn] HACKCLUB_CDN_KEY is not set in .env."

    headers = {**_headers(), "Content-Type": "application/json"}
    if source_auth:
        headers["X-Download-Authorization"] = source_auth

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{_BASE}/api/v4/upload_from_url",
                headers=headers,
                json={"url": url},
            )
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err = body.get("error", resp.text[:200])
            return f"[cdn] Upload-from-URL failed ({resp.status_code}): {err}"

        result = resp.json()
        return (f"Uploaded to CDN from URL.\n"
                f"  url: {result.get('url', '')}\n"
                f"  filename: {result.get('filename', '')}\n"
                f"  id: {result.get('id', '')}")
    except Exception as exc:
        return f"[cdn] Upload-from-URL error: {exc}"


async def cdn_delete(upload_id: str) -> str:
    """Delete an uploaded file by its ID."""
    if not settings.hackclub_cdn_key:
        return "[cdn] HACKCLUB_CDN_KEY is not set in .env."

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.delete(
                f"{_BASE}/api/v4/upload/{upload_id}",
                headers=_headers(),
            )
        if resp.status_code == 404:
            return f"[cdn] Upload {upload_id} not found."
        if resp.status_code >= 400:
            return f"[cdn] Delete failed ({resp.status_code}): {resp.text[:200]}"

        result = resp.json()
        if result.get("deleted"):
            return f"Deleted CDN upload {upload_id}."
        return f"[cdn] Unexpected response: {result}"
    except Exception as exc:
        return f"[cdn] Delete error: {exc}"


async def cdn_quota() -> str:
    """Check CDN storage quota and usage."""
    if not settings.hackclub_cdn_key:
        return "[cdn] HACKCLUB_CDN_KEY is not set in .env."

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/api/v4/me", headers=_headers())
        if resp.status_code >= 400:
            return f"[cdn] Quota check failed ({resp.status_code}): {resp.text[:200]}"

        data = resp.json()
        used = data.get("storage_used", 0)
        limit = data.get("storage_limit", 0)
        tier = data.get("quota_tier", "unknown")
        pct = (used / limit * 100) if limit else 0
        return (f"CDN Quota ({tier}):\n"
                f"  used: {used / 1024 / 1024:.1f} MB / {limit / 1024 / 1024 / 1024:.1f} GB\n"
                f"  {pct:.1f}% used")
    except Exception as exc:
        return f"[cdn] Quota error: {exc}"
