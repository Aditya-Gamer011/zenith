"""Tests for Cross-Platform Shell Execution, Host Introspection, and Tool Configuration.

Verifies:
- Safe shell execution across Linux, macOS, and Windows.
- Stateful working directory (cwd) tracking and `cd` navigation.
- Command history logging (command, cwd, exit code, duration, status).
- Safety guardrails (refusal of forbidden commands across OS).
- Host and server introspection (detecting server/thingy, OS, hardware, environment type).
- Cross-platform system vitals (system_status, disk_usage, memory_usage, cpu_usage, top_processes).
- Available tools exploration and configurable tools catalog.
- System prompt and orchestrator context injection.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from zenith.core import tools as tool_reg
from zenith.core.config import settings
from zenith.core import orchestrator, prompts
from zenith.tools import computer, system_info, tool_explorer


def _run(coro):
    return asyncio.run(coro)


def test_cross_platform_shell_execution(monkeypatch):
    monkeypatch.setattr(settings, "allow_shell", True)

    # Test basic command execution
    res = _run(computer.run_shell("echo 'Zenith Sovereign Agent'"))
    assert "exit: 0 (SUCCESS)" in res
    assert "Zenith Sovereign Agent" in res
    assert "[cwd:" in res
    assert "[os:" in res
    assert "[duration:" in res

    # Test tool execution via registry
    reg_res = _run(tool_reg.call_tool("shell", {"command": "echo 'From Tool Registry'"}))
    assert reg_res["ok"] is True
    assert "From Tool Registry" in reg_res["result"]
    assert "exit: 0 (SUCCESS)" in reg_res["result"]


def test_failed_command_returns_stderr_and_exit_code(monkeypatch):
    monkeypatch.setattr(settings, "allow_shell", True)

    res = _run(computer.run_shell("non_existent_command_zenith_12345"))
    assert "exit:" in res
    assert "FAILED" in res or "not found" in res.lower() or "error" in res.lower()


def test_command_history_tracking(monkeypatch):
    monkeypatch.setattr(settings, "allow_shell", True)

    _run(computer.run_shell("echo 'History Test 1'"))
    _run(computer.run_shell("echo 'History Test 2'"))

    history = computer.get_command_history(limit=5)
    assert len(history) >= 2
    assert any("History Test 1" in h["command"] for h in history)
    assert any("History Test 2" in h["command"] for h in history)
    assert all("exit_code" in h and "duration_seconds" in h and "cwd" in h for h in history)

    # Test via tool
    res = _run(tool_reg.call_tool("get_command_history", {"limit": 5}))
    assert res["ok"] is True
    assert "History Test" in res["result"]


def test_stateful_cwd_and_cd_navigation(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "allow_shell", True)

    sub_dir = tmp_path / "zenith_test_sub"
    sub_dir.mkdir()

    computer.set_active_cwd(tmp_path)
    assert computer.get_active_cwd() == tmp_path

    # Test cd into sub_dir
    res = _run(computer.run_shell(f"cd zenith_test_sub"))
    assert "Changed active working directory" in res
    assert computer.get_active_cwd() == sub_dir

    # Test cd back
    res_back = _run(computer.run_shell("cd .."))
    assert computer.get_active_cwd() == tmp_path


def test_safety_refusal_across_os(monkeypatch):
    monkeypatch.setattr(settings, "allow_shell", True)

    # Linux / Unix forbidden
    res_unix = _run(computer.run_shell("rm -rf /"))
    assert "REFUSED" in res_unix
    assert "no-go" in res_unix

    # Windows forbidden
    res_win = _run(computer.run_shell("format c:"))
    assert "REFUSED" in res_win
    assert "no-go" in res_win

    res_win_del = _run(computer.run_shell("del /f /s /q c:\\"))
    assert "REFUSED" in res_win_del


def test_host_server_introspection():
    data = system_info.get_full_host_introspection()
    assert "os" in data
    assert "environment" in data
    assert "hardware" in data
    assert "runtime" in data

    os_info = data["os"]
    assert os_info["family"] in ("linux", "darwin", "windows")
    assert len(os_info["name"]) > 0

    env = data["environment"]
    assert "description" in env
    assert isinstance(env["is_container"], bool)

    hw = data["hardware"]
    assert hw["cpu_cores"] >= 1
    assert "memory" in hw
    assert "disk" in hw
    assert "uptime" in hw

    # Test markdown report and summary
    summary = system_info.format_host_summary()
    assert "- OS:" in summary
    assert "- Environment:" in summary
    assert "- Hardware:" in summary

    report = system_info.format_host_details_markdown()
    assert "# 🖥️ Host & Server Environment Report" in report

    # Test tool invocation
    res_summary = _run(tool_reg.call_tool("get_system_info", {"detail_level": "summary"}))
    assert res_summary["ok"] is True
    assert "- OS:" in res_summary["result"]

    res_full = _run(tool_reg.call_tool("get_system_info", {"detail_level": "full"}))
    assert res_full["ok"] is True
    assert "Host & Server Environment Report" in res_full["result"]


def test_cross_platform_system_vitals():
    # system_status
    res_status = _run(system_info.cross_platform_system_status())
    assert "uptime" in res_status
    assert "mem" in res_status

    # disk_usage
    res_disk = _run(system_info.cross_platform_disk_usage())
    assert len(res_disk) > 0

    # memory_usage
    res_mem = _run(system_info.cross_platform_memory_usage())
    assert len(res_mem) > 0

    # cpu_usage
    res_cpu = _run(system_info.cross_platform_cpu_usage())
    assert "CPU:" in res_cpu or "load" in res_cpu.lower()


def test_tool_explorer_and_configurable_tools():
    # Available tools listing
    all_tools_txt = tool_explorer.get_available_tools()
    assert "Zenith Tools Catalog" in all_tools_txt
    assert "System, Shell & Execution" in all_tools_txt

    # Category filter
    shell_tools_txt = tool_explorer.get_available_tools(category="system_shell")
    assert "shell" in shell_tools_txt

    # Query search
    search_txt = tool_explorer.get_available_tools(query="disk_usage")
    assert "disk_usage" in search_txt

    # Configurable tools catalog
    config_txt = tool_explorer.get_configurable_tools()
    assert "Zenith Configurable Integrations & Tools Catalog" in config_txt
    assert "GEMINI_API_KEY" in config_txt
    assert "setup_secret" in config_txt

    # Test via tool registry
    res_avail = _run(tool_reg.call_tool("get_available_tools", {"category": "system_shell"}))
    assert res_avail["ok"] is True
    assert "shell" in res_avail["result"]

    res_config = _run(tool_reg.call_tool("get_configurable_tools", {}))
    assert res_config["ok"] is True
    assert "GEMINI_API_KEY" in res_config["result"]


def test_orchestrator_context_injection():
    orch = orchestrator.Orchestrator()
    prompt = orch.build_system_prompt()

    # Verify context injection
    assert "Host & Server Environment:" in prompt
    assert "- OS:" in prompt
    assert "- Environment:" in prompt
    assert "Active Working Directory:" in prompt
    assert "Workspace:" in prompt
    assert "Today's Date & Local Time:" in prompt

    # Verify prompt guidelines for autonomous agent execution
    assert "Autonomous Agent Command Execution Protocol" in prompt
    assert "Read what happened" in prompt
    assert "Decide what next command to run" in prompt
    assert "Host, Server & Environment Introspection" in prompt
    assert "Tool Understanding & Configuration Mastery" in prompt


def test_health_endpoint_host_info():
    from fastapi.testclient import TestClient
    from zenith.main import app

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "os" in data
    assert "environment" in data
    assert len(data["os"]) > 0
    assert len(data["environment"]) > 0

