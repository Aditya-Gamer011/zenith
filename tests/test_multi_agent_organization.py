"""Tests for Zenith Multi-Agent Organization, Departmental Catalogs, and HR Agent Forge."""
import pytest
from unittest.mock import patch, AsyncMock
from zenith.agents.agent_service import AgentService, DEPARTMENTS
from zenith.core import tools as tool_reg
from zenith.core.orchestrator import Orchestrator
from zenith.memory import store
from zenith.tools.agent import (
    delegate_task,
    list_agents,
    get_agent_status,
    hire_agent,
    update_agent,
    fire_agent,
    inspect_agent,
    list_available_tools,
    agent,
)


def test_agent_service_departments_and_roster():
    svc = AgentService()
    roster = svc.list_roster()
    dept_ids = {d["id"] for d in roster}
    
    expected_depts = {
        "communication", "coding", "hr", "research",
        "operations", "productivity", "creative", "utility",
    }
    assert expected_depts.issubset(dept_ids), f"Missing departments: {expected_depts - dept_ids}"

    # Verify scoped catalogs
    coding_cat = svc.get_catalog("coding")
    coding_names = {t["function"]["name"] for t in coding_cat}
    assert "agent_submit" in coding_names
    assert "shell" in coding_names
    assert "read_file" in coding_names
    assert "docker_start" not in coding_names  # Belong to operations
    assert "calendar" not in coding_names      # Belong to productivity

    comms_cat = svc.get_catalog("communication")
    comms_names = {t["function"]["name"] for t in comms_cat}
    assert "email_search" in comms_names
    assert "email_draft" in comms_names
    assert "shell" not in comms_names

    ops_cat = svc.get_catalog("operations")
    ops_names = {t["function"]["name"] for t in ops_cat}
    assert "docker_list" in ops_names
    assert "ha_overview" in ops_names
    assert "system_status" in ops_names
    assert "email_send" not in ops_names


def test_orchestrator_executive_catalog():
    exec_cat = tool_reg.executive_catalog()
    names = {t["function"]["name"] for t in exec_cat}
    
    assert "delegate_task" in names
    assert "list_agents" in names
    assert "get_agent_status" in names
    assert "update_user_profile" in names
    assert "memory" in names
    assert "graph" in names
    assert "switch_mode" in names
    assert "get_mode" in names
    assert "setup_secret" in names
    assert "get_setup_status" in names
    assert "zenith_docs" in names

    # Crucial: verify that monolithic domain tools are pruned from Zenith's executive view
    assert "docker_logs" not in names
    assert "ha_climate" not in names
    assert "generate_pptx" not in names
    assert "figma_export_assets" not in names
    assert "email_send" not in names
    assert len(names) <= 15


def test_orchestrator_system_prompt_structure():
    orch = Orchestrator()
    prompt = orch.build_system_prompt()
    assert "MULTI-AGENT ORGANIZATION & DELEGATION" in prompt
    assert "delegate_task" in prompt
    assert "communication" in prompt
    assert "coding" in prompt
    assert "hr" in prompt
    assert "operations" in prompt


@pytest.mark.anyio
async def test_hr_hire_update_inspect_fire_agent():
    # 1. Hire a custom agent
    res = await hire_agent(
        agent_id="rover_telemetry",
        name="Rover Telemetry Specialist",
        department="Robotics Lab",
        role_description="Monitors and analyzes autonomous rover sensor streams and telemetry",
        system_prompt="You are Zenith's Rover Telemetry Specialist.",
        tool_names=["system_status", "disk_usage", "notes", "web_search", "invalid_bogus_tool"],
    )
    assert "Successfully hired and registered agent" in res
    assert "Warning: Ignored unrecognized tools: invalid_bogus_tool" in res

    # 2. Inspect the agent
    inspection = await inspect_agent("rover_telemetry")
    assert "Rover Telemetry Specialist" in inspection
    assert "Robotics Lab" in inspection
    assert "system_status" in inspection

    # 3. Check that it appears in roster
    roster_txt = await list_agents()
    assert "rover_telemetry" in roster_txt

    # 4. Check that AgentService discovers it and generates its scoped catalog
    svc = AgentService()
    cat = svc.get_catalog("rover_telemetry")
    cat_names = {t["function"]["name"] for t in cat}
    assert "system_status" in cat_names
    assert "notes" in cat_names
    assert "docker_start" not in cat_names

    # 5. Update the agent
    up_res = await update_agent(
        agent_id="rover_telemetry",
        role_description="Updated description for rover telemetry",
    )
    assert "Updated agent 'Rover Telemetry Specialist'" in up_res

    # 6. Fire the agent
    fire_res = await fire_agent("rover_telemetry")
    assert "Successfully retired and removed agent" in fire_res
    assert store.get_custom_agent("rover_telemetry") is None


@pytest.mark.anyio
async def test_delegate_task_execution():
    with patch("zenith.agents.agent_service.AgentService.execute_task", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "ok": True,
            "result": "CAD drawings received from Prof. Verma. Draft prepared.",
            "tool_calls": 3,
            "steps": [],
            "run_id": "test1234",
            "agent": "Communications Dispatch",
        }
        
        res = await delegate_task(
            department="communication",
            task="Check rover emails",
            context="Aditya is awaiting CAD review",
            synchronous=True,
        )
        assert "[Communications Dispatch Report (3 tool steps)]" in res
        assert "CAD drawings received" in res


@pytest.mark.anyio
async def test_legacy_agent_tool_backward_compatibility():
    res = await agent(action="list")
    assert "Zenith Organization Roster" in res
    
    status_res = await agent(action="status")
    assert "No active or recent agent runs" in status_res or "Recent agent runs" in status_res


def test_api_agents_roster_and_tools():
    from fastapi.testclient import TestClient
    from zenith.main import app

    client = TestClient(app)
    
    # 1. Test /api/agents/roster
    resp = client.get("/api/agents/roster")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    roster_ids = {d["id"] for d in data["roster"]}
    assert "coding" in roster_ids
    assert "communication" in roster_ids
    assert "hr" in roster_ids
    assert "operations" in roster_ids

    # 2. Test /api/agents/tools
    tools_resp = client.get("/api/agents/tools?filter=docker")
    assert tools_resp.status_code == 200
    tools_data = tools_resp.json()
    assert tools_data["ok"] is True
    docker_tools = {t["name"] for t in tools_data["tools"]}
    assert "docker_list" in docker_tools

    # 3. Test /api/agents/hire via REST
    hire_resp = client.post("/api/agents/hire", json={
        "id": "rover_pathfinder",
        "name": "Rover Pathfinder",
        "department": "Robotics Lab",
        "role_description": "Path planning and obstacle avoidance",
        "system_prompt": "You are Zenith's Rover Pathfinder Specialist.",
        "tools": ["maps_directions", "maps_search"],
    })
    assert hire_resp.status_code == 200
    assert hire_resp.json()["ok"] is True

    # 4. Test /api/agents/{id}
    inspect_resp = client.get("/api/agents/rover_pathfinder")
    assert inspect_resp.status_code == 200
    assert inspect_resp.json()["profile"]["name"] == "Rover Pathfinder"

    # 5. Test /api/agents/{id} DELETE (fire)
    del_resp = client.delete("/api/agents/rover_pathfinder")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

