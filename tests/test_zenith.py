"""Unit tests for Zenith's core plumbing — run from /app inside the container.

    docker compose up --build -d && docker exec zenith python -m pytest tests -q
"""
from __future__ import annotations

import asyncio
import json

import pytest


def _run(coro):
    return asyncio.run(coro)


# ── registry ──────────────────────────────────────────────────────────────────

def test_catalog_has_new_capabilities():
    from zenith.core import tools as reg

    names = set(reg.TOOLS)
    for expected in (
        "docker_list", "docker_status", "docker_start", "docker_stop",
        "docker_restart", "docker_logs", "system_status", "disk_usage",
        "memory_usage", "top_processes", "gh_whoami", "gh_list_repos",
        "gh_issues", "gh_pulls", "gh_repo_status", "gh_create_issue",
        "mc_status", "mc_players", "mc_start", "mc_stop", "mc_restart",
        "email_search", "email_read", "email_draft", "email_send",
        "browser", "browser_screenshot", "browser_click", "browser_type",
        "shell", "write_file", "read_file", "list_dir",
        "git_status", "git_log", "git_diff", "git_branch", "port_inspector",
        "systemd_status", "systemd_control", "ping_check", "endpoint_health",
        "jellyfin_status", "jellyfin_search", "jellyfin_recent",
        "maps_search", "maps_directions", "maps_commute", "maps_geocode", "maps_embed",
        "research_synthesis", "generate_pptx", "ha_fan", "ha_ac", "ha_climate", "ha_soundbar",
        "ha_switch", "ha_smart_plug", "ha_overview", "ha_entity",
    ):
        assert expected in names, f"missing tool {expected}"


def test_direct_execution_no_gate():
    from zenith.core import tools as t

    res = _run(t.call_tool("docker_status", {"container": "zenith"}))
    assert res["ok"] is True


# ── validation ────────────────────────────────────────────────────────────────

def test_missing_required_fails():
    from zenith.core import tools as t

    res = _run(t.call_tool("docker_start", {}))
    assert res["ok"] is False


# ── provider markup parsing ───────────────────────────────────────────────────

def test_markup_parser():
    from zenith.core import orchestrator

    txt = '<|tool_calls|>\n<|invoke name="docker_list" />\n</|tool_calls|>'
    assert orchestrator._parse_markup_calls(txt) == [("docker_list", "{}")]

    # full-width DeepSeek relay form: <｜invoke name="todo"><｜parameter …>…
    fw = ('<｜tool_calls>\n'
          '<｜invoke name="todo">\n'
          '<｜parameter name="action" string="true">list</｜parameter>\n'
          '</｜invoke>\n'
          '</｜tool_calls>')
    parsed = orchestrator._parse_markup_calls(fw)
    assert parsed == [("todo", '{"action": "list"}')], parsed

    # parameter-tag args convert to a JSON object
    shell = '<|invoke name="shell"><|parameter name="command" string="true">whoami</|parameter></|invoke>'
    assert orchestrator._parse_markup_calls(shell) == [("shell", '{"command": "whoami"}')]


# ── docker helpers (guard rails) ──────────────────────────────────────────────

def test_guarded_containers():
    from zenith.tools import homelab
    from unittest.mock import patch

    with patch.object(homelab, "GUARDED", {"jellyfin", "zenith-core"}):
        assert "jellyfin" in homelab.GUARDED
        assert "bogus" not in homelab.GUARDED
        assert homelab._guarded("bogus") is not None
        assert homelab._guarded("jellyfin") is None


def test_tool_parameter_signature_fixes():
    from zenith.core import tools as t
    from zenith.tools import homelab

    # Test todo with title parameter
    res = _run(t.call_tool("todo", {"action": "list"}))
    assert res["ok"] is True

    # Test agent status/list
    res = _run(t.call_tool("agent", {"action": "list"}))
    assert res["ok"] is True

    # Test calendar list
    res = _run(t.call_tool("calendar", {"action": "list"}))
    assert res["ok"] is True

    # Test _repo_arg owner/repo splitting
    parsed = homelab._repo_arg("testowner", "testowner/zenith")
    assert parsed == ("testowner", "zenith")


def test_email_arg_normalization():
    from zenith.tools import homelab
    from zenith.core import orchestrator

    to, sub, body = homelab._normalize_email_args(
        "Hi Mike, Hope you're doing well. mikesharma253@gmail.com", "", ""
    )
    assert to == "mikesharma253@gmail.com"
    assert "Hi Mike" in body

    # Test key-value raw arg parsing
    parsed = orchestrator._parse_args("to: mikesharma253@gmail.com\nsubject: Test\nbody: Hello")
    assert parsed == {"to": "mikesharma253@gmail.com", "subject": "Test", "body": "Hello"}


def test_maps_tools():
    from zenith.core import tools as t
    from zenith.tools import maps

    # Test maps_embed generation
    iframe = maps.generate_map_embed_iframe(q_or_place="Dehradun", embed_type="place")
    assert "<iframe" in iframe
    assert "google.com/maps/embed/v1/place" in iframe

    # Test maps_search execution via tool runner
    res = _run(t.call_tool("maps_search", {"query": "cafes", "location": "Dehradun"}))
    assert res["ok"] is True
    assert "cafes" in res["result"].lower() or "dehradun" in res["result"].lower()

    # Test maps_directions execution via tool runner
    res_dir = _run(t.call_tool("maps_directions", {"origin": "Dehradun", "destination": "Delhi", "mode": "driving"}))
    assert res_dir["ok"] is True
    assert "Dehradun" in res_dir["result"] or "Delhi" in res_dir["result"]

    # Test maps_commute execution
    res_com = _run(t.call_tool("maps_commute", {"origin": "Dehradun", "destinations": "Delhi, Rishikesh"}))
    assert res_com["ok"] is True
    assert "Commute" in res_com["result"] or "Dehradun" in res_com["result"]


