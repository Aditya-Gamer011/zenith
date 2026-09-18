"""Tests for host paths dynamic resolution, cross-platform compatibility,
direct executive shell execution, and orchestrator action guards.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zenith.tools.host_paths import (
    clear_host_paths_cache,
    format_host_paths_summary,
    get_host_paths,
    is_container,
    resolve_host_path,
)
from zenith.tools.computer import run_shell, read_file, write_file, list_dir
from zenith.core.tools import EXECUTIVE_TOOL_NAMES, executive_catalog


def test_host_paths_dynamic_no_hardcoding():
    """Verify get_host_paths discovers host paths dynamically with no hardcoded names."""
    clear_host_paths_cache()
    paths = get_host_paths()
    assert isinstance(paths, dict)
    assert "home" in paths
    assert "desktop" in paths
    assert "downloads" in paths
    assert "documents" in paths
    assert "workspace" in paths
    assert "os_family" in paths

    # Verify home directory is an absolute path and exists or is well-formed
    assert paths["home"].startswith("/") or ":" in paths["home"]
    assert paths["desktop"].startswith(paths["home"]) or paths["os_family"] != "linux"

    summary = format_host_paths_summary()
    assert "File System Paths" in summary
    assert paths["desktop"] in summary


def test_resolve_host_path():
    """Verify resolve_host_path resolves tilde and common folder prefixes."""
    clear_host_paths_cache()
    paths = get_host_paths()
    desktop = paths["desktop"]
    home = paths["home"]

    # Test tilde expansion
    assert resolve_host_path("~/Desktop/my_test_dir") == f"{desktop}/my_test_dir"
    assert resolve_host_path("~/test.txt") == f"{home}/test.txt"

    # Test friendly prefix expansion
    assert resolve_host_path("Desktop/my_test_dir") == f"{desktop}/my_test_dir"
    assert resolve_host_path("Downloads/sample.pdf") == f"{paths['downloads']}/sample.pdf"
    assert resolve_host_path("Documents/report.docx") == f"{paths['documents']}/report.docx"


def test_executive_tools_includes_shell():
    """Verify shell is an executive tool for immediate, direct command execution."""
    assert "shell" in EXECUTIVE_TOOL_NAMES
    tools = executive_catalog()
    tool_names = [t["function"]["name"] for t in tools]
    assert "shell" in tool_names
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "list_dir" in tool_names
    assert "get_host_paths" in tool_names


@pytest.mark.anyio
async def test_run_shell_local_or_worker():
    """Test shell command execution returns exit code and output."""
    res = await run_shell("echo 'ZENITH_SHELL_TEST_42'")
    assert isinstance(res, str)
    assert "ZENITH_SHELL_TEST_42" in res
    assert "[exit: 0" in res or "SUCCESS" in res


@pytest.mark.anyio
async def test_computer_fs_host_resolution(tmp_path: Path):
    """Test filesystem tools resolve and operate on paths cleanly."""
    test_file = tmp_path / "zenith_test_file.txt"
    test_content = "Hello from dynamic path resolution test!"

    # Write
    write_res = await write_file(str(test_file), test_content)
    assert isinstance(write_res, str)
    assert "Wrote" in write_res

    # Read
    read_res = await read_file(str(test_file))
    assert isinstance(read_res, str)
    assert test_content in read_res

    # List
    list_res = await list_dir(str(tmp_path))
    assert isinstance(list_res, str)
    assert "zenith_test_file.txt" in list_res


@pytest.mark.anyio
async def test_imperative_action_guard_forces_tool_execution():
    """Verify that if LLM responds with verbal promise but NO tool call in round 1,
    the Imperative Action Guard emits ack, injects System Action Directive, and forces round 2 execution."""
    from zenith.core import orchestrator, provider

    orch = orchestrator.Orchestrator()
    emitted = []

    async def mock_emit(evt):
        emitted.append(evt)

    round_count = 0

    async def mock_chat_stream(messages, tools=None, system=None, **kwargs):
        nonlocal round_count
        round_count += 1
        if round_count == 1:
            # Round 1: Model promises action verbally but emits NO tool calls
            yield {"type": "text", "text": "I'm on it, Aditya. Creating the buahahaha folder right away!"}
            yield {"type": "done", "model": "gemini-test"}
        elif round_count == 2:
            # Round 2: After System Action Directive, model emits shell tool call
            yield {
                "type": "tool_call",
                "index": 0,
                "id": "call_shell_1",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"command": "echo 'folder created'"}),
                },
            }
            yield {"type": "done", "model": "gemini-test"}
        else:
            # Final report
            yield {"type": "text", "text": "All done, Aditya! The buahahaha folder has been created."}
            yield {"type": "done", "model": "gemini-test"}

    with patch.object(provider, "PROVIDER_MODE", "direct"):
        with patch.object(provider, "chat_stream", side_effect=mock_chat_stream):
            result = await orch.handle("create a folder on my desktop named buahahaha", emit=mock_emit)

            # 1. Verify ack event was emitted to UI with the verbal acknowledgment
            ack_events = [e for e in emitted if e.get("type") == "ack"]
            assert len(ack_events) >= 1
            assert "I'm on it" in ack_events[0]["text"]

            # 2. Verify tool execution occurred in round 2
            tool_start_events = [e for e in emitted if e.get("type") == "tool_start"]
            assert len(tool_start_events) == 1
            assert tool_start_events[0]["name"] == "shell"

            # 3. Verify final report returned
            assert "All done" in result or "buahahaha" in result
            assert round_count >= 2

