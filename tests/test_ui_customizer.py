import pytest
from fastapi.testclient import TestClient
from zenith.main import app
from zenith.core import config, tools, prompts
from zenith.tools import ui_customizer


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "auth_mode", "none")
    test_css = tmp_path / "custom_theme.css"
    monkeypatch.setattr(ui_customizer, "CUSTOM_CSS_PATH", test_css)
    config.settings.zenith_mode = "setup"


@pytest.mark.anyio
async def test_mode_switching_and_aliases():
    res = await ui_customizer.switch_mode("sovereign", "Testing switch")
    assert "Sovereign Mode" in res
    assert config.settings.zenith_mode == "sovereign"

    info = ui_customizer.get_current_mode()
    assert info["mode"] == "sovereign"

    # Switch to setup with alias
    res2 = await ui_customizer.switch_mode("starter")
    assert "Setup Mode" in res2
    assert config.settings.zenith_mode == "setup"

    # Switch with genesis alias
    res3 = await ui_customizer.switch_mode("genesis")
    assert "Setup Mode" in res3
    assert config.settings.zenith_mode == "setup"


@pytest.mark.anyio
async def test_dynamic_prompt_mode_reflection():
    config.settings.zenith_mode = "setup"
    prompt_setup = prompts.build_system_prompt()
    assert "Setup Mode" in prompt_setup
    assert "starter companion" in prompt_setup.lower()

    config.settings.zenith_mode = "sovereign"
    prompt_sovereign = prompts.build_system_prompt()
    assert "Sovereign Mode" in prompt_sovereign
    assert "autonomous engineering" in prompt_sovereign.lower()


@pytest.mark.anyio
async def test_user_profile_and_secret_update(monkeypatch):
    monkeypatch.setattr("zenith.core.setup.save_configuration", lambda updates: {"ok": True, "saved": list(updates.keys())})
    monkeypatch.setattr("zenith.memory.store.save_memory", lambda *args, **kwargs: None)

    res = await ui_customizer.update_user_profile(name="Sam", email="sam@example.com", bio="AI researcher")
    assert "Profile updated successfully" in res
    assert config.settings.user_name == "Sam"
    assert config.settings.user_email == "sam@example.com"
    assert config.settings.user_bio == "AI researcher"

    secret_res = await ui_customizer.setup_secret("RESEND_API_KEY", "re_test_1234567890abcdef")
    assert "Successfully configured RESEND_API_KEY" in secret_res


@pytest.mark.anyio
async def test_ui_theme_customization_and_reset():
    res = await ui_customizer.ui_customize_theme(
        accent_color="#10b981",
        font="Outfit",
        custom_css="body { background: #000; }"
    )
    assert "UI theme updated instantly" in res

    inspect_text = await ui_customizer.ui_inspect()
    assert "#10b981" in inspect_text
    assert "Outfit" in inspect_text

    reset_res = await ui_customizer.ui_reset_theme()
    assert "reset to Zenith default" in reset_res


@pytest.mark.anyio
async def test_tools_execution_via_core_tools():
    res = await tools.call_tool("switch_mode", {"mode": "sovereign", "reason": "test"})
    assert res["ok"] is True
    assert "Sovereign Mode" in res["result"]

    res_mode = await tools.call_tool("get_mode", {})
    assert res_mode["ok"] is True
    assert "sovereign" in res_mode["result"]

    res_theme = await tools.call_tool("ui_customize_theme", {"accent_color": "#8b5cf6"})
    assert res_theme["ok"] is True


def test_mode_and_theme_api_endpoints():
    client = TestClient(app)

    # Mode API
    resp = client.get("/api/mode")
    assert resp.status_code == 200
    data = resp.json()
    assert "mode" in data

    resp_post = client.post("/api/mode", json={"mode": "sovereign", "reason": "API test"})
    assert resp_post.status_code == 200
    assert resp_post.json()["mode"] == "sovereign"

    # Theme API
    resp_theme_get = client.get("/api/theme")
    assert resp_theme_get.status_code == 200

    resp_theme_post = client.post("/api/theme", json={"accent_color": "#ec4899"})
    assert resp_theme_post.status_code == 200

    resp_theme_reset = client.post("/api/theme/reset")
    assert resp_theme_reset.status_code == 200


@pytest.mark.anyio
async def test_get_setup_status_tool():
    res = await tools.call_tool("get_setup_status", {})
    assert res["ok"] is True
    assert "Setup & Integration Catalog" in res["result"]
    assert "GEMINI_API_KEY" in res["result"]

