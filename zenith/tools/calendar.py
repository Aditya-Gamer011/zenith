"""Google Calendar adapter — real read/write via OAuth.

Zenith uses the user's Google Calendar (full read/write): it lists upcoming
events, and with confirmation can add/edit/delete. Auth is a stored refresh
token in .env (GOOGLE_REFRESH_TOKEN); the provider layer is httpx.

Everything degrades gracefully: no token → the local SQLite calendar still
works as a fallback source for the UI, and tools say "calendar not connected"
so the model doesn't pretend otherwise.
"""
from __future__ import annotations

import datetime as dt
import json

import httpx

from ..core.config import settings

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CAL_URL = "https://www.googleapis.com/calendar/v3"

_SCOPES = "https://www.googleapis.com/auth/calendar"


def _connected() -> bool:
    return bool(
        settings.google_refresh_token
        and (settings.google_client_id or settings.google_client_secret)
        or settings.google_refresh_token  # allow token-only installs
    )


def _get_tz():
    from zoneinfo import ZoneInfo
    import os
    tz_name = getattr(settings, "user_timezone", "") or os.getenv("USER_TIMEZONE") or os.getenv("TZ", "Asia/Kolkata")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return dt.timezone.utc


_token_cache: dict[str, Any] = {
    "access_token": "",
    "expires_at": 0.0,
    "last_failure": 0.0,
    "failure_err": "",
}


async def _access_token() -> str:
    """Exchange the stored refresh token for a short-lived access token with caching and failure backoff."""
    if not _connected():
        raise RuntimeError("Google Calendar not configured (set GOOGLE_REFRESH_TOKEN).")

    import time
    now = time.time()

    # If we have a cached valid token, reuse it
    if _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    # If recent refresh failed, back off for 10 minutes (600s) to avoid spamming Google with 400s
    if _token_cache["last_failure"] and (now - _token_cache["last_failure"] < 600):
        remaining = int(600 - (now - _token_cache["last_failure"]))
        raise RuntimeError(f"Google OAuth token refresh in backoff ({remaining}s remaining): {_token_cache['failure_err']}")

    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": settings.google_refresh_token,
        "grant_type": "refresh_token",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(_TOKEN_URL, data=payload)
        if resp.status_code >= 400:
            err_msg = resp.text[:200]
            _token_cache["last_failure"] = now
            _token_cache["failure_err"] = err_msg
            _token_cache["access_token"] = ""
            _token_cache["expires_at"] = 0.0
            raise RuntimeError(f"Token refresh failed ({resp.status_code}): {err_msg}")

        data = resp.json()
        token = data.get("access_token", "")
        if not token:
            raise RuntimeError(f"Token response missing access_token: {resp.text[:200]}")
        expires_in = data.get("expires_in", 3600)
        _token_cache["access_token"] = token
        _token_cache["expires_at"] = now + max(expires_in - 60, 60)
        _token_cache["last_failure"] = 0.0
        _token_cache["failure_err"] = ""
        return token
    except httpx.RequestError as exc:
        _token_cache["last_failure"] = now
        _token_cache["failure_err"] = str(exc)
        raise RuntimeError(f"Token refresh network error: {exc}")


async def _request(method: str, path: str, **kw) -> dict:
    token = await _access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{_CAL_URL}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, **kw)
    if resp.status_code >= 400:
        raise RuntimeError(f"[calendar] API {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else {}


async def list_upcoming(limit: int = 10) -> str:
    """Fetch the next `limit` upcoming events, formatted for Zenith."""
    tz = _get_tz()
    now_dt = dt.datetime.now(tz)
    time_min_dt = now_dt - dt.timedelta(minutes=15)
    time_max_dt = now_dt + dt.timedelta(days=60)

    if _connected():
        try:
            data = await _request(
                "GET",
                f"/calendars/{settings.google_calendar_id}/events",
                params={
                    "timeMin": time_min_dt.isoformat(),
                    "maxResults": limit,
                    "orderBy": "startTime",
                    "singleEvents": "true",
                },
            )
            items = data.get("items", [])
            if items:
                lines = []
                for ev in items:
                    start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "?")
                    lines.append(f"- {start} — {ev.get('summary', '(no title)')}")
                return "\n".join(lines)
            return "No upcoming events on your calendar."
        except Exception as exc:
            pass  # Fall back to local SQLite mirror

    # Local SQLite mirror fallback
    local_evs = _local_upcoming(time_min_dt, time_max_dt, limit=limit)
    if not local_evs:
        return "No upcoming events on your schedule."
    lines = [f"- {ev['at']} — {ev['title']}" for ev in local_evs]
    return "\n".join(lines)


