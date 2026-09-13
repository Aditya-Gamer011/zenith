"""Privacy Guard & Sovereign Consent Layer for Zenith.

Provides:
  - Ghost Mode (master privacy switch that turns off all background sensing:
    screen awareness, camera, activitywatch, and memory auto-extraction).
  - Granular sensor toggles (screen, camera, activity, browser, memory).
  - Application and domain blocklists to protect sensitive apps (password managers, banking, etc.).
  - Local persistence via SQLite.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List, Set

from ..core.config import settings

log = logging.getLogger("zenith.privacy_guard")

# Default sensitive applications never to observe
DEFAULT_BLOCKED_APPS = [
    "1password",
    "bitwarden",
    "keepass",
    "lastpass",
    "keychain",
    "authenticator",
    "tor browser",
    "signal",
    "veracrypt",
]

# Default sensitive domains / URLs never to track
DEFAULT_BLOCKED_DOMAINS = [
    "bank",
    "chase.com",
    "bankofamerica.com",
    "wellsfargo.com",
    "paypal.com",
    "accounts.google.com",
    "login.microsoftonline.com",
    "auth0",
    "stripe.com",
    "wallet",
]


class PrivacyGuard:
    """Manages system-wide privacy state, sensor gates, and application blocklists."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or settings.db_path)
        self._lock = threading.Lock()
        self._ghost_mode = False
        self._sensors: Dict[str, bool] = {
            "screen_awareness": True,
            "activity_watch": True,
            "camera": True,
            "browser_automation": True,
            "memory_recording": True,
        }
        self._blocked_apps: Set[str] = set(DEFAULT_BLOCKED_APPS)
        self._blocked_domains: Set[str] = set(DEFAULT_BLOCKED_DOMAINS)
        self._init_db()
        self._load_state()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS privacy_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );"""
                )
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS privacy_blocklists (
                        type TEXT NOT NULL,
                        item TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(type, item)
                    );"""
                )
                conn.commit()
        except Exception as e:
            log.warning("PrivacyGuard failed to initialize tables: %s", e)

    def _load_state(self) -> None:
        try:
            with self._connect() as conn:
                rows = conn.execute("SELECT key, value FROM privacy_settings").fetchall()
                for r in rows:
                    k, v = r["key"], r["value"]
                    if k == "ghost_mode":
                        self._ghost_mode = v.lower() in ("true", "1", "yes")
                    elif k.startswith("sensor:"):
                        sensor_name = k.split("sensor:", 1)[1]
                        self._sensors[sensor_name] = v.lower() in ("true", "1", "yes")

                block_rows = conn.execute("SELECT type, item FROM privacy_blocklists").fetchall()
                for br in block_rows:
                    b_type, item = br["type"], br["item"].lower().strip()
                    if b_type == "app":
                        self._blocked_apps.add(item)
                    elif b_type == "domain":
                        self._blocked_domains.add(item)
        except Exception as e:
            log.warning("PrivacyGuard failed to load persisted state: %s", e)

    def _save_setting(self, key: str, value: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO privacy_settings (key, value) VALUES (?, ?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
                    (key, str(value)),
                )
                conn.commit()
        except Exception as e:
            log.warning("PrivacyGuard failed to save setting %s: %s", key, e)

    # ── Ghost Mode ─────────────────────────────────────────────────────────────

    def is_ghost_mode(self) -> bool:
        with self._lock:
            return self._ghost_mode

    def set_ghost_mode(self, enabled: bool) -> bool:
        with self._lock:
            self._ghost_mode = bool(enabled)
            self._save_setting("ghost_mode", "true" if self._ghost_mode else "false")
            log.info("PrivacyGuard Ghost Mode set to: %s", self._ghost_mode)
            return self._ghost_mode

    def toggle_ghost_mode(self) -> bool:
        with self._lock:
            self._ghost_mode = not self._ghost_mode
            self._save_setting("ghost_mode", "true" if self._ghost_mode else "false")
            log.info("PrivacyGuard Ghost Mode toggled to: %s", self._ghost_mode)
            return self._ghost_mode

    # ── Granular Sensor Controls ───────────────────────────────────────────────

    def is_sensor_enabled(self, sensor_name: str) -> bool:
        with self._lock:
            # Ghost Mode forces all background sensing off
            if self._ghost_mode:
                return False
            return self._sensors.get(sensor_name, True)

    def set_sensor(self, sensor_name: str, enabled: bool) -> bool:
        with self._lock:
            val = bool(enabled)
            self._sensors[sensor_name] = val
            self._save_setting(f"sensor:{sensor_name}", "true" if val else "false")
            log.info("PrivacyGuard sensor '%s' set to: %s", sensor_name, val)
            return val

    def toggle_sensor(self, sensor_name: str) -> bool:
        with self._lock:
            cur = self._sensors.get(sensor_name, True)
            new_val = not cur
            self._sensors[sensor_name] = new_val
            self._save_setting(f"sensor:{sensor_name}", "true" if new_val else "false")
            return new_val

    # ── Blocklists (Apps and Domains) ──────────────────────────────────────────

    def can_observe_app(self, app_name: str) -> bool:
        """Return False if Ghost Mode is ON, screen sensing is OFF, or app is blocked."""
        if not self.is_sensor_enabled("screen_awareness"):
            return False
        if not app_name:
            return True
        low = app_name.lower().strip()
        with self._lock:
            for b in self._blocked_apps:
                if b in low:
                    return False
        return True

    def can_observe_domain(self, domain_or_url: str) -> bool:
        """Return False if Ghost Mode is ON, activity tracking is OFF, or domain is blocked."""
        if not self.is_sensor_enabled("activity_watch"):
            return False
        if not domain_or_url:
            return True
        low = domain_or_url.lower().strip()
        with self._lock:
            for b in self._blocked_domains:
                if b in low:
                    return False
        return True

    def add_blocked_app(self, app_name: str) -> None:
        item = app_name.lower().strip()
        with self._lock:
            self._blocked_apps.add(item)
            try:
                with self._connect() as conn:
                    conn.execute("INSERT OR IGNORE INTO privacy_blocklists (type, item) VALUES ('app', ?)", (item,))
                    conn.commit()
            except Exception as e:
                log.warning("Failed to persist blocked app: %s", e)

    def remove_blocked_app(self, app_name: str) -> None:
        item = app_name.lower().strip()
        with self._lock:
            self._blocked_apps.discard(item)
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM privacy_blocklists WHERE type='app' AND item=?", (item,))
                    conn.commit()
            except Exception as e:
                log.warning("Failed to delete blocked app: %s", e)

    def add_blocked_domain(self, domain: str) -> None:
        item = domain.lower().strip()
        with self._lock:
            self._blocked_domains.add(item)
            try:
                with self._connect() as conn:
                    conn.execute("INSERT OR IGNORE INTO privacy_blocklists (type, item) VALUES ('domain', ?)", (item,))
                    conn.commit()
            except Exception as e:
                log.warning("Failed to persist blocked domain: %s", e)

    def remove_blocked_domain(self, domain: str) -> None:
        item = domain.lower().strip()
        with self._lock:
            self._blocked_domains.discard(item)
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM privacy_blocklists WHERE type='domain' AND item=?", (item,))
                    conn.commit()
            except Exception as e:
                log.warning("Failed to delete blocked domain: %s", e)

    # ── Status Summary ─────────────────────────────────────────────────────────

    def get_privacy_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ghost_mode": self._ghost_mode,
                "sensors": {
                    "screen_awareness": self._sensors.get("screen_awareness", True) and not self._ghost_mode,
                    "activity_watch": self._sensors.get("activity_watch", True) and not self._ghost_mode,
                    "camera": self._sensors.get("camera", True) and not self._ghost_mode,
                    "browser_automation": self._sensors.get("browser_automation", True) and not self._ghost_mode,
                    "memory_recording": self._sensors.get("memory_recording", True) and not self._ghost_mode,
                },
                "raw_sensors": dict(self._sensors),
                "blocked_apps": sorted(list(self._blocked_apps)),
                "blocked_domains": sorted(list(self._blocked_domains)),
            }


# Singleton instance
privacy_guard = PrivacyGuard()
