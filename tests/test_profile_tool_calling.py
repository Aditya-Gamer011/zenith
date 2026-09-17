import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from zenith.main import app
from zenith.core.config import settings
from zenith.core import orchestrator, provider
from zenith.tools.ui_customizer import update_user_profile
from zenith.memory import store


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.anyio
async def test_update_user_profile_sets_name_and_memory():
    """update_user_profile should update in-memory settings, memory store, and return confirmation."""
    res = await update_user_profile(name="Aditya")
    assert "✓ Profile updated successfully" in res
    assert settings.user_name == "Aditya"

    # Verify memory store
    store.init_db()
    with store._connect() as conn:
        row = conn.execute("SELECT value FROM memories WHERE category = 'user' AND key = 'name'").fetchone()
        assert row and row[0] == "Aditya"


def test_api_auth_me_returns_current_name(client):
    """GET /api/auth/me should return settings.user_name."""
    settings.user_name = "Aditya"
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["user"]["name"] == "Aditya"


@pytest.mark.anyio
async def test_orchestrator_active_profile_intent_guard():
    """If model produces conversational apology without tool call, orchestrator should auto-invoke update_user_profile."""
    orch = orchestrator.Orchestrator()

    # Mock provider returning conversational reply without any tool calls
    async def mock_stream(*args, **kwargs):
        yield {"type": "text", "text": "I am so sorry about that, Aditya. Let me update your user profile right away so your name displays correctly everywhere."}
        yield {"type": "done", "model": "gemini-test"}

    emitted = []
    async def mock_emit(evt):
        emitted.append(evt)

    settings.user_name = "Maya"
    with patch.object(provider, "PROVIDER_MODE", "gemini"):
        with patch.object(provider, "chat_stream", side_effect=mock_stream):
            reply = await orch.handle("the dashboard still says maya...pls fix (call me Aditya instead)", emit=mock_emit)

            # Assert orchestrator invoked update_user_profile
            assert any(e.get("name") == "update_user_profile" for e in emitted)
            assert settings.user_name == "Aditya"
            assert "Aditya" in reply
