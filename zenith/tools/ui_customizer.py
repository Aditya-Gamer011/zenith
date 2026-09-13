"""Zenith UI Customizer & Runtime Mode Tools.

Allows Zenith to inspect and live-customize its own UI (theme, accent color,
custom CSS, components) and seamlessly manage operating modes:
- 'genesis': Starter / onboarding companion mode helping user set up their environment.
- 'sovereign': Normal / full autonomous operations mode.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from ..core.config import PROJECT_ROOT, settings
from ..core.proactive import hub
from ..core import setup
from ..memory import store

log = logging.getLogger("zenith.ui_customizer")

CUSTOM_CSS_PATH = PROJECT_ROOT / "static" / "custom_theme.css"


def _ensure_custom_css_file() -> Path:
    if not CUSTOM_CSS_PATH.is_file():
        CUSTOM_CSS_PATH.write_text(
            "/* Zenith Custom Theme Styles — injected live by Zenith */\n:root {}\n",
            encoding="utf-8"
        )
    return CUSTOM_CSS_PATH


# ─── Mode Management Tools ───────────────────────────────────────────────────

def get_current_mode() -> dict[str, str]:
    mode = getattr(settings, "zenith_mode", "setup")
    is_setup = mode in {"setup", "genesis"}
    return {
        "mode": "setup" if is_setup else "sovereign",
        "name": "Setup Mode" if is_setup else "Sovereign Mode",
        "description": (
            "Setup Mode: Guided starter and onboarding companion mode."
            if is_setup
            else "Sovereign Mode: Full autonomous command, coding, and orchestration mode."
        )
    }


async def switch_mode(mode: str, reason: str = "") -> str:
    """Switch Zenith's operating mode between 'setup' (starter onboarding) and 'sovereign' (autonomous operations)."""
    target = str(mode).strip().lower()
    if target in {"setup", "starter", "onboarding", "genesis", "companion"}:
        norm_mode = "setup"
        title = "Setup Mode (Starter)"
    elif target in {"normal", "standard", "sovereign", "autonomous", "nexus", "apex"}:
        norm_mode = "sovereign"
        title = "Sovereign Mode (Autonomous)"
    else:
        return f"Unknown mode '{mode}'. Available modes are 'setup' (starter setup companion) or 'sovereign' (full autonomous)."

    # Persist in settings & .env
    settings.zenith_mode = norm_mode
    try:
        setup.save_configuration({"ZENITH_MODE": norm_mode})
    except Exception as exc:
        log.warning("Could not persist ZENITH_MODE to .env: %s", exc)

    # Broadcast to all live WebSocket sessions
    hub.broadcast({
        "type": "zenith_mode_changed",
        "mode": norm_mode,
        "mode_title": title,
        "reason": reason,
    })

    return f"✓ Switched operating mode to {title}. {reason}".strip()


# ─── Profile & Secret Setup Tools ───────────────────────────────────────────

async def update_user_profile(
    name: str = "",
    email: str = "",
    timezone: str = "",
    bio: str = "",
) -> str:
    """Update user identity and background profile conversationally. Saves to .env and memory store."""
    updates: dict[str, str] = {}
    if name:
        updates["USER_NAME"] = name.strip()
        settings.user_name = name.strip()
    if email:
        updates["USER_EMAIL"] = email.strip()
        settings.user_email = email.strip()
    if timezone:
        updates["USER_TIMEZONE"] = timezone.strip()
        settings.user_timezone = timezone.strip()
    if bio:
        updates["USER_BIO"] = bio.strip()
        settings.user_bio = bio.strip()

    if not updates:
        return "No profile fields provided to update."

    setup.save_configuration(updates)

    # Seed fact into memory
    if bio or name:
        try:
            store.save_memory(
                category="user",
                key="profile",
                value=f"Name: {settings.user_name} | Bio: {settings.user_bio} | Email: {settings.user_email}",
            )
        except Exception as exc:
            log.warning("Could not store user profile in SQLite memory: %s", exc)

    # Broadcast update to UI
    hub.broadcast({
        "type": "user_profile_updated",
        "user_name": settings.user_name,
        "user_email": settings.user_email,
        "user_timezone": settings.user_timezone,
    })

    fields_updated = ", ".join(updates.keys())
    return f"✓ Profile updated successfully ({fields_updated})."


