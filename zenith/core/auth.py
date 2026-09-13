"""Zenith — Axiom Identity & Authentication Layer.

Enforces centralized Single Sign-On via Axiom (OpenID Connect + PKCE S256).
Provides secure session cookie minting/verification, OAuth state sealing,
token exchange, and authentication guards for FastAPI REST routes & WebSockets.
Pure Python standard library implementation with zero external crypto dependencies.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException, Request, Response, WebSocket, status

from .config import settings

log = logging.getLogger("zenith.auth")

COOKIE_NAME = settings.session_cookie_name
STATE_COOKIE_NAME = "zenith_oauth_state"
SESSION_DURATION_SEC = 30 * 86400  # 30 days
STATE_DURATION_SEC = 600  # 10 minutes

_ROLE_CACHE: dict[str, tuple[str, float]] = {}
ROLE_CACHE_TTL_SEC = 20.0


def query_axiom_role(identifier: str) -> str | None:
    """Query Axiom SQLite database directly for user's current role."""
    if not identifier:
        return None
    ident = str(identifier).strip()
    now = time.time()
    cached = _ROLE_CACHE.get(ident.lower())
    if cached and (now - cached[1]) < ROLE_CACHE_TTL_SEC:
        return cached[0]

    db_candidates = [
        settings.axiom_db_path,
        "/app/axiom_prisma/dev.db",
        "/home/singh/Desktop/Axiom/prisma/dev.db",
        str(Path(__file__).resolve().parents[3] / "Axiom" / "prisma" / "dev.db"),
    ]
    for db_path in db_candidates:
        if not db_path:
            continue
        p = Path(db_path)
        if p.is_file():
            try:
                uri = f"file:{p.resolve()}?mode=ro"
                with sqlite3.connect(uri, uri=True, timeout=1.0) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT role FROM User WHERE id = ? OR LOWER(email) = LOWER(?) OR LOWER(username) = LOWER(?) LIMIT 1",
                        (ident, ident, ident),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        role_str = str(row[0]).strip().lower()
                        _ROLE_CACHE[ident.lower()] = (role_str, now)
                        return role_str
            except Exception as e:
                log.debug("Axiom DB lookup error for %s at %s: %s", ident, db_path, e)
    return None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + pad)


# ─── PKCE & OAuth State ───────────────────────────────────────────────────────

def generate_pkce() -> tuple[str, str]:
    """Generate RFC 7636 code_verifier and SHA-256 code_challenge."""
    raw = secrets.token_bytes(32)
    verifier = _b64url_encode(raw)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = _b64url_encode(digest)
    return verifier, challenge


def seal_oauth_state(data: dict) -> str:
    """Seal OAuth state dict with HMAC-SHA256 signature and timestamp."""
    payload = {
        "d": data,
        "iat": int(time.time()),
        "exp": int(time.time()) + STATE_DURATION_SEC,
    }
    encoded = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(
        settings.session_secret.encode("utf-8"),
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_encoded = _b64url_encode(sig)
    return f"{encoded}.{sig_encoded}"


def unseal_oauth_state(token: str) -> dict | None:
    """Verify and unseal an OAuth state string."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        encoded, sig_encoded = parts
        expected_sig = hmac.new(
            settings.session_secret.encode("utf-8"),
            encoded.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        provided_sig = _b64url_decode(sig_encoded)
        if not hmac.compare_digest(expected_sig, provided_sig):
            log.warning("OAuth state signature mismatch")
            return None
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            log.warning("OAuth state expired")
            return None
        return payload.get("d")
    except Exception as exc:
        log.warning("Failed to unseal oauth state: %s", exc)
        return None


# ─── JWT Session Token (Standard HS256) ───────────────────────────────────────

def create_session_token(user_data: dict, expires_sec: int = SESSION_DURATION_SEC) -> str:
    """Create an RFC 7519 standard signed HS256 JWT session token."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user_data.get("sub") or user_data.get("id") or "user",
        "email": user_data.get("email"),
        "username": user_data.get("username") or user_data.get("preferred_username") or "user",
        "name": user_data.get("name") or user_data.get("displayName") or "User",
        "picture": user_data.get("picture") or user_data.get("avatarUrl"),
        "role": user_data.get("role", "user"),
        "roles": user_data.get("roles") or ([user_data["role"]] if user_data.get("role") else ["user"]),
        "iat": now,
        "exp": now + expires_sec,
    }
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    msg = f"{h_b64}.{p_b64}"
    sig = hmac.new(
        settings.session_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{msg}.{_b64url_encode(sig)}"


def verify_session_token(token: str) -> dict | None:
    """Verify and decode standard HS256 JWT session token."""
    if not token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h_b64, p_b64, sig_b64 = parts
        msg = f"{h_b64}.{p_b64}"
        expected_sig = hmac.new(
            settings.session_secret.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            log.debug("Session signature mismatch")
            return None
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            log.debug("Session token expired")
            return None
        return payload
    except Exception as exc:
        log.debug("Session token verification failed: %s", exc)
        return None


# ─── Cookie Helpers ───────────────────────────────────────────────────────────

def set_session_cookie(response: Response, token: str, is_secure: bool = False):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_DURATION_SEC,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
    )


def clear_session_cookie(response: Response, is_secure: bool = False):
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_secure,
    )


# ─── Axiom OAuth Client ───────────────────────────────────────────────────────

