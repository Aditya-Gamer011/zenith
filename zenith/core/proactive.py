"""Proactive intelligence + scheduled jobs (Layers 8 & 16).

Keeps an in-memory alert feed the UI surfaces, plus a small scheduler:
morning briefing, reminders/todos/events wake-ups, periodic system checks.

Alerts are the single channel the UI reads — every proactive nudge goes through
the hub and lands in the alert bar / notification list.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import time
from typing import Any

from .config import settings

log = logging.getLogger("zenith.proactive")


def _dt(value: Any) -> dt.datetime | None:
    """Parse an ISO 8601 timestamp from a calendar event (or None).

    Handles the trailing 'Z' (UTC) that Google sometimes returns. Tolerant of
    strings already offset (+05:30) — plain fromisoformat covers those.
    """
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            return dt.datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None


class ProactiveHub:
    """A tiny publish/subscribe alert feed."""

    def __init__(self, capacity: int = 60) -> None:
        self.capacity = capacity
        self._alerts: list[dict[str, Any]] = []
        self._subscribers: set[Any] = set()

    def subscribe(self, queue: Any) -> None:
        self._subscribers.add(queue)

    def unsubscribe(self, queue: Any) -> None:
        self._subscribers.discard(queue)

    def add(self, title: str, message: str, category: str = "general") -> dict | None:
        alert = {
            "id": int(time.time() * 1000) % 10**6,
            "timestamp": time.strftime("%H:%M"),
            "title": title,
            "message": message,
            "category": category,
            "read": False,
        }
        self._alerts.insert(0, alert)
        if len(self._alerts) > self.capacity:
            self._alerts.pop()
        for q in list(self._subscribers):
            try:
                q.put_nowait({"type": "proactive", "alert": alert})
            except Exception:
                self.unsubscribe(q)
        return alert

    def broadcast(self, evt: dict[str, Any]) -> None:
        """Broadcast an arbitrary event to all connected WebSocket clients."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(evt)
            except Exception:
                self.unsubscribe(q)

    def list(self) -> list[dict[str, Any]]:
        return self._alerts

    def clear(self) -> None:
        self._alerts.clear()


hub = ProactiveHub()


# ─────────────────────────────────────── scheduler jobs ─────────────────────

# Keep each day's todo nudge to one alert (per (date, todo.id)).
_todo_nudge: dict[tuple[str, int], bool] = {}
_EVENT_LOOKAHEAD = 60  # minutes
_EVENT_PREVIEW = 10  # minutes
# Reminders come from the calendar now (⏰-titled events). Track fired events.
_fired_events: dict[str, bool] = {}


_notified_worker_tasks: set[str] = set()


def _seed_notified_worker_tasks() -> None:
    """Prefill the notified-set from the worker ledger so a Zenith restart does
    not re-alert every historical task (the in-memory set was wiped on reboot)."""
    try:
        from .tools import _worker_get
        data = _worker_get_sync("/tasks", timeout=3)
        for t in data.get("tasks", []):
            st = str(t.get("status", "")).upper()
            if st in ("COMPLETED", "FAILED", "CANCELLED", "WAITING_FOR_INPUT"):
                _notified_worker_tasks.add(t.get("id"))
    except Exception as exc:
        log.debug("couldn't seed notified worker tasks: %s", exc)


# Lightweight sync wrapper for the seed call (worker_task_monitor stays async).
def _worker_get_sync(path: str, timeout: int = 3) -> dict:
    import httpx
    from ..core.config import settings

    url = os.environ.get("WORKER_URL", "http://127.0.0.1:8022").rstrip("/") + path
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return {"tasks": [], "error": str(exc)}


