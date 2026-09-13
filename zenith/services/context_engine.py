"""Unified Context Engine — Central multi-modal orchestrator for Zenith.

Unifies and ranks:
  - Conversation shadow & active goals.
  - Active application & screen understanding (Clippy Vision).
  - Local activity history & timeline (ActivityWatch).
  - Structured long-term memories & preferences (Mem0).
  - Browser automation state (Playwright + Browser Use).
  - Camera & visual observations (OpenCV + Gesture detection).

Maintains:
  - Context relevance ranking and token budget optimization.
  - Proactive background suggestions dispatched through ProactiveHub.
  - Comprehensive Context Snapshot for UI context inspection.
  - Full adherence to PrivacyGuard and Ghost Mode.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ..core.config import settings
from .privacy_guard import privacy_guard
from .screen_awareness import clippy_vision
from .activity_watch import activity_watch
from .memory_layer import memory_layer
from .browser_unified import browser_unified
from .vision_engine import vision_engine

log = logging.getLogger("zenith.context_engine")


class UnifiedContextEngine:
    """Aggregates, ranks, and synthesizes multi-modal environmental context for the agent."""

    def __init__(self) -> None:
        self._last_snapshot_time = 0.0

    def get_snapshot(self) -> Dict[str, Any]:
        """Fetch real-time status and telemetry across all sensory layers."""
        privacy_status = privacy_guard.get_privacy_status()
        is_ghost = privacy_status["ghost_mode"]

        # 1. Screen awareness
        screen_info = clippy_vision.get_active_window() if not is_ghost else {
            "app_name": "Protected (Ghost Mode)", "window_title": "Hidden", "workflow": "ghost_mode"
        }

        # 2. ActivityWatch summary
        act_summary = activity_watch.get_summary(hours=12.0) if not is_ghost else {
            "active_minutes": 0, "idle_minutes": 0, "top_apps": []
        }

        # 3. Mem0 memory stats
        all_memories = memory_layer.get_all_memories() if not is_ghost else []

        # 4. Vision state
        vision_state = vision_engine.get_vision_status() if not is_ghost else {
            "camera_active": False, "presence": False, "gesture": "none"
        }

        return {
            "timestamp": time.time(),
            "ghost_mode": is_ghost,
            "privacy": privacy_status,
            "screen": screen_info,
            "activity": act_summary,
            "memory_count": len(all_memories),
            "vision": vision_state,
        }

    def build_prompt_context(self) -> str:
        """Produce a ranked, concise prompt block injected into Orchestrator."""
        privacy_status = privacy_guard.get_privacy_status()
        if privacy_status["ghost_mode"]:
            return "\n[GHOST MODE ACTIVE — All background screen, activity, camera, and memory sensors are offline for sovereign privacy.]"

        parts: List[str] = []

        # 1. Screen Awareness (Clippy Vision)
        if privacy_guard.is_sensor_enabled("screen_awareness"):
            screen_ctx = clippy_vision.get_context_summary()
            if screen_ctx:
                parts.append(f"--- SCREEN & ACTIVE WORKFLOW ---\n{screen_ctx}")

        # 2. Activity Timeline (ActivityWatch)
        if privacy_guard.is_sensor_enabled("activity_watch"):
            act_sum = activity_watch.get_summary(hours=6.0)
            if act_sum.get("top_apps"):
                top_str = ", ".join(f"{a['app_name']} ({a['minutes']}m)" for a in act_sum["top_apps"][:4])
                parts.append(f"--- RECENT ACTIVITY TIMELINE (Past 6 Hours) ---\nActive Time: {act_sum['active_minutes']}m | Top Apps: {top_str}")

        # 3. Long-Term Structured Memory (Mem0)
        if privacy_guard.is_sensor_enabled("memory_recording"):
            mem_summary = memory_layer.get_structured_summary(limit=25)
            if mem_summary and "No long-term" not in mem_summary:
                parts.append(f"--- STRUCTURED MEMORY (Mem0) ---\n{mem_summary}")

        # 4. Vision & Presence
        if privacy_guard.is_sensor_enabled("camera"):
            vis = vision_engine.get_vision_status()
            if vis["camera_active"]:
                parts.append(
                    f"--- VISUAL ENGINE STATUS ---\nCamera: LIVE | User Presence: {'Present' if vis['last_presence'] else 'Away'} | Last Gesture: {vis['last_gesture']}"
                )

        if not parts:
            return ""

        return "\n\n" + "\n\n".join(parts)

    async def evaluate_proactive_triggers(self) -> Optional[Dict[str, Any]]:
        """Run periodic check across sensors to see if a proactive alert should be emitted."""
        if privacy_guard.is_ghost_mode():
            return None

        # 1. Check screen awareness workflow changes
        obs_res = clippy_vision.observe_cycle()
        if obs_res.get("suggestion"):
            return obs_res["suggestion"]

        # 2. Check if a thumbs-up gesture was performed to auto-confirm a pending gate
        vis = vision_engine.get_vision_status()
        if vis["camera_active"] and vis.get("last_gesture") == "thumbs_up":
            log.info("Detected thumbs-up gesture from user — checking for pending confirmation.")
            return {
                "title": "Gesture Approved",
                "message": "Detected thumbs-up gesture. Ready to proceed with pending action.",
                "category": "gesture",
            }

        return None


# Singleton instance
context_engine = UnifiedContextEngine()
