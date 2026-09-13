"""REST API Routes for Zenith Operating Layer & Modular Services.

Exposes REST contracts for:
  - Sovereign Privacy Guard & Ghost Mode
  - ActivityWatch Local Timeline & Productivity Stats
  - Clippy Vision Screen & Active Window Awareness
  - Mem0 Multi-Tier Long-Term Memory
  - Unified Browser Automation (Playwright + Browser Use)
  - Camera & Computer Vision Pipeline (OpenCV + Gestures)
  - Unified Multi-Modal Context Engine
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .privacy_guard import privacy_guard
from .activity_watch import activity_watch
from .screen_awareness import clippy_vision
from .memory_layer import memory_layer
from .browser_unified import browser_unified
from .vision_engine import vision_engine
from .context_engine import context_engine

log = logging.getLogger("zenith.services.routes")

router = APIRouter(prefix="/api")


# ── Pydantic Request Schemas ──────────────────────────────────────────────────

class GhostModePayload(BaseModel):
    enabled: Optional[bool] = None

class SensorTogglePayload(BaseModel):
    sensor: str = Field(..., description="Sensor name (e.g. screen_awareness, activity_watch, camera, browser_automation, memory_recording)")
    enabled: Optional[bool] = None

class BlocklistPayload(BaseModel):
    type: str = Field(..., description="'app' or 'domain'")
    item: str = Field(..., description="Application name or domain to block/unblock")
    action: str = Field("add", description="'add' or 'remove'")

class Mem0AddPayload(BaseModel):
    content: str = Field(..., min_length=1)
    tier: str = Field("project", description="'preference', 'project', 'workflow', or 'decision'")
    topic: str = Field("general")

class Mem0UpdatePayload(BaseModel):
    content: str = Field(..., min_length=1)
    tier: Optional[str] = None
    topic: Optional[str] = None

class BrowserNavPayload(BaseModel):
    url: str
    max_chars: Optional[int] = 5000

class BrowserActPayload(BaseModel):
    url: str
    action: str = Field(..., description="'click', 'type', or 'screenshot'")
    selector: Optional[str] = None
    text: Optional[str] = None
    submit: Optional[bool] = False

class BrowserGoalPayload(BaseModel):
    goal: str
    start_url: Optional[str] = None
    max_steps: Optional[int] = 5

class VisionAnalyzePayload(BaseModel):
    question: str = "Describe what is visible."
    source: str = "camera"  # 'camera' or 'screen'


# ── 1. Sovereign Privacy Guard ───────────────────────────────────────────────

@router.get("/privacy/status")
async def get_privacy_status():
    """Get status of Ghost Mode, individual sensors, and application blocklists."""
    return {"ok": True, "privacy": privacy_guard.get_privacy_status()}


@router.post("/privacy/ghost_mode")
async def toggle_ghost_mode(payload: Optional[GhostModePayload] = None):
    """Toggle or explicitly set Ghost Mode (master privacy switch)."""
    if payload and payload.enabled is not None:
        val = privacy_guard.set_ghost_mode(payload.enabled)
    else:
        val = privacy_guard.toggle_ghost_mode()
    return {"ok": True, "ghost_mode": val}


@router.post("/privacy/sensor")
async def toggle_sensor(payload: SensorTogglePayload):
    """Toggle or explicitly set an individual sensor's permission."""
    if payload.enabled is not None:
        val = privacy_guard.set_sensor(payload.sensor, payload.enabled)
    else:
        val = privacy_guard.toggle_sensor(payload.sensor)
    return {"ok": True, "sensor": payload.sensor, "enabled": val}


@router.post("/privacy/blocklist")
async def manage_blocklist(payload: BlocklistPayload):
    """Add or remove an application or domain from the privacy blocklist."""
    b_type = payload.type.lower().strip()
    action = payload.action.lower().strip()
    item = payload.item.strip()

    if b_type == "app":
        if action == "add":
            privacy_guard.add_blocked_app(item)
        else:
            privacy_guard.remove_blocked_app(item)
    elif b_type == "domain":
        if action == "add":
            privacy_guard.add_blocked_domain(item)
        else:
            privacy_guard.remove_blocked_domain(item)
    else:
        raise HTTPException(status_code=400, detail="Type must be 'app' or 'domain'")

    return {"ok": True, "type": b_type, "action": action, "item": item}


