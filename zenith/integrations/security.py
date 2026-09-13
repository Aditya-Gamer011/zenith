"""Zenith — Integration Security Utilities.

Cryptographic helpers for OAuth integrations: Fernet token encryption,
state parameter generation/validation, and PKCE (S256) support.

Never logs tokens or secrets. All crypto operations use the stdlib
`secrets` module and the `cryptography` library's Fernet.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("zenith.integrations.security")

# ── Fernet Encryption ────────────────────────────────────────────────────────

_fernet_instance = None


def _get_fernet():
    """Lazy-init a Fernet instance keyed from SESSION_SECRET."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        log.error("cryptography package not installed — token encryption unavailable")
        raise RuntimeError(
            "The 'cryptography' package is required for integration token storage. "
            "Install it with: pip install cryptography>=42.0"
        )
    from ..core.config import settings
    secret = settings.session_secret or "zenith-default-integration-key-2026"
    # Derive a 32-byte key from the session secret via SHA-256, then base64 it
    key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    _fernet_instance = Fernet(fernet_key)
    return _fernet_instance


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns base64-encoded ciphertext."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token string. Returns plaintext."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        log.warning("Failed to decrypt token — may be corrupted or key changed")
        return ""


# ── OAuth State Management ───────────────────────────────────────────────────

def generate_state() -> str:
    """Generate a cryptographically secure OAuth state parameter."""
    return secrets.token_urlsafe(32)


def store_oauth_state(
    db_path: Path,
    state: str,
    provider: str,
    user_id: str = "local",
    pkce_verifier: str = "",
    ttl_seconds: int = 600,
) -> None:
    """Persist an OAuth state token with expiration."""
    expires_at = datetime.now(timezone.utc).isoformat()
    # Calculate actual expiry
    import datetime as dt
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=ttl_seconds)
    expires_at = expires.isoformat()

    verifier_enc = encrypt_token(pkce_verifier) if pkce_verifier else ""

    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO oauth_states
               (state, provider, user_id, pkce_verifier_enc, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (state, provider, user_id, verifier_enc, expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    log.info("Stored OAuth state for provider=%s user=%s", provider, user_id)


def validate_and_consume_state(
    db_path: Path,
    state: str,
    provider: str,
) -> dict:
    """Validate an OAuth state token and consume it (single use).

    Returns {"valid": True, "user_id": str, "pkce_verifier": str} on success.
    Returns {"valid": False, "error": str} on failure.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM oauth_states WHERE state = ? AND provider = ?",
            (state, provider),
        ).fetchone()

        if not row:
            log.warning("OAuth state not found: provider=%s", provider)
            return {"valid": False, "error": "Invalid or expired OAuth state"}

        # Check expiration
        expires_at = row["expires_at"]
        now = datetime.now(timezone.utc).isoformat()
        if now > expires_at:
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            conn.commit()
            log.warning("OAuth state expired: provider=%s", provider)
            return {"valid": False, "error": "OAuth state has expired"}

        # Consume the state (single use)
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        conn.commit()

        pkce_verifier = ""
        if row["pkce_verifier_enc"]:
            pkce_verifier = decrypt_token(row["pkce_verifier_enc"])

        return {
            "valid": True,
            "user_id": row["user_id"],
            "pkce_verifier": pkce_verifier,
        }
    finally:
        conn.close()


def cleanup_expired_states(db_path: Path) -> int:
    """Remove expired OAuth states. Returns count deleted."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        cur = conn.execute(
            "DELETE FROM oauth_states WHERE expires_at < ?", (now,)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ── PKCE (Proof Key for Code Exchange) ───────────────────────────────────────

def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256).

    Returns (code_verifier, code_challenge).
    The verifier is 43-128 chars of unreserved URI chars.
    The challenge is base64url(SHA256(verifier)).
    """
    # Generate 64 bytes of randomness → 86 chars base64url (within 43-128 range)
    verifier = secrets.token_urlsafe(64)
    # Ensure within bounds
    if len(verifier) > 128:
        verifier = verifier[:128]

    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")

    return verifier, challenge


# ── Audit Logging ────────────────────────────────────────────────────────────

def audit_log(
    db_path: Path,
    provider: str,
    action: str,
    details: str = "",
    user_id: str = "local",
) -> None:
    """Log an integration action (never includes tokens/secrets)."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        conn.execute(
            """INSERT INTO integration_audit_log
               (user_id, provider, action, details)
               VALUES (?, ?, ?, ?)""",
            (user_id, provider, action, details),
        )
        conn.commit()
    except Exception as exc:
        log.debug("Audit log write failed: %s", exc)
    finally:
        conn.close()
