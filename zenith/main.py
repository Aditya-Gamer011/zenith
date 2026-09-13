"""Zenith — FastAPI application.

Web layer: REST endpoints + WebSocket for live chats. Kept deliberately slim —
the Orchestrator holds the intelligence, tools hold the skills, and the scheduler
holds proactive work.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from . import __version__
from .core import orchestrator, auth
from .core.config import settings
from .core.proactive import hub, schedule
from .memory import store
from .agents.runner import runner
from .tools.browser import _engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("zenith.app")

_orpheus = orchestrator.Orchestrator()
START_TIME = time.time()

# Live WS sessions that can answer confirmation docks. The confirmation hook
# emits on all of them; the WS receive-pump resolves the decision.
_pending_ws: set[asyncio.Queue] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    # Real confirmation checkpoint for mutating tools (the WS pump resolves it).
    from .core import tools as _tool_reg
    from .core.confirmation import confirm_tools

    async def _ask(name: str, args: dict) -> bool:
        # Emit a `confirm` event to every live WS session and wait (bounded)
        # for the UI dock to answer. Auto-refuses on timeout — never wedges.
        try:
            if not _pending_ws:
                return True  # no live session → don't block (tests/daemon paths)
            gate = _orpheus.confirm_gate

            async def _emit(evt: dict):
                sent = False
                for q in list(_pending_ws):
                    try:
                        q.put_nowait(evt)
                        sent = True
                    except Exception:
                        _pending_ws.discard(q)
                return sent

            gate.emit = _emit
            return await gate.request(name, args)
        except Exception:
            return False

    _tool_reg.set_confirmation_hook(_ask)

    # Ensure God's Eye View 3D Earth Observation server is running in background if enabled
    if getattr(settings, "gev_enabled", True):
        from .tools.gods_eye_view import ensure_gev_server_started
        asyncio.create_task(ensure_gev_server_started())

    # scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    sched = AsyncIOScheduler()
    schedule(sched)
    sched.start()
    log.info("Zenith online — %s", __version__)
    yield
    sched.shutdown(wait=False)
    await _engine.close()
    if getattr(settings, "gev_enabled", True):
        from .tools.gods_eye_view import stop_gev_server
        stop_gev_server()


app = FastAPI(title="Zenith", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Integration Routes (Art & Design OAuth) ────────────────────────────────
from .integrations.routes import router as integrations_router
app.include_router(integrations_router)

# ─── Figma Plugin Bridge (WebSocket) ─────────────────────────────────────────
from .integrations.plugin_bridge import router as plugin_bridge_router
app.include_router(plugin_bridge_router)

# ─── Operating Layer Services (Screen, Activity, Mem0, Browser, Vision, Privacy) ───
from .services.routes import router as services_router
app.include_router(services_router)


# ─── Authentication Routes (Zero-Auth Standalone Mode) ───────────────────────

@app.get("/auth/login")
async def auth_login(return_to: str = "/"):
    """Standalone mode: redirect directly to root — zero login friction."""
    target = return_to if return_to.startswith("/") else "/"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


@app.get("/auth/callback")
async def auth_callback():
    """Standalone mode: redirect directly to root."""
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@app.get("/auth/logout")
@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    """Standalone mode: sign out confirmation."""
    if request.method == "POST":
        return JSONResponse({"ok": True, "message": "Signed out successfully"})
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@app.get("/api/auth/me")
@app.get("/api/auth/session")
async def auth_session(request: Request):
    """Return local owner user claims (zero friction, full owner access)."""
    user_name = settings.user_name or "Friend"
    user_email = settings.user_email or ""
    return {
        "authenticated": True,
        "is_superadmin": True,
        "user": {
            "id": "owner",
            "email": user_email,
            "username": user_name.lower().replace(" ", "_"),
            "name": user_name,
            "picture": None,
            "role": "owner",
            "roles": ["owner", "superadmin"],
        },
    }


@app.get("/api/auth/config")
async def auth_config():
    """Public auth configuration for client SPA."""
    return {
        "auth_mode": "none",
        "login_url": "/",
    }


@app.post("/api/auth/exchange")
async def auth_exchange():
    """PKCE code exchange stub returning owner session."""
    user_name = settings.user_name or "Friend"
    user_email = settings.user_email or ""
    return JSONResponse({
        "ok": True,
        "is_superadmin": True,
        "user": {
            "id": "owner",
            "email": user_email,
            "name": user_name,
            "username": user_name.lower().replace(" ", "_"),
            "picture": None,
            "role": "owner",
            "roles": ["owner", "superadmin"],
        },
    })


# ─── Setup & Secrets Management Routes ───────────────────────────────────────

@app.get("/api/setup/status")
async def api_setup_status():
    """Check whether Zenith has been onboarded and configured."""
    from .core import setup
    return setup.get_status()


@app.get("/api/setup/config")
async def api_setup_config():
    """Return catalog of configuration options, instructions, and masked values."""
    from .core import setup
    return {
        "status": setup.get_status(),
        "catalog": setup.get_catalog_with_values(),
    }


@app.post("/api/setup/test-key")
async def api_setup_test_key(request: Request):
    """Test a candidate Gemini API key against Google AI Studio API."""
    from .core import setup
    body = await request.json()
    api_key = body.get("gemini_api_key") or body.get("api_key", "")
    return await setup.test_gemini_api_key(api_key)


@app.post("/api/setup/save")
async def api_setup_save(request: Request):
    """Save configuration to .env and reload settings."""
    from .core import setup
    body = await request.json()
    updates = body.get("updates") or {}
    if not isinstance(updates, dict):
        return JSONResponse({"error": "Invalid payload format"}, status_code=400)

    # Ensure a Gemini key is present either in updates or current config
    gemini_key = updates.get("GEMINI_API_KEY") or settings.gemini_api_key
    if not gemini_key:
        return JSONResponse(
            {"error": "Google Gemini API Key is required to power Zenith's intelligence."},
            status_code=400,
        )

    res = setup.save_configuration(updates)
    return res


@app.post("/api/setup/summarize-profile")
async def api_setup_summarize_profile(request: Request):
    """Summarize and store user profile info (name, birthday, hobbies, bio) via LLM and memory store."""
    from .core import setup
    body = await request.json()
    name = str(body.get("name") or "").strip()
    birthday = str(body.get("birthday") or "").strip()
    hobbies = str(body.get("hobbies") or "").strip()
    bio = str(body.get("bio") or "").strip()
    res = await setup.summarize_and_store_profile(
        name=name,
        birthday=birthday,
        hobbies=hobbies,
        bio=bio,
    )
    return res


@app.get("/api/mode")
async def api_get_mode():
    """Get current Zenith operating mode (genesis vs sovereign)."""
    from .tools import ui_customizer
    return ui_customizer.get_current_mode()


@app.post("/api/mode")
async def api_set_mode(request: Request):
    """Switch Zenith operating mode."""
    from .tools import ui_customizer
    body = await request.json()
    mode = body.get("mode", "setup")
    reason = body.get("reason", "")
    msg = await ui_customizer.switch_mode(mode, reason)
    return {"ok": True, "message": msg, "mode": getattr(settings, "zenith_mode", mode)}


@app.get("/api/theme")
async def api_get_theme():
    """Get current UI theme customization state."""
    from .tools import ui_customizer
    return {"info": await ui_customizer.ui_inspect()}


@app.post("/api/theme")
async def api_set_theme(request: Request):
    """Live-customize Zenith UI appearance."""
    from .tools import ui_customizer
    body = await request.json()
    accent = body.get("accent_color", "")
    theme_mode = body.get("theme_mode", "")
    font = body.get("font", "")
    custom_css = body.get("custom_css", "")
    res = await ui_customizer.ui_customize_theme(accent, theme_mode, font, custom_css)
    return {"ok": True, "message": res}


@app.post("/api/theme/reset")
async def api_reset_theme():
    """Reset UI customizations back to defaults."""
    from .tools import ui_customizer
    res = await ui_customizer.ui_reset_theme()
    return {"ok": True, "message": res}


# ─── REST ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    from .tools import system_info
    env_id, env_desc, _ = system_info.detect_environment_type()
    return {
        "status": "ok",
        "system": "Zenith",
        "version": __version__,
        "host": settings.host,
        "os": system_info.get_pretty_os_name(),
        "environment": env_desc,
        "uptime": int(time.time() - START_TIME),
        "memory": store.graph_stats(),
        "allow_shell": settings.allow_shell,
        "docker_socket": bool(settings.docker_socket),
        "integrations": _integration_status(),
    }


def _integration_status() -> dict:
    """One-line per-service capability status for the UI/health."""
    from zenith.tools import mail, integrations

    return {
        "gmail_read": mail._imap_ok(),
        "resend_send": mail._resend_ok(),
        "google_calendar": bool(settings.google_refresh_token),
        "google_maps": bool(settings.google_maps_api_key),
        "cloudflare": bool(settings.cloudflare_token and settings.cloudflare_zone),
        "r2": integ_r2_ok(),
        "vercel": bool(settings.vercel_token),
        "home_assistant": bool(settings.home_assistant_token),
    }



def integ_r2_ok() -> bool:
    return bool(
        settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_endpoint
    )


@app.get("/api/memory")
async def memory():
    return {"memories": store.all_memories(), "graph": store.graph_export()}


@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    """Handle the Gemini-Live OAuth consent redirect: swap ?code= for a refresh
    token carrying the generativelanguage scope, store it, and show a done page.

    The Live WebSocket does NOT accept API/AQ tokens — it needs an OAuth2 access
    token with the Gemini scope. Zenith stores the refresh token here (so the
    token itself can be minted server-side whenever a Live session opens).
    """
    from fastapi.responses import HTMLResponse
    import urllib.parse, re, httpx

    code = request.query_params.get("code") or request.query_params.get("error") or ""
    if query_error := request.query_params.get("error"):
        return HTMLResponse(
            f"<h3>Authorization failed: {query_error}</h3>"
            "<p>Close this tab and try the consent URL again.</p>")

    if not code:
        return HTMLResponse("<h3>No code in callback.</h3>")

    # Exchange the code for a refresh token with the Gemini scope.
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(token_url, data=payload)
        if resp.status_code >= 400:
            return HTMLResponse(f"<h3>Token exchange failed: {resp.text[:200]}</h3>")
        data = resp.json()
        refresh = data.get("refresh_token", "")
        if not refresh:
            return HTMLResponse("<h3>No refresh_token returned — enable 'Cloud OAuth app' + offline access.</h3>")
    except Exception as exc:
        return HTMLResponse(f"<h3>Exchange error: {exc}</h3>")

    # Persist to .env (host path). Keep the calendar token untouched.
    env_path = Path(__file__).resolve().parents[2] / ".env"
    lines = env_path.read_text() if env_path.exists() else ""
    set_line = f"GEMINI_LIVE_REFRESH_TOKEN={refresh}\n"
    if "GEMINI_LIVE_REFRESH_TOKEN=" in lines:
        lines = re.sub(r"(?m)^GEMINI_LIVE_REFRESH_TOKEN=.*\n?", "", lines)
    if lines and not lines.endswith("\n"):
        lines += "\n"
    env_path.write_text(lines + set_line)

    return HTMLResponse(
        "<h3 style='font-family:sans-serif'>✅ Zenith is connected to the Gemini Live API</h3>"
        "<p style='font-family:sans-serif'>Refresh token saved. Restart the container "
        "(<code>docker compose up -d --no-deps zenith</code>) and open Voice — it will use "
        "bidirectional Live audio.</p>"
        "<p style='font-family:sans-serif'>You can close this tab.</p>")


@app.get("/api/state")
async def state():
    """One fetch for the whole command center: memories, reminders, todos,
    events, notes, graph, recent chat history, and Zenith's confirm state."""
    from zenith.tools import reminders, todo, calendar, notes

    return {
        "memories": store.all_memories(),
        "graph": store.graph_export(),
        "reminders": reminders.all_rows(),
        "todos": todo.all_todos(),
        "events": await calendar.upcoming(),
        "notes": notes.all_notes(),
        "history": store.recent_conversation(limit=40),
        "user_name": settings.user_name or "Friend",
        "user_email": settings.user_email,
        "user_timezone": settings.user_timezone,
        "user_bio": settings.user_bio,
        "user_birthday": settings.user_birthday,
        "user_hobbies": settings.user_hobbies,
        "setup_completed": settings.setup_completed,
        "auth_mode": settings.auth_mode,
    }


