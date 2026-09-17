"""Tests for automated Antigravity Coding Worker installation, setup, and status."""
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from zenith.main import app
from zenith.core.tools import _get_worker_url, _worker_get, _worker_post
from worker import agy, manage


@pytest.fixture
def client():
    return TestClient(app)


def test_api_worker_status_endpoint_online(client):
    """Verify /api/worker/status returns online schema when worker health succeeds."""
    mock_payload = {
        "status": "ok",
        "worker": "antigravity-agy",
        "version": "1.0.0",
        "agy_installed": True,
        "authenticated": True,
    }
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_payload
        resp = client.get("/api/worker/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["online"] is True
        assert data["agy_installed"] is True
        assert data["authenticated"] is True
        assert "worker_url" in data


def test_api_worker_status_endpoint_offline(client):
    """Verify /api/worker/status gracefully handles unreachable worker with diagnostics."""
    with patch("zenith.core.tools._worker_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = ConnectionRefusedError("Connection refused on port 8022")
        resp = client.get("/api/worker/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["online"] is False
        assert data["agy_installed"] is False
        assert "Connection refused" in data["error"]
        assert "setup-worker" in data["help"]


def test_worker_url_resolution(monkeypatch):
    """Verify _get_worker_url respects WORKER_URL env var or container defaults."""
    monkeypatch.setenv("WORKER_URL", "http://custom-host:9999")
    assert _get_worker_url() == "http://custom-host:9999"

    monkeypatch.delenv("WORKER_URL", raising=False)
    # On host (no /.dockerenv), should return 127.0.0.1:8022
    url = _get_worker_url()
    assert url in ("http://127.0.0.1:8022", "http://host.docker.internal:8022")


def test_agy_check_auth_status():
    """Verify agy.check_auth_status structure."""
    res = agy.check_auth_status()
    assert isinstance(res, dict)
    assert "installed" in res
    assert "authenticated" in res
    assert "model" in res


def test_worker_manage_helpers():
    """Verify worker.manage helper functions."""
    assert isinstance(manage.is_worker_alive(), bool)
    py = manage.resolve_python()
    assert os.path.exists(py)
