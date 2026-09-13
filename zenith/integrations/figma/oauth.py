"""Figma OAuth 2.0 flow implementation.

Endpoints per https://developers.figma.com/docs/rest-api/oauth-apps/:
  Authorization: GET https://www.figma.com/oauth
  Token exchange: POST https://www.figma.com/api/oauth/token
  Token refresh:  POST https://www.figma.com/api/oauth/refresh
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from ...core.config import settings

log = logging.getLogger("zenith.integrations.figma.oauth")

FIGMA_AUTH_URL = "https://www.figma.com/oauth"
FIGMA_TOKEN_URL = "https://www.figma.com/api/oauth/token"
FIGMA_REFRESH_URL = "https://www.figma.com/api/oauth/refresh"

# Minimum scopes for the features we implement
DEFAULT_SCOPES = "current_user:read,file_content:read"


def get_authorize_url(state: str, scopes: str = "") -> str:
    """Build the Figma OAuth authorization URL."""
    client_id = settings.figma_client_id or "zenith_figma_app"
    redirect_uri = settings.figma_redirect_uri or "http://localhost:8005/api/integrations/figma/callback"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes or DEFAULT_SCOPES,
        "state": state,
        "response_type": "code",
    }
    return f"{FIGMA_AUTH_URL}?{urlencode(params)}"


def generate_auth_url(scopes: str = "") -> tuple[str, str]:
    """Generate a random state parameter and return (authorize_url, state)."""
    from ..security import generate_state
    state = generate_state()
    url = get_authorize_url(state, scopes)
    return url, state



async def exchange_code(code: str, redirect_uri: str = "") -> dict:
    """Exchange an authorization code for access and refresh tokens.

    Returns dict with keys: access_token, refresh_token, expires_in, user_id.
    Raises on HTTP or protocol errors.
    """
    data = {
        "client_id": settings.figma_client_id,
        "client_secret": settings.figma_client_secret,
        "redirect_uri": redirect_uri or settings.figma_redirect_uri,
        "code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(FIGMA_TOKEN_URL, data=data)

    if resp.status_code != 200:
        log.error("Figma token exchange failed: status=%d", resp.status_code)
        raise RuntimeError(
            f"Figma token exchange failed (HTTP {resp.status_code}): "
            f"{resp.text[:200]}"
        )

    result = resp.json()
    if "access_token" not in result:
        raise RuntimeError(f"Figma token response missing access_token: {resp.text[:200]}")

    log.info("Figma token exchange successful")
    return result


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired Figma access token.

    Returns dict with keys: access_token, expires_in.
    """
    data = {
        "client_id": settings.figma_client_id,
        "client_secret": settings.figma_client_secret,
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(FIGMA_REFRESH_URL, data=data)

    if resp.status_code != 200:
        log.error("Figma token refresh failed: status=%d", resp.status_code)
        raise RuntimeError(
            f"Figma token refresh failed (HTTP {resp.status_code}): "
            f"{resp.text[:200]}"
        )

    result = resp.json()
    if "access_token" not in result:
        raise RuntimeError("Figma refresh response missing access_token")

    log.info("Figma token refresh successful")
    return result
