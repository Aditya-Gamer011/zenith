"""Canva Connect OAuth 2.0 with PKCE (S256) implementation.

Endpoints per https://www.canva.dev/docs/connect/authentication/:
  Authorization: GET  https://www.canva.com/api/oauth/authorize
  Token exchange: POST https://api.canva.com/rest/v1/oauth/token
  Token refresh:  POST https://api.canva.com/rest/v1/oauth/token
"""
from __future__ import annotations

import base64
import logging
from urllib.parse import urlencode

import httpx

from ...core.config import settings

log = logging.getLogger("zenith.integrations.canva.oauth")

CANVA_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"

# Minimum scopes for the features we implement
DEFAULT_SCOPES = "design:content:read design:meta:read profile:read"


def _basic_auth_header() -> str:
    """Build Basic auth header from client credentials."""
    creds = f"{settings.canva_client_id}:{settings.canva_client_secret}"
    encoded = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


def get_authorize_url(state: str, code_challenge: str, scopes: str = "") -> str:
    """Build the Canva OAuth authorization URL with PKCE challenge."""
    client_id = settings.canva_client_id or "zenith_canva_app"
    redirect_uri = settings.canva_redirect_uri or "http://localhost:8005/api/integrations/canva/callback"
    params = {
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": scopes or DEFAULT_SCOPES,
        "response_type": "code",
        "client_id": client_id,
        "state": state,
        "redirect_uri": redirect_uri,
    }
    return f"{CANVA_AUTH_URL}?{urlencode(params)}"


def generate_auth_url(scopes: str = "") -> tuple[str, str, str]:
    """Generate state + PKCE pair and return (authorize_url, state, code_verifier)."""
    from ..security import generate_state, generate_pkce_pair
    state = generate_state()
    code_verifier, code_challenge = generate_pkce_pair()
    url = get_authorize_url(state, code_challenge, scopes)
    return url, state, code_verifier



async def exchange_code(
    code: str, code_verifier: str, redirect_uri: str = ""
) -> dict:
    """Exchange an authorization code + PKCE verifier for tokens.

    Returns dict with keys: access_token, refresh_token, token_type, expires_in, scope.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri or settings.canva_redirect_uri,
    }
    headers = {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(CANVA_TOKEN_URL, data=data, headers=headers)

    if resp.status_code != 200:
        log.error("Canva token exchange failed: status=%d", resp.status_code)
        raise RuntimeError(
            f"Canva token exchange failed (HTTP {resp.status_code}): "
            f"{resp.text[:200]}"
        )

    result = resp.json()
    if "access_token" not in result:
        raise RuntimeError(f"Canva token response missing access_token: {resp.text[:200]}")

    log.info("Canva token exchange successful")
    return result


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired Canva access token.

    Returns dict with keys: access_token, refresh_token, token_type, expires_in, scope.
    """
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    headers = {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(CANVA_TOKEN_URL, data=data, headers=headers)

    if resp.status_code != 200:
        log.error("Canva token refresh failed: status=%d", resp.status_code)
        raise RuntimeError(
            f"Canva token refresh failed (HTTP {resp.status_code}): "
            f"{resp.text[:200]}"
        )

    result = resp.json()
    if "access_token" not in result:
        raise RuntimeError("Canva refresh response missing access_token")

    log.info("Canva token refresh successful")
    return result
