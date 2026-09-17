import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from zenith.main import app, _active_chat_turns
from zenith.core import orchestrator, provider


@pytest.fixture
def client():
    return TestClient(app)


def test_api_chat_stop_cancels_active_turns(client):
    """Test that POST /api/chat/stop cancels pending tasks in _active_chat_turns."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def dummy_coro():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    task = loop.create_task(dummy_coro())
    _active_chat_turns.add(task)

    try:
        res = client.post("/api/chat/stop")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["stopped"] >= 1
        assert getattr(task, "cancelling", lambda: 0)() > 0 or task.cancelled()
    finally:
        _active_chat_turns.discard(task)
        try:
            loop.run_until_complete(asyncio.sleep(0))
        except Exception:
            pass
        loop.close()


def test_operating_layer_mem0_and_blocklist_hidden():
    """Verify that Mem0 tab/pane and blocklist apps are removed from static/index.html."""
    with open("static/index.html") as f:
        html = f.read()

    assert 'data-tab="ctx-memory"' not in html
    assert 'id="pane-ctx-memory"' not in html
    assert 'id="ctx-blocklist-apps"' not in html
    assert 'Protected Applications Blocklist' not in html


@pytest.mark.anyio
async def test_orchestrator_antigravity_fallback_to_direct_stream():
    """When chat_stream_antigravity fails, orchestrator should fall back to chat_stream."""
    orch = orchestrator.Orchestrator()

    async def mock_antigravity_fail(*args, **kwargs):
        yield {"type": "error", "error": "worker_failed", "detail": "connection refused"}

    async def mock_direct_success(*args, **kwargs):
        yield {"type": "text", "text": "Hello from direct stream!"}
        yield {"type": "done", "model": "gemini-direct"}

    with patch.object(provider, "PROVIDER_MODE", "antigravity"):
        with patch.object(provider, "chat_stream_antigravity", side_effect=mock_antigravity_fail):
            with patch.object(provider, "chat_stream", side_effect=mock_direct_success):
                emitted = []
                async def mock_emit(evt):
                    emitted.append(evt)

                res = await orch.handle("test prompt", emit=mock_emit)
                assert "Hello from direct stream!" in res
                assert any(e.get("type") == "provider_fallback" for e in emitted)
