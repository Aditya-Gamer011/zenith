"""App-wide settings, loaded once from environment (or a .env file).

Zenith's world is defined here: which home/edge services exist, what the LLM is
allowed to touch, and where projects live on disk. Everything a tool
module needs to find its capabilities comes from this object.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# Project root is the directory containing this file's package parent.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DOTENV = load_dotenv(PROJECT_ROOT / ".env")  # no-op if missing


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "yes" if default else "no").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _as_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


# Well-known containers Zenith may start/stop/restart as discrete ops.
DEFAULT_GUARDED_CONTAINERS = (
    "zenith,hostpheus,codraw-app,jellyfin,sonarr,radarr,prowlarr,"
    "qbittorrent,seerr,n8n,portainer,uptime-kuma,vaultwarden,homepage,"
    "twilight-mc-server,twilight-mc-playit,twilight-mc-bore,cloudflared,homelab-caddy"
)


class Settings:
    """Central configuration for the Zenith runtime."""

    # ── Onboarding & General Use Identity ──────────────────────────────────
    setup_completed: bool = _flag("ZENITH_SETUP_COMPLETED", default=False)
    user_name: str = os.getenv("USER_NAME", os.getenv("ZENITH_USER_NAME", "Friend")).strip()
    user_email: str = os.getenv("USER_EMAIL", os.getenv("ZENITH_USER_EMAIL", "")).strip()
    user_timezone: str = os.getenv("USER_TIMEZONE", os.getenv("TZ", "Asia/Kolkata")).strip()
    user_bio: str = os.getenv("USER_BIO", "").strip()
    user_birthday: str = os.getenv("USER_BIRTHDAY", "").strip()
    user_hobbies: str = os.getenv("USER_HOBBIES", "").strip()
    github_user: str = os.getenv("GITHUB_USER", "").strip()
    zenith_mode: str = os.getenv("ZENITH_MODE", "setup").strip().lower()

    # 'none' enables zero-friction single-user local access.
    auth_mode: str = os.getenv("AUTH_MODE", "none").strip().lower()

    # ── Provider ───────────────────────────────────────────────────────────
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_audio: str = os.getenv("GEMINI_AUDIO", "").strip()
    # Fallback provider (DeepSeek, OpenAI, Groq, OpenRouter)
    fallback_api_key: str = os.getenv("FALLBACK_API_KEY", "").strip()
    fallback_endpoint: str = os.getenv("FALLBACK_ENDPOINT", "https://llmsolutions.top/v1/chat/completions").strip()
    fallback_model: str = os.getenv("FALLBACK_MODEL", "deepseek-v4-flash-0731").strip()
    fallback_prefer: bool = _flag("FALLBACK_PREFER", default=False)
    # Gemini Live API OAuth.
    gemini_live_refresh_token: str = os.getenv("GEMINI_LIVE_REFRESH_TOKEN", "").strip()
    # ── Maps & Geospatial / God's Eye View ──────────────────────────────────
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    cesium_ion_token: str = os.getenv("CESIUM_ION_TOKEN", "").strip()
    gev_enabled: bool = _flag("GEV_ENABLED", default=True)
    gev_port: int = int(os.getenv("GEV_PORT", "4173"))
    gev_host: str = os.getenv("GEV_HOST", "localhost").strip()
    gev_public_url: str = os.getenv("GEV_PUBLIC_URL", "").strip()
    opensky_client_id: str = os.getenv("OPENSKY_CLIENT_ID", "").strip()
    opensky_client_secret: str = os.getenv("OPENSKY_CLIENT_SECRET", "").strip()
    oauth_project_number: str = os.getenv("OAUTH_PROJECT_NUMBER", "").strip()

    # ── Voice & Audio ─────────────────────────────────────────────────────
    groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()
    groq_whisper_model: str = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo").strip()
    live_voice_enabled: bool = _flag("LIVE_VOICE_ENABLED", default=True)
    edge_voice: str = os.getenv("EDGE_VOICE", "en-IN-NeerjaNeural").strip()

    # ── Server ────────────────────────────────────────────────────────────
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("ZENITH_PORT", os.getenv("PORT", "8005")))

    # ── Axiom SSO Identity & Auth ──────────────────────────────────────────
    axiom_url: str = os.getenv("AXIOM_URL", "").rstrip("/")
    axiom_client_id: str = os.getenv("AXIOM_CLIENT_ID", "").strip()
    axiom_client_secret: str = os.getenv("AXIOM_CLIENT_SECRET", "").strip()
    session_secret: str = os.getenv("SESSION_SECRET", "zenith-identity-session-signing-key-2026").strip()
    session_cookie_name: str = "zenith_session"
    axiom_db_path: str = os.getenv("AXIOM_DB_PATH", "/app/axiom_prisma/dev.db").strip()
    superadmin_emails: list[str] = _as_list("SUPERADMIN_EMAILS") or [
        "admin@example.com",
    ]
    superadmin_usernames: list[str] = _as_list("SUPERADMIN_USERNAMES") or [
        "admin",
    ]

    # ── Capabilities ──────────────────────────────────────────────────────
    # Arbitrary shell is OFF by default. Docker/GitHub/system tools are always
    # on (they are safely wrapped) unless individually disabled.
    allow_shell: bool = _flag("ALLOW_SHELL", default=False)
    allow_docker: bool = _flag("ALLOW_DOCKER", default=True)
    allow_github: bool = _flag("ALLOW_GITHUB", default=True)
    allow_system: bool = _flag("ALLOW_SYSTEM", default=True)

    # Docker socket — mounted read-only into the container (see docker-compose).
    docker_socket: str = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")
    # Only these containers may be started/stopped/restarted by control-plane ops.
    guarded_containers: list[str] = _as_list("GUARDED_CONTAINERS") or list(
        filter(None, DEFAULT_GUARDED_CONTAINERS.split(","))
    )

    # GitHub CLI (requires gh authenticated + ~/.config/gh mounted in).
    gh_bin: str = os.getenv("GH_BIN", shutil.which("gh") or "gh")

    # Minecraft compose project (start/stop/restart/players).
    mc_compose_dir: Path = Path(
        os.getenv("MC_COMPOSE_DIR", str(PROJECT_ROOT / ".." / ".." / "Twilight-MC"))
    )
    mc_compose_files: str = os.getenv("MC_COMPOSE_FILES", "-f docker-compose.yml")

    # ── Email ──────────────────────────────────────────────────────────────
    # Gmail IMAP (read path for the agm.quest catch-all forwarded to Gmail).
    mail_imap_host: str = os.getenv("MAIL_IMAP_HOST", "imap.gmail.com").strip()
    mail_imap_user: str = os.getenv("MAIL_IMAP_USER", "").strip()
    mail_imap_pass: str = os.getenv("MAIL_IMAP_PASS", "").strip()
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", os.getenv("MAIL_IMAP_PASS", "")).strip()
    gmail_user: str = os.getenv("GMAIL_USER", os.getenv("MAIL_IMAP_USER", "")).strip()
    # Outbound: Resend
    resend_api_key: str = os.getenv("RESEND_API_KEY", "").strip()
    resend_from: str = os.getenv("RESEND_FROM", "Zenith <zenith@example.com>").strip()
    resend_reply_to: str = os.getenv("RESEND_REPLY_TO", "").strip()
    # Legacy IMAP/SMTP pair (still read if present).
    mail_smtp_host: str = os.getenv("MAIL_SMTP_HOST", os.getenv("MAIL_IMAP_HOST", "")).strip()
    mail_smtp_user: str = os.getenv("MAIL_SMTP_USER", os.getenv("MAIL_IMAP_USER", "")).strip()
    mail_smtp_pass: str = os.getenv("MAIL_SMTP_PASS", os.getenv("MAIL_IMAP_PASS", "")).strip()

    # ── Google Calendar (OAuth refresh token) ───────────────────────────────
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    google_refresh_token: str = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    google_calendar_id: str = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip()
    # Redirect for the Gemini-Live OAuth consent (must match the OAuth app).
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/oauth/callback").strip()

    # ── Cloudflare (DNS + Email Routing via API) ─────────────────────────
    cloudflare_token: str = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    cloudflare_zone: str = os.getenv("CLOUDFLARE_ZONE", "").strip()
    cloudflare_account_id: str = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    # R2 object storage (same account).
    r2_access_key_id: str = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    r2_secret_access_key: str = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    r2_endpoint: str = os.getenv("R2_ENDPOINT", "").strip()

    # ── Home Assistant / Smart Home ─────────────────────────────────────────
    home_assistant_url: str = os.getenv("HOME_ASSISTANT_URL", "http://172.17.0.1:8123").strip()
    home_assistant_token: str = os.getenv("HOME_ASSISTANT_TOKEN", "").strip()

    # ── Media stack *arr API keys ───────────────────────────────────────────
    sonarr_api_key: str = os.getenv("SONARR_API_KEY", "").strip()
    radarr_api_key: str = os.getenv("RADARR_API_KEY", "").strip()
    prowlarr_api_key: str = os.getenv("PROWLARR_API_KEY", "").strip()

    # ── Vercel (project deploys) ──────────────────────────────────────────
    vercel_token: str = os.getenv("VERCEL_TOKEN", "").strip()

    # ── n8n (workflow automation) ─────────────────────────────────────────
    n8n_url: str = os.getenv("N8N_URL", "").strip()
    n8n_api_key: str = os.getenv("N8N_API_KEY", "").strip()

    # ── Hack Club CDN (file hosting at cdn.hackclub.com) ──────────────────
    hackclub_cdn_key: str = os.getenv("HACKCLUB_CDN_KEY", "").strip()

    # ── Art & Design Integrations ─────────────────────────────────────────
    figma_client_id: str = os.getenv("FIGMA_CLIENT_ID", "").strip()
    figma_client_secret: str = os.getenv("FIGMA_CLIENT_SECRET", "").strip()
    figma_redirect_uri: str = os.getenv("FIGMA_REDIRECT_URI", "").strip()
    canva_client_id: str = os.getenv("CANVA_CLIENT_ID", "").strip()
    canva_client_secret: str = os.getenv("CANVA_CLIENT_SECRET", "").strip()
    canva_redirect_uri: str = os.getenv("CANVA_REDIRECT_URI", "").strip()

    # ── GitHub & Cloudflare OAuth ─────────────────────────────────────────
    github_client_id: str = os.getenv("GITHUB_CLIENT_ID", "").strip()
    github_client_secret: str = os.getenv("GITHUB_CLIENT_SECRET", "").strip()
    github_redirect_uri: str = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8005/api/integrations/github/callback").strip()
    cloudflare_client_id: str = os.getenv("CLOUDFLARE_CLIENT_ID", "").strip()
    cloudflare_client_secret: str = os.getenv("CLOUDFLARE_CLIENT_SECRET", "").strip()
    cloudflare_redirect_uri: str = os.getenv("CLOUDFLARE_REDIRECT_URI", "http://localhost:8005/api/integrations/cloudflare/callback").strip()


    # Fine-grained op renames (human-friendly labels the model maps to).
    allow_destructive: bool = _flag("ALLOW_DESTRUCTIVE", default=False)

    # Model routing — NOTE: gemini-2.5/3.0 are retired for new keys; use 3.x.
    #   brain  -> gemini-3.6-flash (capable, fast, free tier)
    #   fast   -> gemini-3.1-flash-lite (cheap & snappy)
    brain_model: str = os.getenv("BRAIN_MODEL", "gemini-3.5-flash-lite")
    fast_model: str = os.getenv("FAST_MODEL", "gemini-3.5-flash-lite")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

    # Tiers (complexity -> provider)
    tier_routing: dict[str, str] = {
        "fast": "fast_model",
        "standard": "brain_model",
        "deep": "brain_model",
    }

    # Confirmation policy: seconds to wait for user confirmation on a risky op.
    confirm_timeout: int = int(os.getenv("CONFIRM_TIMEOUT", "180"))

    # ── Paths ─────────────────────────────────────────────────────────────
    data_dir: Path = PROJECT_ROOT / "data"
    screenshots_dir: Path = PROJECT_ROOT / "static" / "screenshots"
    static_dir: Path = PROJECT_ROOT / "static"
    db_path: Path = PROJECT_ROOT / "data" / "zenith.db"
    workspace_dir: Path = Path(os.getenv("ZENITH_WORKSPACE", str(Path.home() / "Desktop" / "helper")))
    gev_dir: Path = PROJECT_ROOT / "gods-eye-view"

    def reload(self) -> None:
        """Reload configuration from .env and update in-memory settings."""
        load_dotenv(PROJECT_ROOT / ".env", override=True)
        self.setup_completed = _flag("ZENITH_SETUP_COMPLETED", default=False)
        self.user_name = os.getenv("USER_NAME", os.getenv("ZENITH_USER_NAME", "Friend")).strip()
        self.user_email = os.getenv("USER_EMAIL", os.getenv("ZENITH_USER_EMAIL", "")).strip()
        self.user_timezone = os.getenv("USER_TIMEZONE", os.getenv("TZ", "Asia/Kolkata")).strip()
        self.user_bio = os.getenv("USER_BIO", "").strip()
        self.user_birthday = os.getenv("USER_BIRTHDAY", "").strip()
        self.user_hobbies = os.getenv("USER_HOBBIES", "").strip()
        self.zenith_mode = os.getenv("ZENITH_MODE", "setup").strip().lower()
        self.auth_mode = os.getenv("AUTH_MODE", "none").strip().lower()

        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_audio = os.getenv("GEMINI_AUDIO", "").strip()
        self.fallback_api_key = os.getenv("FALLBACK_API_KEY", "").strip()
        self.fallback_endpoint = os.getenv("FALLBACK_ENDPOINT", "https://llmsolutions.top/v1/chat/completions").strip()
        self.fallback_model = os.getenv("FALLBACK_MODEL", "deepseek-v4-flash-0731").strip()
        self.fallback_prefer = _flag("FALLBACK_PREFER", default=False)
        self.gemini_live_refresh_token = os.getenv("GEMINI_LIVE_REFRESH_TOKEN", "").strip()
        self.google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
        self.cesium_ion_token = os.getenv("CESIUM_ION_TOKEN", "").strip()
        self.gev_enabled = _flag("GEV_ENABLED", default=True)
        self.gev_port = int(os.getenv("GEV_PORT", "4173"))
        self.gev_host = os.getenv("GEV_HOST", "localhost").strip()
        self.gev_public_url = os.getenv("GEV_PUBLIC_URL", "").strip()
        self.opensky_client_id = os.getenv("OPENSKY_CLIENT_ID", "").strip()
        self.opensky_client_secret = os.getenv("OPENSKY_CLIENT_SECRET", "").strip()
        self.oauth_project_number = os.getenv("OAUTH_PROJECT_NUMBER", "").strip()

        self.groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.groq_whisper_model = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo").strip()
        self.live_voice_enabled = _flag("LIVE_VOICE_ENABLED", default=True)
        self.edge_voice = os.getenv("EDGE_VOICE", "en-IN-NeerjaNeural").strip()

        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("ZENITH_PORT", os.getenv("PORT", "8005")))

        self.axiom_url = os.getenv("AXIOM_URL", "").rstrip("/")
        self.axiom_client_id = os.getenv("AXIOM_CLIENT_ID", "").strip()
        self.axiom_client_secret = os.getenv("AXIOM_CLIENT_SECRET", "").strip()
        self.session_secret = os.getenv("SESSION_SECRET", "zenith-identity-session-signing-key-2026").strip()
        self.axiom_db_path = os.getenv("AXIOM_DB_PATH", "/app/axiom_prisma/dev.db").strip()

        self.allow_shell = _flag("ALLOW_SHELL", default=False)
        self.allow_docker = _flag("ALLOW_DOCKER", default=True)
        self.allow_github = _flag("ALLOW_GITHUB", default=True)
        self.allow_system = _flag("ALLOW_SYSTEM", default=True)

        self.mail_imap_host = os.getenv("MAIL_IMAP_HOST", "imap.gmail.com").strip()
        self.mail_imap_user = os.getenv("MAIL_IMAP_USER", "").strip()
        self.mail_imap_pass = os.getenv("MAIL_IMAP_PASS", "").strip()
        self.gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", os.getenv("MAIL_IMAP_PASS", "")).strip()
        self.gmail_user = os.getenv("GMAIL_USER", os.getenv("MAIL_IMAP_USER", "")).strip()
        self.resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
        self.resend_from = os.getenv("RESEND_FROM", "Zenith <zenith@example.com>").strip()
        self.resend_reply_to = os.getenv("RESEND_REPLY_TO", "").strip()

        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        self.google_refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
        self.google_calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip()
        self.google_redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI", "http://localhost:8000/oauth/callback").strip()

        self.cloudflare_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
        self.cloudflare_zone = os.getenv("CLOUDFLARE_ZONE", "").strip()
        self.cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        self.r2_access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip()
        self.r2_secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
        self.r2_endpoint = os.getenv("R2_ENDPOINT", "").strip()

        self.home_assistant_url = os.getenv("HOME_ASSISTANT_URL", "http://172.17.0.1:8123").strip()
        self.home_assistant_token = os.getenv("HOME_ASSISTANT_TOKEN", "").strip()

        self.sonarr_api_key = os.getenv("SONARR_API_KEY", "").strip()
        self.radarr_api_key = os.getenv("RADARR_API_KEY", "").strip()
        self.prowlarr_api_key = os.getenv("PROWLARR_API_KEY", "").strip()

        self.vercel_token = os.getenv("VERCEL_TOKEN", "").strip()
        self.n8n_url = os.getenv("N8N_URL", "").strip()
        self.n8n_api_key = os.getenv("N8N_API_KEY", "").strip()
        self.hackclub_cdn_key = os.getenv("HACKCLUB_CDN_KEY", "").strip()
        self.allow_destructive = _flag("ALLOW_DESTRUCTIVE", default=False)

        # Art & Design Integrations
        self.figma_client_id = os.getenv("FIGMA_CLIENT_ID", "").strip()
        self.figma_client_secret = os.getenv("FIGMA_CLIENT_SECRET", "").strip()
        self.figma_redirect_uri = os.getenv("FIGMA_REDIRECT_URI", "").strip()
        self.canva_client_id = os.getenv("CANVA_CLIENT_ID", "").strip()
        self.canva_client_secret = os.getenv("CANVA_CLIENT_SECRET", "").strip()
        self.canva_redirect_uri = os.getenv("CANVA_REDIRECT_URI", "").strip()

        # GitHub & Cloudflare OAuth
        self.github_client_id = os.getenv("GITHUB_CLIENT_ID", "").strip()
        self.github_client_secret = os.getenv("GITHUB_CLIENT_SECRET", "").strip()
        self.github_redirect_uri = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8005/api/integrations/github/callback").strip()
        self.cloudflare_client_id = os.getenv("CLOUDFLARE_CLIENT_ID", "").strip()
        self.cloudflare_client_secret = os.getenv("CLOUDFLARE_CLIENT_SECRET", "").strip()
        self.cloudflare_redirect_uri = os.getenv("CLOUDFLARE_REDIRECT_URI", "http://localhost:8005/api/integrations/cloudflare/callback").strip()


settings = Settings()

if not settings.gemini_api_key:
    print("[warn] GEMINI_API_KEY is not set in .env — model calls will fail.\n"
          "  Also mount your API key: cp .env.example .env and fill it in.")