@app.get("/api/proactive")
async def get_proactive():
    return {"alerts": hub.list()}


@app.get("/api/briefing")
async def briefing():
    """Opening brief — Zenith greets user with a little context on load."""
    from .core.briefing import build_briefing

    return await build_briefing()


@app.post("/api/clear")
async def clear():
    store.init_db()  # reset
    return {"status": "cleared"}


@app.post("/api/upload")
async def upload_file_endpoint(file: Request):
    """Receive a user-uploaded file or image, save it, and return metadata & static URL."""
    from pathlib import Path
    from fastapi import UploadFile, File
    import time

    form = await file.form()
    uploaded_file = form.get("file")
    if not uploaded_file:
        return {"status": "error", "message": "No file uploaded"}

    import tempfile
    uploads_dir = Path(settings.static_dir) / "uploads"
    tmp_dir = Path(tempfile.gettempdir()) / "zenith-files"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())
    orig_name = getattr(uploaded_file, "filename", "file")
    clean_name = f"{ts}_{orig_name.replace(' ', '_')}"

    out_path = uploads_dir / clean_name
    tmp_path = tmp_dir / clean_name

    content = await uploaded_file.read()
    out_path.write_bytes(content)
    tmp_path.write_bytes(content)

    ext = out_path.suffix.lower()
    is_img = ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")

    return {
        "status": "ok",
        "filename": orig_name,
        "saved_name": clean_name,
        "path": str(out_path),
        "url": f"/static/uploads/{clean_name}",
        "size": len(content),
        "is_image": is_img,
    }


