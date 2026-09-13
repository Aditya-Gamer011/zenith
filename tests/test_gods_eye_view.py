"""Automated tests for God's Eye View (GEV) 3D Earth Observation integration."""
import os
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from zenith.core.config import settings
from zenith.core import tools as tool_reg
from zenith.core import setup
from zenith.tools import gods_eye_view as gev
from zenith.tools.tool_explorer import get_available_tools, get_configurable_tools
from zenith.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_normalize_style():
    """Verify style aliases map correctly to GEV internal style tokens."""
    assert gev.normalize_style("normal") == "normal"
    assert gev.normalize_style("nvg") == "nvg"
    assert gev.normalize_style("night vision") == "nvg"
    assert gev.normalize_style("surveillance") == "nvg"
    assert gev.normalize_style("flir") == "flir"
    assert gev.normalize_style("thermal") == "flir"
    assert gev.normalize_style("infrared") == "flir"
    assert gev.normalize_style("crt") == "crt"
    assert gev.normalize_style("retro") == "crt"
    assert gev.normalize_style("anime") == "anime"
    assert gev.normalize_style("noir") == "noir"
    assert gev.normalize_style("snow") == "snow"
    assert gev.normalize_style("unknown_style") == "normal"
    assert gev.normalize_style("") == "normal"


def test_normalize_hud():
    """Verify HUD normalization."""
    assert gev.normalize_hud("tactical") == "tactical"
    assert gev.normalize_hud("standard") == "standard"
    assert gev.normalize_hud("minimal") == "minimal"
    assert gev.normalize_hud("off") == "off"
    assert gev.normalize_hud("unknown") == "tactical"
    assert gev.normalize_hud("") == "tactical"


def test_parse_raw_coordinates():
    """Verify coordinate extraction from raw string."""
    assert gev.parse_raw_coordinates("37.77, -122.42") == (37.77, -122.42)
    assert gev.parse_raw_coordinates("Target at 40.7128, -74.0060 now") == (40.7128, -74.0060)
    assert gev.parse_raw_coordinates("No coordinates here") is None


@pytest.mark.anyio
async def test_geocode_location_presets():
    """Verify preset lookup for iconic landmarks."""
    lat, lon, name = await gev.geocode_location("pentagon")
    assert pytest.approx(lat, rel=1e-3) == 38.8719
    assert pytest.approx(lon, rel=1e-3) == -77.0563
    assert "Pentagon" in name

    lat, lon, name = await gev.geocode_location("white house")
    assert pytest.approx(lat, rel=1e-3) == 38.8977
    assert "White House" in name

    lat, lon, name = await gev.geocode_location("pyramids of giza")
    assert pytest.approx(lat, rel=1e-3) == 29.9792
    assert "Giza" in name


@pytest.mark.anyio
async def test_geocode_raw_coordinates():
    """Verify raw coordinates pass through correctly."""
    lat, lon, name = await gev.geocode_location("51.5074, -0.1278")
    assert pytest.approx(lat, rel=1e-3) == 51.5074
    assert pytest.approx(lon, rel=1e-3) == -0.1278


def test_build_gev_url():
    """Verify URL hash formatting."""
    url = gev.build_gev_url(
        lat=37.7749,
        lon=-122.4194,
        alt=1200,
        heading=45,
        pitch=-40,
        style="flir",
        hud="tactical",
        map_layer="photoreal",
    )
    assert url.startswith("/gev/#")
    assert "lat=37.77490" in url
    assert "lon=-122.41940" in url
    assert "alt=1200" in url
    assert "heading=45" in url
    assert "pitch=-40" in url
    assert "style=flir" in url
    assert "hud=tactical" in url
    assert "map=photoreal" in url


def test_build_gev_url_public_override():
    """Verify public URL override when configured."""
    url = gev.build_gev_url(
        lat=0.0,
        lon=0.0,
        base_override="https://gev.example.com",
    )
    assert url.startswith("https://gev.example.com/#lat=0.00000")


