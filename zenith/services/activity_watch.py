"""ActivityWatch local timeline recorder and activity analysis for Zenith.

Maintains a privacy-conscious local activity timeline:
  - Applications and websites visited.
  - Time spent on tasks, projects, and documents.
  - Distinguishes between active work, idle time, and interruptions.
  - Contextual recall (e.g., "What was I working on before lunch?").
  - Privacy-preserving: local storage, respects PrivacyGuard blocklists & Ghost Mode, easily cleared.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ..core.config import settings
from .privacy_guard import privacy_guard

log = logging.getLogger("zenith.activity_watch")

# Rule-based application categorization
CATEGORY_RULES = {
    "coding": [
        "code", "vscode", "cursor", "pycharm", "intellij", "sublime", "vim", "nvim",
        "emacs", "terminal", "bash", "zsh", "alacritty", "iterm", "git", "tmux"
    ],
    "research": [
        "firefox", "chrome", "chromium", "brave", "edge", "safari", "wikipedia",
        "stackoverflow", "github", "arxiv", "doc", "pdf", "notion", "obsidian"
    ],
    "design": [
        "figma", "canva", "photoshop", "illustrator", "gimp", "blender", "inkscape"
    ],
    "communication": [
        "slack", "discord", "teams", "telegram", "thunderbird", "mail", "zoom", "meet"
    ],
    "entertainment": [
        "spotify", "youtube", "netflix", "vlc", "steam", "game"
    ],
}


def categorize_app(app_name: str, window_title: str) -> str:
    """Classify app/window into coding, research, design, communication, or general."""
    text = f"{app_name} {window_title}".lower()
    for cat, keywords in CATEGORY_RULES.items():
        if any(k in text for k in keywords):
            return cat
    return "general"


class ActivityWatchService:
    """Local timeline recorder and contextual recall engine."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or settings.db_path)
        self._lock = threading.Lock()
        self._last_event: Optional[Dict[str, Any]] = None
        self._last_heartbeat_time = time.time()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS activity_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        epoch_time REAL NOT NULL,
                        duration_seconds REAL DEFAULT 15.0,
                        app_name TEXT NOT NULL,
                        window_title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        domain TEXT DEFAULT '',
                        is_idle INTEGER DEFAULT 0,
                        details_json TEXT DEFAULT '{}'
                    );"""
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_activity_epoch ON activity_events(epoch_time);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_activity_app ON activity_events(app_name);"
                )
                conn.commit()
        except Exception as e:
            log.warning("ActivityWatchService table init failed: %s", e)

    def record_heartbeat(
        self,
        app_name: str,
        window_title: str,
        domain: str = "",
        duration_seconds: float = 15.0,
        is_idle: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record an activity pulse. Respects Ghost Mode and privacy blocklists."""
        if not privacy_guard.can_observe_app(app_name):
            return False
        if domain and not privacy_guard.can_observe_domain(domain):
            return False

        app_name = (app_name or "Unknown").strip()
        window_title = (window_title or "").strip()
        domain = (domain or "").strip()
        category = categorize_app(app_name, window_title)
        now_epoch = time.time()
        det_str = json.dumps(details or {})

        with self._lock:
            # If the current event is a continuation of the last active window within 45s,
            # we can accumulate duration instead of creating infinite row spam
            if (
                self._last_event
                and self._last_event["app_name"] == app_name
                and self._last_event["window_title"] == window_title
                and self._last_event["is_idle"] == int(is_idle)
                and (now_epoch - self._last_heartbeat_time) <= 60.0
            ):
                event_id = self._last_event["id"]
                add_dur = max(1.0, now_epoch - self._last_heartbeat_time)
                try:
                    with self._connect() as conn:
                        conn.execute(
                            "UPDATE activity_events SET duration_seconds = duration_seconds + ? WHERE id = ?",
                            (add_dur, event_id),
                        )
                        conn.commit()
                    self._last_heartbeat_time = now_epoch
                    return True
                except Exception as e:
                    log.warning("Failed to update activity event duration: %s", e)

            # Otherwise, insert a new event row
            try:
                with self._connect() as conn:
                    cur = conn.execute(
                        """INSERT INTO activity_events
                           (epoch_time, duration_seconds, app_name, window_title, category, domain, is_idle, details_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (now_epoch, duration_seconds, app_name, window_title, category, domain, int(is_idle), det_str),
                    )
                    conn.commit()
                    self._last_event = {
                        "id": cur.lastrowid,
                        "app_name": app_name,
                        "window_title": window_title,
                        "is_idle": int(is_idle),
                    }
                    self._last_heartbeat_time = now_epoch
                    return True
            except Exception as e:
                log.warning("Failed to insert activity event: %s", e)
                return False

    def get_timeline(self, limit: int = 60, hours: float = 24.0) -> List[Dict[str, Any]]:
        """Fetch timeline events from the last N hours."""
        since = time.time() - (hours * 3600.0)
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT id, timestamp, epoch_time, duration_seconds, app_name, window_title,
                              category, domain, is_idle, details_json
                       FROM activity_events
                       WHERE epoch_time >= ?
                       ORDER BY epoch_time DESC LIMIT ?""",
                    (since, limit),
                ).fetchall()
                out = []
                for r in rows:
                    out.append({
                        "id": r["id"],
                        "timestamp": r["timestamp"],
                        "epoch_time": r["epoch_time"],
                        "duration_seconds": round(r["duration_seconds"], 1),
                        "app_name": r["app_name"],
                        "window_title": r["window_title"],
                        "category": r["category"],
                        "domain": r["domain"],
                        "is_idle": bool(r["is_idle"]),
                        "details": json.loads(r["details_json"] or "{}"),
                    })
                return out
        except Exception as e:
            log.warning("Failed to fetch activity timeline: %s", e)
            return []

    def get_summary(self, hours: float = 24.0) -> Dict[str, Any]:
        """Aggregate productivity statistics, active vs idle duration, and top apps."""
        since = time.time() - (hours * 3600.0)
        try:
            with self._connect() as conn:
                total_rows = conn.execute(
                    """SELECT
                         SUM(CASE WHEN is_idle = 0 THEN duration_seconds ELSE 0 END) as active_sec,
                         SUM(CASE WHEN is_idle = 1 THEN duration_seconds ELSE 0 END) as idle_sec,
                         COUNT(*) as total_events
                       FROM activity_events WHERE epoch_time >= ?""",
                    (since,),
                ).fetchone()

                active_sec = float(total_rows["active_sec"] or 0)
                idle_sec = float(total_rows["idle_sec"] or 0)

                # Top apps
                app_rows = conn.execute(
                    """SELECT app_name, category, SUM(duration_seconds) as total_sec
                       FROM activity_events
                       WHERE epoch_time >= ? AND is_idle = 0
                       GROUP BY app_name ORDER BY total_sec DESC LIMIT 10""",
                    (since,),
                ).fetchall()
                top_apps = [
                    {
                        "app_name": r["app_name"],
                        "category": r["category"],
                        "minutes": round(r["total_sec"] / 60.0, 1),
                        "percent": round((r["total_sec"] / active_sec * 100.0) if active_sec > 0 else 0, 1),
                    }
                    for r in app_rows
                ]

                # Category breakdown
                cat_rows = conn.execute(
                    """SELECT category, SUM(duration_seconds) as total_sec
                       FROM activity_events
                       WHERE epoch_time >= ? AND is_idle = 0
                       GROUP BY category ORDER BY total_sec DESC""",
                    (since,),
                ).fetchall()
                categories = {
                    r["category"]: round(r["total_sec"] / 60.0, 1) for r in cat_rows
                }

                return {
                    "hours_inspected": hours,
                    "active_minutes": round(active_sec / 60.0, 1),
                    "idle_minutes": round(idle_sec / 60.0, 1),
                    "total_events": total_rows["total_events"] or 0,
                    "top_apps": top_apps,
                    "categories": categories,
                }
        except Exception as e:
            log.warning("Failed to generate activity summary: %s", e)
            return {"active_minutes": 0, "idle_minutes": 0, "top_apps": [], "categories": {}}

    def recall_activity(self, query: str = "", time_anchor: Optional[str] = None, hours: float = 24.0) -> str:
        """Search past activity matching natural language or keyword query."""
        timeline = self.get_timeline(limit=120, hours=hours)
        if not timeline:
            return f"No activity recorded in the past {hours} hours (or Ghost Mode was active)."

        # If natural language time anchor given (e.g. 'morning', 'lunch', 'yesterday', 'afternoon')
        q_low = (query or "").lower().strip()
        t_low = (time_anchor or "").lower().strip()
        combined = f"{q_low} {t_low}".strip()

        matched = []
        for ev in timeline:
            ev_text = f"{ev['app_name']} {ev['window_title']} {ev['category']} {ev['domain']}".lower()
            if not combined or any(term in ev_text for term in combined.split()):
                matched.append(ev)

        if not matched:
            matched = timeline[:15]  # fall back to most recent entries

        lines = [f"Found {len(matched)} relevant activity entries:"]
        for ev in matched[:20]:
            idle_tag = " [IDLE]" if ev["is_idle"] else ""
            lines.append(
                f"- [{ev['timestamp']}] {ev['app_name']} ({ev['category']}): "
                f"\"{ev['window_title']}\" ({ev['duration_seconds']}s){idle_tag}"
            )
        return "\n".join(lines)

    def clear_activity(self, hours: Optional[float] = None) -> int:
        """Clear all or recent activity events."""
        with self._lock:
            try:
                with self._connect() as conn:
                    if hours is None:
                        cur = conn.execute("DELETE FROM activity_events")
                    else:
                        since = time.time() - (hours * 3600.0)
                        cur = conn.execute("DELETE FROM activity_events WHERE epoch_time >= ?", (since,))
                    conn.commit()
                    self._last_event = None
                    return cur.rowcount
            except Exception as e:
                log.warning("Failed to clear activity: %s", e)
                return 0


# Singleton instance
activity_watch = ActivityWatchService()