@app.post("/api/transcribe")
async def api_transcribe(request: Request):
    """Receive a browser voice recording, transcribe it via the STT provider.

    NEW (Aug 2026): the **primary** path is Gemini Live — a WebSocket that
    accepts the browser speech as ``realtimeInput`` and returns the model's
    spoken reply as **native audio**, so no text STT is produced and no Edge
    TTS is needed (the model speaks). When Live fails or is disabled for any
    reason, we fall back to the classic text path (Groq Whisper → Edge TTS).

    Every credential stays on the server — the browser only ever POSTs raw
    audio to Zenith itself. Uploads are capped on bytes and duration, and temp
    files are removed after recognition.
    """
    from fastapi.responses import Response
    from zenith.voice import live, stt

    form = await request.form()
    uploaded_file = form.get("audio") or form.get("file")
    if not uploaded_file:
        return {"status": "error", "message": "No audio file provided"}

    content = await uploaded_file.read()
    if not content:
        return {"status": "error", "message": "Empty audio file"}
    if len(content) > stt.MAX_AUDIO_BYTES:
        return {"status": "error", "message": "Recording too large"}

    filename = getattr(uploaded_file, "filename", "speech.webm")
    ext = (Path(filename).suffix or ".webm").lstrip(".")

    loop = asyncio.get_running_loop()
    duration = await loop.run_in_executor(None, stt.bytes_to_seconds, content, ext)
    if duration and duration > stt.MAX_AUDIO_SECONDS:
        log.warning("Rejecting %.0fs recording (cap %ds).", duration, stt.MAX_AUDIO_SECONDS)
        return {"status": "error", "message": "Recording too long"}

    # ── Gemini Live (primary, native audio) ─────────────────────────────────
    if live.available():
        turn = await live.live_handle(content, fmt=ext)
        if turn.ok and turn.audio:
            # Return the model's spoken reply as raw audio. media_type is whatever
            # container Gemini chose for the native-audio response (webm/pcm/…).
            return Response(content=turn.audio, media_type=turn.audio_mime,
                            headers={"x-zenith-live": "1",
                                     "x-zenith-model": turn.model,
                                     "x-zenith-audio-mime": turn.audio_mime})
        # Live is configured and reachable but this turn produced no audio (the
        # model silently alternates empty turns). Do NOT fall through to Groq —
        # the user wants Gemini's voice only, and switching voices mid-convo
        # sounds like "a second person". Treat it as "no speech" so the user just
        # says it again. Groq is reserved for when Live is entirely unavailable.
        log.warning("Live turn produced no audio (%s); treating as no speech.",
                    turn.error or "?")
        return {"status": "error", "message": "No speech detected"}

    # ── Classic text path (Groq Whisper → Edge TTS) — Live unavailable ──
    # Only reached when NO Gemini keys/models are configured (live.available() is
    # False). This is the ONLY legitimate Groq route.
    text = await loop.run_in_executor(None, stt.transcribe_audio, content, ext)
    if not text.strip():
        return {"status": "error", "message": "No speech detected"}

    return {"status": "ok", "text": text.strip(), "provider": stt.STT_PROVIDER}


