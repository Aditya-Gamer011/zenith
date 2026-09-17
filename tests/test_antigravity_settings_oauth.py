"""Tests for Antigravity Settings OAuth Integration and God's Eye View static serving."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from zenith.main import app
from zenith.core.config import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_integration_status_includes_antigravity(client):
    """Verify /api/integrations/status includes antigravity fields."""
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "status": "ok",
            "worker": "antigravity-agy",
            "agy": {
                "installed": True,
                "authenticated": True,
                "model": "gemini-3.1-pro-high",
            }
        }
        resp = client.get("/api/integrations/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "antigravity_configured" in data
        assert data["antigravity_configured"] is True
        assert data["antigravity_worker"]["online"] is True
        assert data["antigravity_worker"]["authenticated"] is True


def test_antigravity_authorize_already_authenticated(client):
    """Verify /api/integrations/antigravity/authorize when already authenticated."""
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "status": "ok",
            "agy": {"authenticated": True}
        }
        resp = client.post("/api/integrations/antigravity/authorize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["already_authenticated"] is True


def test_antigravity_authorize_initiates_login(client):
    """Verify /api/integrations/antigravity/authorize initiates login when not authenticated."""
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get, \
         patch("zenith.core.tools._worker_post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = {"status": "ok", "agy": {"authenticated": False}}
        mock_post.return_value = {
            "ok": True,
            "status": "initiated",
            "message": "Google OAuth prompt initiated.",
            "cli_command": "python -m worker.manage login"
        }
        resp = client.post("/api/integrations/antigravity/authorize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "initiated"
        assert "cli_command" in data


def test_antigravity_disconnect(client):
    """Verify /api/integrations/antigravity/disconnect clears tokens."""
    with patch("zenith.core.tools._worker_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"ok": True, "status": "logged_out"}
        resp = client.post("/api/integrations/antigravity/disconnect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


def test_gev_static_serving_root(client):
    """Verify /gev and /gev/ serve the static index.html with SAMEORIGIN headers."""
    resp = client.get("/gev")
    assert resp.status_code == 200
    assert "God's Eye View" in resp.text
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "frame-ancestors" in resp.headers.get("Content-Security-Policy", "")


def test_gev_static_serving_assets(client):
    """Verify /gev/cesium/Cesium.js or assets serve with HTTP 200."""
    resp = client.get("/gev/cesium/Cesium.js")
    assert resp.status_code == 200
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_gev_api_proxy_fallback(client):
    """Verify /api/celestrak returns valid upstream or fallback response rather than crashing with 502/503."""
    import httpx
    mock_resp = httpx.Response(200, content=b"1 25544U 98067A   24001.00000000 ...", headers={"content-type": "text/plain"})
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        resp = client.get("/api/celestrak?GROUP=active&FORMAT=tle")
        assert resp.status_code in (200, 400, 404)

