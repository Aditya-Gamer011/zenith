"""Figma REST API client.

Authenticated HTTP client for the Figma REST API (https://api.figma.com).
Supports auto-refresh of expired tokens on 401 responses.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("zenith.integrations.figma.client")

FIGMA_API_BASE = "https://api.figma.com"


class FigmaClient:
    """Authenticated Figma REST API client with auto-refresh."""

    def __init__(self, access_token: str, db: Any = None, user_id: str = "local"):
        self.access_token = access_token
        self.db = db
        self.user_id = user_id
        self._refreshed = False

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def _request(
        self, method: str, path: str, **kwargs
    ) -> dict:
        """Make an authenticated request with auto-refresh on 401."""
        url = f"{FIGMA_API_BASE}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, headers=self._headers(), **kwargs)

        if resp.status_code == 401 and not self._refreshed and self.db:
            # Attempt token refresh
            try:
                await self._refresh_token()
                self._refreshed = True
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.request(
                        method, url, headers=self._headers(), **kwargs
                    )
            except Exception as exc:
                log.warning("Figma token refresh failed: %s", exc)
                raise RuntimeError("Figma authentication expired. Please reconnect.") from exc

        if resp.status_code == 403:
            raise RuntimeError(
                "Figma API returned 403 Forbidden. The required scope may not be authorized."
            )
        if resp.status_code == 404:
            raise RuntimeError("Figma resource not found (404).")
        if resp.status_code == 429:
            raise RuntimeError("Figma API rate limit exceeded. Please try again later.")

        resp.raise_for_status()
        return resp.json()

    async def _refresh_token(self) -> None:
        """Refresh the access token and update storage."""
        from .oauth import refresh_access_token
        from ..models import STATUS_EXPIRED

        conn = self.db.get_connection("figma", self.user_id)
        if not conn or not conn.get("refresh_token"):
            self.db.update_status("figma", STATUS_EXPIRED, self.user_id)
            raise RuntimeError("No refresh token available for Figma")

        result = await refresh_access_token(conn["refresh_token"])
        self.access_token = result["access_token"]

        from datetime import datetime, timezone, timedelta
        expires_in = result.get("expires_in", 0)
        expires_at = ""
        if expires_in:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat()

        self.db.update_tokens(
            "figma",
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token", conn["refresh_token"]),
            token_expires_at=expires_at,
            user_id=self.user_id,
        )

    # ── API Methods ──────────────────────────────────────────────────────────

    async def get_me(self) -> dict:
        """Get the authenticated user's profile."""
        return await self._request("GET", "/v1/me")

    async def get_file(self, file_key: str) -> dict:
        """Get a Figma file's metadata (shallow, depth=1 for performance)."""
        return await self._request("GET", f"/v1/files/{file_key}", params={"depth": 1})

    async def get_file_nodes(self, file_key: str, node_ids: list[str]) -> dict:
        """Get specific nodes from a Figma file."""
        ids_param = ",".join(node_ids)
        return await self._request(
            "GET", f"/v1/files/{file_key}/nodes", params={"ids": ids_param}
        )

    async def get_images(
        self,
        file_key: str,
        node_ids: list[str],
        format: str = "png",
        scale: float = 2,
    ) -> dict:
        """Export nodes as images."""
        ids_param = ",".join(node_ids)
        return await self._request(
            "GET",
            f"/v1/images/{file_key}",
            params={"ids": ids_param, "format": format, "scale": scale},
        )

    async def get_comments(self, file_key: str) -> dict:
        """Get comments on a Figma file."""
        return await self._request("GET", f"/v1/files/{file_key}/comments")