@app.get("/api/tts")
async def api_tts(text: str = "", stream: int = 0):
    """Speak Zenith's reply via the TTS provider (natural, Edge-based default).

    ``stream=1`` returns a chunked ``StreamingResponse`` — Edge TTS yields audio
    sentence-chunks as they synthesize, so the browser can start playback while
    the rest is still generated (much lower time-to-first-audio). One-shot mode
    (default) collects the full MP3 in memory and returns it in one response.
    Audio is never stored.
    """
    from fastapi.responses import Response, StreamingResponse
    from zenith.voice import tts

    if not text.strip():
        return Response(content=b"", media_type="audio/mpeg", status_code=400)

    if stream:
        async def _gen():
            async for chunk in tts.synthesize_stream(text):
                yield chunk
        return StreamingResponse(_gen(), media_type="audio/mpeg")

    loop = asyncio.get_running_loop()
    mp3_bytes = await loop.run_in_executor(None, tts.synthesize, text)

    if not mp3_bytes:
        return {"status": "error", "message": "TTS unavailable"}

    return Response(content=mp3_bytes, media_type="audio/mpeg")


@app.get("/api/voice/status")
async def api_voice_status():
    """Capability flags + live-conversation tuning for the voice UI.

    The client reads VAD/silence thresholds from here so the conversation feels
    natural (pause detection, utterance cap) without hard-coding constants.
    """
    from zenith.voice import live, stt, tts

    stt_ok = stt.available()
    return {
        "live_provider": "gemini-live",
        "live_ready": live.available(),
        "live_models": live.configured_models(),
        "stt_provider": stt.STT_PROVIDER,
        "stt_ready": stt_ok,
        "stt_reason": stt.reason_configured(),
        "stt_language": stt.STT_LANGUAGE,
        "tts_ready": True,
        "tts_provider": tts.provider_name(),
        "tts_stream": True,
        # Live-conversation tuning (ms). The client adjusts its VAD to these.
        "silence_ms": int(os.getenv("VOICE_SILENCE_MS", "700")),
        "min_speech_ms": int(os.getenv("VOICE_MIN_SPEECH_MS", "200")),
        "max_utterance_ms": int(os.getenv("VOICE_MAX_UTTERANCE_MS", "20000")),
        "echo_cancel": True,
        "noise_suppress": True,
        "auto_gain": True,
    }