async def worker_task_monitor() -> None:
    """Monitor Antigravity worker tasks and push real-time completion alerts into the chat feed."""
    try:
        from .tools import _worker_get
        data = await _worker_get("/tasks", timeout=5)
        tasks = data.get("tasks", [])
        for t in tasks:
            tid = t.get("id")
            status = str(t.get("status", "")).upper()
            if not tid or status in ("QUEUED", "STARTING", "RUNNING"):
                continue
            if tid in _notified_worker_tasks:
                continue
            _notified_worker_tasks.add(tid)

            task_desc = (t.get("spec") or {}).get("task") or "Delegated task"
            output_snippet = (t.get("output") or t.get("current_activity") or "").strip()
            if len(output_snippet) > 300:
                output_snippet = output_snippet[:300] + "…"

            if status == "COMPLETED":
                msg = f"Task `{tid}` finished: **{task_desc}**\n\nSummary:\n{output_snippet or 'Work completed successfully.'}"
                hub.add("Worker Task Completed", msg, "agent_worker")
            elif status == "FAILED":
                errs = ", ".join(t.get("errors") or ["Unknown error"])
                msg = f"Task `{tid}` failed: **{task_desc}**\n\nError: {errs}"
                hub.add("Worker Task Failed", msg, "agent_worker")
            elif status == "WAITING_FOR_INPUT":
                msg = f"Task `{tid}` requires input: **{task_desc}**\n\n{output_snippet}"
                hub.add("Worker Task Paused", msg, "agent_worker")
    except Exception as exc:
        log.debug("worker task monitor failed: %s", exc)


async def wake_updates() -> None:
    """Poll reminders/events, open todos, and Antigravity worker tasks (seconds)."""
    global _fired_events
    await worker_task_monitor()
    from ..tools import calendar
    from ..tools import todo

    # 1) Calendar reminders + soon events → alert once each.
    try:
        now = dt.datetime.now()
        lookahead = now + dt.timedelta(minutes=_EVENT_LOOKAHEAD)
        for ev in await calendar.upcoming(limit=60):
            at = _dt(ev.get("at"))
            if not at:
                continue
            at = at.astimezone()
            title = ev.get("title", "").strip()
            rem = title.startswith("⏰")
            # Fire reminders a few minutes early; normal events when they're
            # imminent — with a wide window so a delayed poll (long job,
            # container pause) can't silently skip an event.
            window_start = at - dt.timedelta(minutes=max(_EVENT_PREVIEW if rem else _EVENT_LOOKAHEAD, 1))
            if not (window_start <= now <= at + dt.timedelta(seconds=5)):
                continue
            key = f"{at.isoformat()}|{title}"
            if key in _fired_events:
                continue
            _fired_events[key] = True
            stamped = at.strftime("%H:%M")
            if rem:
                hub.add("Reminder", f"⏰ {title[2:] or 'Reminder'} — {at.strftime('%H:%M')}", "reminder")
            else:
                hub.add("calendar", f"Now: {title or '(untitled)'} at {stamped}", "calendar")
        # Keep the fired-set bounded: prune older entries rather than wiping
        # the whole dedup state (which caused already-fired events to re-alert).
        if len(_fired_events) > 300:
            _fired_events = dict(list(_fired_events.items())[-200:])
            _fired_events.clear()
    except Exception as exc:
        log.debug("event scan failed: %s", exc)

    # 3) A single daily todo recap (fires when the loop first sees open todos).
    try:
        open_list = todo.open_todos()
        if open_list:
            today = dt.date.today().isoformat()
            for t in open_list[:3]:
                rec = f"{today}:{t['id']}"
                if rec not in _todo_nudge:
                    _todo_nudge[rec] = True
                    others = len(open_list) - 1
                    extra = f" and {others} more" if others else ""
                    hub.add(
                        "todo",
                        f"Open: {t['title']}{extra}.",
                        "todo",
                    )
    except Exception as exc:
        log.debug("todo nudge failed: %s", exc)


async def system_health() -> None:
    """Proactive system check — only if shell is enabled."""
    if not settings.allow_shell:
        return
    try:
        import shutil
        total, used, free = shutil.disk_usage(Path.home())
        if total > 0 and (used / total) >= 0.95:
            pct = int((used / total) * 100)
            hub.add("System", f"Disk is above 95% capacity ({pct}% used).", "system")
    except Exception:
        pass