async def add_event(summary: str, when: str = "", desc: str = "") -> str:
    """Add an event to the real calendar. `when` is a freeform date/time."""
    at = _parse_when(when)
    _local_add_event(summary, at[0])
    if not _connected():
        return f"Event added locally to schedule: {summary} @ {at[0]} (Google Calendar not connected)."
    try:
        body = {
            "summary": summary,
            "start": {"dateTime": at[0]},
            "end": {"dateTime": at[1]},
        }
        if desc:
            body["description"] = desc
        data = await _request("POST", f"/calendars/{settings.google_calendar_id}/events", json=body)
        return f"Event added: {summary} ({data.get('htmlLink', '')[:60]}…)"
    except Exception as exc:
        return f"Event saved locally (Google Calendar add failed: {exc})."


def _local_add_event(title: str, at: str) -> None:
    try:
        from ..memory.store import _connect
        with _connect() as conn:
            conn.execute("INSERT INTO events (title, at) VALUES (?, ?)", (title, at))
            conn.commit()
    except Exception:
        pass


async def delete_event(event_id: str) -> str:
    """Delete an event by its id, or (when given a title) by searching upcoming
    and deleting every matching event. This makes 'remove X from my schedule'
    actually work — the model often has the title but not the opaque Google id."""
    target = (event_id or "").strip()
    if not target:
        return "Provide an event title or id to delete."

    # 1) Fall back to local mirror first, then Google.
    deleted_local = _local_delete_event(target)

    if not _connected():
        return "Deleted from local schedule." if deleted_local else (
            "Google Calendar isn't connected, and nothing matched locally.")

    # 2) If target looks like an event id (not a title), delete directly.
    if "/" not in target and target.isalnum() and len(target) > 6:
        try:
            await _request("DELETE", f"/calendars/{settings.google_calendar_id}/events/{target}")
            return "Deleted event."
        except Exception as exc:
            return f"[calendar] delete by id failed: {exc}"

    # 3) Otherwise treat it as a title: list upcoming, delete the matches.
    try:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        data = await _request(
            "GET",
            f"/calendars/{settings.google_calendar_id}/events",
            params={"timeMin": now, "maxResults": 100, "orderBy": "startTime",
                    "singleEvents": "true", "q": target},
        )
    except Exception as exc:
        return f"[calendar] delete search failed: {exc}"

    items = data.get("items", [])
    if not items:
        return "No matching upcoming event found to delete."
    deleted = 0
    for ev in items:
        eve_id = ev.get("id")
        if not eve_id:
            continue
        try:
            await _request("DELETE", f"/calendars/{settings.google_calendar_id}/events/{eve_id}")
            deleted += 1
        except Exception:
            pass
    return (f"Deleted {deleted} event(s) matching '{target}'."
            if deleted else "Events found but nothing could be deleted.")


def _local_delete_event(target: str) -> bool:
    """Delete local-mirror events by exact title or substring."""
    try:
        from ..memory.store import _connect
        with _connect() as conn:
            cur = conn.execute("DELETE FROM events WHERE title = ? OR title LIKE ?",
                               (target, f"%{target}%"))
            conn.commit()
        return cur.rowcount > 0
    except Exception:
        return False


def _parse_when(when: str) -> tuple[str, str]:
    """Return (start, end) ISO datetimes from freeform `when`.

    Accepts everything the model might send: full ISO / RFC3339 strings, 'YYYY-
    MM-DD HH:MM', relative keywords (today/tomorrow + clock), or just a time
    ('4pm', '21:30', 'noon'). A naive datetime or a pure time is placed in
    Zenith's local timezone (Asia/Kolkata) even when the container itself runs
    UTC, so "remind me today 8pm" means India 8pm — not UTC 8pm.
    """
    text = (when or "").strip()
    if not text:
        text = "today"

    tz = _get_tz()
    start: dt.datetime | None = None

    # 1) Already an ISO / RFC3339 string with an offset or 'Z'.
    iso_attempt = text.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M%z",
                "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M%z",
                "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            start = dt.datetime.strptime(iso_attempt, fmt)
            break
        except ValueError:
            continue

    low = text.lower()
    if start is None:
        day = dt.datetime.now(tz).replace(second=0, microsecond=0)
        if "tomorrow" in low or "next day" in low:
            day += dt.timedelta(days=1)
        elif "day after" in low:
            day += dt.timedelta(days=2)
        m = __import__("re").search(r"(\d{1,2})[:.](\d{2})", text)
        if m:
            hour = int(m.group(1)) % 24
            minute = int(m.group(2))
            if "pm" in low and hour < 12:
                hour += 12
            if "am" in low and hour == 12:
                hour = 0
            start = day.replace(hour=hour, minute=minute)
        elif "noon" in low:
            start = day.replace(hour=12, minute=0)
        elif re_full := __import__("re").search(r"(\d{1,2})\s*(am|pm)", low):
            hour = int(re_full.group(1)) % 12
            if re_full.group(2) == "pm":
                hour += 12
            start = day.replace(hour=hour, minute=0)
        else:
            start = day.replace(hour=21, minute=0)  # default: tonight

    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)

    end = start + dt.timedelta(hours=1)
    # RFC3339 "+05:30" offset (Google rejects "+0530").
    off = start.utcoffset() or dt.timedelta(0)
    sign = "+" if off >= dt.timedelta(0) else "-"
    off = abs(off)
    off_s = f"{sign}{int(off.total_seconds()//3600):02d}:{int(off.total_seconds()%3600//60):02d}"
    return start.strftime("%Y-%m-%dT%H:%M:%S") + off_s, end.strftime("%Y-%m-%dT%H:%M:%S") + off_s