@app.get("/api/agents")
async def agents():
    runs = runner.list()
    return {"agents": [{"id": r.id, "name": r.name, "status": r.status,
                        "goal": r.goal,
                        "steps": len(r.steps),
                        "recent": r.steps[-4:],
                        "result": r.result[:400]} for r in runs]}


@app.get("/api/fleet")
async def fleet():
    """Compact container status for the UI status strip. Read-only."""
    from zenith.tools.homelab import docker_table

    try:
        text = await docker_table()
    except Exception as exc:
        return {"containers": [], "error": str(exc)}
    containers = []
    for line in text.splitlines():
        parts = line.split("  ")
        if not parts[0].strip():
            continue
        name = parts[0].strip()
        state = (parts[1].strip() if len(parts) > 1 else "").rstrip()
        image = (parts[2].strip() if len(parts) > 2 else "")[:40]
        containers.append({
            "name": name,
            "state": state,
            "image": image,
            "up": state.startswith("running"),
        })
    return {"containers": containers}


@app.get("/api/docker/table")
async def docker_table_api():
    """Raw table string — legacy UI hook, kept for the chat-only flow."""
    from zenith.tools.homelab import docker_table

    return {"text": await docker_table()}


@app.get("/api/tools")
async def tools():
    return {"tools": sorted(orchestrator.tool_names().split(", "))}


