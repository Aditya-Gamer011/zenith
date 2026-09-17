"""Tests for Zenith Worker Tools, Dual-Engine Fallback, and Cognitive Awareness."""
import pytest
from unittest.mock import patch, AsyncMock
from zenith.core.tools import (
    tool_worker_status,
    tool_worker_control,
    tool_agent_submit,
    catalog,
)
from zenith.core.prompts import build_system_prompt


def test_tool_catalog_contains_worker_tools():
    names = {t["function"]["name"] for t in catalog()}
    assert "worker_status" in names
    assert "worker_control" in names
    assert "agent_submit" in names
    assert "agent_status" in names


@pytest.mark.anyio
async def test_worker_status_online():
    mock_status_payload = {
        "status": "ok",
        "agy": {
            "installed": True,
            "path": "/usr/local/bin/agy",
            "authenticated": True,
            "model": "gemini-3.1-pro-high",
            "effort": "high",
        },
        "tasks": {
            "total": 5,
            "active": 1,
        }
    }
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_status_payload
        res = await tool_worker_status()
        assert "ONLINE" in res
        assert "Authenticated" in res
        assert "1 active / 5 total tasks" in res


@pytest.mark.anyio
async def test_worker_status_offline():
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = ConnectionError("Failed to connect")
        res = await tool_worker_status()
        assert "OFFLINE" in res
        assert "Zenith Native Agent" in res


@pytest.mark.anyio
async def test_worker_control_actions():
    res_login = await tool_worker_control("login")
    assert "setup-worker.sh login" in res_login
    assert "setup-worker.ps1" in res_login

    res_stop = await tool_worker_control("stop")
    assert "setup-worker.sh stop" in res_stop

    with patch("zenith.core.tools.tool_worker_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = "Mocked Status OK"
        res_stat = await tool_worker_control("status")
        assert res_stat == "Mocked Status OK"


@pytest.mark.anyio
async def test_agent_submit_delegates_when_authenticated():
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get, \
         patch("zenith.core.tools._worker_post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = {"status": "ok", "authenticated": True}
        mock_post.return_value = {"task_id": "task-xyz-123", "status": "QUEUED", "workspace": "/tmp/ws"}

        res = await tool_agent_submit("Build a REST API in Go")
        assert "task-xyz-123" in res
        assert "Delegated to Antigravity worker" in res


@pytest.mark.anyio
async def test_agent_submit_falls_back_when_unauthenticated():
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get, \
         patch("zenith.tools.agent.agent", new_callable=AsyncMock) as mock_native_agent:
        mock_get.return_value = {"status": "ok", "authenticated": False}
        mock_native_agent.return_value = "Agent started: coding (agt-native-999)"

        res = await tool_agent_submit("Implement a FastAPI router")
        assert "Zenith Native Coding Agent" in res
        assert "agt-native-999" in res
        assert "agy" in res


def test_system_prompt_contains_command_awareness():
    prompt = build_system_prompt()
    assert "System Lifecycle Commands & Antigravity Worker Awareness" in prompt
    assert "zenith.exe" in prompt
    assert "start.sh" in prompt
    assert "worker_status" in prompt
    assert "Containerized Mode" in prompt
    assert "Zenith Native Host Mode" in prompt
    assert "One-Time Google OAuth Authentication" in prompt
