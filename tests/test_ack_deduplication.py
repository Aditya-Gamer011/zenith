"""Tests for Acknowledgment and Streaming Deduplication in Zenith Orchestrator."""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from zenith.core.orchestrator import Orchestrator
from zenith.core import provider


def _run(coro):
    return asyncio.run(coro)


def test_make_dedup_emitter_suppresses_duplicate():
    """Verify _make_dedup_emitter filters out streamed text that repeats first_ack_text."""
    emitted = []

    async def base_emit(evt):
        emitted.append(evt)

    ack = "I'm on it, Aditya! I'm having our creative studio put together a designer-grade presentation on lions for you right now."
    dedup_emit, flush = Orchestrator._make_dedup_emitter(base_emit, ack)

    async def _test():
        # Round 2 model starts by repeating the acknowledgment in multiple streaming deltas
        await dedup_emit({"type": "text", "text": "I'm on it, Aditya! "})
        await dedup_emit({"type": "text", "text": "I'm having our creative studio put together a designer-grade presentation on lions for you right now. "})
        # Then outputs the actual round 2 report
        await dedup_emit({"type": "text", "text": "All done, Aditya! The presentation is ready."})
        await flush()

    _run(_test())

    # Only the non-duplicate completion report should be emitted
    text_chunks = [e["text"] for e in emitted if e.get("type") == "text"]
    full_emitted = "".join(text_chunks)
    assert "All done, Aditya! The presentation is ready." in full_emitted
    assert full_emitted.count("I'm on it, Aditya!") == 0


def test_make_dedup_emitter_flushes_immediately_on_non_duplicate():
    """Verify _make_dedup_emitter passes through text immediately when it does not repeat first_ack_text."""
    emitted = []

    async def base_emit(evt):
        emitted.append(evt)

    ack = "I'm on it, Aditya! Putting together a presentation on lions for you right now."
    dedup_emit, flush = Orchestrator._make_dedup_emitter(base_emit, ack)

    async def _test():
        await dedup_emit({"type": "text", "text": "All done, Aditya!"})
        await dedup_emit({"type": "text", "text": " Here is your deck."})
        await flush()

    _run(_test())

    text_chunks = [e["text"] for e in emitted if e.get("type") == "text"]
    assert "".join(text_chunks) == "All done, Aditya! Here is your deck."


def test_orchestrator_handle_deduplicates_ack_when_model_repeats_it():
    """Full Orchestrator.handle test: round 1 promises and calls tool, round 2 repeats ack before reporting completion."""
    orch = Orchestrator()
    orch.restart()

    round_count = 0
    ack_phrase = "I'm on it, Aditya! I'm having our creative studio put together a designer-grade presentation on lions for you right now."

    async def mock_stream(tier, messages, tool_specs, max_tokens=1000):
        nonlocal round_count
        round_count += 1
        if round_count == 1:
            # Round 1: Model streams the acknowledgment and calls generate_presentation
            yield {"type": "text", "text": ack_phrase}
            yield {
                "type": "tool_call",
                "index": 0,
                "function": {
                    "name": "generate_presentation",
                    "arguments": '{"topic": "lions"}',
                },
            }
            yield {"type": "done", "model": "gemini-test"}
        else:
            # Round 2: Model erroneously begins by repeating the acknowledgment before giving the final report
            yield {"type": "text", "text": f"{ack_phrase}\n\nAll done, Aditya! Here is your presentation on lions."}
            yield {"type": "done", "model": "gemini-test"}

    emitted_events = []

    async def mock_emit(evt):
        emitted_events.append(evt)

    async def _test():
        with patch.object(provider, "PROVIDER_MODE", "gemini"):
            with patch.object(provider, "chat_stream", side_effect=mock_stream):
                with patch("zenith.core.tools.call_tool", new_callable=AsyncMock) as mock_call:
                    mock_call.return_value = {"ok": True, "result": "Created presentation at /tmp/lions.pptx"}
                    reply = await orch.handle("send me a ppt on lions", emit=mock_emit)

                    # 1. Verify ack event was emitted exactly once
                    ack_events = [e for e in emitted_events if e.get("type") == "ack"]
                    assert len(ack_events) == 1
                    assert ack_events[0]["text"] == ack_phrase

                    # 2. Verify streaming text events did NOT repeat ack_phrase in Round 2
                    streamed_texts = [e["text"] for e in emitted_events if e.get("type") == "text"]
                    round2_streamed = "".join(streamed_texts[1:])  # texts after round 1
                    assert ack_phrase not in round2_streamed
                    assert "All done, Aditya!" in round2_streamed

                    # 3. Verify final combined reply has ack_phrase exactly once at the beginning
                    assert reply.count(ack_phrase) == 1
                    assert reply.startswith(ack_phrase)
                    assert "\n\n---\n\n" in reply
                    assert "All done, Aditya!" in reply

    _run(_test())


