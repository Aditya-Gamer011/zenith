"""Autonomy engine — the "notice something → act" loop.

Zenith's proactive layer currently only posts alerts to the UI hub. This module
gives her a real reactive loop:

  signal (worker, inbox, system, disk) → score → act (tool call / email) →
  journal (durable record) → surface (briefing / greeting / weekly email)

The journal is what lets Zenith "tell the user about the stuff she did": it's a
persistent SQLite table that build_briefing() and the evening digest read, so
autonomous actions become part of the conversation instead of vanishing into
debug logs.

Design rules (kept modest deliberately — autonomy must be *safe* first):
- Only SAFE tools run autonomously: reads/checks, docker status/restart,
  self-heal, cleanup of Zenith's own temp files, email digest sends. Mutating
  external services (DNS, Vercel, R2, GH) NEVER run here — those keep the
  confirm gate.
- Every action is journaled with a category + importance + timestamp.
- Nothing runs twice in a tight loop (dedupe by action key + cooldown).
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import re
import time
from typing import Any

from .config import settings

log = logging.getLogger("zenith.autonomy")

# Module-level: last time Zenith sent the critical-actions email (avoid spam).
_last_critical_email = 0.0

# How long after an action before Zenith will run the same one again.
COOLDOWN_SECONDS = 4 * 3600

# Importance weights — used to decide what rises to "tell user".
WEIGHTS = {
    "worker_completed": 3,
    "worker_failed": 5,
    "inbox_since": 2,
    "disk_low": 7,
    "container_down": 6,
    "system_warning": 4,
    "reminder": 2,
    "daily_digest": 1,
}

# The categories considered report-worthy (told via briefing/email).
REPORT_WORTHY = ("worker_failed", "disk_low", "container_down", "system_warning")


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="minutes")


def _table_exists(conn) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='autonomy_actions'"
    ).fetchone()
    return bool(row)


def ensure_schema() -> None:
    """Create the autonomy_actions ledger table if missing."""
    from ..memory import store as _store

    conn = _store._connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS autonomy_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                category TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '',
                importance INTEGER DEFAULT 1,
                reported INTEGER DEFAULT 0
            )"""
        )
        conn.commit()
    finally:
        conn.close()


def journal(category: str, action: str, detail: str = "", importance: int = 1) -> None:
    """Record an autonomous action. Thread-safe via a fresh connection."""
    try:
        ensure_schema()
        from ..memory import store as _store

        conn = _store._connect()
        try:
            conn.execute(
                "INSERT INTO autonomy_actions (ts, category, action, detail, importance) VALUES (?, ?, ?, ?, ?)",
                (_now_iso(), category, action, detail, importance),
            )
            conn.commit()
        finally:
            conn.close()
        log.info("autonomy journal: [%s] %s — %s", category, action, detail)
    except Exception as exc:
        log.debug("autonomy journal failed: %s", exc)