def get_redirect_uri(request: Request) -> str:
    """Compute callback URL matching current host scheme."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or f"{settings.host}:{settings.port}"
    proto = request.headers.get("x-forwarded-proto")
    if not proto:
        proto = "https" if request.url.scheme == "https" or (not host.startswith("127.0.0.1") and not host.startswith("localhost")) else "http"
    return f"{proto}://{host}/auth/callback"


def build_axiom_authorize_url(
    redirect_uri: str,
    state: str,
    code_challenge: str,
    prompt: str | None = None,
) -> str:
    """Build Axiom /oauth/authorize redirect URL."""
    base_url = settings.axiom_url.rstrip("/")
    params = {
        "client_id": settings.axiom_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email offline_access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if prompt:
        params["prompt"] = prompt
    return f"{base_url}/oauth/authorize?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict:
    """Exchange authorization code at Axiom /api/oauth/token."""
    token_url = f"{settings.axiom_url.rstrip('/')}/api/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.axiom_client_id,
        "client_secret": settings.axiom_client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data=payload)
        if resp.status_code >= 400:
            err_data = {}
            try:
                err_data = resp.json()
            except Exception:
                pass
            err_msg = err_data.get("error_description") or err_data.get("error") or resp.text
            raise RuntimeError(f"Axiom token exchange failed ({resp.status_code}): {err_msg}")
        return resp.json()


async def fetch_userinfo(access_token: str) -> dict:
    """Query Axiom /api/oauth/userinfo for user profile claims."""
    userinfo_url = f"{settings.axiom_url.rstrip('/')}/api/oauth/userinfo"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code >= 400:
            log.warning("Userinfo fetch failed: %s", resp.text)
            return {}
        return resp.json()


# ─── Auth Guards & Extractors ─────────────────────────────────────────────────

def get_user_from_request(request: Request) -> dict | None:
    """Extract authenticated user payload from cookies or Authorization header."""
    user = None
    # 1. Check HttpOnly cookie
    cookie_token = request.cookies.get(COOKIE_NAME)
    if cookie_token:
        user = verify_session_token(cookie_token)

    # 2. Check Bearer Authorization header
    if not user:
        auth_hdr = request.headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            bearer_token = auth_hdr[7:].strip()
            user = verify_session_token(bearer_token)

    # 3. Check query param for direct token handshakes
    if not user:
        query_token = request.query_params.get("token")
        if query_token:
            user = verify_session_token(query_token)

    if user:
        # Dynamically evaluate superadmin status to transparently update stale tokens
        is_superadmin(user)
        return user

    if settings.auth_mode == "none":
        return {
            "sub": "local-owner",
            "id": "local-owner",
            "name": settings.user_name or "Friend",
            "username": (settings.user_name or "owner").lower(),
            "email": settings.user_email or "owner@local",
            "role": "superadmin",
            "roles": ["superadmin"],
            "permissions": ["all:manage"],
        }

    return None


def get_user_from_websocket(websocket: WebSocket) -> dict | None:
    """Extract authenticated user payload from WebSocket connection."""
    user = None
    # 1. Check cookies
    cookie_token = websocket.cookies.get(COOKIE_NAME)
    if cookie_token:
        user = verify_session_token(cookie_token)

    # 2. Check query param
    if not user:
        query_token = websocket.query_params.get("token")
        if query_token:
            user = verify_session_token(query_token)

    # 3. Check headers
    if not user:
        auth_hdr = websocket.headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            user = verify_session_token(auth_hdr[7:].strip())

    if user:
        is_superadmin(user)
        return user

    if settings.auth_mode == "none":
        return {
            "sub": "local-owner",
            "id": "local-owner",
            "name": settings.user_name or "Friend",
            "username": (settings.user_name or "owner").lower(),
            "email": settings.user_email or "owner@local",
            "role": "superadmin",
            "roles": ["superadmin"],
            "permissions": ["all:manage"],
        }

    return None


def is_superadmin(user: dict | None) -> bool:
    """Check if the user has super admin permissions."""
    if settings.auth_mode == "none":
        if isinstance(user, dict):
            user["role"] = "superadmin"
            user["roles"] = ["superadmin"]
        return True

    if not user or not isinstance(user, dict):
        return False

    # 1. Check direct role claims in session token
    role = str(user.get("role", "")).strip().lower()
    if role in {"superadmin", "super_admin", "super-admin", "super admin"}:
        return True
    roles = user.get("roles")
    if isinstance(roles, list):
        if any(str(r).strip().lower() in {"superadmin", "super_admin", "super-admin", "super admin"} for r in roles):
            return True
    perms = user.get("permissions")
    if isinstance(perms, list):
        if "all:manage" in perms:
            return True

    # 2. Check Axiom database directly if role was missing or stale ("user")
    sub = user.get("sub") or user.get("id")
    email = str(user.get("email", "")).strip().lower()
    username = str(user.get("username", "")).strip().lower()

    for ident in filter(None, [sub, email, username]):
        db_role = query_axiom_role(ident)
        if db_role:
            if db_role in {"superadmin", "super_admin", "super-admin", "super admin"}:
                user["role"] = "superadmin"
                user["roles"] = ["superadmin"]
                return True
            else:
                return False

    # 3. Check known superadmin owner identities (fallback)
    configured_emails = {e.lower() for e in settings.superadmin_emails}
    if settings.user_email:
        configured_emails.add(settings.user_email.lower())
    configured_usernames = {u.lower() for u in settings.superadmin_usernames}
    if settings.user_name:
        configured_usernames.add(settings.user_name.lower())
    if (email and email in configured_emails) or (username and username in configured_usernames):
        user["role"] = "superadmin"
        user["roles"] = ["superadmin"]
        return True

    return False


def require_auth(request: Request) -> dict:
    """FastAPI dependency: require authenticated user or raise 401."""
    user = get_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Sign in with Axiom.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_superadmin(request: Request) -> dict:
    """FastAPI dependency: require authenticated user with Axiom super admin perms."""
    user = require_auth(request)
    if not is_superadmin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have perms to access this.",
        )
    return user