# ─── God's Eye View (GEV) 3D Earth Observation Endpoints & Proxy ─────────────

GEV_API_PROXY_PREFIXES = (
    "opensky", "firms", "celestrak", "military-installations", "adsblol",
    "ais-live", "terrain", "traffic", "weather-effects", "overpass",
    "cctv", "regional-brief", "radio", "gbfs", "realtime"
)


@app.get("/api/gev/status")
async def api_gev_status():
    """Inspect God's Eye View server status, configured tokens, and capabilities."""
    from .tools.gods_eye_view import is_gev_server_running
    gev_dir = settings.gev_dir
    dist_ready = (gev_dir / "dist" / "index.html").exists()
    running = is_gev_server_running()
    return {
        "ok": True,
        "enabled": getattr(settings, "gev_enabled", True),
        "running": running,
        "port": getattr(settings, "gev_port", 4173),
        "host": getattr(settings, "gev_host", "localhost"),
        "dist_ready": dist_ready,
        "cesium_configured": bool(getattr(settings, "cesium_ion_token", "")),
        "gmaps_configured": bool(getattr(settings, "google_maps_api_key", "")),
        "opensky_configured": bool(getattr(settings, "opensky_client_id", "")),
    }


@app.post("/api/gev/start")
async def api_gev_start():
    """Ensure the God's Eye View Vite server is running."""
    from .tools.gods_eye_view import ensure_gev_server_started
    ok, msg = await ensure_gev_server_started()
    return {"ok": ok, "message": msg}


@app.api_route("/gev", methods=["GET", "HEAD"])
@app.api_route("/gev/{full_path:path}", methods=["GET", "HEAD", "POST"])
async def proxy_gev(request: Request, full_path: str = ""):
    """Reverse proxy God's Eye View through Zenith to ensure seamless iframe embedding."""
    from .tools.gods_eye_view import ensure_gev_server_started, is_gev_server_running

    port = getattr(settings, "gev_port", 4173)
    target_url = f"http://127.0.0.1:{port}/gev/{full_path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            body = await request.body()
            headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

            # Strip restrictive framing headers and inject permissive ones
            excluded = {"content-encoding", "content-length", "transfer-encoding", "connection", "x-frame-options", "content-security-policy"}
            resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
            resp_headers["X-Frame-Options"] = "SAMEORIGIN"
            resp_headers["Content-Security-Policy"] = "frame-ancestors 'self' http://localhost:* http://127.0.0.1:* https://*"

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
                media_type=resp.headers.get("content-type"),
            )
    except Exception as e:
        # Fallback to static dist bundle if server is starting or offline
        index_file = settings.gev_dir / "dist" / "index.html"
        if not full_path and index_file.exists():
            return FileResponse(index_file, headers={"X-Frame-Options": "SAMEORIGIN"})
        # Otherwise attempt background start and return informative message
        asyncio.create_task(ensure_gev_server_started())
        return JSONResponse(
            {"error": "God's Eye View service initializing", "detail": str(e)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@app.api_route("/api/{gev_endpoint:path}", methods=["GET", "HEAD", "POST"])
async def proxy_gev_apis(request: Request, gev_endpoint: str):
    """Proxy God's Eye View telemetry data feeds if matching a GEV provider endpoint."""
    first_segment = gev_endpoint.split("/")[0]
    if first_segment in GEV_API_PROXY_PREFIXES or any(first_segment.startswith(p) for p in GEV_API_PROXY_PREFIXES):
        port = getattr(settings, "gev_port", 4173)
        target_url = f"http://127.0.0.1:{port}/api/{gev_endpoint}"
        if request.url.query:
            target_url += f"?{request.url.query}"
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                body = await request.body()
                headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
                resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                )
                excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
                resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=resp_headers,
                    media_type=resp.headers.get("content-type"),
                )
        except Exception as e:
            return JSONResponse({"error": f"GEV data proxy failed: {e}"}, status_code=502)

    return JSONResponse({"error": "Not Found"}, status_code=404)


