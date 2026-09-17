"""Tests for Zenith Multi-Agent Organization, Departmental Catalogs, and HR Agent Forge."""
import pytest
from unittest.mock import patch, AsyncMock
from zenith.agents.agent_service import AgentService, DEPARTMENTS
from zenith.core import tools as tool_reg
from zenith.core.orchestrator import Orchestrator
from zenith.memory import store
from zenith.tools.agent import (
    delegate_task,
    delegate_parallel,
    ask_specialist,
    share_finding,
    query_findings,
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
    assert "delegate_parallel" in names
    assert "share_finding" in names
    assert "query_findings" in names
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
    assert "delegate_parallel" in prompt
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


@pytest.mark.anyio
async def test_delegate_parallel_execution():
    with patch("zenith.agents.agent_service.AgentService.execute_task", new_callable=AsyncMock) as mock_exec:
        async def side_effect(dept, task, **kw):
            if dept == "communication":
                return {"ok": True, "agent": "Communications Dispatch", "tool_calls": 2, "result": "Inbox checked: 0 unread."}
            elif dept == "operations":
                return {"ok": True, "agent": "DevOps SRE", "tool_calls": 1, "result": "Containers: 5 running, healthy."}
            return {"ok": True, "agent": dept, "tool_calls": 0, "result": "Done"}

        mock_exec.side_effect = side_effect

        res = await delegate_parallel(tasks=[
            {"department": "communication", "task": "Check unread emails"},
            {"department": "operations", "task": "Verify docker health"},
        ])

        assert "Organization Parallel Mission Summary (2 Specialists Deployed)" in res
        assert "Communications Dispatch — ✓ Completed (2 tool steps)" in res
        assert "Inbox checked: 0 unread" in res
        assert "DevOps SRE — ✓ Completed (1 tool steps)" in res
        assert "Containers: 5 running, healthy" in res


@pytest.mark.anyio
async def test_ask_specialist_peer_consultation_and_recursion_limit():
    with patch("zenith.agents.agent_service.AgentService.execute_task", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "ok": True,
            "agent": "DevOps SRE",
            "result": "Port 8000 is open and listening.",
        }

        # 1. Normal peer consultation
        res = await ask_specialist(department="operations", question="Is port 8000 open?")
        assert "[DevOps SRE Consultation Response]" in res
        assert "Port 8000 is open" in res

        # 2. Recursion limit protection (depth >= 2)
        from zenith.agents.agent_service import current_agent_depth
        token = current_agent_depth.set(2)
        try:
            blocked_res = await ask_specialist(department="operations", question="Check port again")
            assert "Peer consultation limit reached" in blocked_res
        finally:
            current_agent_depth.reset(token)


@pytest.mark.anyio
async def test_organizational_blackboard_lifecycle():
    # 1. Share finding
    pub_res = await share_finding(
        topic="telemetry_alert",
        content="Battery voltage stabilized at 12.6V after solar deployment.",
        department="Robotics Lab",
    )
    assert "✓ Finding published to organizational blackboard" in pub_res

    # 2. Query findings via tool
    query_res = await query_findings(query="voltage")
    assert "Organizational Blackboard" in query_res
    assert "Robotics Lab" in query_res
    assert "Battery voltage stabilized" in query_res

    # 3. Context blackboard summary
    summary = store.blackboard_summary(limit=3)
    assert "voltage" in summary.lower() or "battery" in summary.lower()


def test_api_agents_dispatch_and_blackboard():
    from fastapi.testclient import TestClient
    from zenith.main import app

    client = TestClient(app)

    # 1. Test POST /api/agents/dispatch
    with patch("zenith.agents.agent_service.AgentService.execute_task", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "ok": True,
            "agent": "Communications Dispatch",
            "tool_calls": 1,
            "result": "Draft saved.",
            "run_id": "test_disp_1",
        }
        disp_resp = client.post("/api/agents/dispatch", json={
            "department": "communication",
            "task": "Draft email to Prof. Verma",
        })
        assert disp_resp.status_code == 200
        disp_data = disp_resp.json()
        assert disp_data["ok"] is True
        assert disp_data["result"] == "Draft saved."

    # 2. Test POST /api/agents/blackboard
    post_resp = client.post("/api/agents/blackboard", json={
        "department": "Coding",
        "topic": "git_tag_v2",
        "content": "Release v2.0 deployed and healthy.",
    })
    assert post_resp.status_code == 200
    assert post_resp.json()["ok"] is True

    # 3. Test GET /api/agents/blackboard
    get_resp = client.get("/api/agents/blackboard?query=git_tag_v2")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["ok"] is True
    assert any(f["topic"] == "git_tag_v2" for f in get_data["findings"])


@pytest.mark.anyio
async def test_delegation_lifecycle_events_and_background():
    import asyncio
    svc = AgentService()
    events = []

    async def mock_emit(evt):
        events.append(evt)

    with patch.object(svc, "_run_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = "Task accomplished with precision."

        # 1. Test synchronous execution for communication specialist
        events.clear()
        res = await svc.execute_task("communication", "Send email test", emit=mock_emit)
        assert res["ok"] is True
        assert len(events) >= 2
        start_evt = events[0]
        done_evt = events[-1]
        assert start_evt["type"] == "delegation_start"
        assert start_evt["department"] == "communication"
        assert start_evt["agent_name"] == "Communications Dispatch"
        assert done_evt["type"] == "delegation_done"
        assert done_evt["status"] == "done"
        assert done_evt["run_id"] == start_evt["run_id"]

        # 2. Test execution for all other departments
        all_departments = ["coding", "research", "operations", "productivity", "creative", "hr", "utility"]
        for dept in all_departments:
            events.clear()
            dept_res = await svc.execute_task(dept, f"Execute domain mission for {dept}", emit=mock_emit)
            assert dept_res["ok"] is True
            assert events[0]["type"] == "delegation_start"
            assert events[0]["department"] == dept
            assert events[-1]["type"] == "delegation_done"
            assert events[-1]["status"] == "done"

        # 3. Test asynchronous background start
        events.clear()
        run_id = await svc.start("coding", "Implement backend feature", emit=mock_emit)
        assert run_id
        # Wait for background task to finish
        for _ in range(20):
            if any(e.get("type") == "delegation_done" for e in events):
                break
            await asyncio.sleep(0.05)

        bg_start = [e for e in events if e.get("type") == "delegation_start"]
        bg_done = [e for e in events if e.get("type") == "delegation_done"]
        assert len(bg_start) == 1
        assert len(bg_done) == 1
        assert bg_start[0]["run_id"] == run_id
        assert bg_done[0]["status"] == "done"



