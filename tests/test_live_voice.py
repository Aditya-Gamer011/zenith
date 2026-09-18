"""Tests for Gemini Live voice plane, model configurations, schema sanitization,
barge-in interruption handling, and WebSocket streaming.
"""
from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from zenith.main import app
from zenith.voice import live


@pytest.fixture
def client():
    return TestClient(app)


def test_live_voice_available_and_defaults():
    """Verify live voice availability and fallback model ordering."""
    assert live.available() is True
    with patch.object(live, "LIVE_MODELS", [m.strip() for m in live._DEFAULT_LIVE_MODELS.split(",") if m.strip()]):
        models = live.configured_models()
        assert len(models) >= 4
        assert models[0] == "gemini-3.8-live-extended-thinking"
        assert models[1] == "gemini-3.8-live"
        assert models[2] == "gemini-3.1-flash-live-preview"
        assert models[3] == "gemini-2.5-flash-native-audio-latest"
    assert live.LIVE_VOICE_NAME == "Aoede"


def test_strip_conversational_cliches():
    """Verify snag-related conversational filler is cleanly stripped."""
    t1 = "All done, Aditya! The file was created. Let me know if there are any snags."
    assert live.strip_conversational_cliches(t1) == "All done, Aditya! The file was created."

    t2 = "Done! If you run into any snags, let me know."
    assert live.strip_conversational_cliches(t2) == "Done!"

    t3 = "I've deployed the site. Feel free to reach out if you hit any snags."
    assert live.strip_conversational_cliches(t3) == "I've deployed the site."

    t4 = "All set, Aditya! Leme know if there are any snags."
    assert live.strip_conversational_cliches(t4) == "All set, Aditya!"


def test_sanitize_tools_supports_non_blocking():
    """Verify non_blocking flag adds behavior: NON_BLOCKING to tool declarations."""
    specs = [{"type": "function", "function": {"name": "test_cmd", "description": "test", "parameters": {"type": "object", "properties": {}}}}]
    clean_blocking = live._sanitize_tools(specs, non_blocking=False)
    assert "behavior" not in clean_blocking[0]["function"]

    clean_non_blocking = live._sanitize_tools(specs, non_blocking=True)
    assert clean_non_blocking[0]["function"].get("behavior") == "NON_BLOCKING"


def test_schema_sanitizer_removes_empty_enums_and_fixes_types():
    """Sanitizer must eliminate empty strings from enums and supply missing items/props."""
    schema = {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "enum": ["", "markdown", "pdf", ""],
            },
            "empty_enum": {
                "type": "string",
                "enum": ["", ""],
            },
            "tags": {
                "type": "array",
                # missing items
            },
            "nested_obj": {
                "type": "object",
                # missing properties
            },
            "nested_list": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["", "tech", "art"],
                        }
                    }
                }
            }
        }
    }

    live._sanitize_schema(schema)

    # Empty string stripped, valid strings preserved
    assert schema["properties"]["format"]["enum"] == ["markdown", "pdf"]
    # If all items were empty, enum key is removed entirely
    assert "enum" not in schema["properties"]["empty_enum"]
    # Missing array items defaulted
    assert schema["properties"]["tags"]["items"] == {"type": "string"}
    # Missing object properties defaulted
    assert schema["properties"]["nested_obj"]["properties"] == {}
    # Nested schemas recursively sanitized
    assert schema["properties"]["nested_list"]["items"]["properties"]["category"]["enum"] == ["tech", "art"]


def test_first_msg_config_for_standard_and_thinking_models():
    """Test setup message generationConfig for gemini-3.8-live and thinking models."""
    msg_standard = live._first_msg("gemini-3.8-live", system_instruction="You are Zenith.")
    setup_std = msg_standard["setup"]
    assert setup_std["model"] == "models/gemini-3.8-live"
    assert setup_std["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert "thinkingConfig" not in setup_std["generationConfig"]
    assert "You are Zenith." in setup_std["systemInstruction"]["parts"][0]["text"]
    assert "Spoken Voice & Execution Directives" in setup_std["systemInstruction"]["parts"][0]["text"]

    # Extended thinking model requires thinkingConfig with thinkingLevel: HIGH
    msg_thinking = live._first_msg("gemini-3.8-live-extended-thinking", system_instruction="You are Zenith.")
    setup_thk = msg_thinking["setup"]
    assert setup_thk["model"] == "models/gemini-3.8-live-extended-thinking"
    assert setup_thk["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "HIGH"}
    assert setup_thk["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Aoede"


@pytest.mark.anyio
async def test_live_session_interrupt_resets_pending_tools():
    """session.interrupt() resets pending tool execution counter."""
    session = live.LiveSession()
    session._pending_tools = 5
    await session.interrupt()
    assert session._pending_tools == 0


@pytest.mark.anyio
async def test_live_session_tool_handling_sends_turn_complete_for_gemini_38():
    """Gemini 3.8 models require clientContent.turnComplete: True after toolResponse."""
    session = live.LiveSession()
    session.model = "gemini-3.8-live"
    mock_ws = AsyncMock()
    session.ws = mock_ws

    fc = {
        "id": "call_123",
        "name": "test_tool",
        "args": {"param": "val"}
    }

    with patch("zenith.core.tools.call_tool", new_callable=AsyncMock) as mock_tool:
        mock_tool.return_value = {"result": "tool executed successfully"}
        await session._handle_tool_calls(fc)

    assert mock_ws.send.call_count == 2
    tool_resp_raw = mock_ws.send.call_args_list[0][0][0]
    turn_complete_raw = mock_ws.send.call_args_list[1][0][0]

    tool_resp = json.loads(tool_resp_raw)
    assert tool_resp["toolResponse"]["functionResponses"][0]["id"] == "call_123"
    assert tool_resp["toolResponse"]["functionResponses"][0]["response"]["result"] == "tool executed successfully"

    turn_complete = json.loads(turn_complete_raw)
    assert turn_complete == {"clientContent": {"turnComplete": True}}


@pytest.mark.anyio
async def test_live_session_tool_handling_for_gemini_25():
    """Gemini 2.5 models only receive toolResponse without empty turnComplete."""
    session = live.LiveSession()
    session.model = "gemini-2.5-flash-native-audio-latest"
    mock_ws = AsyncMock()
    session.ws = mock_ws

    fc = {
        "id": "call_456",
        "name": "test_tool",
        "args": {}
    }

    with patch("zenith.core.tools.call_tool", new_callable=AsyncMock) as mock_tool:
        mock_tool.return_value = {"result": "ok"}
        await session._handle_tool_calls(fc)

    assert mock_ws.send.call_count == 1
    tool_resp = json.loads(mock_ws.send.call_args_list[0][0][0])
    assert tool_resp["toolResponse"]["functionResponses"][0]["id"] == "call_456"


@pytest.mark.anyio
async def test_live_session_events_stream_and_barge_in():
    """LiveSession.events yields audio, text, heard, interrupted, and suppresses interim done."""
    session = live.LiveSession()
    mock_ws = AsyncMock()
    session.ws = mock_ws

    audio_bytes = b"\x01\x02\x03\x04"
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    messages = [
        # Server detects barge-in
        json.dumps({"serverContent": {"interrupted": True}}),
        # User speech transcript
        json.dumps({"serverContent": {"inputTranscription": {"text": "hello zenith"}}}),
        # Audio packet
        json.dumps({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": audio_b64}}]}}}),
        # Model transcript
        json.dumps({"serverContent": {"outputTranscription": {"text": "greetings"}}}),
        # Interim turnComplete while pending tools > 0 (should be suppressed)
        json.dumps({"serverContent": {"turnComplete": True}}),
    ]

    async def mock_recv():
        if messages:
            return messages.pop(0)
        session._closed = True
        raise asyncio.CancelledError()

    mock_ws.recv.side_effect = mock_recv
    session._pending_tools = 1

    results = []
    try:
        async for evt in session.events():
            results.append(evt)
    except (asyncio.CancelledError, Exception):
        pass

    kinds = [r[0] for r in results]
    assert "interrupted" in kinds
    assert ("heard", "hello zenith") in results
    assert ("audio", audio_bytes) in results
    assert ("text", "greetings") in results
    # Interim "done" was suppressed because _pending_tools was 1
    assert "done" not in kinds


def test_ws_live_endpoint_barge_in_and_ready(client):
    """WebSocket /ws/live emits ready with model and processes barge_in messages."""
    mock_session = MagicMock()
    mock_session.model = "gemini-3.8-live"
    mock_session.interrupt = AsyncMock()
    mock_session.end_turn = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.push_audio = AsyncMock()

    mock_session.open = AsyncMock(return_value=None)

    async def mock_events():
        yield ("audio", b"\x00\x00")
        yield ("interrupted", None)

    mock_session.events = mock_events

    with patch("zenith.voice.live.LiveSession", return_value=mock_session):

        with client.websocket_connect("/ws/live") as ws:
            # 1. First message must be {"type": "ready", "model": "gemini-3.8-live"}
            ready_msg = ws.receive_json()
            assert ready_msg["type"] == "ready"
            assert ready_msg["model"] == "gemini-3.8-live"

            # 2. Binary audio data
            binary_data = ws.receive_bytes()
            assert binary_data == b"\x00\x00"

            # 3. Interrupted signal
            interrupted_msg = ws.receive_json()
            assert interrupted_msg["type"] == "interrupted"

            # 4. Client sends barge_in frame
            ws.send_json({"type": "barge_in"})
            # Give a small moment for async task to process
            import time
            time.sleep(0.05)
            mock_session.interrupt.assert_awaited()


@pytest.mark.anyio
async def test_live_session_events_suppresses_intermediate_turn_complete_until_post_tool_speech():
    """LiveSession.events must suppress the intermediate turnComplete following tool execution
    and only yield 'done' after the post-tool spoken audio/turn completes."""
    session = live.LiveSession()
    mock_ws = AsyncMock()
    session.ws = mock_ws

    audio_bytes = b"\x05\x06\x07\x08"
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    messages = [
        # 1. Model requests a tool
        json.dumps({
            "toolCall": {
                "functionCalls": [{"id": "c1", "name": "time_now", "args": {}}]
            }
        }),
        # 2. Intermediate turnComplete closing the tool request
        json.dumps({"serverContent": {"turnComplete": True}}),
        # 3. Model speaks post-tool response
        json.dumps({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": audio_b64}}]}}}),
        json.dumps({"serverContent": {"outputTranscription": {"text": "It is 8:30 PM."}}}),
        # 4. Final turnComplete after spoken answer
        json.dumps({"serverContent": {"turnComplete": True}}),
    ]

    async def mock_recv():
        if messages:
            await asyncio.sleep(0.01)
            return messages.pop(0)
        session._closed = True
        raise asyncio.CancelledError()

    mock_ws.recv.side_effect = mock_recv

    results = []
    with patch("zenith.core.tools.call_tool", new_callable=AsyncMock) as mock_tool:
        mock_tool.return_value = {"result": "8:30 PM"}
        try:
            async for evt in session.events():
                results.append(evt)
        except (asyncio.CancelledError, Exception):
            pass

    # Two-Phase Protocol verification:
    # 1. Acknowledgment text & audio emitted FIRST
    assert results[0][0] == "text"
    assert "on it" in results[0][1].lower()
    assert any(r[0] == "audio" for r in results)
    # 2. Tool executed
    assert any(r[0] == "tool" for r in results)
    # 3. Post-tool speech delivered before done
    assert results[-1] == ("done", None)
    assert ("audio", audio_bytes) in results
    assert ("text", "It is 8:30 PM.") in results


def test_classify_ack_and_pcm_cache():
    """Verify acknowledgment classifier maps departments and tools correctly."""
    from zenith.voice.live import classify_ack, get_ack_audio_pcm
    tag, text = classify_ack([{"name": "delegate_task", "args": {"department": "research"}}])
    assert tag == "research"
    assert "research" in text.lower()
    pcm = get_ack_audio_pcm("research")
    assert len(pcm) > 1000

    tag, text = classify_ack([{"name": "delegate_task", "args": {"department": "coding"}}])
    assert tag == "coding"
    assert "coding" in text.lower()

    tag, text = classify_ack([{"name": "delegate_pipeline", "args": {}}])
    assert tag == "pipeline"

    tag, text = classify_ack([{"name": "agent_submit", "args": {}}])
    assert tag == "worker"

    tag, text = classify_ack([{"name": "ha_switch", "args": {}}])
    assert tag == "smart_home"


@pytest.mark.anyio
async def test_live_session_concurrent_multi_tool_execution():
    """LiveSession._handle_tool_calls batches multiple functionCalls concurrently."""
    session = live.LiveSession()
    session.model = "gemini-3.8-live"
    mock_ws = AsyncMock()
    session.ws = mock_ws

    calls = [
        {"id": "call_a", "name": "tool_a", "args": {"x": 1}},
        {"id": "call_b", "name": "tool_b", "args": {"y": 2}},
    ]

    async def fake_call(name, args):
        return {"result": f"res_{name}"}

    with patch("zenith.core.tools.call_tool", side_effect=fake_call):
        session._pending_tools = 2
        await session._handle_tool_calls(calls)

    assert session._pending_tools == 0
    assert mock_ws.send.call_count == 2

    # First send is batched toolResponse
    tool_resp = json.loads(mock_ws.send.call_args_list[0][0][0])
    responses = tool_resp["toolResponse"]["functionResponses"]
    assert len(responses) == 2
    assert responses[0]["id"] == "call_a"
    assert responses[0]["response"]["result"] == "res_tool_a"
    assert responses[1]["id"] == "call_b"
    assert responses[1]["response"]["result"] == "res_tool_b"

    # Second send is clientContent turnComplete for 3.8
    turn_complete = json.loads(mock_ws.send.call_args_list[1][0][0])
    assert turn_complete == {"clientContent": {"turnComplete": True}}

