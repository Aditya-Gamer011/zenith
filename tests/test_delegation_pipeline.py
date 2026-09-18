"""Tests for Delegation Pipeline, Circular Peer Consultation Blocker, and Blackboard Artifact Discovery."""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from zenith.agents.agent_service import AgentService, current_agent_chain, current_agent_name
from zenith.core import tools as tool_reg
from zenith.memory import store
from zenith.tools.agent import (
    delegate_pipeline,
    ask_specialist,
    query_findings,
)


def _run(coro):
    return asyncio.run(coro)


def test_delegate_pipeline_registered():
    """Verify delegate_pipeline is registered and available to executive orchestrator."""
    assert "delegate_pipeline" in tool_reg.TOOLS
    assert "delegate_pipeline" in tool_reg.EXECUTIVE_TOOL_NAMES
    
    exec_cat = tool_reg.executive_catalog()
    tool_names = {t["function"]["name"] for t in exec_cat}
    assert "delegate_pipeline" in tool_names


def test_delegate_pipeline_sequential_execution():
    """Verify delegate_pipeline executes steps sequentially and forwards previous deliverables as context."""
    executed_steps = []

    async def mock_execute(dept, task, context="", emit=None, depth=0):
        executed_steps.append((dept, task, context))
        if dept == "creative":
            return {
                "ok": True,
                "agent": "Creative Lead",
                "tool_calls": 2,
                "result": "Created Kingdom of the Bears presentation at /presentation/bears-123",
            }
        elif dept == "communication":
            return {
                "ok": True,
                "agent": "Comms Specialist",
                "tool_calls": 1,
                "result": "Dispatched email to heyyitsmeaditya@gmail.com with presentation link.",
            }
        return {"ok": False, "error": "Unknown dept"}

    async def _test():
        with patch("zenith.tools.agent._get_service") as mock_get_svc:
            mock_svc = AsyncMock()
            mock_svc.execute_task = mock_execute
            mock_get_svc.return_value = mock_svc

            steps = [
                {"department": "creative", "task": "Generate presentation on bears"},
                {"department": "communication", "task": "Email the presentation link to user"},
            ]

            result = await delegate_pipeline(steps=steps, initial_context="User loves wildlife")

            assert len(executed_steps) == 2
            assert executed_steps[0][0] == "creative"
            assert executed_steps[1][0] == "communication"
            # Verify step 2 received deliverables from step 1
            assert "Created Kingdom of the Bears presentation" in executed_steps[1][2]
            assert "Sequential Pipeline Execution Summary" in result
            assert "Step 1: [Creative Lead] — ✅ Completed" in result
            assert "Step 2: [Comms Specialist] — ✅ Completed" in result

    _run(_test())


def test_circular_peer_consultation_blocked():
    """Verify circular consultation loops between agents are immediately halted."""
    svc = AgentService()

    async def _test():
        # Simulate creative currently consulting communication: chain = ('creative', 'communication')
        token_chain = current_agent_chain.set(("creative", "communication"))
        token_name = current_agent_name.set("communication")

        try:
            # communication attempts to ask creative (cycle detected!)
            result = await svc.execute_task("creative", "Where is the deck you made?")
            assert not result.get("ok")
            assert "Circular consultation blocked" in result.get("error", "")
            assert "already in the active consultation chain" in result.get("error", "")
        finally:
            current_agent_chain.reset(token_chain)
            current_agent_name.reset(token_name)

    _run(_test())


def test_query_findings_with_artifacts():
    """Verify query_findings discovers both blackboard entries and saved presentation/document artifacts."""
    store.init_db()

    # Save a test presentation artifact
    art_id = "test_bears_deck_123"
    store.save_artifact(
        artifact_id=art_id,
        artifact_type="presentation",
        title="Kingdom of the Bears",
        theme="nordic_navy",
        data_json={"slides": []},
        file_path="/tmp/zenith-files/bears.pptx",
        web_url="/presentation/test_bears_deck_123",
    )

    # Publish a blackboard item
    store.blackboard_publish(
        department="Creative",
        topic="Completed Mission: Bears Presentation",
        content="Deck created successfully.",
    )

    async def _test():
        result = await query_findings(query="bear")
        assert "Discovered Artifacts & Deliverables" in result
        assert "Kingdom of the Bears" in result
        assert "/presentation/test_bears_deck_123" in result
        assert "Organizational Blackboard" in result

    _run(_test())


def test_orchestrator_two_phase_acknowledgment_and_done():
    """Verify orchestrator emits 'I'm on it' first, executes delegated tasks, then confirms completion."""
    from zenith.core.orchestrator import Orchestrator
    from zenith.core.config import settings
    from zenith.core import provider

    orch = Orchestrator()
    settings.user_name = "Aditya"

    emitted_events = []

    async def mock_emit(evt):
        emitted_events.append(evt)

    # Round 1: Model calls delegate_task with no text
    round1 = [
        {"type": "tool_call", "index": 0, "function": {"name": "delegate_task", "arguments": '{"department": "research", "task": "Search AI trends"}'}}
    ]
    # Round 2: Model returns final report
    round2 = [
        {"type": "text", "text": "Here are the top AI trends for this week: Multimodal agents and on-device models."}
    ]

    stream_rounds = [round1, round2]

    async def mock_stream(*args, **kwargs):
        cur = stream_rounds.pop(0)
        for e in cur:
            yield e

    async def _test():
        with patch.object(provider, "PROVIDER_MODE", "gemini"):
            with patch.object(provider, "chat_stream", side_effect=mock_stream):
                with patch("zenith.core.tools.call_tool", new_callable=AsyncMock) as mock_call:
                    mock_call.return_value = {"ok": True, "result": "Research report: Found 5 papers."}
                    reply = await orch.handle("Research the latest AI trends", emit=mock_emit)

                    # 1. First reply: emitted 'ack' with "I'm on it" before tools ran
                    ack_events = [e for e in emitted_events if e.get("type") == "ack"]
                    assert len(ack_events) >= 1
                    assert "on it" in ack_events[0]["text"].lower()
                    assert "research" in ack_events[0]["text"].lower()

                    # 2. Tool executed
                    assert mock_call.called

                    # 3. Completion confirmed done
                    assert "all done" in reply.lower() or "done" in reply.lower()
                    assert "Multimodal agents" in reply
                    assert "I'm on it" in reply

    _run(_test())