def test_ha_device_controls():
    from zenith.core import tools as t
    from zenith.tools.homeassistant import _normalize_fan_id, _resolve_switch_id

    # Test Fan normalizer
    assert _normalize_fan_id("fan 1") == "fan.fan_1"
    assert _normalize_fan_id("2") == "fan.fan_2"

    # Test Switch resolver
    assert _resolve_switch_id("ac")[0] == "switch.power_switch_switch_2"
    assert _resolve_switch_id("soundbar")[0] == "switch.power_switch_switch_1"

    # Test status checks for fan 1 & fan 2
    res1 = _run(t.call_tool("ha_fan", {"action": "status", "entity_id": "fan 1"}))
    assert res1["ok"] is True
    assert "FAN 1" in res1["result"] or "fan.fan_1" in res1["result"]

    res2 = _run(t.call_tool("ha_fan", {"action": "status", "entity_id": "fan 2"}))
    assert res2["ok"] is True
    assert "FAN 2" in res2["result"] or "fan.fan_2" in res2["result"]

    # Test AC control & climate functions
    res_ac = _run(t.call_tool("ha_ac", {"action": "status"}))
    assert res_ac["ok"] is True
    assert "Panasonic AC" in res_ac["result"] or "switch_2" in res_ac["result"]

    # Test setting AC temperature explicitly and implicitly
    res_temp = _run(t.call_tool("ha_ac", {"action": "temp", "temperature": 23.0}))
    assert res_temp["ok"] is True
    assert "23.0°C" in res_temp["result"]

    res_temp_implicit = _run(t.call_tool("ha_ac", {"temperature": 22.5}))
    assert res_temp_implicit["ok"] is True
    assert "22.5°C" in res_temp_implicit["result"]

    # Test setting AC fan speed
    res_fan = _run(t.call_tool("ha_ac", {"action": "fan", "fan_mode": "high"}))
    assert res_fan["ok"] is True
    assert "HIGH" in res_fan["result"]

    res_fan_implicit = _run(t.call_tool("ha_ac", {"fan_mode": "medium"}))
    assert res_fan_implicit["ok"] is True
    assert "MEDIUM" in res_fan_implicit["result"]

    # Test Soundbar control
    res_sb = _run(t.call_tool("ha_soundbar", {"action": "status"}))
    assert res_sb["ok"] is True

    assert "Soundbar" in res_sb["result"] or "switch_1" in res_sb["result"]

    # Test Smart Plug control
    res_plug = _run(t.call_tool("ha_smart_plug", {"action": "status"}))
    assert res_plug["ok"] is True
    assert "Smart Plug" in res_plug["result"]

    # Test HA Overview
    res_ov = _run(t.call_tool("ha_overview", {}))
    assert res_ov["ok"] is True
    assert "Home Assistant Device Overview" in res_ov["result"]


def test_zenith_docs_tool():
    from zenith.core import tools as t
    import asyncio
    _run = asyncio.run

    # Test all index
    res_index = _run(t.call_tool("zenith_docs", {"topic": "all"}))
    assert res_index["ok"] is True
    assert "Zenith System Documentation Index" in res_index["result"]

    # Test overview
    res_overview = _run(t.call_tool("zenith_docs", {"topic": "overview"}))
    assert res_overview["ok"] is True
    assert "Core Architecture" in res_overview["result"]

    # Test tools
    res_tools = _run(t.call_tool("zenith_docs", {"topic": "tools"}))
    assert res_tools["ok"] is True
    assert "generate_pptx" in res_tools["result"]

    # Test deployment
    res_deploy = _run(t.call_tool("zenith_docs", {"topic": "deployment"}))
    assert res_deploy["ok"] is True
    assert "Launching Zenith Live" in res_deploy["result"]

    # Test agent manual
    res_agent = _run(t.call_tool("zenith_docs", {"topic": "agent"}))
    assert res_agent["ok"] is True
    assert "Direct Execution — Always" in res_agent["result"]


def test_calendar_upcoming_filters_past_events():
    from zenith.tools import calendar
    from zenith.memory.store import _connect
    import asyncio
    _run = asyncio.run

    # Insert a past event (e.g. 5 days ago) and a future event
    with _connect() as conn:
        conn.execute("DELETE FROM events WHERE title IN ('Test Past Event', 'Test Future Event')")
        conn.execute("INSERT INTO events (title, at) VALUES (?, ?)",
                     ("Test Past Event", "2026-09-01T10:00:00+05:30"))
        conn.execute("INSERT INTO events (title, at) VALUES (?, ?)",
                     ("Test Future Event", "2026-09-28T15:00:00+05:30"))
        conn.commit()

    upcoming_list = _run(calendar.upcoming())
    titles = [e["title"] for e in upcoming_list]

    # Clean up
    with _connect() as conn:
        conn.execute("DELETE FROM events WHERE title IN ('Test Past Event', 'Test Future Event')")
        conn.commit()

    assert "Test Past Event" not in titles
    assert "Test Future Event" in titles


def test_prompt_personalization():
    from zenith.core import prompts, server_prompts, orchestrator
    from zenith.core.config import settings

    settings.user_name = "Milind"
    prompt = prompts.build_system_prompt()
    assert "Milind" in prompt
    assert 'NEVER refer to Milind as "user"' in prompt or 'Never address Milind as "user"' in prompt

    orch = orchestrator.Orchestrator()
    sys_prompt = orch.build_system_prompt()
    assert "Today's Date & Local Time:" in sys_prompt
    assert "Milind" in sys_prompt

    cat = orchestrator.tool_reg.catalog()
    assert any("Milind" in t["function"]["description"] for t in cat)