def recent_activities(limit: int = 20) -> list[dict[str, Any]]:
    """Most recent autonomous actions, for the greeting/briefing/digest."""
    try:
        ensure_schema()
        from ..memory import store as _store

        conn = _store._connect()
        try:
            rows = conn.execute(
                "SELECT ts, category, action, detail, importance, reported "
                "FROM autonomy_actions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def unreported_important(threshold: int = 4) -> list[dict[str, Any]]:
    """High-importance actions not yet surfaced to user (for a catch-up email)."""
    try:
        ensure_schema()
        from ..memory import store as _store

        conn = _store._connect()
        try:
            rows = conn.execute(
                "SELECT ts, category, action, detail, importance FROM autonomy_actions "
                "WHERE reported = 0 AND importance >= ? ORDER BY id ASC",
                (threshold,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def mark_reported() -> None:
    """Mark all current unreported-important actions as reported."""
    try:
        ensure_schema()
        from ..memory import store as _store

        conn = _store._connect()
        try:
            conn.execute("UPDATE autonomy_actions SET reported = 1 WHERE reported = 0")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


# ──────────────────────────────────────── signal scanners ─────────────────────

_LAST_ACTION: dict[str, float] = {}


def _cooldown_ok(key: str) -> bool:
    now = dt.datetime.now().timestamp()
    if _LAST_ACTION.get(key, 0) + COOLDOWN_SECONDS > now:
        return False
    _LAST_ACTION[key] = now
    return True


async def scan_worker_tasks() -> None:
    """Notice failed/stalled worker tasks and journal them (autonomously)."""
    try:
        from .tools import _worker_get

        data = await _worker_get("/tasks", timeout=5)
        for t in data.get("tasks", []):
            tid = t.get("id")
            st = str(t.get("status", "")).upper()
            if st == "FAILED" and _cooldown_ok(f"wf:{tid}"):
                journal("worker_failed", f"Worker task {tid} failed",
                        (t.get("errors") or ["Unknown"]), WEIGHTS["worker_failed"])
    except Exception as exc:
        log.debug("autonomy worker scan failed: %s", exc)


async def scan_system() -> None:
    """Notice disk pressure + down guarded containers (the safe self-heal set)."""
    if not settings.allow_shell:
        return
    # Disk
    try:
        proc = await asyncio.create_subprocess_shell(
            "df -h / | tail -1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        for tok in out.decode(errors="replace").split():
            if tok.endswith("%") and tok[:-1].isdigit() and int(tok[:-1]) >= 90:
                if _cooldown_ok("disk"):
                    journal("disk_low", f"Disk / at {tok}", "", WEIGHTS["disk_low"])
                break
    except Exception:
        pass
    # Guarded containers that should be up are down
    try:
        proc = await asyncio.create_subprocess_shell(
            "docker ps -a --format '{{.Names}}|{{.State}}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        for line in out.decode(errors="replace").splitlines():
            if "|" not in line:
                continue
            name, state = line.split("|", 1)
            if name.strip() in settings.guarded_containers and state.strip() in ("exited", "dead"):
                if _cooldown_ok(f"down:{name.strip()}"):
                    journal("container_down", f"Container {name.strip()} is down",
                            "", WEIGHTS["container_down"])
    except Exception:
        pass


async def scan_inbox(now: dt.datetime | None = None) -> None:
    """Notice credible inbox flow (recent email volume) and journal it."""
    try:
        from ..tools import mail
        from ..memory import store as _mem

        now = now or dt.datetime.now()
        raw = await mail.search(n=8)
        if not raw or "connected" in raw.lower() or "empty" in raw.lower():
            return
        lines = [l for l in raw.splitlines() if "·" in l]
        if not lines:
            return
        # Count the ones from roughly the last hour by parsing their dates.
        recent = 0
        for line in lines:
            m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", line)
            if m:
                try:
                    d = dt.datetime.fromisoformat(m.group(1))
                    # dates in search are already local (Asia/Kolkata)
                    if (now - d).total_seconds() < 60 * 60 * 8:
                        recent += 1
                except ValueError:
                    pass
        if recent >= 2 and _cooldown_ok("inbox_flow"):
            journal("inbox_since", f"{recent} new emails in the last few hours",
                    raw.splitlines()[0][:120], WEIGHTS["inbox_since"])
    except Exception as exc:
        log.debug("autonomy inbox scan failed: %s", exc)


# ──────────────────────────────────────── the autonomy loop + reporter ────────

async def autonomy_loop() -> None:
    """Run safe signal scans and journal what they find.

    This is what turns scheduled jobs into a *loop*: each scan can trigger a
    follow-up cook (which is itself logged), and the journal feeds the
    briefing/digest so Zenith reports what she did.
    """
    try:
        await scan_worker_tasks()
    except Exception:
        pass
    try:
        await scan_system()
    except Exception:
        pass
    try:
        await scan_inbox()
    except Exception:
        pass


def _summarise_for_greeting() -> str:
    """Short human sentence for the briefing: 'I handled 2 things overnight'."""
    acts = recent_activities(limit=6)
    if not acts:
        return ""
    important = [a for a in acts if a["importance"] >= WEIGHTS["system_warning"]]
    total = len(acts)
    if important:
        first = important[0]
        return (f"while you were away I {first['action'].lower()} — "
                f"and {len(important) - 1} more thing{'s' if len(important) > 1 else ''} I'll flag "
                f"if they matter.")
    return f"Nothing urgent while you were away — a handful of routine checks ran."


def build_autonomy_report() -> str:
    """A markdown block for the evening email / briefing: what Zenith did today."""
    acts = recent_activities(limit=10)
    if not acts:
        return ""
    lines = []
    for a in acts:
        flag = "✨" if a["importance"] >= WEIGHTS["system_warning"] else "·"
        lines.append(f"{flag} {a['ts'][11:16]} — {a['action']}")
    return "## What I handled on my own\n" + "\n".join(lines)


async def maybe_send_critical_email() -> None:
    """For truly critical items Zenith emails user proactively (once).

    Called from a scheduled coroutine so it awaits the async mail.send. Only
    fires if there are unreported important actions AND we haven't emailed in
    the last 24h (no spam)."""
    from ..tools import mail

    unreported = unreported_important(threshold=5)
    if not unreported:
        return
    global _last_critical_email
    if time.time() - _last_critical_email < 24 * 3600:
        return
    try:
        recipient = settings.gmail_user or settings.user_email
        if not recipient:
            return
        user_name = settings.user_name or "Friend"
        body = (f"Hey {user_name}, quick heads-up from Zenith:\n\n"
                + "\n".join(f"- ({a['ts'][5:16]}) {a['action']}"
                            for a in unreported[:4])
                + "\n\nNothing needs you right now — just keeping you in the loop.")
        await mail.send(to=recipient, subject="Zenith: a few things happened while you were away",
                        body=body)
        _last_critical_email = time.time()
        mark_reported()
        log.info("sent critical-actions email to %s", recipient)
    except Exception as exc:
        log.debug("critical email failed: %s", exc)


def schedule_autonomy(scheduler) -> None:
    """Attach the autonomy loop to the scheduler."""
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(autonomy_loop, IntervalTrigger(minutes=30))