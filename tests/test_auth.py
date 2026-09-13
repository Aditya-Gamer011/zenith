"""Zenith — Zero-Auth Standalone & Open Access Integration Tests."""
import pytest
from fastapi.testclient import TestClient

from zenith.core import auth, config
from zenith.main import app


@pytest.fixture(autouse=True)
def ensure_none_auth_mode(monkeypatch):
    monkeypatch.setattr(config.settings, "auth_mode", "none")


@pytest.fixture
def client():
    return TestClient(app)


def test_pkce_generation():
    verifier, challenge = auth.generate_pkce()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    assert verifier != challenge


def test_oauth_state_sealing():
    payload = {"s": "test_csrf_token", "v": "test_verifier", "r": "/dashboard"}
    sealed = auth.seal_oauth_state(payload)
    assert isinstance(sealed, str)
    assert "." in sealed

    unsealed = auth.unseal_oauth_state(sealed)
    assert unsealed is not None
    assert unsealed["s"] == "test_csrf_token"
    assert unsealed["v"] == "test_verifier"
    assert unsealed["r"] == "/dashboard"

    # Tampered signature should fail
    tampered = sealed[:-3] + "xyz"
    assert auth.unseal_oauth_state(tampered) is None


def test_jwt_session_lifecycle():
    user_data = {
        "id": "usr_99812",
        "email": "user@example.com",
        "username": "user",
        "name": "Friend",
    }
    token = auth.create_session_token(user_data, expires_sec=3600)
    assert token is not None

    decoded = auth.verify_session_token(token)
    assert decoded is not None
    assert decoded["sub"] == "usr_99812"
    assert decoded["email"] == "user@example.com"
    assert decoded["name"] == "Friend"

    # Expired token
    expired_token = auth.create_session_token(user_data, expires_sec=-10)
    assert auth.verify_session_token(expired_token) is None


def test_zero_auth_open_endpoints(client):
    """Verify that in the general version all endpoints are fully open with zero login friction."""
    # 1. Health check is accessible
    r_health = client.get("/api/health")
    assert r_health.status_code == 200

    # 2. Auth me returns authenticated owner claims directly
    r_auth_me = client.get("/api/auth/me")
    assert r_auth_me.status_code == 200
    data = r_auth_me.json()
    assert data["authenticated"] is True
    assert data["is_superadmin"] is True
    assert data["user"]["role"] == "owner"
    assert "error" not in data

    # 3. State and tools APIs are accessible without any session cookie or token
    r_state = client.get("/api/state")
    assert r_state.status_code == 200

    r_tools = client.get("/api/tools")
    assert r_tools.status_code == 200
    assert "tools" in r_tools.json()


def test_zero_auth_websocket_access(client):
    """Verify that WebSockets connect without requiring session cookies or tokens."""
    with client.websocket_connect("/ws/chat") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "status"
        assert msg["message"] == "connected"


def test_auth_routes_redirection(client):
    """Verify that login and callback routes redirect smoothly to root."""
    # 1. /auth/login redirects to /
    r_login = client.get("/auth/login", follow_redirects=False)
    assert r_login.status_code == 302
    assert r_login.headers["location"] == "/"

    # 2. /auth/callback redirects to /
    r_cb = client.get("/auth/callback", follow_redirects=False)
    assert r_cb.status_code == 302
    assert r_cb.headers["location"] == "/"

    # 3. /auth/logout redirects to /
    r_logout = client.get("/auth/logout", follow_redirects=False)
    assert r_logout.status_code == 302
    assert r_logout.headers["location"] == "/"

    # 4. POST /api/auth/logout succeeds
    r_api_logout = client.post("/api/auth/logout")
    assert r_api_logout.status_code == 200
    assert r_api_logout.json()["ok"] is True

    # 5. /api/auth/config returns none
    r_cfg = client.get("/api/auth/config")
    assert r_cfg.status_code == 200
    assert r_cfg.json()["auth_mode"] == "none"

    # 6. /api/auth/exchange returns owner claims
    r_exch = client.post("/api/auth/exchange")
    assert r_exch.status_code == 200
    assert r_exch.json()["ok"] is True
    assert r_exch.json()["user"]["role"] == "owner"