# ─── WebSocket ───────────────────────────────────────────────────────────────



@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({
        "type": "status",
        "message": "connected",
        "user": settings.user_name or "Friend",
    })

    queue = asyncio.Queue()
    hub.subscribe(queue)
    _pending_ws.add(queue)

    async def feed_sender():
        """Forward proactive events on this connection."""
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    return
                continue
            try:
                await websocket.send_json(item)
            except Exception:
                return

    sender_task = asyncio.create_task(feed_sender())

    async def emit(evt: dict):
        if evt.get("type") == "ping":
            return
        try:
            await websocket.send_json(evt)
        except Exception:
            pass

    async def speak_final(text: str) -> str:
        """Synthesize Zenith's final reply to spoken audio for the voice path.
        Tries Gemini Live native audio first (the model actually *speaks* the
        reply — same voice as the conversation, no separate TTS engine), and
        only falls back to text so the client renders it normally.

        Returns either the original text (fallback) or a JSON string carrying
        the native-audio bytes + its real container type.
        """
        try:
            from zenith.voice import live
            if live.available():
                turn = await asyncio.wait_for(
                    live.live_speak(text, _orpheus.build_system_prompt()),
                    timeout=30.0,  # a Live socket hang must not wedge /ws/chat
                )
                if turn.ok and turn.audio:
                    return json.dumps({"audio": True,
                                       "audio_b64": base64.b64encode(turn.audio).decode("ascii"),
                                       "audio_mime": turn.audio_mime,
                                       "model": turn.model})
        except asyncio.TimeoutError:
            log.warning("Live speak for final reply timed out; falling back to text")
        except Exception:
            log.exception("Live speak for final reply failed")
        return text


    try:
        while True:
            data = await websocket.receive_json()
            mtype = data.get("type")
            if mtype == "clear":
                _orpheus.restart()
                await websocket.send_json({"type": "cleared"})
                continue

            # Confirmation decision from the UI dock → satisfy a pending gate.
            if mtype == "confirm":
                cid = int(data.get("id") or 0)
                decision = bool(data.get("decision"))
                resolved = _orpheus.confirm_gate.resolve(cid, decision)
                if not resolved:
                    await websocket.send_json({"type": "error",
                                               "error": "Confirmation no longer pending."})
                continue

            prompt = data.get("prompt") or data.get("message") or ""
            if not prompt.strip():
                continue

            # Zenith should know the turn arrived by voice so it can reply in
            # the right register (and the memory layer can attribute it).
            is_voice = bool(data.get("voice"))
            if is_voice:
                u_label = settings.user_name or "Friend"
                prompt = f"[spoken aloud by {u_label}] {prompt}"

            try:
                await websocket.send_json({"type": "agent_start", "prompt": prompt})
            except Exception:
                pass
            try:
                final = await _orpheus.handle(prompt, emit)
                try:
                    payload = {"type": "done", "text": final}
                    if is_voice:
                        spoke = await speak_final(final)
                        # speak_final returns either a string (text fallback) or
                        # a JSON string carrying base64 audio.
                        if isinstance(spoke, str) and spoke.startswith('{"'):
                            try:
                                spoke = json.loads(spoke)
                            except Exception:
                                pass
                            if isinstance(spoke, dict) and spoke.get("audio"):
                                payload = {"type": "done", "text": {
                                    "audio": spoke["audio_b64"],
                                    "audio_mime": spoke.get("audio_mime", "audio/webm"),
                                    "model": spoke.get("model", "")}}
                    await websocket.send_json(payload)
                except Exception:
                    pass
            except Exception as exc:
                log.exception("orchestrator failed")
                try:
                    await websocket.send_json({"type": "error", "error": str(exc)})
                except Exception:
                    pass
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.unsubscribe(queue)
        _pending_ws.discard(queue)
        sender_task.cancel()