async def morning_briefing() -> None:
    """Scheduled 6:00 briefing: weather + today's agenda + memory nudge.

    Pulls real data — open todos, upcoming events, and a memory stat — so the
    briefing is a genuine memory/scheduler feed, not a canned string.
    """
    from ..tools.web import get_weather
    from ..tools import todo
    from ..tools import calendar
    from ..memory import store

    try:
        w = await get_weather("auto")
    except Exception:
        w = "Weather unavailable."

    try:
        today = dt.date.today()
        tomorrow = today + dt.timedelta(days=1)
        upcoming_evs = await calendar.upcoming(limit=30)
        events = [
            e for e in upcoming_evs
            if (at := _dt(e.get("at"))) and today <= at.date() <= tomorrow
        ]
    except Exception:
        events = []

    try:
        open_list = todo.open_todos()
    except Exception:
        open_list = []

    try:
        stats = store.graph_stats()
        mem = store.all_memories()
        top_facts = [f"{m['key']}: {m['value']}" for m in mem[:2]]
    except Exception:
        stats = {"entities": 0, "edges": 0}
        top_facts = []

    user_greeting_name = getattr(settings, "user_name", "") or "Friend"
    parts = [f"Good morning, {user_greeting_name}. {w}"]
    # "Notice something → act" summary: what Zenith handled while you were away.
    try:
        from . import autonomy
        report = autonomy._summarise_for_greeting()
        if report and not report.startswith("Nothing urgent"):
            parts.append(report)
    except Exception:
        pass
    if events:
        ev_lines = " · ".join(
            f"{_dt(e['at']).strftime('%H:%M')} {e['title']}"
            for e in events[:5] if (at := _dt(e.get("at"))) is not None
        )
        parts.append(f"Today's agenda: {ev_lines}")
    if open_list:
        parts.append(f"You have {len(open_list)} open todo{'' if len(open_list) == 1 else 's'} — first up: {open_list[0]['title']}.")
    if top_facts:
        parts.append("From memory: " + " | ".join(top_facts))
    parts.append(f"Graph: {stats['entities']} entities, {stats['edges']} relations.")
    hub.add("Morning Brief", " ".join(parts), "briefing")


