"""Canva Connect API client.

Authenticated HTTP client for the Canva Connect API (https://api.canva.com).
Supports auto-refresh of expired tokens on 401 responses.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("zenith.integrations.canva.client")

CANVA_API_BASE = "https://api.canva.com"


class CanvaClient:
    """Authenticated Canva Connect API client with auto-refresh."""

    def __init__(self, access_token: str, db: Any = None, user_id: str = "local"):
        self.access_token = access_token
        self.db = db
        self.user_id = user_id
        self._refreshed = False

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated request with auto-refresh on 401."""
        url = f"{CANVA_API_BASE}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, headers=self._headers(), **kwargs)

        if resp.status_code == 401 and not self._refreshed and self.db:
            try:
                await self._refresh_token()
                self._refreshed = True
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.request(
                        method, url, headers=self._headers(), **kwargs
                    )
            except Exception as exc:
                log.warning("Canva token refresh failed: %s", exc)
                raise RuntimeError("Canva authentication expired. Please reconnect.") from exc

        if resp.status_code == 403:
            raise RuntimeError(
                "Canva API returned 403 Forbidden. The required scope may not be authorized."
            )
        if resp.status_code == 404:
            raise RuntimeError("Canva resource not found (404).")
        if resp.status_code == 429:
            raise RuntimeError("Canva API rate limit exceeded. Please try again later.")

        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def _refresh_token(self) -> None:
        """Refresh the access token and update storage."""
        from .oauth import refresh_access_token
        from ..models import STATUS_EXPIRED

        conn = self.db.get_connection("canva", self.user_id)
        if not conn or not conn.get("refresh_token"):
            self.db.update_status("canva", STATUS_EXPIRED, self.user_id)
            raise RuntimeError("No refresh token available for Canva")

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
            "canva",
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token", conn["refresh_token"]),
            token_expires_at=expires_at,
            user_id=self.user_id,
        )

    # ── API Methods ──────────────────────────────────────────────────────────

    async def get_user_profile(self) -> dict:
        """Get the authenticated user's Canva profile."""
        return await self._request("GET", "/rest/v1/users/me")

    async def list_designs(
        self,
        query: str = "",
        continuation: str = "",
        ownership: str = "owned",
    ) -> dict:
        """List the user's Canva designs."""
        params: dict[str, str] = {"ownership": ownership}
        if query:
            params["query"] = query
        if continuation:
            params["continuation"] = continuation
        return await self._request("GET", "/rest/v1/designs", params=params)

    async def get_design(self, design_id: str) -> dict:
        """Get a specific Canva design."""
        return await self._request("GET", f"/rest/v1/designs/{design_id}")

    async def create_design(
        self,
        design_type: str = "",
        title: str = "",
        width: int | None = None,
        height: int | None = None,
    ) -> dict:
        """Create a new Canva design."""
        body: dict[str, Any] = {}
        if design_type:
            body["design_type"] = design_type
        if title:
            body["title"] = title
        if width and height:
            body["dimensions"] = {"width": width, "height": height, "units": "px"}
        return await self._request("POST", "/rest/v1/designs", json=body)

    async def create_export(
        self,
        design_id: str,
        format: str = "png",
        quality: str = "regular",
        pages: list[int] | None = None,
    ) -> dict:
        """Create an export job for a Canva design."""
        body: dict[str, Any] = {
            "design_id": design_id,
            "format": {"type": format},
        }
        if quality:
            body["format"]["quality"] = quality
        if pages:
            body["pages"] = pages
        return await self._request("POST", "/rest/v1/exports", json=body)

    async def get_export(self, export_id: str) -> dict:
        """Get the status/result of an export job."""
        return await self._request("GET", f"/rest/v1/exports/{export_id}")
