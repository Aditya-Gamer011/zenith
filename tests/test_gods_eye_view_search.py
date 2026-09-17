import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from zenith.main import app
from zenith.tools.gods_eye_view import (
    parse_raw_coordinates,
    geocode_location,
    build_gev_url,
    gods_eye_view,
    PRESETS,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_parse_raw_coordinates_decimals():
    """Verify parsing standard decimal coordinate pairs."""
    assert parse_raw_coordinates("48.8584, 2.2945") == (48.8584, 2.2945)
    assert parse_raw_coordinates("-37.7749, 144.9631") == (-37.7749, 144.9631)
    assert parse_raw_coordinates("37.7749 -122.4194") == (37.7749, -122.4194)


def test_parse_raw_coordinates_compass():
    """Verify parsing compass directions (N, S, E, W) and degree symbols."""
    coords = parse_raw_coordinates("48.8584 N, 2.2945 E")
    assert coords is not None
    assert round(coords[0], 4) == 48.8584
    assert round(coords[1], 4) == 2.2945

    coords_south_west = parse_raw_coordinates("33.8568° S, 151.2153° W")
    assert coords_south_west is not None
    assert round(coords_south_west[0], 4) == -33.8568
    assert round(coords_south_west[1], 4) == -151.2153


def test_parse_raw_coordinates_dict():
    """Verify parsing dictionary inputs defensively."""
    assert parse_raw_coordinates({"lat": 48.8584, "lon": 2.2945}) == (48.8584, 2.2945)
    assert parse_raw_coordinates({"latitude": 37.77, "longitude": -122.42}) == (37.77, -122.42)


@pytest.mark.anyio
async def test_geocode_location_preset():
    """Verify curated presets resolve immediately with accurate names."""
    lat, lon, name = await geocode_location("taj mahal")
    assert round(lat, 4) == 27.1751
    assert round(lon, 4) == 78.0421
    assert "Taj Mahal" in name

    lat, lon, name = await geocode_location("eiffel tower")
    assert round(lat, 4) == 48.8584
    assert round(lon, 4) == 2.2945
    assert "Eiffel Tower" in name


@pytest.mark.anyio
async def test_geocode_location_coordinates():
    """Verify coordinate inputs bypass remote requests."""
    lat, lon, name = await geocode_location("28.6139, 77.2090")
    assert round(lat, 4) == 28.6139
    assert round(lon, 4) == 77.2090
    assert "Target" in name


@pytest.mark.anyio
async def test_geocode_location_defensive_dict():
    """Verify passing a dictionary does not crash."""
    lat, lon, name = await geocode_location({"location": "taj mahal"})
    assert round(lat, 4) == 27.1751
    assert round(lon, 4) == 78.0421

    lat, lon, name = await geocode_location({"lat": 51.5074, "lon": -0.1278})
    assert round(lat, 4) == 51.5074
    assert round(lon, 4) == -0.1278


def test_build_gev_url_includes_loc():
    """Verify build_gev_url embeds the location name in the hash state."""
    url = build_gev_url(lat=48.8584, lon=2.2945, target_name="Eiffel Tower, Paris")
    assert "/gev/#" in url
    assert "lat=48.85840" in url
    assert "lon=2.29450" in url
    assert "loc=Eiffel%20Tower%2C%20Paris" in url


@pytest.mark.anyio
async def test_gods_eye_view_tool_dict_input():
    """Verify gods_eye_view tool handles dict input gracefully."""
    output = await gods_eye_view(location={"location": "taj mahal"})
    assert "God's Eye View — Orbital Satellite Reconnaissance" in output
    assert "Taj Mahal" in output
    assert "<iframe" in output
    assert "loc=Taj%20Mahal" in output


def test_api_gev_geocode_endpoint(client):
    """Verify GET /api/gev/geocode returns valid JSON and coordinates."""
    # Preset
    res = client.get("/api/gev/geocode?q=taj+mahal")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["found"] is True
    assert round(data["lat"], 2) == 27.18
    assert "Taj Mahal" in data["label"]
    assert "place" in data
    assert data["place"]["viewport"] is not None

    # Coordinate string
    res_coord = client.get("/api/gev/geocode?q=35.6762,139.6503")
    assert res_coord.status_code == 200
    d_coord = res_coord.json()
    assert d_coord["ok"] is True
    assert d_coord["found"] is True
    assert round(d_coord["lat"], 4) == 35.6762
    assert round(d_coord["lng"], 4) == 139.6503

    # Empty query
    res_empty = client.get("/api/gev/geocode?q=")
    assert res_empty.status_code == 200
    assert res_empty.json()["found"] is False