def test_raw_ack_repeated_lines_cleaned():
    """Verify that if model produces duplicate acknowledgment lines in round 1, orchestrator cleans it to a single line."""
    orch = Orchestrator()
    orch.restart()

    round_count = 0
    ack_phrase = "I'm on it, Aditya! Putting together a presentation on lions for you right now."

    async def mock_stream(tier, messages, tool_specs, max_tokens=1000):
        nonlocal round_count
        round_count += 1
        if round_count == 1:
            # Model generated the line twice in round 1
            yield {"type": "text", "text": f"{ack_phrase}\n\n{ack_phrase}"}
            yield {
                "type": "tool_call",
                "index": 0,
                "function": {
                    "name": "generate_presentation",
                    "arguments": '{"topic": "lions"}',
                },
            }
            yield {"type": "done", "model": "gemini-test"}
        else:
            yield {"type": "text", "text": "All done, Aditya! Here is your presentation on lions."}
            yield {"type": "done", "model": "gemini-test"}

    emitted_events = []

    async def mock_emit(evt):
        emitted_events.append(evt)

    async def _test():
        with patch.object(provider, "PROVIDER_MODE", "gemini"):
            with patch.object(provider, "chat_stream", side_effect=mock_stream):
                with patch("zenith.core.tools.call_tool", new_callable=AsyncMock) as mock_call:
                    mock_call.return_value = {"ok": True, "result": "Created presentation at /tmp/lions.pptx"}
                    reply = await orch.handle("send me a ppt on lions", emit=mock_emit)

                    ack_events = [e for e in emitted_events if e.get("type") == "ack"]
                    assert len(ack_events) == 1
                    # Acknowledgment event must contain the phrase once, not duplicated
                    assert ack_events[0]["text"] == ack_phrase
                    # Final reply must also only have it once
                    assert reply.count(ack_phrase) == 1

    _run(_test())


def test_raw_ack_repeated_inline_sentences_and_round2_ack_only():
    """Verify that if model produces duplicate acknowledgment sentences inline without newlines,

    and in round 2 emits only the acknowledgment, deduplication ensures the line is stated only once.
    """
    orch = Orchestrator()
    orch.restart()

    round_count = 0
    ack_phrase = "I'm on it, Aditya! I'm having our creative studio put together a designer-grade presentation on lions for you right now."

    async def mock_stream(tier, messages, tool_specs, max_tokens=1000):
        nonlocal round_count
        round_count += 1
        if round_count == 1:
            # Model generated the line twice inline in round 1
            yield {"type": "text", "text": f"{ack_phrase} {ack_phrase}"}
            yield {
                "type": "tool_call",
                "index": 0,
                "function": {
                    "name": "generate_presentation",
                    "arguments": '{"topic": "lions"}',
                },
            }
            yield {"type": "done", "model": "gemini-test"}
        else:
            # Round 2 only emits the ack
            yield {"type": "text", "text": ack_phrase}
            yield {"type": "done", "model": "gemini-test"}

    emitted_events = []

    async def mock_emit(evt):
        emitted_events.append(evt)

    async def _test():
        with patch.object(provider, "PROVIDER_MODE", "gemini"):
            with patch.object(provider, "chat_stream", side_effect=mock_stream):
                with patch("zenith.core.tools.call_tool", new_callable=AsyncMock) as mock_call:
                    mock_call.return_value = {"ok": True, "result": "Created presentation at /tmp/lions.pptx"}
                    reply = await orch.handle("send me a ppt on lions", emit=mock_emit)

                    ack_events = [e for e in emitted_events if e.get("type") == "ack"]
                    assert len(ack_events) == 1
                    assert ack_events[0]["text"] == ack_phrase
                    assert reply.count(ack_phrase) == 1

    _run(_test())


