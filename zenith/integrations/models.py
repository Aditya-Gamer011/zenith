"""Zenith — Integration Database Models.

SQLite-backed storage for OAuth integration connections.
Handles encrypted token persistence, connection status tracking,
and CRUD operations for Figma/Canva integrations.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import security

log = logging.getLogger("zenith.integrations.models")


# ── Connection Status Constants ──────────────────────────────────────────────

STATUS_NOT_CONNECTED = "not_connected"
STATUS_CONNECTED = "connected"
STATUS_EXPIRED = "expired"
STATUS_ERROR = "error"


class IntegrationDB:
    """CRUD operations for oauth_integrations table."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_connection(
        self,
        provider: str,
        access_token: str,
        refresh_token: str = "",
        token_expires_at: str = "",
        scopes: str = "",
        provider_user_id: str = "",
        provider_user_name: str = "",
        user_id: str = "local",
        metadata: dict | None = None,
    ) -> None:
        """Create or update an integration connection with encrypted tokens."""
        access_enc = security.encrypt_token(access_token)
        refresh_enc = security.encrypt_token(refresh_token) if refresh_token else ""
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})

        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO oauth_integrations
                   (user_id, provider, access_token_enc, refresh_token_enc,
                    token_expires_at, scopes, provider_user_id, provider_user_name,
                    status, connected_at, last_sync_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, provider)
                   DO UPDATE SET
                    access_token_enc = excluded.access_token_enc,
                    refresh_token_enc = excluded.refresh_token_enc,
                    token_expires_at = excluded.token_expires_at,
                    scopes = excluded.scopes,
                    provider_user_id = excluded.provider_user_id,
                    provider_user_name = excluded.provider_user_name,
                    status = excluded.status,
                    connected_at = excluded.connected_at,
                    last_sync_at = excluded.last_sync_at,
                    metadata_json = excluded.metadata_json""",
                (
                    user_id, provider, access_enc, refresh_enc,
                    token_expires_at, scopes, provider_user_id, provider_user_name,
                    STATUS_CONNECTED, now, now, meta_json,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        log.info("Upserted %s connection for user=%s", provider, user_id)
        security.audit_log(
            self.db_path, provider, "connected",
            f"scopes={scopes} provider_user={provider_user_name}", user_id,
        )

    def get_connection(
        self, provider: str, user_id: str = "local"
    ) -> dict[str, Any] | None:
        """Get a connection record with decrypted tokens."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT * FROM oauth_integrations
                   WHERE user_id = ? AND provider = ?""",
                (user_id, provider),
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            # Decrypt tokens
            result["access_token"] = security.decrypt_token(
                result.pop("access_token_enc", "") or ""
            )
            result["refresh_token"] = security.decrypt_token(
                result.pop("refresh_token_enc", "") or ""
            )
            # Parse metadata
            try:
                result["metadata"] = json.loads(result.pop("metadata_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                result["metadata"] = {}
            return result
        finally:
            conn.close()

    def get_connection_status(
        self, provider: str, user_id: str = "local"
    ) -> dict[str, Any]:
        """Get connection status without decrypting tokens (safe for frontend)."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT provider, status, scopes, provider_user_id,
                          provider_user_name, connected_at, last_sync_at,
                          token_expires_at
                   FROM oauth_integrations
                   WHERE user_id = ? AND provider = ?""",
                (user_id, provider),
            ).fetchone()
            if not row:
                return {
                    "provider": provider,
                    "status": STATUS_NOT_CONNECTED,
                    "connected": False,
                    "provider_user_name": "",
                    "connected_at": "",
                    "last_sync_at": "",
                    "scopes": "",
                }

            result = dict(row)
            # Check if token is expired
            if result.get("token_expires_at"):
                try:
                    expires = datetime.fromisoformat(result["token_expires_at"])
                    if expires < datetime.now(timezone.utc):
                        result["status"] = STATUS_EXPIRED
                except (ValueError, TypeError):
                    pass

            result["connected"] = result["status"] == STATUS_CONNECTED
            return result
        finally:
            conn.close()

    def update_tokens(
        self,
        provider: str,
        access_token: str,
        refresh_token: str = "",
        token_expires_at: str = "",
        user_id: str = "local",
    ) -> None:
        """Update tokens after a refresh."""
        access_enc = security.encrypt_token(access_token)
        refresh_enc = security.encrypt_token(refresh_token) if refresh_token else ""
        now = datetime.now(timezone.utc).isoformat()

        conn = self._connect()
        try:
            conn.execute(
                """UPDATE oauth_integrations
                   SET access_token_enc = ?, refresh_token_enc = ?,
                       token_expires_at = ?, status = ?, last_sync_at = ?
                   WHERE user_id = ? AND provider = ?""",
                (access_enc, refresh_enc, token_expires_at, STATUS_CONNECTED,
                 now, user_id, provider),
            )
            conn.commit()
        finally:
            conn.close()
        log.info("Refreshed tokens for %s user=%s", provider, user_id)

    def update_status(
        self, provider: str, status: str, user_id: str = "local"
    ) -> None:
        """Update connection status (e.g. on error)."""
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE oauth_integrations SET status = ?
                   WHERE user_id = ? AND provider = ?""",
                (status, user_id, provider),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_connection(
        self, provider: str, user_id: str = "local"
    ) -> bool:
        """Delete a connection (disconnect)."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """DELETE FROM oauth_integrations
                   WHERE user_id = ? AND provider = ?""",
                (user_id, provider),
            )
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()

        if deleted:
            log.info("Deleted %s connection for user=%s", provider, user_id)
            security.audit_log(
                self.db_path, provider, "disconnected", "", user_id,
            )
        return deleted

    def list_connections(
        self, user_id: str = "local"
    ) -> list[dict[str, Any]]:
        """List all connection statuses for a user (no tokens)."""
        providers = ["figma", "canva"]
        return [self.get_connection_status(p, user_id) for p in providers]
