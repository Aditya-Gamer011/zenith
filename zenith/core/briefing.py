"""Opening briefing — Zenith greets user with a little context the moment they
open the UI.

Synthesizes tasks, unread email, upcoming events, and weather, and
shows it as Zenith's first message: what's on today, what's overdue, what's new.
It should feel like she *knows* — a quick spoken summary, not a dashboard dump.

The briefing stays light on purpose: it only reads the local store + the
calendar call already used by the sidebar. No heavy tools fire on page load;
if anything fails, we degrade to a plain time-appropriate greeting.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import settings

log = logging.getLogger("zenith.briefing")

# In-process summary cache: {"key": (hour, date), "summary": str, "ts": float}
_SUMMARY_CACHE: dict = {}

IST_TZ = ZoneInfo("Asia/Kolkata")


def _local_now() -> datetime:
    """User's wall-clock (container may run UTC)."""
    tz_name = settings.user_timezone or os.getenv("TZ", "Asia/Kolkata")
    try:
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now(IST_TZ)


def greeting_for(now: datetime | None = None) -> str:
    now = now or _local_now()
    h = now.hour
    name = settings.user_name or "Friend"
    if 5 <= h < 12:
        return f"Good morning, {name}."
    if 12 <= h < 17:
        return f"Good afternoon, {name}."
    if 17 <= h < 21:
        return f"Good evening, {name}."
    return f"Good night, {name}."


async def build_briefing() -> dict[str, str]:
    """Greeting + warm short summary of the user's day/life right now.

    Cache the LLM-synthesized summary for ~6 minutes so a page refresh doesn't
    pay another LLM call + Google Calendar roundtrip. The greeting is always
    fresh (cheap); only the contextual summary is cached.
    """
    now = _local_now()
    greeting = greeting_for(now)

    mode = getattr(settings, "zenith_mode", "setup")
    name = settings.user_name or "Friend"

    cache_key = (now.hour, now.date().isoformat(), mode, name)
    if _SUMMARY_CACHE.get("key") == cache_key:
        return {"greeting": greeting, "summary": _SUMMARY_CACHE["summary"]}

    # Dedicated greeting for Setup Mode
    if mode in {"setup", "genesis"}:
        setup_greeting = (
            f"Hello, {name}! I'm awake and in **🌱 Setup Mode**.\n\n"
            "My primary goal right now is to help you set up more stuff—like connecting your keys, email, GitHub, smart home, "
            "or customizing how I look and sound.\n\n"
            "What would you like to set up first? You can ask me *'what can I set up?'* to explore available integrations, "
            "or tell me to *'switch to sovereign mode'* anytime you want to jump straight into autonomous work!"
        )
        _SUMMARY_CACHE["key"] = cache_key
        _SUMMARY_CACHE["summary"] = setup_greeting
        return {"greeting": greeting, "summary": setup_greeting}

    ctx = await _context_digest()
    if not ctx:
        return {"greeting": greeting, "summary": f"{greeting} I'm here whenever you need me."}

    # "She did stuff while you were away" — surface the autonomy journal.
    try:
        from . import autonomy

        report = autonomy._summarise_for_greeting()
        if report and not report.startswith("Nothing urgent"):
            ctx += f"\n\nAutonomy: {report}"
    except Exception:
        pass

    try:
        from . import provider

        prompt = (
            f"You are Zenith, {name}'s calm, warm personal assistant. They just opened "
            "you. Greet them naturally and briefly using the context below — say good "
            "evening/whatever fits, note a couple of the most relevant things going on, "
            "and leave the door open (a phrase like 'what shall we tackle today?'). "
            "One short markdown paragraph (2-4 sentences), friendly but not "
            "performative. Do not list the raw facts; speak them naturally.\n\n"
            f"Current day: {now.strftime('%A, %d %B %Y, %I:%M %p')}.\n\n"
            f"What's happening:\n{ctx}"
        )
        result = await provider.chat_once(
            "fast",
            [
                {"role": "system", "content": (
                    f"You are Zenith — the warm, calm personal assistant built around "
                    f"{name}. Speak softly and naturally, in the first person, always "
                    f"addressing {name} by name, never narrating tools or memory, and never "
                    "referring to them as 'user'. Under 5 sentences."
                )},
                {"role": "user", "content": prompt},
            ],
            max_tokens=220,
        )
        if result and len(result.strip()) >= 20:
            _SUMMARY_CACHE["key"] = cache_key
            _SUMMARY_CACHE["summary"] = result.strip()
            return {"greeting": greeting, "summary": result.strip()}
        log.debug("briefing provider returned nothing useful")
    except Exception as exc:
        log.info("briefing provider unavailable, using fallback: %s", exc)

    return {
        "greeting": greeting,
        "summary": f"{greeting} I'm here whenever you need me.",
    }


async def _context_digest() -> str:
    """Small, structured digest of what's going on — the stuff that makes Zenith
    sound like it's been paying attention."""
    from ..tools import calendar, reminders, todo, notes
    from ..memory import store

    parts: list[str] = []

    try:
        open_todos = [t for t in todo.open_todos() if t.get("title")]
        if open_todos:
            top = " | ".join(t["title"] for t in open_todos[:4])
            more = f" (+{len(open_todos) - 4} more)" if len(open_todos) > 4 else ""
            parts.append(f"Open to-dos: {top}{more}")
    except Exception as exc:
        log.debug("briefing to-dos failed: %s", exc)

    try:
        due = [r for r in reminders.all_rows() if r.get("active") and r.get("at")]
        if due:
            shown = [f"{r['text']} ({r['at']})" for r in due[:3]]
            parts.append("Reminders: " + " | ".join(shown))
    except Exception as exc:
        log.debug("briefing reminders failed: %s", exc)

    try:
        events = await calendar.upcoming()
        if events:
            shown = []
            for e in events[:3]:
                at = e.get("at") or ""
                try:
                    at = datetime.fromisoformat(at.replace("Z", "+00:00")).strftime("%a %H:%M")
                except Exception:
                    pass
                shown.append(f"{e.get('title')} ({at})")
            parts.append("Upcoming: " + " | ".join(shown))
    except Exception as exc:
        log.debug("briefing calendar failed: %s", exc)

    try:
        recent = store.recent_conversation(limit=15)
        if recent:
            last = recent[-1].get("content", "")
            if last and len(last) > 140:
                last = last[:140].rstrip() + "…"
            if last:
                parts.append(f"Last we talked about: {last}")
    except Exception as exc:
        log.debug("briefing history failed: %s", exc)

    try:
        memories = store.all_memories()
        goals = [f"{m['key']}: {m['value']}"
                 for m in memories if m.get("category") == "goals"
                 and m.get("key") and m.get("value")]
        if goals:
            parts.append("Goals: " + " | ".join(goals[:2]))
    except Exception as exc:
        log.debug("briefing goals failed: %s", exc)

    return "\n".join(parts) if parts else ""