# ── tool-facing wrappers ────────────────────────────────────────────────────

async def upcoming(limit: int = 30) -> list[dict]:
    """Upcoming events strictly from now to the end of the current month (or next 14 days) for the UI/scheduler."""
    tz = _get_tz()
    now_dt = dt.datetime.now(tz)
    # Give a 15-minute grace window so events starting right now remain visible
    time_min_dt = now_dt - dt.timedelta(minutes=15)

    if now_dt.month == 12:
        next_month_first = now_dt.replace(year=now_dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_month_first = now_dt.replace(month=now_dt.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = next_month_first - dt.timedelta(microseconds=1)
    time_max_dt = max(last_day, now_dt + dt.timedelta(days=14))

    time_min = time_min_dt.isoformat()
    time_max = time_max_dt.isoformat()

    if _connected():
        try:
            data = await _request(
                "GET",
                f"/calendars/{settings.google_calendar_id}/events",
                params={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "maxResults": limit,
                    "orderBy": "startTime",
                    "singleEvents": "true",
                },
            )
            out = []
            for ev in data.get("items", []):
                start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
                out.append({"title": ev.get("summary", "(no title)"), "at": start})
            return out
        except Exception:
            pass  # fall through to local mirror
    # Local SQLite mirror (works without Google creds).
    local = _local_upcoming(time_min_dt, time_max_dt, limit)
    return local


def _local_upcoming(time_min_dt: dt.datetime | str, time_max_dt: dt.datetime | str, limit: int = 30) -> list[dict]:
    try:
        from ..memory.store import _connect

        if isinstance(time_min_dt, str):
            clean = time_min_dt.replace("Z", "+00:00")
            time_min_dt = dt.datetime.fromisoformat(clean)
        if isinstance(time_max_dt, str):
            clean = time_max_dt.replace("Z", "+00:00")
            time_max_dt = dt.datetime.fromisoformat(clean)

        tz = time_min_dt.tzinfo or _get_tz()

        with _connect() as conn:
            rows = conn.execute("SELECT title, at FROM events ORDER BY at ASC").fetchall()

        out = []
        for r in rows:
            at_raw = r["at"]
            if not at_raw:
                continue
            try:
                clean_at = at_raw.replace("Z", "+00:00")
                if len(clean_at) <= 10:
                    ev_date = dt.date.fromisoformat(clean_at)
                    if time_min_dt.date() <= ev_date <= time_max_dt.date():
                        out.append({"title": r["title"], "at": r["at"]})
                else:
                    ev_dt = dt.datetime.fromisoformat(clean_at)
                    if ev_dt.tzinfo is None:
                        ev_dt = ev_dt.replace(tzinfo=tz)
                    if time_min_dt <= ev_dt <= time_max_dt:
                        out.append({"title": r["title"], "at": r["at"]})
            except Exception:
                if at_raw >= time_min_dt.isoformat() and at_raw <= time_max_dt.isoformat():
                    out.append({"title": r["title"], "at": r["at"]})
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []



async def calendar(action: str, text: str = "", when: str = "", event_id: str = "") -> str:
    action = (action or "").lower()
    if action == "add":
        if not text:
            return "Provide a title for the event."
        return await add_event(text, when)
    if action == "list":
        return await list_upcoming(limit=15)
    if action == "delete":
        target = (event_id or text).strip()
        if not target:
            return "Provide event_id to delete."
        return await delete_event(target)
    return "Unknown calendar action."