async def setup_secret(key: str, value: str) -> str:
    """Store an API key or service token into Zenith's configuration (e.g. RESEND_API_KEY, GROQ_API_KEY, HOME_ASSISTANT_TOKEN)."""
    clean_key = str(key).strip().upper()
    clean_val = str(value).strip()

    if not clean_key or not clean_val:
        return "Both key name and value are required."

    # Validate against known catalog keys
    known_keys = {item["key"] for item in setup.SECRETS_CATALOG}
    if clean_key not in known_keys and not clean_key.endswith("_KEY") and not clean_key.endswith("_TOKEN"):
        return f"Warning: '{clean_key}' is not in the standard catalog. Valid keys include: {', '.join(sorted(list(known_keys)[:10]))}..."

    setup.save_configuration({clean_key: clean_val})

    # Broadcast masked notification
    masked = setup.mask_secret(clean_val)
    hub.broadcast({
        "type": "secret_updated",
        "key": clean_key,
        "display": masked,
    })

    return f"✓ Successfully configured {clean_key} ({masked}). Service integration is now live."


async def get_setup_status(category: str = "") -> str:
    """Inspect what integrations, API keys, and secrets are currently configured vs missing in Zenith."""
    return setup.get_setup_summary_text(category)


# ─── Live UI Customization Tools ────────────────────────────────────────────

async def ui_inspect(target: str = "theme") -> str:
    """Inspect the current UI styling variables (accent color, backgrounds, fonts) and custom CSS."""
    css_file = _ensure_custom_css_file()
    content = css_file.read_text(encoding="utf-8")

    accent = "#818cf8"
    m = re.search(r"--accent:\s*([^;]+);", content)
    if m:
        accent = m.group(1).strip()

    return f"""Current UI Theme State:
- Primary Accent: {accent}
- Mode: {getattr(settings, 'zenith_mode', 'setup')}
- Custom CSS Rules in static/custom_theme.css:
{content}

You can live-customize styles with `ui_customize_theme(accent_color, custom_css)`."""


async def ui_customize_theme(
    accent_color: str = "",
    theme_mode: str = "",
    font: str = "",
    custom_css: str = "",
) -> str:
    """Live-customize Zenith's UI appearance. Changes apply instantly in the browser without reloading."""
    css_file = _ensure_custom_css_file()

    rules = []
    root_vars = []

    if accent_color:
        clean_accent = accent_color.strip()
        root_vars.append(f"  --accent: {clean_accent} !important;")
        root_vars.append(f"  --accent-soft: {clean_accent}25 !important;")
        root_vars.append(f"  --accent-glow: {clean_accent}45 !important;")

    if font:
        clean_font = font.strip()
        root_vars.append(f"  --font: {clean_font}, Inter, system-ui, sans-serif !important;")

    new_content = "/* Zenith Custom Theme Styles — injected live by Zenith */\n"
    if root_vars:
        new_content += ":root {\n" + "\n".join(root_vars) + "\n}\n\n"

    if custom_css:
        new_content += custom_css.strip() + "\n"

    css_file.write_text(new_content, encoding="utf-8")
    log.info("Wrote updated custom theme to %s", css_file)

    # Broadcast live style update directly to connected browsers
    hub.broadcast({
        "type": "ui_theme_updated",
        "accent_color": accent_color or "",
        "custom_css": new_content,
    })

    changes = []
    if accent_color:
        changes.append(f"accent color -> {accent_color}")
    if font:
        changes.append(f"font -> {font}")
    if custom_css:
        changes.append("injected custom CSS rules")

    return f"✓ UI theme updated instantly ({', '.join(changes) or 'styles saved'}). Check your browser window!"


async def ui_reset_theme() -> str:
    """Reset all UI customizations back to Zenith's default design."""
    css_file = _ensure_custom_css_file()
    css_file.write_text("/* Zenith Custom Theme Styles — Reset to default */\n:root {}\n", encoding="utf-8")

    hub.broadcast({
        "type": "ui_theme_reset",
    })

    return "✓ UI theme reset to Zenith default."
