"""Zenith — Integration API Routes.

FastAPI router for OAuth integration flows (Figma, Canva).
Handles authorization redirects, OAuth callbacks, connection management,
and status queries. Mounted at /api/integrations/ in main.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import httpx

from ..core.config import settings
from .models import IntegrationDB
from . import security

log = logging.getLogger("zenith.integrations.routes")

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def _db() -> IntegrationDB:
    return IntegrationDB(settings.db_path)


# ── Status ───────────────────────────────────────────────────────────────────

@router.get("/status")
async def integration_status():
    """Get the connection status of all integrations."""
    db = _db()
    return {
        "integrations": db.list_connections(),
        "figma_configured": bool(settings.figma_client_id),
        "canva_configured": bool(settings.canva_client_id),
        "github_configured": bool(settings.github_user or getattr(settings, "github_token", "")),
        "cloudflare_configured": bool(getattr(settings, "cloudflare_api_token", "")),
    }



# ── Figma OAuth ──────────────────────────────────────────────────────────────

@router.get("/figma/authorize")
async def figma_authorize():
    """Generate and redirect to Figma OAuth authorization URL."""
    cid = getattr(settings, "figma_client_id", "") or ""
    if not cid or cid == "figma_client_id_placeholder":
        return JSONResponse({
            "need_config": True,
            "provider": "figma",
            "name": "Figma",
            "dev_url": "https://www.figma.com/developers/apps",
            "redirect_uri": getattr(settings, "figma_redirect_uri", "") or "http://localhost:8005/api/integrations/figma/callback",
            "fields": [
                {"key": "FIGMA_CLIENT_ID", "label": "Figma Client ID", "placeholder": "Paste your Figma App Client ID"},
                {"key": "FIGMA_CLIENT_SECRET", "label": "Figma Client Secret", "placeholder": "Paste your Figma App Client Secret"}
            ],
            "instructions": "Figma requires an official OAuth 2.0 Client ID. Create a free app at the Figma Developer Console with Redirect URI: http://localhost:8005/api/integrations/figma/callback"
        })

    from .figma.oauth import get_authorize_url

    state = security.generate_state()
    security.store_oauth_state(
        settings.db_path, state, "figma", user_id="local"
    )

    auth_url = get_authorize_url(state)
    return JSONResponse({"url": auth_url})


@router.get("/figma/callback")
async def figma_callback(code: str = "", state: str = "", error: str = ""):
    """Handle Figma OAuth callback after user authorization."""
    if error:
        log.warning("Figma OAuth error: %s", error)
        return _oauth_result_page("Figma", success=False, message=f"Authorization denied: {error}")

    if not code or not state:
        return _oauth_result_page("Figma", success=False, message="Missing authorization code or state.")

    # Validate state
    validation = security.validate_and_consume_state(settings.db_path, state, "figma")
    if not validation["valid"]:
        return _oauth_result_page("Figma", success=False, message=validation["error"])

    # Exchange code for tokens
    try:
        from .figma.oauth import exchange_code

        token_data = await exchange_code(code)
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 0)

        expires_at = ""
        if expires_in:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat()

        # Get user info
        provider_user_id = ""
        provider_user_name = ""
        try:
            from .figma.client import FigmaClient
            client = FigmaClient(access_token)
            me = await client.get_me()
            provider_user_id = str(me.get("id", ""))
            provider_user_name = me.get("handle", me.get("email", ""))
        except Exception:
            pass

        # Store connection
        db = _db()
        db.upsert_connection(
            provider="figma",
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
            scopes=token_data.get("scope", "current_user:read,file_content:read"),
            provider_user_id=provider_user_id,
            provider_user_name=provider_user_name,
        )

        return _oauth_result_page("Figma", success=True, message=f"Connected as {provider_user_name or 'Figma user'}")

    except Exception as exc:
        log.error("Figma OAuth callback error: %s", exc)
        return _oauth_result_page("Figma", success=False, message=str(exc))


@router.post("/figma/disconnect")
async def figma_disconnect():
    """Disconnect Figma integration."""
    db = _db()
    deleted = db.delete_connection("figma")
    return {"ok": deleted, "message": "Figma disconnected" if deleted else "No Figma connection found"}


@router.get("/figma/user")
async def figma_user_info():
    """Get connected Figma user info."""
    from .figma import service
    return await service.get_user_info()


# ── Canva OAuth ──────────────────────────────────────────────────────────────

@router.get("/canva/authorize")
async def canva_authorize():
    """Generate and redirect to Canva OAuth authorization URL with PKCE."""
    cid = getattr(settings, "canva_client_id", "") or ""
    if not cid or cid == "canva_client_id_placeholder":
        return JSONResponse({
            "need_config": True,
            "provider": "canva",
            "name": "Canva",
            "dev_url": "https://www.canva.dev/",
            "redirect_uri": getattr(settings, "canva_redirect_uri", "") or "http://localhost:8005/api/integrations/canva/callback",
            "fields": [
                {"key": "CANVA_CLIENT_ID", "label": "Canva Client ID", "placeholder": "Paste your Canva Client ID"},
                {"key": "CANVA_CLIENT_SECRET", "label": "Canva Client Secret", "placeholder": "Paste your Canva Client Secret"}
            ],
            "instructions": "Canva requires an official OAuth 2.0 Client ID with PKCE. Create a free integration in the Canva Developer Portal with Redirect URI: http://localhost:8005/api/integrations/canva/callback"
        })

    from .canva.oauth import get_authorize_url

    state = security.generate_state()
    code_verifier, code_challenge = security.generate_pkce_pair()

    security.store_oauth_state(
        settings.db_path, state, "canva",
        user_id="local", pkce_verifier=code_verifier,
    )

    auth_url = get_authorize_url(state, code_challenge)
    return JSONResponse({"url": auth_url})


@router.get("/canva/callback")
async def canva_callback(code: str = "", state: str = "", error: str = ""):
    """Handle Canva OAuth callback with PKCE verification."""
    if error:
        log.warning("Canva OAuth error: %s", error)
        return _oauth_result_page("Canva", success=False, message=f"Authorization denied: {error}")

    if not code or not state:
        return _oauth_result_page("Canva", success=False, message="Missing authorization code or state.")

    # Validate state and retrieve PKCE verifier
    validation = security.validate_and_consume_state(settings.db_path, state, "canva")
    if not validation["valid"]:
        return _oauth_result_page("Canva", success=False, message=validation["error"])

    pkce_verifier = validation.get("pkce_verifier", "")
    if not pkce_verifier:
        return _oauth_result_page("Canva", success=False, message="PKCE verifier not found. Please try connecting again.")

    # Exchange code + verifier for tokens
    try:
        from .canva.oauth import exchange_code

        token_data = await exchange_code(code, pkce_verifier)
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 0)

        expires_at = ""
        if expires_in:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat()

        # Get user info
        provider_user_id = ""
        provider_user_name = ""
        try:
            from .canva.client import CanvaClient
            client = CanvaClient(access_token)
            profile = await client.get_user_profile()
            provider_user_id = str(profile.get("user", {}).get("id", ""))
            provider_user_name = profile.get("user", {}).get("display_name", "")
        except Exception:
            pass

        # Store connection
        db = _db()
        db.upsert_connection(
            provider="canva",
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
            scopes=token_data.get("scope", "design:content:read design:meta:read profile:read"),
            provider_user_id=provider_user_id,
            provider_user_name=provider_user_name,
        )

        return _oauth_result_page("Canva", success=True, message=f"Connected as {provider_user_name or 'Canva user'}")

    except Exception as exc:
        log.error("Canva OAuth callback error: %s", exc)
        return _oauth_result_page("Canva", success=False, message=str(exc))


@router.post("/canva/disconnect")
async def canva_disconnect():
    """Disconnect Canva integration."""
    db = _db()
    deleted = db.delete_connection("canva")
    return {"ok": deleted, "message": "Canva disconnected" if deleted else "No Canva connection found"}


@router.get("/canva/user")
async def canva_user_info():
    """Get connected Canva user info."""
    from .canva import service
    return await service.get_user_info()


# ── GitHub Integration ───────────────────────────────────────────────────────

@router.get("/github/authorize")
async def github_authorize():
    """Generate and redirect to GitHub OAuth authorization URL."""
    cid = getattr(settings, "github_client_id", "") or ""
    if not cid or cid == "github_client_id_placeholder":
        return JSONResponse({
            "need_config": True,
            "provider": "github",
            "name": "GitHub",
            "dev_url": "https://github.com/settings/developers",
            "fields": [
                {"key": "GITHUB_CLIENT_ID", "label": "Client ID", "placeholder": "Enter GitHub OAuth App Client ID"},
                {"key": "GITHUB_CLIENT_SECRET", "label": "Client Secret", "placeholder": "Enter GitHub OAuth App Client Secret"}
            ],
            "instructions": "GitHub requires an OAuth App for simple sign-in. Create a free OAuth App in Developer Settings with Authorization callback URL: http://localhost:8005/api/integrations/github/callback"
        })

    state = security.generate_state()
    security.store_oauth_state(settings.db_path, state, "github", user_id="local")
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "state": state,
        "scope": "repo,read:user",
    }
    from urllib.parse import urlencode
    auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    return JSONResponse({"url": auth_url})


@router.get("/github/callback")
async def github_callback(code: str = "", state: str = "", error: str = ""):
    """Handle GitHub OAuth callback."""
    if error:
        return _oauth_result_page("GitHub", success=False, message=f"Authorization denied: {error}")
    if not code or not state:
        return _oauth_result_page("GitHub", success=False, message="Missing authorization code or state.")

    validation = security.validate_and_consume_state(settings.db_path, state, "github")
    if not validation["valid"]:
        return _oauth_result_page("GitHub", success=False, message=validation["error"])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            token_data = resp.json()
            access_token = token_data.get("access_token", "")
            if not access_token:
                raise RuntimeError(f"GitHub token exchange failed: {resp.text[:200]}")

            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json", "User-Agent": "Zenith-AI"},
            )
            gh_user = user_resp.json()
            username = gh_user.get("login", "")
            display_name = gh_user.get("name") or username

        db = _db()
        db.upsert_connection(
            provider="github",
            access_token=access_token,
            provider_user_id=username,
            provider_user_name=display_name,
            scopes="repo,read:user",
        )

        from ..core import setup
        setup.save_configuration({
            "GITHUB_USER": username,
            "GITHUB_TOKEN": access_token,
        })

        return _oauth_result_page("GitHub", success=True, message=f"Connected as {display_name} (@{username})")
    except Exception as exc:
        log.error("GitHub OAuth callback error: %s", exc)
        return _oauth_result_page("GitHub", success=False, message=str(exc))


@router.post("/github/connect")
async def github_connect(req: Request):
    """Connect GitHub using token, verify via GitHub API, save credentials."""
    try:
        body = await req.json()
        token = body.get("token", "").strip()
        username = body.get("username", "").strip()
        if not token:
            return JSONResponse({"error": "GitHub Personal Access Token is required"}, status_code=400)

        # Verify token with GitHub API
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Zenith-AI",
                },
            )
            if resp.status_code == 200:
                gh_user = resp.json()
                username = gh_user.get("login", username)
                display_name = gh_user.get("name") or username
            else:
                log.warning("GitHub API verification returned HTTP %d, storing token", resp.status_code)
                display_name = username or "GitHub User"

        db = _db()
        db.upsert_connection(
            provider="github",
            access_token=token,
            provider_user_id=username,
            provider_user_name=display_name,
            scopes="repo,read:user",
        )

        from ..core import setup
        setup.save_configuration({
            "GITHUB_USER": username,
            "GITHUB_TOKEN": token,
        })

        return {
            "ok": True,
            "username": username,
            "token": token,
            "message": f"Successfully connected GitHub as {username}",
        }
    except Exception as exc:
        log.error("GitHub connect error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/github/disconnect")
async def github_disconnect():
    """Disconnect GitHub integration and clear stored credentials."""
    db = _db()
    deleted = db.delete_connection("github")
    from ..core import setup
    setup.save_configuration({
        "GITHUB_USER": "",
        "GITHUB_TOKEN": "",
    })
    return {"ok": True, "message": "GitHub disconnected"}


# ── Cloudflare Integration ────────────────────────────────────────────────────

@router.get("/cloudflare/authorize")
async def cloudflare_authorize():
    """Generate and redirect to Cloudflare authorization URL."""
    cid = getattr(settings, "cloudflare_client_id", "") or ""
    if not cid or cid == "cloudflare_client_id_placeholder":
        return JSONResponse({
            "need_config": True,
            "provider": "cloudflare",
            "name": "Cloudflare",
            "dev_url": "https://dash.cloudflare.com/?to=/:account/oauth-apps",
            "fields": [
                {"key": "CLOUDFLARE_CLIENT_ID", "label": "Client ID", "placeholder": "Enter Cloudflare OAuth App Client ID"},
                {"key": "CLOUDFLARE_CLIENT_SECRET", "label": "Client Secret", "placeholder": "Enter Cloudflare OAuth App Client Secret"}
            ],
            "instructions": "Cloudflare requires an OAuth App for simple sign-in. Create one in Cloudflare Account Settings -> OAuth Apps with Authorization callback URL: http://localhost:8005/api/integrations/cloudflare/callback"
        })

    state = security.generate_state()
    security.store_oauth_state(settings.db_path, state, "cloudflare", user_id="local")
    params = {
        "client_id": settings.cloudflare_client_id,
        "redirect_uri": settings.cloudflare_redirect_uri,
        "state": state,
        "response_type": "code",
        "scope": "account:read,zone:read,dns:edit",
    }
    from urllib.parse import urlencode
    auth_url = f"https://dash.cloudflare.com/oauth2/auth?{urlencode(params)}"
    return JSONResponse({"url": auth_url})


@router.get("/cloudflare/callback")
async def cloudflare_callback(code: str = "", state: str = "", error: str = ""):
    """Handle Cloudflare OAuth callback."""
    if error:
        return _oauth_result_page("Cloudflare", success=False, message=f"Authorization denied: {error}")
    if not code or not state:
        return _oauth_result_page("Cloudflare", success=False, message="Missing authorization code or state.")

    validation = security.validate_and_consume_state(settings.db_path, state, "cloudflare")
    if not validation["valid"]:
        return _oauth_result_page("Cloudflare", success=False, message=validation["error"])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://dash.cloudflare.com/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.cloudflare_client_id,
                    "client_secret": settings.cloudflare_client_secret,
                    "code": code,
                    "redirect_uri": settings.cloudflare_redirect_uri,
                },
            )
            token_data = resp.json()
            access_token = token_data.get("access_token", "")
            if not access_token:
                raise RuntimeError(f"Cloudflare token exchange failed: {resp.text[:200]}")

            zone_name = ""
            z_resp = await client.get(
                "https://api.cloudflare.com/client/v4/zones?per_page=1",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if z_resp.status_code == 200:
                zones = z_resp.json().get("result", [])
                if zones:
                    zone_name = zones[0].get("name", "")

        db = _db()
        db.upsert_connection(
            provider="cloudflare",
            access_token=access_token,
            provider_user_id=zone_name or "cloudflare_account",
            provider_user_name=zone_name or "Cloudflare Managed Domain",
            scopes="zone:read,dns:edit",
        )

        from ..core import setup
        setup.save_configuration({
            "CLOUDFLARE_API_TOKEN": access_token,
            "CLOUDFLARE_ZONE": zone_name,
        })

        return _oauth_result_page("Cloudflare", success=True, message=f"Connected Cloudflare ({zone_name or 'Active'})")
    except Exception as exc:
        log.error("Cloudflare OAuth callback error: %s", exc)
        return _oauth_result_page("Cloudflare", success=False, message=str(exc))

@router.post("/cloudflare/connect")
async def cloudflare_connect(req: Request):
    """Connect Cloudflare using API token, verify, auto-detect zone, save credentials."""
    try:
        body = await req.json()
        token = body.get("token", "").strip()
        zone = body.get("zone", "").strip()
        if not token:
            return JSONResponse({"error": "Cloudflare API Token is required"}, status_code=400)

        # Verify token and auto-detect zone
        async with httpx.AsyncClient(timeout=15) as client:
            if not zone:
                z_resp = await client.get(
                    "https://api.cloudflare.com/client/v4/zones?per_page=1",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if z_resp.status_code == 200:
                    z_data = z_resp.json()
                    zones = z_data.get("result", [])
                    if zones:
                        zone = zones[0].get("name", "")

        db = _db()
        db.upsert_connection(
            provider="cloudflare",
            access_token=token,
            provider_user_id=zone or "cloudflare_user",
            provider_user_name=zone or "Cloudflare Account",
            scopes="zone:read,dns:edit",
        )

        from ..core import setup
        setup.save_configuration({
            "CLOUDFLARE_API_TOKEN": token,
            "CLOUDFLARE_ZONE": zone,
        })

        return {
            "ok": True,
            "zone": zone,
            "token": token,
            "message": f"Successfully connected Cloudflare ({zone or 'Active'})",
        }
    except Exception as exc:
        log.error("Cloudflare connect error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/cloudflare/disconnect")
async def cloudflare_disconnect():
    """Disconnect Cloudflare integration and clear stored credentials."""
    db = _db()
    deleted = db.delete_connection("cloudflare")
    from ..core import setup
    setup.save_configuration({
        "CLOUDFLARE_API_TOKEN": "",
        "CLOUDFLARE_ZONE": "",
    })
    return {"ok": True, "message": "Cloudflare disconnected"}


# ── OAuth Result Page ────────────────────────────────────────────────────────


def _oauth_result_page(provider: str, success: bool, message: str) -> HTMLResponse:
    """Render a self-closing OAuth result page."""
    icon = "✓" if success else "✗"
    color = "#4ade80" if success else "#f87171"
    status = "Connected" if success else "Error"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zenith — {provider} {status}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            background: #0a0a0f; color: #e4e4e7; font-family: 'Inter', -apple-system, sans-serif;
        }}
        .card {{
            text-align: center; padding: 48px; border-radius: 20px;
            background: rgba(24, 24, 32, 0.9); border: 1px solid rgba(255,255,255,0.08);
            backdrop-filter: blur(24px); max-width: 440px;
        }}
        .icon {{ font-size: 48px; color: {color}; margin-bottom: 16px; }}
        h2 {{ font-size: 22px; font-weight: 600; margin-bottom: 8px; }}
        p {{ font-size: 14px; color: #a1a1aa; margin-bottom: 24px; line-height: 1.5; }}
        .msg {{ color: {color}; font-weight: 500; }}
        .btn {{
            display: inline-block; padding: 10px 24px; border-radius: 10px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff;
            text-decoration: none; font-weight: 500; font-size: 14px; cursor: pointer;
            border: none; transition: opacity .2s;
        }}
        .btn:hover {{ opacity: 0.85; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">{icon}</div>
        <h2>{provider} {status}</h2>
        <p class="msg">{message}</p>
        <p>This window will close automatically, or you can close it manually.</p>
        <button class="btn" onclick="window.close(); window.location='/';">Return to Zenith</button>
    </div>
    <script>
        // Notify the opener window about the result
        if (window.opener) {{
            try {{
                window.opener.postMessage({{
                    type: 'zenith-oauth-callback',
                    provider: '{provider.lower()}',
                    success: {'true' if success else 'false'},
                    message: '{message.replace("'", "\\'")}'
                }}, '*');
            }} catch(e) {{}}
        }}
        // Auto-close after 3 seconds on success
        {'setTimeout(() => { try { window.close(); } catch(e) {} }, 3000);' if success else ''}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)
