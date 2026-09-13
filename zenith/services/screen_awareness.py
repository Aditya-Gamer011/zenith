"""Clippy Vision — Proactive screen and active window awareness for Zenith.

Features:
  - Non-intrusive observation of the active application, window title, and workflow context.
  - Understands whether the user is coding, researching, designing, debugging, or communicating.
  - Detects workflow transitions (e.g. from editor to terminal, or hitting build errors).
  - Throttled, non-spammy proactive assistance triggers with cool-down intervals.
  - Strict privacy enforcement: respects PrivacyGuard Ghost Mode and application blocklists.
  - Cross-platform support (Linux X11/Wayland, macOS, Windows, and headless fallbacks).
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import time
from typing import Any, Dict, Optional

from ..core.config import settings
from .privacy_guard import privacy_guard
from .activity_watch import activity_watch

log = logging.getLogger("zenith.screen_awareness")


class ClippyVisionService:
    """Proactive screen awareness & workflow detection engine."""

    def __init__(self) -> None:
        self._last_observed: Dict[str, Any] = {
            "app_name": "Zenith",
            "window_title": "Zenith Operating Layer",
            "workflow": "standby",
            "timestamp": time.time(),
        }
        self._last_suggestion_time = 0.0
        self._suggestion_cooldown = 600.0  # 10 minutes between proactive interruptions
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused or not privacy_guard.is_sensor_enabled("screen_awareness")

    def pause(self) -> None:
        self._paused = True
        log.info("Clippy Vision screen awareness paused.")

    def resume(self) -> None:
        self._paused = False
        log.info("Clippy Vision screen awareness resumed.")

    def toggle_pause(self) -> bool:
        self._paused = not self._paused
        return self._paused

    def get_active_window(self) -> Dict[str, str]:
        """Query host OS for the currently focused window and application name."""
        if self.is_paused():
            return {
                "app_name": "Private / Paused",
                "window_title": "Screen awareness is currently disabled or in Ghost Mode.",
                "workflow": "paused",
            }

        os_name = platform.system().lower()
        app_name = "Desktop"
        window_title = "Active Workspace"

        try:
            if "linux" in os_name:
                # 1. Try xdotool if available in X11
                if shutil.which("xdotool"):
                    try:
                        res_win = subprocess.run(
                            ["xdotool", "getactivewindow"],
                            capture_output=True,
                            text=True,
                            timeout=1.5,
                        )
                        if res_win.returncode == 0 and res_win.stdout.strip():
                            win_id = res_win.stdout.strip()
                            res_name = subprocess.run(
                                ["xdotool", "getwindowname", win_id],
                                capture_output=True,
                                text=True,
                                timeout=1.5,
                            )
                            if res_name.returncode == 0:
                                window_title = res_name.stdout.strip()
                            # Get WM_CLASS for app_name
                            if shutil.which("xprop"):
                                res_prop = subprocess.run(
                                    ["xprop", "-id", win_id, "WM_CLASS"],
                                    capture_output=True,
                                    text=True,
                                    timeout=1.5,
                                )
                                if res_prop.returncode == 0 and "=" in res_prop.stdout:
                                    parts = res_prop.stdout.split("=")[1].replace('"', '').split(",")
                                    app_name = parts[-1].strip() or parts[0].strip()
                    except Exception:
                        pass

                # 2. Fallback to inspecting current terminal / shell or active processes
                if app_name == "Desktop" or not app_name:
                    from ..tools import computer
                    active_cwd = computer.get_active_cwd()
                    recent = computer.get_command_history(limit=1)
                    if recent:
                        app_name = "Terminal / Bash"
                        window_title = f"{active_cwd} - $ {recent[0]['command']}"
                    else:
                        app_name = "Codebase Workspace"
                        window_title = f"{active_cwd}"

            elif "darwin" in os_name:
                # macOS AppleScript
                cmd = (
                    'osascript -e \'tell application "System Events" to '
                    'get {name of first application process whose frontmost is true, '
                    'name of window 1 of (first application process whose frontmost is true)}\''
                )
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2.0)
                if res.returncode == 0 and "," in res.stdout:
                    parts = res.stdout.strip().split(",", 1)
                    app_name = parts[0].strip()
                    window_title = parts[1].strip() if len(parts) > 1 else app_name

            elif "windows" in os_name:
                # Windows PowerShell
                ps_cmd = (
                    '(Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } | '
                    'Select-Object -First 1 -ExpandProperty ProcessName)'
                )
                res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, timeout=2.0)
                if res.returncode == 0 and res.stdout.strip():
                    app_name = res.stdout.strip()
                    window_title = f"{app_name} Window"

        except Exception as e:
            log.debug("Active window query failed: %s", e)

        # Check PrivacyGuard blocklist
        if not privacy_guard.can_observe_app(app_name):
            return {
                "app_name": "Protected Application",
                "window_title": "[Blocked by Privacy Policy]",
                "workflow": "protected",
            }

        workflow = self.classify_workflow(app_name, window_title)
        return {
            "app_name": app_name,
            "window_title": window_title,
            "workflow": workflow,
        }

    def classify_workflow(self, app_name: str, window_title: str) -> str:
        """Deduce high-level user state from application and title hints."""
        combined = f"{app_name} {window_title}".lower()

        if any(w in combined for w in ("err", "exception", "failed", "traceback", "stacktrace", "bug", "crash")):
            return "debugging"
        if any(w in combined for w in ("code", "vscode", "pycharm", "cursor", "nvim", "vim", ".py", ".js", ".ts", ".rs", ".go")):
            return "coding"
        if any(w in combined for w in ("figma", "canva", "photoshop", "illustrator", "design", "wireframe", "art")):
            return "designing"
        if any(w in combined for w in ("docs", "documentation", "arxiv", "paper", "github.com", "stackoverflow", "wiki")):
            return "researching"
        if any(w in combined for w in ("slack", "discord", "mail", "gmail", "zoom", "teams", "telegram")):
            return "communicating"
        if any(w in combined for w in ("terminal", "bash", "zsh", "ssh", "docker", "htop")):
            return "terminal_ops"
        return "general_work"

    def observe_cycle(self) -> Dict[str, Any]:
        """Perform one periodic awareness cycle, feed ActivityWatch, and check for proactive triggers."""
        if self.is_paused():
            return {"status": "paused"}

        curr = self.get_active_window()
        app_name = curr["app_name"]
        win_title = curr["window_title"]
        workflow = curr["workflow"]

        # Feed ActivityWatch
        activity_watch.record_heartbeat(
            app_name=app_name,
            window_title=win_title,
            domain="",
            duration_seconds=15.0,
            is_idle=False,
            details={"workflow": workflow},
        )

        # Detect significant workflow change
        prev = self._last_observed
        changed = (prev.get("workflow") != workflow or prev.get("app_name") != app_name)

        self._last_observed = {
            "app_name": app_name,
            "window_title": win_title,
            "workflow": workflow,
            "timestamp": time.time(),
            "changed": changed,
        }

        # Check proactive suggestion condition
        suggestion = self._evaluate_proactive_suggestion(curr, changed)
        return {
            "status": "active",
            "observation": self._last_observed,
            "suggestion": suggestion,
        }

    def _evaluate_proactive_suggestion(self, current: Dict[str, str], changed: bool) -> Optional[Dict[str, str]]:
        """Determine if a non-intrusive proactive suggestion should be made."""
        now = time.time()
        # Enforce strict cooldown between proactive suggestions
        if (now - self._last_suggestion_time) < self._suggestion_cooldown:
            return None

        workflow = current["workflow"]
        app_name = current["app_name"]
        win_title = current["window_title"]

        # 1. Error / Debugging assistance
        if workflow == "debugging":
            self._last_suggestion_time = now
            return {
                "title": "Detected Error / Debugging Context",
                "message": f"Noticed an active issue in {app_name} ({win_title[:50]}). Would you like me to analyze the traceback and formulate a fix?",
                "category": "debugging",
            }

        # 2. Research session summary
        if workflow == "researching" and changed:
            self._last_suggestion_time = now
            return {
                "title": "Research Session Underway",
                "message": f"You're currently exploring {win_title[:60]}. I can distill key takeaways, compare documentation, or save notes.",
                "category": "research",
            }

        return None

    def get_context_summary(self) -> str:
        """Produce a tight, rich context string for injection into the Orchestrator prompt."""
        if self.is_paused():
            return "Screen Awareness: Paused or in Ghost Mode (Privacy Guard enabled)."

        curr = self.get_active_window()
        return (
            f"Active Application: {curr['app_name']}\n"
            f"Active Window/Context: \"{curr['window_title']}\"\n"
            f"Detected User Workflow: {curr['workflow'].upper()}"
        )


# Singleton instance
clippy_vision = ClippyVisionService()