# ── 2. ActivityWatch (Timeline & Productivity Stats) ─────────────────────────

@router.get("/activity/timeline")
async def get_activity_timeline(limit: int = 60, hours: float = 24.0):
    """Retrieve recent local activity timeline entries."""
    timeline = activity_watch.get_timeline(limit=limit, hours=hours)
    return {"ok": True, "timeline": timeline}


@router.get("/activity/summary")
async def get_activity_summary(hours: float = 24.0):
    """Get productivity stats, active vs idle duration, and top applications."""
    summary = activity_watch.get_summary(hours=hours)
    return {"ok": True, "summary": summary}


@router.get("/activity/recall")
async def recall_activity(
    query: str = Query("", description="Keywords, tasks, or app names"),
    time_anchor: str = Query("", description="Time reference (e.g. 'morning', 'before lunch')"),
    hours: float = Query(24.0, description="Hours back to search"),
):
    """Contextual recall of past activity ('What was I working on before lunch?')."""
    recalled = activity_watch.recall_activity(query=query, time_anchor=time_anchor, hours=hours)
    return {"ok": True, "result": recalled}


@router.post("/activity/clear")
async def clear_activity(hours: Optional[float] = None):
    """Clear local activity history."""
    count = activity_watch.clear_activity(hours=hours)
    return {"ok": True, "cleared_events": count}


# ── 3. Screen Awareness (Clippy Vision) ───────────────────────────────────────

@router.get("/screen/status")
async def get_screen_status():
    """Get active window, application name, workflow categorization, and pause state."""
    active_win = clippy_vision.get_active_window()
    return {
        "ok": True,
        "paused": clippy_vision.is_paused(),
        "active_window": active_win,
    }


@router.post("/screen/toggle")
async def toggle_screen_awareness():
    """Toggle pause state for screen observation."""
    paused = clippy_vision.toggle_pause()
    return {"ok": True, "paused": paused}


@router.get("/screen/summary")
async def get_screen_summary():
    """Get compact context summary formatted for prompt injection."""
    summary = clippy_vision.get_context_summary()
    return {"ok": True, "summary": summary}


# ── 4. Mem0 Long-Term Structured Memory ──────────────────────────────────────

@router.get("/memory/mem0/all")
async def get_mem0_memories(tier: Optional[str] = None):
    """Fetch all Mem0 memories, optionally filtered by tier."""
    memories = memory_layer.get_all_memories(tier=tier)
    return {"ok": True, "memories": memories}


@router.get("/memory/mem0/search")
async def search_mem0_memories(
    q: str = Query(..., description="Query string"),
    tier: Optional[str] = Query(None, description="Optional tier filter"),
    limit: int = Query(15, description="Max results"),
):
    """Search Mem0 memories across cognitive tiers."""
    results = memory_layer.search_memories(query=q, tier=tier, limit=limit)
    return {"ok": True, "results": results}


@router.post("/memory/mem0/add")
async def add_mem0_memory(payload: Mem0AddPayload):
    """Manually add a durable memory to Mem0."""
    mid = memory_layer.add_memory(content=payload.content, tier=payload.tier, topic=payload.topic)
    if mid is None:
        return JSONResponse({"ok": False, "error": "Memory recording is disabled in Privacy Guard or in Ghost Mode."}, status_code=403)
    return {"ok": True, "memory_id": mid}


@router.put("/memory/mem0/{memory_id}")
async def update_mem0_memory(memory_id: int, payload: Mem0UpdatePayload):
    """Edit or correct an existing memory in Mem0."""
    ok = memory_layer.update_memory(memory_id=memory_id, content=payload.content, tier=payload.tier, topic=payload.topic)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found or update failed.")
    return {"ok": True, "memory_id": memory_id}