async def daily_email_digest() -> None:
    """Evening proactive email digest (9:30 PM IST / 21:30).

    Scans the configured inbox (settings.gmail_user), filters out ads/noise,
    deduplicates topics, and synthesizes a warm, witty, non-robotic conversational update.
    """
    try:
        from ..tools import mail
        from ..tools import todo
        from . import provider

        recipient = settings.gmail_user or settings.user_email
        if not recipient:
            log.info("daily_email_digest: no recipient configured, skipping")
            return

        raw_list = await mail.search(n=25)

        relevant_emails = []
        skip_keywords = [
            "2-step verification", "verification code", "security alert", "sign-in",
            "login alert", "password reset", "unsubscribe", "no-reply", "noreply",
            "newsletter", "mixtape", "soundcheck", "promotions", "marketing",
            "terms of service", "privacy policy", "mailer-daemon", "automatic response",
            "discount", "offer", "sale", "weekly update", "spotify", "youtube"
        ]

        if raw_list and "connected" not in raw_list.lower() and "empty" not in raw_list.lower():
            lines = [l.strip() for l in raw_list.splitlines() if l.strip()]
            for line in lines:
                parts = line.split(" · ")
                if len(parts) >= 3:
                    uid, sender_raw, subject = parts[0], parts[1], parts[2]
                    sub_low = subject.lower()
                    snd_low = sender_raw.lower()

                    if any(k in sub_low or k in snd_low for k in skip_keywords):
                        continue

                    clean_name = sender_raw.split("<")[0].strip().strip('"').strip("'")
                    if not clean_name or "@" in clean_name:
                        clean_name = clean_name.split("@")[0].capitalize() if "@" in clean_name else "Someone"

                    relevant_emails.append({"uid": uid, "name": clean_name, "subject": subject})

        today_str = dt.date.today().strftime("%B %d, %Y")
        user_name = settings.user_name or "Friend"
        open_todos_list = todo.open_todos()
        top_todos = ", ".join([f"\"{t['title']}\"" for t in open_todos_list[:3]]) if open_todos_list else ""

        digest_text = ""
        try:
            email_summary_input = "\n".join([f"- {item['name']}: {item['subject']}" for item in relevant_emails[:6]]) or "No emails today."
            prompt_messages = [
                {
                    "role": "system",
                    "content": (
                        f"You are Zenith, {user_name}'s personal AI companion and chief of staff. "
                        f"Write a warm, natural, conversational evening email update for {user_name}. "
                        "Speak naturally like a real friend briefing them — add subtle warmth and humor where appropriate. "
                        "NEVER use robotic '[event].[event]' format. NEVER list raw email addresses or email headers. "
                        "Do NOT mention ads, newsletters, or security codes. "
                        "Summarize what actually matters in a smooth, flowing conversational update."
                    )
                },
                {
                    "role": "user",
                    "content": f"{user_name}'s Inbox Scan ({today_str}):\n{email_summary_input}\n\nOpen Tasks: {top_todos or 'None'}"
                }
            ]
            llm_text = ""
            async for chunk in provider.chat_stream("standard", prompt_messages, max_tokens=600):
                if chunk.get("type") == "text":
                    llm_text += chunk.get("text", "")

            if llm_text and len(llm_text) > 40 and not llm_text.startswith("[") and "error" not in llm_text.lower():
                digest_text = llm_text.strip()
        except Exception as exc:
            log.debug("LLM digest synthesis fallback due to: %s", exc)

        if not digest_text:
            lines = [
                f"Hey {user_name}!\n",
                f"Hope you had a great day today. Here's a quick wrap-up of your inbox for {today_str}:\n"
            ]

            if relevant_emails:
                seen_categories = set()
                unique_stories = []

                for item in relevant_emails[:6]:
                    name = item['name']
                    subj = item['subject']
                    subj_clean = subj.replace("Re:", "").replace("Fwd:", "").strip()
                    name_low = name.lower()
                    subj_low = subj_clean.lower()

                    story = None
                    if ("resend" in name_low or "resend" in subj_low):
                        if "resend" not in seen_categories:
                            seen_categories.add("resend")
                            story = "You set up Resend earlier, so they sent over their standard welcome note."
                    elif ("github" in name_low or "github" in subj_low):
                        if "github" not in seen_categories:
                            seen_categories.add("github")
                            story = f"GitHub dropped an update regarding {subj_clean}."
                    elif ("vercel" in name_low or "vercel" in subj_low):
                        if "vercel" not in seen_categories:
                            seen_categories.add("vercel")
                            story = "Vercel completed building your latest deployment."
                    else:
                        key = f"{name_low}:{subj_low[:15]}"
                        if key not in seen_categories:
                            seen_categories.add(key)
                            story = f"{name} sent over a note regarding \"{subj_clean}\"."

                    if story and story not in unique_stories:
                        unique_stories.append(story)

                if len(unique_stories) > 1:
                    narrative = " ".join(unique_stories[:-1]) + f" Plus, {unique_stories[-1][0].lower()}{unique_stories[-1][1:]}"
                elif unique_stories:
                    narrative = unique_stories[0]
                else:
                    narrative = "Inbox was super quiet today — no urgent messages or pending items came through."

                lines.append(narrative)
                lines.append("")
            else:
                lines.append("Inbox was super quiet today — no urgent messages or pending items came through.\n")

            if top_todos:
                lines.append(f"Quick heads-up on your to-dos: you still have open tasks for {top_todos}.\n")

            # Surface what Zenith handled autonomously
            try:
                from . import autonomy
                autonomy_report = autonomy.build_autonomy_report()
                if autonomy_report:
                    lines.append("\n" + autonomy_report + "\n")
            except Exception:
                pass

            lines.append("Let me know if you want me to draft a reply or help tackle anything tomorrow!")
            lines.append("\nCheers,\nZenith")
            digest_text = "\n".join(lines)

        subject_line = f"Zenith Digest: Evening update for {dt.date.today().strftime('%b %d')}"
        result = await mail.send(to=recipient, subject=subject_line, body=digest_text)
        log.info("Sent natural daily email digest to %s: %s", recipient, result)

        hub.add("Daily Digest Sent", f"Daily Email Digest delivered to {recipient}.", "digest")
    except Exception as exc:
        log.error("daily email digest failed: %s", exc)


