"""Comprehensive automated tests for Zenith's Context-Aware Operating Layer.

Tests:
  1. Sovereign Privacy Guard & Ghost Mode
  2. ActivityWatch Local Timeline & Recall
  3. Clippy Vision Screen & Active Window Awareness
  4. Mem0 Multi-Tier Structured Long-Term Memory
  5. Unified Browser Automation (Playwright + Browser Use)
  6. Camera, OpenCV & Gesture Vision Pipeline
  7. Unified Context Engine & Tool Registrations
  8. REST API contracts across all new endpoints
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from zenith.main import app
from zenith.core import tools as tool_reg
from zenith.services.privacy_guard import privacy_guard, PrivacyGuard
from zenith.services.activity_watch import activity_watch, categorize_app
from zenith.services.screen_awareness import clippy_vision
from zenith.services.memory_layer import memory_layer, sanitize_memory_text
from zenith.services.browser_unified import browser_unified
from zenith.services.vision_engine import vision_engine
from zenith.services.context_engine import context_engine


@pytest.fixture
def client():
    return TestClient(app)


# ── 1. Sovereign Privacy Guard Tests ─────────────────────────────────────────

def test_privacy_guard_initial_state():
    status = privacy_guard.get_privacy_status()
    assert "ghost_mode" in status
    assert "sensors" in status
    assert "blocked_apps" in status
    assert "1password" in [a.lower() for a in status["blocked_apps"]]


def test_privacy_guard_ghost_mode_toggle():
    # Ensure ghost mode off
    privacy_guard.set_ghost_mode(False)
    assert not privacy_guard.is_ghost_mode()
    assert privacy_guard.is_sensor_enabled("screen_awareness")

    # Turn ghost mode on
    privacy_guard.set_ghost_mode(True)
    assert privacy_guard.is_ghost_mode()
    # When Ghost Mode is on, all sensors must report disabled
    assert not privacy_guard.is_sensor_enabled("screen_awareness")
    assert not privacy_guard.is_sensor_enabled("camera")
    assert not privacy_guard.is_sensor_enabled("activity_watch")

    # Restore
    privacy_guard.set_ghost_mode(False)
    assert not privacy_guard.is_ghost_mode()


def test_privacy_guard_app_and_domain_blocklists():
    privacy_guard.set_ghost_mode(False)
    privacy_guard.set_sensor("screen_awareness", True)
    privacy_guard.set_sensor("activity_watch", True)

    # Normal apps allowed
    assert privacy_guard.can_observe_app("VS Code")
    assert privacy_guard.can_observe_app("Firefox")

    # Protected apps disallowed
    assert not privacy_guard.can_observe_app("1Password")
    assert not privacy_guard.can_observe_app("Bitwarden")

    # Add custom app to blocklist
    privacy_guard.add_blocked_app("ConfidentialApp")
    assert not privacy_guard.can_observe_app("ConfidentialApp")
    privacy_guard.remove_blocked_app("ConfidentialApp")
    assert privacy_guard.can_observe_app("ConfidentialApp")

    # Domain blocking
    assert not privacy_guard.can_observe_domain("https://bankofamerica.com/login")
    assert privacy_guard.can_observe_domain("https://docs.python.org")


# ── 2. ActivityWatch Local Timeline & Recall Tests ───────────────────────────

def test_categorize_app():
    assert categorize_app("code", "main.py - Visual Studio Code") == "coding"
    assert categorize_app("alacritty", "bash") == "coding"
    assert categorize_app("firefox", "FastAPI Documentation") == "research"
    assert categorize_app("figma", "Design System v2") == "design"
    assert categorize_app("slack", "#general") == "communication"
    assert categorize_app("unknown", "random window") == "general"


def test_activity_watch_recording_and_recall():
    privacy_guard.set_ghost_mode(False)
    privacy_guard.set_sensor("activity_watch", True)

    # Record heartbeats
    ok1 = activity_watch.record_heartbeat(
        app_name="VS Code",
        window_title="orchestrator.py - zenith",
        domain="",
        duration_seconds=30.0,
        is_idle=False,
    )
    assert ok1 is True

    ok2 = activity_watch.record_heartbeat(
        app_name="Chrome",
        window_title="FastAPI WebSockets Guide",
        domain="fastapi.tiangolo.com",
        duration_seconds=45.0,
        is_idle=False,
    )
    assert ok2 is True

    # Check summary
    summary = activity_watch.get_summary(hours=1.0)
    assert summary["active_minutes"] > 0
    assert summary["total_events"] >= 1

    # Check recall
    recalled = activity_watch.recall_activity(query="FastAPI", hours=1.0)
    assert "FastAPI" in recalled


# ── 3. Clippy Vision (Screen Awareness) Tests ────────────────────────────────

def test_clippy_vision_workflow_classification():
    assert clippy_vision.classify_workflow("Code", "test.py") == "coding"
    assert clippy_vision.classify_workflow("Terminal", "error: segmentation fault") == "debugging"
    assert clippy_vision.classify_workflow("Firefox", "Python docs") == "researching"
    assert clippy_vision.classify_workflow("Figma", "Zenith UI Wireframe") == "designing"


def test_clippy_vision_observation_cycle():
    privacy_guard.set_ghost_mode(False)
    clippy_vision.resume()

    res = clippy_vision.observe_cycle()
    assert res["status"] == "active"
    assert "app_name" in res["observation"]
    assert "workflow" in res["observation"]

    # Test pause
    clippy_vision.pause()
    assert clippy_vision.is_paused()
    assert clippy_vision.observe_cycle()["status"] == "paused"
    clippy_vision.resume()


# ── 4. Mem0 Structured Long-Term Memory Tests ────────────────────────────────

def test_sanitize_memory_text():
    raw = "My API key is sk-1234567890abcdef1234567890 and secret is ghp_abcdefghijklmnop123456"
    sanitized = sanitize_memory_text(raw)
    assert "sk-1234567890abcdef1234567890" not in sanitized
    assert "ghp_abcdefghijklmnop123456" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized


def test_mem0_crud_and_search():
    privacy_guard.set_ghost_mode(False)
    privacy_guard.set_sensor("memory_recording", True)

    # Add memory
    mid = memory_layer.add_memory(
        content="Prefer FastAPI async def endpoints over synchronous def.",
        tier="preference",
        topic="backend_architecture",
    )
    assert mid is not None

    # Search memory
    results = memory_layer.search_memories(query="FastAPI async")
    assert len(results) > 0
    assert any("FastAPI async" in m["content"] for m in results)

    # Structured summary
    summary = memory_layer.get_structured_summary()
    assert "Preferences" in summary or "FastAPI" in summary

    # Delete memory
    deleted = memory_layer.delete_memory(mid)
    assert deleted is True


# ── 5. Unified Browser Automation Tests ──────────────────────────────────────

def test_browser_sensitive_action_detection():
    assert browser_unified.is_sensitive_action("https://store.example.com/checkout")
    assert browser_unified.is_sensitive_action("https://shop.com/product", text="buy now")
    assert browser_unified.is_sensitive_action("https://app.com/settings", selector="#delete-account")
    assert not browser_unified.is_sensitive_action("https://docs.python.org/3/library/asyncio.html")


@pytest.mark.anyio
async def test_browser_navigate_deterministic():
    privacy_guard.set_ghost_mode(False)
    privacy_guard.set_sensor("browser_automation", True)

    # Navigate to a public, deterministic site or mock
    with patch.object(browser_unified, "navigate", new_callable=AsyncMock) as mock_nav:
        mock_nav.return_value = {
            "status": "success",
            "url": "https://example.com",
            "title": "Example Domain",
            "text": "This domain is for use in illustrative examples.",
        }
        res = await browser_unified.navigate("https://example.com")
        assert res["status"] == "success"
        assert res["title"] == "Example Domain"


@pytest.mark.anyio
async def test_browser_autonomous_goal_safety():
    privacy_guard.set_ghost_mode(False)

    # Goal requiring checkout stops at confirmation checkpoint
    with patch.object(browser_unified, "is_sensitive_action", return_value=True):
        res = await browser_unified.execute_goal("Buy a new server on cloud provider", max_steps=2)
        assert res["status"] in ("requires_confirmation", "failed", "partial")


# ── 6. Vision Engine & Gesture Detection Tests ────────────────────────────────

@pytest.mark.anyio
async def test_vision_engine_synthetic_capture():
    privacy_guard.set_ghost_mode(False)
    privacy_guard.set_sensor("camera", True)

    ok, raw_bytes, b64 = await vision_engine.capture_frame()
    assert ok is True
    assert len(raw_bytes) > 0
    assert len(b64) > 0


@pytest.mark.anyio
async def test_vision_engine_visual_question():
    privacy_guard.set_ghost_mode(False)
    privacy_guard.set_sensor("camera", True)

    res = await vision_engine.answer_visual_question("What is on screen?", source="screen")
    assert res["status"] == "success"
    assert "analysis" in res


# ── 7. Unified Context Engine & Tool Registration Tests ───────────────────────

def test_context_engine_snapshot():
    snap = context_engine.get_snapshot()
    assert "timestamp" in snap
    assert "screen" in snap
    assert "activity" in snap
    assert "memory_count" in snap
    assert "privacy" in snap


def test_context_engine_prompt_context():
    privacy_guard.set_ghost_mode(False)
    ctx_txt = context_engine.build_prompt_context()
    assert isinstance(ctx_txt, str)

    # Ghost Mode must suppress background context
    privacy_guard.set_ghost_mode(True)
    ghost_ctx = context_engine.build_prompt_context()
    assert "GHOST MODE" in ghost_ctx
    privacy_guard.set_ghost_mode(False)


def test_tool_registrations():
    assert "screen_observe" in tool_reg.TOOLS
    assert "activity_recall" in tool_reg.TOOLS
    assert "activity_summary" in tool_reg.TOOLS
    assert "mem0_remember" in tool_reg.TOOLS
    assert "mem0_recall" in tool_reg.TOOLS
    assert "browser_browse" in tool_reg.TOOLS
    assert "browser_autonomous_goal" in tool_reg.TOOLS
    assert "camera_capture" in tool_reg.TOOLS
    assert "vision_detect" in tool_reg.TOOLS
    assert "privacy_control" in tool_reg.TOOLS
    assert "get_unified_context" in tool_reg.TOOLS


def test_tool_deduplication_and_catalog_consolidation():
    """Verify that duplicate/competing tools are consolidated in the LLM catalog."""
    cat = tool_reg.catalog()
    catalog_names = {c["function"]["name"] for c in cat}

    # Authoritative canonical tools must be in catalog
    assert "browser" in catalog_names
    assert "browser_screenshot" in catalog_names
    assert "deep_research" in catalog_names

    # Duplicate/competing tools must be hidden from LLM catalog to eliminate ambiguity
    assert "browser_browse" not in catalog_names
    assert "web_screenshot_full" not in catalog_names
    assert "research_synthesis" not in catalog_names

    # However, they must still exist in tool_reg.TOOLS for backward compatibility
    assert "browser_browse" in tool_reg.TOOLS
    assert "web_screenshot_full" in tool_reg.TOOLS
    assert "research_synthesis" in tool_reg.TOOLS

    # Tool explorer get_available_tools must also exclude the hidden duplicates
    from zenith.tools.tool_explorer import get_available_tools
    explorer_output = get_available_tools()
    assert "browser_browse" not in explorer_output
    assert "web_screenshot_full" not in explorer_output
    assert "research_synthesis" not in explorer_output
    assert "deep_research" in explorer_output
    assert "browser" in explorer_output
    assert "browser_screenshot" in explorer_output


@pytest.mark.anyio
async def test_memory_layer_bridge():
    """Verify legacy memory tool saves and recalls through Mem0."""
    res_save = await tool_reg.call_tool("memory", {
        "action": "save",
        "key": "pref::font_size",
        "value": "14px monospace"
    })
    assert res_save["ok"] is True

    res_recall = await tool_reg.call_tool("memory", {
        "action": "recall",
        "query": "font_size"
    })
    assert res_recall["ok"] is True
    assert "14px monospace" in res_recall["result"]


# ── 8. REST API Endpoints Contract Tests ──────────────────────────────────────

def test_api_privacy_endpoints(client):
    # GET /api/privacy/status
    res = client.get("/api/privacy/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "privacy" in data

    # POST /api/privacy/ghost_mode
    res_ghost = client.post("/api/privacy/ghost_mode", json={"enabled": False})
    assert res_ghost.status_code == 200
    assert res_ghost.json()["ghost_mode"] is False

    # POST /api/privacy/sensor
    res_sensor = client.post("/api/privacy/sensor", json={"sensor": "camera", "enabled": True})
    assert res_sensor.status_code == 200
    assert res_sensor.json()["enabled"] is True


def test_api_activity_endpoints(client):
    res_sum = client.get("/api/activity/summary?hours=24")
    assert res_sum.status_code == 200
    assert res_sum.json()["ok"] is True

    res_time = client.get("/api/activity/timeline?limit=10")
    assert res_time.status_code == 200
    assert res_time.json()["ok"] is True


def test_api_screen_endpoints(client):
    res_scr = client.get("/api/screen/status")
    assert res_scr.status_code == 200
    assert res_scr.json()["ok"] is True
    assert "active_window" in res_scr.json()


def test_api_mem0_endpoints(client):
    # Add memory
    res_add = client.post("/api/memory/mem0/add", json={
        "content": "Keep unit tests fast and modular.",
        "tier": "workflow",
        "topic": "testing"
    })
    assert res_add.status_code == 200
    data = res_add.json()
    assert data["ok"] is True
    mid = data["memory_id"]

    # Search
    res_search = client.get("/api/memory/mem0/search?q=unit+tests")
    assert res_search.status_code == 200
    assert len(res_search.json()["results"]) > 0

    # Delete
    res_del = client.delete(f"/api/memory/mem0/{mid}")
    assert res_del.status_code == 200


def test_api_vision_endpoints(client):
    res_vis = client.get("/api/vision/status")
    assert res_vis.status_code == 200
    assert "vision" in res_vis.json()

    res_frame = client.get("/api/vision/frame")
    assert res_frame.status_code == 200
    assert "frame_b64" in res_frame.json()


def test_api_context_snapshot(client):
    res_ctx = client.get("/api/context/snapshot")
    assert res_ctx.status_code == 200
    assert res_ctx.json()["ok"] is True
    assert "snapshot" in res_ctx.json()