def test_generate_gev_embed_iframe():
    """Verify iframe generation and title escaping."""
    iframe = gev.generate_gev_embed_iframe("/gev/#lat=10&lon=20", height=420, title="Test <View>")
    assert '<iframe width="100%" height="420"' in iframe
    assert 'src="/gev/#lat=10&lon=20"' in iframe
    assert 'title="Test &lt;View&gt;"' in iframe
    assert 'allowfullscreen' in iframe


@pytest.mark.anyio
async def test_gods_eye_view_tool_execution():
    """Verify execution of gods_eye_view tool with preset and custom options."""
    res = await gev.gods_eye_view(location="pentagon", style="thermal", hud="tactical")
    assert "🛰️ **God's Eye View" in res
    assert "The Pentagon" in res
    assert "FLIR Thermal Infrared" in res
    assert "TACTICAL" in res
    assert "<iframe" in res
    assert "/gev/#" in res


@pytest.mark.anyio
async def test_gods_eye_view_status_tool():
    """Verify status tool inspection."""
    status_text = await gev.gods_eye_view_status()
    assert "God's Eye View Status & Configuration" in status_text
    assert "Service Status" in status_text
    assert "Cesium Ion Token" in status_text


@pytest.mark.anyio
async def test_tool_registry_call():
    """Verify gods_eye_view and status are registered in Zenith TOOLS and callable via call_tool."""
    assert "gods_eye_view" in tool_reg.TOOLS
    assert "gods_eye_view_status" in tool_reg.TOOLS

    res = await tool_reg.call_tool("gods_eye_view", {"location": "eiffel tower", "style": "normal"})
    assert res["ok"] is True
    assert "Eiffel Tower" in res["result"]
    assert "<iframe" in res["result"]

    res_stat = await tool_reg.call_tool("gods_eye_view_status", {})
    assert res_stat["ok"] is True
    assert "God's Eye View" in res_stat["result"]


def test_setup_catalog_entries():
    """Verify GEV entries exist in SECRETS_CATALOG under maps_calendar."""
    catalog = setup.SECRETS_CATALOG
    gev_keys = {item["key"]: item for item in catalog if item.get("category") == "maps_calendar"}

    assert "CESIUM_ION_TOKEN" in gev_keys
    assert gev_keys["CESIUM_ION_TOKEN"]["is_secret"] is True
    assert "ion.cesium.com" in gev_keys["CESIUM_ION_TOKEN"]["where_to_get_url"]

    assert "GEV_ENABLED" in gev_keys
    assert gev_keys["GEV_ENABLED"]["placeholder"] == "yes"

    assert "GEV_PORT" in gev_keys
    assert gev_keys["GEV_PORT"]["placeholder"] == "4173"

    assert "OPENSKY_CLIENT_ID" in gev_keys
    assert "OPENSKY_CLIENT_SECRET" in gev_keys


def test_config_reload():
    """Verify settings.reload() pulls GEV variables."""
    with patch.dict(os.environ, {
        "CESIUM_ION_TOKEN": "test_cesium_token_123",
        "GEV_ENABLED": "true",
        "GEV_PORT": "4175",
        "OPENSKY_CLIENT_ID": "sky_user",
    }):
        settings.reload()
        assert settings.cesium_ion_token == "test_cesium_token_123"
        assert settings.gev_enabled is True
        assert settings.gev_port == 4175
        assert settings.opensky_client_id == "sky_user"


def test_tool_explorer_integration():
    """Verify tool_explorer classifies gods_eye_view and lists configurable items."""
    tools_list = get_available_tools(query="gods_eye_view")
    assert "gods_eye_view" in tools_list

    config_list = get_configurable_tools()
    assert "CESIUM_ION_TOKEN" in config_list
    assert "GEV_ENABLED" in config_list


def test_api_gev_status_endpoint(client):
    """Verify GET /api/gev/status returns expected JSON schema."""
    resp = client.get("/api/gev/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "running" in data
    assert "port" in data
    assert "dist_ready" in data
    assert data["port"] in {4173, 4175}