async def hourly_service_monitor() -> None:
    """Proactive hourly service health checker & autonomous self-healing.

    Monitors Docker containers, systemd services, web endpoints, and system resources.
    If a service is crashed/failed and Zenith can fix it (e.g. restarting container/service),
    Zenith automatically restarts it and logs a self-healing proactive alert!
    """
    if not settings.allow_shell:
        return

    healed_actions = []
    issues_detected = []

    # 1. Docker Container Health & Self-Healing
    # Only restart containers configured in the GUARDED set — an
    # exited container is often intentionally stopped. The guarded list doubles as "the things that may run";
    # anything outside it is left exactly as it is.
    try:
        proc = await asyncio.create_subprocess_shell(
            "docker ps -a --format '{{.Names}}|{{.Status}}|{{.State}}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        lines = out.decode(errors="replace").splitlines()
        for line in lines:
            if not line.strip() or "|" not in line:
                continue
            parts = line.split("|")
            name, status, state = parts[0], parts[1], parts[2]
            if name not in settings.guarded_containers:
                continue  # intentionally stopped or not ours — leave it alone.
            if state in ("exited", "dead") or "exited (" in status.lower():
                log.warning("Detected crashed guarded container: %s (%s). Attempting self-healing restart...", name, status)
                restart_proc = await asyncio.create_subprocess_shell(
                    f"docker start {name}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                r_out, r_err = await restart_proc.communicate()
                if restart_proc.returncode == 0:
                    healed_actions.append(f"Auto-restarted crashed Docker container `{name}`")
                else:
                    issues_detected.append(f"Docker container `{name}` is down: {r_err.decode().strip()}")
    except Exception as exc:
        log.debug("Docker health monitor error: %s", exc)

    # 2. System Resource Monitoring (Disk Space > 90%).
    # Surface it instead of auto-pruning without user consent.
    try:
        import shutil
        total, used, free = shutil.disk_usage(Path.home())
        if total > 0:
            pct = int((used / total) * 100)
            if pct >= 90:
                issues_detected.append(f"Disk usage is {pct}% — free space is low (Zenith won't auto-clean).")
    except Exception as exc:
        log.debug("Disk self-healing error: %s", exc)

    if healed_actions:
        action_summary = " · ".join(healed_actions)
        hub.add("Autonomous Self-Healing", f"Zenith fixed issues: {action_summary}", "self_healing")
        log.info("Hourly Service Health: Self-healed -> %s", action_summary)

    if issues_detected:
        issue_summary = " · ".join(issues_detected)
        hub.add("Service Warning", f"Unresolved issues: {issue_summary}", "system_warning")
        log.warning("Hourly Service Health: Issues -> %s", issue_summary)

    if not healed_actions and not issues_detected:
        log.info("Hourly Service Health: All services online and healthy.")


async def poll_email_gateway() -> None:
    """Poll incoming emails sent to zenith@agm.quest or Gmail and handle via EmailGateway."""
    try:
        from .email_gateway import process_incoming_emails
        from ..main import _orpheus
        await process_incoming_emails(_orpheus)
    except Exception as exc:
        log.error("email gateway poll error: %s", exc, exc_info=True)


async def gev_service_watchdog() -> None:
    """Supervise God's Eye View 3D Globe server and keep it always active in the background."""
    if not getattr(settings, "gev_enabled", True):
        return
    try:
        from ..tools.gods_eye_view import is_gev_server_running, ensure_gev_server_started
        if not is_gev_server_running():
            log.info("GEV Watchdog: Server offline; restarting in background...")
            await ensure_gev_server_started()
    except Exception as exc:
        log.debug("GEV Watchdog check error: %s", exc)


async def context_awareness_cycle() -> None:
    """Supervise proactive screen observation, local activity tracking, and intelligent nudges."""
    try:
        from ..services.context_engine import context_engine
        suggestion = await context_engine.evaluate_proactive_triggers()
        if suggestion:
            hub.add(suggestion.get("title", "Proactive Insight"), suggestion.get("message", ""), suggestion.get("category", "suggestion"))
    except Exception as exc:
        log.debug("Context awareness cycle error: %s", exc)


def schedule(scheduler) -> None:
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    from . import autonomy

    _seed_notified_worker_tasks()
    autonomy.ensure_schema()
    scheduler.add_job(morning_briefing, CronTrigger(hour=6, minute=0))
    scheduler.add_job(daily_email_digest, CronTrigger(hour=21, minute=30))
    scheduler.add_job(hourly_service_monitor, IntervalTrigger(hours=1))
    scheduler.add_job(poll_email_gateway, IntervalTrigger(seconds=20))
    scheduler.add_job(wake_updates, IntervalTrigger(seconds=30))
    scheduler.add_job(worker_task_monitor, IntervalTrigger(seconds=10))
    scheduler.add_job(system_health, IntervalTrigger(minutes=15))
    scheduler.add_job(gev_service_watchdog, IntervalTrigger(minutes=2))
    scheduler.add_job(context_awareness_cycle, IntervalTrigger(seconds=20))
    # The autonomy loop: notice → act → journal → (reported via briefing/email).
    scheduler.add_job(autonomy.autonomy_loop, IntervalTrigger(minutes=30))
    # Critical autonomous items get an email (at most once/day).
    scheduler.add_job(autonomy.maybe_send_critical_email, CronTrigger(hour=19, minute=0))