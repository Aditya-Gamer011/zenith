"""Tests for Zenith Setup & Secrets Management Engine."""
import pytest
from fastapi.testclient import TestClient

from zenith.core import config, setup
from zenith.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_setup_status_endpoint(client):
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "setup_completed" in data
    assert "has_gemini_key" in data
    assert "user_name" in data
    assert "auth_mode" in data


def test_setup_config_catalog(client):
    resp = client.get("/api/setup/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "catalog" in data
    catalog = data["catalog"]
    assert len(catalog) >= 10

    # Verify Gemini API key entry
    gemini_entry = next((item for item in catalog if item["key"] == "GEMINI_API_KEY"), None)
    assert gemini_entry is not None
    assert gemini_entry["required"] is True
    assert gemini_entry["is_secret"] is True
    assert "aistudio.google.com" in gemini_entry["where_to_get_url"]
    assert len(gemini_entry["guide_steps"]) > 0

    # Ensure secrets are NEVER leaked in value attribute
    for item in catalog:
        if item["is_secret"]:
            assert item["value"] == "", f"Secret {item['key']} leaked in value field!"
            if item["is_set"]:
                assert "..." in item["current_display"] or "•" in item["current_display"]


def test_setup_test_key_validation(client):
    # Empty key should return valid: false
    resp = client.post("/api/setup/test-key", json={"gemini_api_key": ""})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False

    # Bogus key should return valid: false with error
    resp_bogus = client.post("/api/setup/test-key", json={"gemini_api_key": "AIzaSyFakeKeyInvalid123456789"})
    assert resp_bogus.status_code == 200
    assert resp_bogus.json()["valid"] is False
    assert "error" in resp_bogus.json()


def test_save_configuration_requires_gemini_key(client, monkeypatch):
    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    resp = client.post("/api/setup/save", json={"updates": {"USER_NAME": "Tester"}})
    assert resp.status_code == 400
    assert "required" in resp.json()["error"].lower()


def test_save_configuration_success(client, tmp_path, monkeypatch):
    test_env = tmp_path / ".env"
    monkeypatch.setattr(setup, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    updates = {
        "GEMINI_API_KEY": "AIzaSyTestValidFormatKey12345",
        "USER_NAME": "Alex Rivera",
        "USER_EMAIL": "alex@example.com",
        "AUTH_MODE": "none",
    }
    resp = client.post("/api/setup/save", json={"updates": updates})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["setup_completed"] is True
    assert data["user_name"] == "Alex Rivera"

    # Verify .env was written
    assert test_env.is_file()
    content = test_env.read_text()
    assert "GEMINI_API_KEY=AIzaSyTestValidFormatKey12345" in content
    assert 'USER_NAME="Alex Rivera"' in content or 'USER_NAME=Alex Rivera' in content
    assert "ZENITH_SETUP_COMPLETED=true" in content
