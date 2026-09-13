"""Context Suite Tools — Screen awareness, ActivityWatch, Mem0, Unified Browser, Vision & Privacy.

Self-registering tool module for Zenith's sensory and operating layer.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..core.tools import register
from ..services.privacy_guard import privacy_guard
from ..services.activity_watch import activity_watch
from ..services.screen_awareness import clippy_vision
from ..services.memory_layer import memory_layer
from ..services.browser_unified import browser_unified
from ..services.vision_engine import vision_engine
from ..services.context_engine import context_engine


# ── 1. Screen Awareness (Clippy Vision) ───────────────────────────────────────

async def tool_screen_observe(detailed: bool = True) -> str:
    """Observe the active application, window title, and workflow state."""
    res = clippy_vision.observe_cycle()
    if res.get("status") == "paused":
        return "Screen observation is currently paused or in Ghost Mode (Privacy Guard)."

    obs = res.get("observation", {})
    sug = res.get("suggestion")
    sug_txt = f"\nProactive Insight: {sug['title']} — {sug['message']}" if sug else ""

    return (
        f"Active App: {obs.get('app_name', 'Unknown')}\n"
        f"Window Title: \"{obs.get('window_title', '')}\"\n"
        f"Detected Workflow: {obs.get('workflow', 'general')}\n"
        f"Observation Status: Active{sug_txt}"
    )


register(
    "screen_observe",
    "Observe the user's currently focused application, window title, and workflow state (coding, researching, designing, debugging) via Clippy Vision. Respects Privacy Guard.",
    {
        "type": "object",
        "properties": {
            "detailed": {"type": "boolean", "default": True, "description": "Whether to return full workflow details."}
        },
    },
    tool_screen_observe,
)


# ── 2. ActivityWatch (Timeline & Contextual Recall) ───────────────────────────

async def tool_activity_recall(query: str = "", time_anchor: str = "", hours: float = 24.0) -> str:
    """Recall past activity from the local ActivityWatch timeline."""
    return activity_watch.recall_activity(query=query, time_anchor=time_anchor, hours=hours)


register(
    "activity_recall",
    "Recall user activity, applications, and documents from the local ActivityWatch timeline (e.g., 'What was I working on before lunch?', 'What was I coding yesterday afternoon?').",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "", "description": "Keywords, app names, or task topics to search for."},
            "time_anchor": {"type": "string", "default": "", "description": "Natural language time reference (e.g. 'morning', 'before lunch', 'yesterday')."},
            "hours": {"type": "number", "default": 24.0, "description": "How many hours back to search (default 24)."}
        },
    },
    tool_activity_recall,
)


async def tool_activity_summary(hours: float = 24.0) -> str:
    """Get productivity summary and time spent per app from ActivityWatch."""
    sum_data = activity_watch.get_summary(hours=hours)
    top_apps = sum_data.get("top_apps", [])
    app_lines = [f"- {a['app_name']} ({a['category']}): {a['minutes']}m ({a['percent']}%)" for a in top_apps]
    apps_txt = "\n".join(app_lines) if app_lines else "No tracked app activity."

    cat_items = [f"{k}: {v}m" for k, v in sum_data.get("categories", {}).items()]
    cat_txt = ", ".join(cat_items) if cat_items else "None"

    return (
        f"Activity Summary (Past {hours} hours):\n"
        f"Active Work Time: {sum_data.get('active_minutes', 0)} mins | Idle Time: {sum_data.get('idle_minutes', 0)} mins\n"
        f"Category Breakdown: {cat_txt}\n\n"
        f"Top Applications:\n{apps_txt}"
    )


register(
    "activity_summary",
    "Get a productivity summary, active vs idle time, and breakdown of time spent on tasks and applications from the local ActivityWatch timeline.",
    {
        "type": "object",
        "properties": {
            "hours": {"type": "number", "default": 24.0, "description": "Inspection window in hours (default 24)."}
        },
    },
    tool_activity_summary,
)


# ── 3. Mem0 Long-Term Structured Memory ──────────────────────────────────────

async def tool_mem0_remember(content: str, tier: str = "project", topic: str = "general") -> str:
    """Store durable long-term knowledge with tier ('preference', 'project', 'workflow', 'decision')."""
    mid = memory_layer.add_memory(content=content, tier=tier, topic=topic)
    if mid is None:
        return "Could not store memory (memory recording disabled or in Ghost Mode)."
    return f"Stored memory [#{mid}] in tier '{tier}' (topic: '{topic}'): {content}"


register(
    "mem0_remember",
    "Save durable, evolving long-term knowledge into Mem0 across structured tiers: 'preference' (user habits/style), 'project' (codebases/architecture), 'workflow' (recurring patterns/tool chains), or 'decision' (past architectural choices and rationales).",
    {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The exact fact, preference, architectural decision, or workflow pattern to store."},
            "tier": {
                "type": "string",
                "enum": ["preference", "project", "workflow", "decision"],
                "default": "project",
                "description": "Cognitive tier: 'preference', 'project', 'workflow', or 'decision'."
            },
            "topic": {"type": "string", "default": "general", "description": "Short topic keyword (e.g. 'frontend', 'docker', 'style', 'auth')."}
        },
        "required": ["content"],
    },
    tool_mem0_remember,
)


async def tool_mem0_recall(query: str = "", tier: str = "", limit: int = 10) -> str:
    """Search and recall structured long-term memories from Mem0."""
    tier_val = tier.strip() or None
    results = memory_layer.search_memories(query=query, tier=tier_val, limit=limit)
    if not results:
        return f"No memories found matching '{query}'" + (f" in tier '{tier}'" if tier else "") + "."

    lines = [f"Found {len(results)} long-term memories:"]
    for m in results:
        lines.append(f"- [#{m['id']} | {m['tier'].upper()} | {m['topic']}] {m['content']}")
    return "\n".join(lines)


register(
    "mem0_recall",
    "Recall and search structured long-term memories from Mem0 across tiers (preferences, projects, workflows, decisions).",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "", "description": "Keyword or search query."},
            "tier": {"type": "string", "default": "", "description": "Optional tier filter ('preference', 'project', 'workflow', 'decision')."},
            "limit": {"type": "integer", "default": 10, "description": "Max results to return."}
        },
    },
    tool_mem0_recall,
)


async def tool_mem0_delete(memory_id: int) -> str:
    """Delete a specific memory by its ID."""
    ok = memory_layer.delete_memory(memory_id)
    if ok:
        return f"Memory #{memory_id} deleted successfully."
    return f"Memory #{memory_id} not found."


register(
    "mem0_delete",
    "Delete a memory from Mem0 by its numeric ID.",
    {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer", "description": "ID of the memory to remove."}
        },
        "required": ["memory_id"],
    },
    tool_mem0_delete,
)


# ── 4. Unified Browser (Playwright + Browser Use) ────────────────────────────

async def tool_browser_browse(url: str, max_chars: int = 5000) -> str:
    """[Alias for 'browser'] Navigate to a web page and extract readable content."""
    res = await browser_unified.navigate(url, max_chars=max_chars)
    if res.get("status") != "success":
        return f"Browser error navigating to '{url}': {res.get('error')}"
    return f"Title: {res.get('title')}\nURL: {res.get('url')}\n\n{res.get('text')}"


register(
    "browser_browse",
    "[Alias for 'browser'] Open any URL in Playwright, wait for page load, and extract clean readable text content and title.",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Website URL to navigate to."},
            "max_chars": {"type": "integer", "default": 5000, "description": "Max text characters to extract."}
        },
        "required": ["url"],
    },
    tool_browser_browse,
    hidden_from_catalog=True,
)


async def tool_browser_autonomous_goal(goal: str, start_url: str = "", max_steps: int = 5) -> str:
    """Execute a dynamic, multi-step browser goal with safety checkpoints."""
    res = await browser_unified.execute_goal(goal=goal, start_url=start_url or None, max_steps=max_steps)
    if res.get("status") == "requires_confirmation":
        return f"[SAFETY CHECKPOINT] {res.get('goal')} requires user confirmation before proceeding with sensitive operations on {res.get('final_url')}."
    if res.get("status") in ("success", "partial"):
        return f"Browser Goal Status: {res.get('status').upper()}\nFinal URL: {res.get('final_url')}\nTitle: {res.get('title')}\n\nSummary:\n{res.get('extracted_summary')}"
    return f"Browser goal failed: {res.get('error')}"


register(
    "browser_autonomous_goal",
    "Execute an autonomous multi-step browsing goal using Browser Use (researching topics, navigating unfamiliar sites, following dynamic links). Enforces safety checkpoints on purchases, messages, and settings.",
    {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "The high-level objective (e.g. 'Search for the latest FastAPI release notes and find WebSocket changes')."},
            "start_url": {"type": "string", "default": "", "description": "Optional starting URL."},
            "max_steps": {"type": "integer", "default": 5, "description": "Max reasoning steps (default 5)."}
        },
        "required": ["goal"],
    },
    tool_browser_autonomous_goal,
)


# ── 5. Camera & Computer Vision ──────────────────────────────────────────────

async def tool_camera_capture(question: str = "", source: str = "camera") -> str:
    """Capture camera feed or screen and answer a visual question."""
    res = await vision_engine.answer_visual_question(question=question or "Describe what you see.", source=source)
    if res.get("status") != "success":
        return f"Visual acquisition error: {res.get('error')}"
    return f"[{res.get('source_label')} Analysis]:\n{res.get('analysis')}"


register(
    "camera_capture",
    "Capture a live frame from the user's camera or screen and answer visual questions (e.g. inspecting physical hardware held up to camera, sketches, documents, or UI on screen).",
    {
        "type": "object",
        "properties": {
            "question": {"type": "string", "default": "Describe what is visible.", "description": "Question to answer about the visual frame."},
            "source": {"type": "string", "enum": ["camera", "screen"], "default": "camera", "description": "Source: 'camera' (webcam) or 'screen' (active window)."}
        },
    },
    tool_camera_capture,
)


async def tool_vision_detect(detection_type: str = "all") -> str:
    """Run OpenCV QR scanning, motion detection, and gesture recognition."""
    reports = []

    # 1. QR code scan
    if detection_type in ("qr_code", "all"):
        qr_res = await vision_engine.scan_qr_codes()
        if qr_res.get("detected"):
            reports.append(f"QR Code Detected: {qr_res.get('data')}")
        else:
            reports.append("QR Code: None detected in current camera frame.")

    # 2. Presence & Gestures
    if detection_type in ("presence_and_gestures", "all"):
        pg_res = await vision_engine.detect_presence_and_gestures()
        presence = "User Present in view" if pg_res.get("presence") else "No presence detected"
        gesture = pg_res.get("gesture", "none")
        reports.append(f"Presence: {presence} | Detected Gesture: {gesture}")

    return "\n".join(reports)


register(
    "vision_detect",
    "Run OpenCV and MediaPipe visual intelligence: QR code and barcode scanning, presence detection, and gesture recognition (thumbs up approval, swipe, wave).",
    {
        "type": "object",
        "properties": {
            "detection_type": {
                "type": "string",
                "enum": ["all", "qr_code", "presence_and_gestures"],
                "default": "all",
                "description": "Which detection pipeline to execute."
            }
        },
    },
    tool_vision_detect,
)


# ── 6. Sovereign Privacy Guard ───────────────────────────────────────────────

async def tool_privacy_control(
    action: str = "status",
    target: str = "",
    enabled: bool = True,
) -> str:
    """Manage Sovereign Privacy Guard, Ghost Mode, and sensor permissions."""
    action = action.lower().strip()

    if action == "status":
        st = privacy_guard.get_privacy_status()
        ghost = "ENABLED (All sensors offline)" if st["ghost_mode"] else "OFF (Normal operation)"
        sensors_txt = ", ".join(f"{k}: {'ON' if v else 'OFF'}" for k, v in st["sensors"].items())
        blocked_apps = ", ".join(st["blocked_apps"][:5])
        return (
            f"Sovereign Privacy Guard Status:\n"
            f"Ghost Mode: {ghost}\n"
            f"Sensors: {sensors_txt}\n"
            f"Protected Apps: {blocked_apps}..."
        )

    elif action in ("toggle_ghost_mode", "ghost_mode"):
        new_val = privacy_guard.toggle_ghost_mode() if action == "toggle_ghost_mode" else privacy_guard.set_ghost_mode(enabled)
        return f"Ghost Mode is now {'ENABLED (all background sensing offline)' if new_val else 'DISABLED'}."

    elif action == "set_sensor" and target:
        val = privacy_guard.set_sensor(target, enabled)
        return f"Sensor '{target}' is now {'ENABLED' if val else 'DISABLED'}."

    elif action == "block_app" and target:
        privacy_guard.add_blocked_app(target)
        return f"Added '{target}' to protected applications blocklist."

    elif action == "unblock_app" and target:
        privacy_guard.remove_blocked_app(target)
        return f"Removed '{target}' from protected applications blocklist."

    return f"Unknown privacy action '{action}'. Available: 'status', 'toggle_ghost_mode', 'set_sensor', 'block_app', 'unblock_app'."


register(
    "privacy_control",
    "Inspect or configure Sovereign Privacy Guard: toggle Ghost Mode (master privacy kill-switch that disables all background sensing with one click), enable/disable individual sensors, or manage application blocklists.",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "toggle_ghost_mode", "set_ghost_mode", "set_sensor", "block_app", "unblock_app"],
                "default": "status",
                "description": "Privacy control action."
            },
            "target": {"type": "string", "default": "", "description": "Target sensor name or app name to block/unblock."},
            "enabled": {"type": "boolean", "default": True, "description": "Value when setting ghost mode or sensor state."}
        },
    },
    tool_privacy_control,
)


# ── 7. Unified Context Engine ────────────────────────────────────────────────

async def tool_get_unified_context() -> str:
    """Retrieve full real-time snapshot of what Zenith senses across all layers."""
    snap = context_engine.get_snapshot()
    return json.dumps(snap, indent=2, default=str)


register(
    "get_unified_context",
    "Retrieve a full multi-modal snapshot of Zenith's Unified Context Engine (active window, screen context, recent activity timeline, memory stats, camera state, and privacy settings).",
    {
        "type": "object",
        "properties": {},
    },
    tool_get_unified_context,
)