@router.delete("/memory/mem0/{memory_id}")
async def delete_mem0_memory(memory_id: int):
    """Delete a memory from Mem0."""
    ok = memory_layer.delete_memory(memory_id=memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"ok": True, "memory_id": memory_id}


@router.post("/memory/mem0/clear")
async def clear_mem0_memories(tier: Optional[str] = None):
    """Clear memories in a specific tier or all memories."""
    count = memory_layer.clear_memories(tier=tier)
    return {"ok": True, "cleared_memories": count}


# ── 5. Unified Browser Automation ────────────────────────────────────────────

@router.get("/browser/status")
async def get_browser_status():
    """Get active browser session telemetry and current URL."""
    status_info = await browser_unified.get_status()
    return {"ok": True, "browser": status_info}


@router.post("/browser/navigate")
async def browser_navigate(payload: BrowserNavPayload):
    """Deterministic browser navigation and text extraction."""
    res = await browser_unified.navigate(payload.url, max_chars=payload.max_chars or 5000)
    return {"ok": res.get("status") == "success", "result": res}


@router.post("/browser/act")
async def browser_act(payload: BrowserActPayload):
    """Perform deterministic element action with safety gating."""
    res = await browser_unified.act(
        url=payload.url,
        action=payload.action,
        selector=payload.selector,
        text=payload.text,
        submit=payload.submit or False,
    )
    return {"ok": res.get("status") == "success", "result": res}


@router.post("/browser/goal")
async def browser_execute_goal(payload: BrowserGoalPayload):
    """Run autonomous multi-step Browser Use agent."""
    res = await browser_unified.execute_goal(
        goal=payload.goal,
        start_url=payload.start_url,
        max_steps=payload.max_steps or 5,
    )
    return {"ok": res.get("status") in ("success", "partial"), "result": res}


@router.post("/browser/close")
async def browser_close():
    """Close active browser session."""
    await browser_unified.close()
    return {"ok": True, "message": "Browser session closed"}


# ── 6. Camera & Computer Vision ──────────────────────────────────────────────

@router.get("/vision/status")
async def get_vision_status():
    """Inspect camera status, detected presence, and recognized gestures."""
    return {"ok": True, "vision": vision_engine.get_vision_status()}


@router.post("/vision/camera/start")
async def start_camera(device: int = 0):
    """Activate camera feed (hardware or simulated fallback)."""
    res = await vision_engine.start_camera(device_index=device)
    return {"ok": res.get("status") in ("success", "already_active"), "result": res}


@router.post("/vision/camera/stop")
async def stop_camera():
    """Deactivate camera feed."""
    res = await vision_engine.stop_camera()
    return {"ok": True, "result": res}


@router.get("/vision/frame")
async def get_vision_frame():
    """Fetch the latest camera frame as a base64 encoded JPEG."""
    ok, _, b64 = await vision_engine.capture_frame()
    if not ok:
        raise HTTPException(status_code=403, detail="Camera disabled or unavailable.")
    return {"ok": True, "frame_b64": b64}


@router.post("/vision/analyze")
async def analyze_visual(payload: VisionAnalyzePayload):
    """Ask questions about visual input from camera or active screen."""
    res = await vision_engine.answer_visual_question(question=payload.question, source=payload.source)
    return {"ok": res.get("status") == "success", "result": res}


@router.post("/vision/detect")
async def detect_visual_features():
    """Run presence and gesture detection pass."""
    res = await vision_engine.detect_presence_and_gestures()
    return {"ok": True, "detection": res}


@router.post("/vision/scan_qr")
async def scan_qr_codes():
    """Run OpenCV QR Code scanning."""
    res = await vision_engine.scan_qr_codes()
    return {"ok": True, "result": res}


# ── 7. Unified Context Engine ────────────────────────────────────────────────

@router.get("/context/snapshot")
async def get_context_snapshot():
    """Retrieve full unified telemetry across all operating layers."""
    snapshot = context_engine.get_snapshot()
    return {"ok": True, "snapshot": snapshot}
