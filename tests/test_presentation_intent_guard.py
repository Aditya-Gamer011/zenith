"""Tests for Presentation Intent Guard & Asset Hallucination Interceptor."""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path
from zenith.core.orchestrator import Orchestrator
from zenith.core import provider
from zenith.memory import store


def _run(coro):
    return asyncio.run(coro)


def test_presentation_intent_guard_intercepts_recycled_cdn_link():
    """Verify that when a model tries to recycle an old CDN URL from turn 1 in turn 2,

    the Presentation Intent Guard intercepts, calls generate_presentation for the new topic,
    and replaces the old URL with the new presentation.
    """
    orch = Orchestrator()
    orch.restart()

    old_uuid = "01a0b5af-c5e7-79a4-8f20-d70706d7f26f"
    lions_cdn = f"https://cdn.hackclub.com/{old_uuid}/presentation_Lions_Monarchs_123.pptx"

    # Simulate turn 1 in history: lions presentation was generated and delivered
    orch.history.append({"role": "user", "content": "send me a ppt on lions", "ts": 1000.0})
    orch.history.append({
        "role": "assistant",
        "content": f"I'm on it!\n\n---\n\nAll done! Here is your presentation:\n- **[Download Presentation Deck (.pptx)]({lions_cdn})**",
        "ts": 1005.0,
    })

    # Save lions artifact in store as initial state
    store.save_artifact(
        artifact_id="deck_lions_123",
        artifact_type="presentation",
        title="Lions Monarchs",
        theme="editorial_slate",
        data_json="{}",
        file_path="/tmp/zenith-files/presentation_Lions_Monarchs_123.pptx",
        web_url="/presentation/deck_lions_123",
    )

    # In turn 2, user asks: "gimme a good ppt on fortnite"
    # The model attempts to hallucinate a text response that reuses the old CDN UUID without calling any tool
    hallucinated_fortnite_cdn = f"https://cdn.hackclub.com/{old_uuid}/presentation_Fortnite_Battle_Royale_456.pptx"

    async def mock_stream(tier, messages, tool_specs, max_tokens=1000):
        # Model returns text directly without tool calls, recycling the old UUID
        yield {
            "type": "text",
            "text": f"All done, Aditya! Here is your presentation:\n- **[Download Presentation Deck (.pptx)]({hallucinated_fortnite_cdn})**",
        }
        yield {"type": "done", "model": "gemini-test"}

    emitted_events = []

    async def mock_emit(evt):
        emitted_events.append(evt)

    async def _test():
        with patch.object(provider, "PROVIDER_MODE", "gemini"):
            with patch.object(provider, "chat_stream", side_effect=mock_stream):
                reply = await orch.handle("gimme a good ppt on fortnite", emit=mock_emit)

                # 1. Verify generate_presentation was invoked automatically by the guard
                tool_starts = [e for e in emitted_events if e.get("type") == "tool_start"]
                assert any(e.get("name") == "generate_presentation" for e in tool_starts)

                # 2. Verify the old recycled UUID was eliminated from the delivered reply
                assert old_uuid not in reply

                # 3. Verify the reply contains the new presentation download link
                assert "presentation_" in reply or "Download Presentation Deck" in reply
                assert "deck_" in reply or ".pptx" in reply

                # 4. Verify store's last generated artifact is now the new presentation, not lions
                last_art_id = store.get_last_generated_artifact_id()
                assert last_art_id != "deck_lions_123"
                assert "fortnite" in last_art_id.lower()

    _run(_test())


def test_presentation_intent_guard_triggers_on_uninvoked_presentation_request():
    """Verify that when user requests a presentation ('send me a ppt on cars') and model outputs text

    without calling tools, the guard generates the deck and provides deliverables.
    """
    orch = Orchestrator()
    orch.restart()

    async def mock_stream(tier, messages, tool_specs, max_tokens=1000):
        # Model just outputs conversational chatter without calling generate_presentation
        yield {"type": "text", "text": "I'm on it! I'm creating a presentation on cars for you right now."}
        yield {"type": "done", "model": "gemini-test"}

    emitted_events = []

    async def mock_emit(evt):
        emitted_events.append(evt)

    async def _test():
        with patch.object(provider, "PROVIDER_MODE", "gemini"):
            with patch.object(provider, "chat_stream", side_effect=mock_stream):
                reply = await orch.handle("send me a ppt on cars", emit=mock_emit)

                # Verify tool was called by the guard
                tool_starts = [e for e in emitted_events if e.get("type") == "tool_start"]
                assert any(e.get("name") == "generate_presentation" for e in tool_starts)

                # Verify deliverable link is present
                assert "Download Presentation Deck" in reply or ".pptx" in reply
                last_id = store.get_last_generated_artifact_id()
                assert "cars" in last_id.lower()

    _run(_test())