# ─── Static / SPA ────────────────────────────────────────────────────────────

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """True bidirectional Gemini Live tunnel.

    The browser connects here with a persistent WebSocket. It streams raw
    PCM16 (16 kHz) audio up as binary frames; the server relays it into the
    persistent Gemini Live session and streams the model's native audio back
    as binary frames. Tool calls are executed server-side; their outcomes and
    the model's text transcription are delivered as JSON messages.

    Frame protocol (client → server):
      binary  → raw PCM16 payload (realtimeInput audio)
      {"type":"end"}            → end the user's turn (model starts replying)
      {"type":"close"}          → end the session
    Server → client:
      binary  → model's native audio (PCM16, 16 kHz — 24k output resampled)
      {"type":"heard","text":…}      → what the model heard (live transcription)
      {"type":"assistant_text","text":…} → model's spoken text (live)
      {"type":"tool","name":…,"args":…,"result":…} → a tool call executed
      {"type":"done"}           → turn complete, model finished
      {"type":"error","error":…}
    """
    from zenith.voice import live

    await websocket.accept()
    system = _orpheus.build_system_prompt() if hasattr(_orpheus, "build_system_prompt") else ""
    session = live.LiveSession(system_instruction=system)
    err = await session.open()
    if err:
        await websocket.send_json({"type": "error", "error": err})
        await websocket.close()
        return

    async def upstream():
        """Relay the model's audio/events to the browser."""
        try:
            async for kind, payload in session.events():
                if kind == "audio":
                    await websocket.send_bytes(payload)
                elif kind == "text":
                    await websocket.send_json({"type": "assistant_text", "text": payload})
                elif kind == "heard":
                    await websocket.send_json({"type": "heard", "text": payload})
                elif kind == "tool":
                    await websocket.send_json({"type": "tool",
                                               "name": payload.get("name", ""),
                                               "args": payload.get("args", {})})
                elif kind == "done":
                    await websocket.send_json({"type": "done"})
                    # The Live session persists across turns — listen for the next
                    # utterance on the SAME WebSocket instead of ending here.
                    # events() breaks its inner loop after a turn and continues,
                    # so this async-for keeps receiving each subsequent turn.
                elif kind == "error":
                    await websocket.send_json({"type": "error", "error": payload})
        except Exception:
            pass

    upstream_task = asyncio.create_task(upstream())

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
            data = msg.get("bytes") or msg.get("text")
            if data is None:
                continue
            if isinstance(data, str):
                try:
                    cmd = json.loads(data)
                except Exception:
                    continue
                t = cmd.get("type")
                if t == "end":
                    await session.end_turn()
                elif t == "close":
                    break
                continue
            # binary PCM audio
            await session.push_audio(data)
    except Exception:
        pass
    finally:
        upstream_task.cancel()
        await session.close()


# Serve the core JS/CSS with no-cache so a browser NEVER plays a stale bundle
# after a deploy. Defined before the /static mount so these exact paths win.
@app.get("/static/app.js")
async def _app_js() -> FileResponse:
    return FileResponse(settings.static_dir / "app.js",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/static/styles.css")
async def _styles_css() -> FileResponse:
    return FileResponse(settings.static_dir / "styles.css",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


GEV_PUBLIC_SVGS = {"location.svg", "logo.svg", "mic.svg", "pin.svg", "visual-presets.svg"}


@app.get("/{svg_name}.svg")
async def _gev_svg_asset(svg_name: str) -> Response:
    filename = f"{svg_name}.svg"
    if filename in GEV_PUBLIC_SVGS:
        fpath = settings.gev_dir / "dist" / filename
        if not fpath.exists():
            fpath = settings.gev_dir / "public" / filename
        if fpath.exists():
            return FileResponse(fpath, media_type="image/svg+xml")
    return Response(status_code=404)


app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")


@app.get("/")
async def index():
    # The page is a live single-filer; never let Cloudflare or a browser cache
    # the HTML, or Zenith's greeting/theme can go stale behind the fresh assets.
    return FileResponse(
        str(settings.static_dir / "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )