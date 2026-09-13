"""Reminders tool — SQLite-backed wakeups checked by the scheduler.

Stored in the same DB as everything else, so a container restart doesn't
forget a reminder. `due()` is called by the scheduler's proactive hub every
30s and marks fired reminders so each fires once.
"""
from __future__ import annotations

import time

from ..memory.store import _connect


def add(text: str, when: str) -> str:
    if not text:
        return "Reminder needs text."
    w = (when or "").strip()
    try:
        hh, mm = (w.split(":") + ["0"])[:2]
        hh, mm = int(hh), int(mm)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError
    except (ValueError, AttributeError):
        return "Use time as HH:MM, e.g. 09:30."
    with _connect() as conn:
        conn.execute(
            "INSERT INTO reminders (text, at, active) VALUES (?, ?, 1)",
            (text, w),
        )
        conn.commit()
    return f"Reminder set: {text} @ {hh:02d}:{mm:02d}"


def list_all() -> str:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, text, at, active FROM reminders ORDER BY at, id"
        ).fetchall()
    if not rows:
        return "No reminders."
    out = []
    for r in rows:
        state = "✓" if not r["active"] else "•"
        out.append(f"{state} {r['id']}. {r['text']} @ {r['at']}")
    return "\n".join(out)


def all_rows() -> list[dict]:
    """Full reminder rows for the UI / scheduler."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, text, at, active FROM reminders ORDER BY at, id LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]


async def clear() -> str:
    with _connect() as conn:
        conn.execute("DELETE FROM reminders")
        conn.commit()
    return "Reminders cleared."


async def remove(rid: int) -> str:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM reminders WHERE id = ?", (rid,))
        conn.commit()
    return "Reminder removed." if cur.rowcount else "Reminder not found."


def now_minutes() -> int:
    lt = time.localtime()
    return lt.tm_hour * 60 + lt.tm_min


def due() -> list[dict]:
    """Return reminders scheduled at-or-before now that haven't fired.

    Fired reminders are marked inactive (they stay visible until cleared).
    If a reminder's time has already passed for today it still fires once on
    the next scheduler tick (so a 08:00 reminder set at 09:00 still nudges).
    """
    lt = time.localtime()
    now_min = lt.tm_hour * 60 + lt.tm_min
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, text, at, active FROM reminders WHERE active = 1"
        ).fetchall()
        out = []
        for r in rows:
            try:
                hh, mm = (r["at"].split(":") + ["0"])[:2]
                if 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
                    at_min = int(hh) * 60 + int(mm)
                    if at_min <= now_min:
                        conn.execute("UPDATE reminders SET active = 0 WHERE id = ?", (r["id"],))
            except (ValueError, TypeError):
                pass
            out.append(dict(r))
        conn.commit()
    return out


async def reminder(action: str, text: str = "", when: str = "", rid: int | None = None) -> str:
    action = (action or "").lower()
    if action == "add":
        return add(text, when)
    if action == "list":
        return list_all()
    if action == "clear":
        return clear()
    if action == "delete":
        if rid is None:
            return "Provide rid."
        return remove(rid)
    return "Unknown reminder action."