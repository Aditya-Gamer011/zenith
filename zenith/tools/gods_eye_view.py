"""God's Eye View (GEV) — 3D Earth Observation & Satellite Simulator for Zenith.

Integrates the God's Eye View intelligence console:
- Photorealistic 3D globe with Cesium and Google Photorealistic 3D Tiles
- Live aircraft (ADS-B via OpenSky), maritime vessels, satellites (CelesTrak), weather, earthquakes, and CCTV
- Multispectral sensor overlays: NVG (Night Vision), FLIR (Thermal Infrared), CRT (Tactical Scanlines), Anime, Noir, and Snow
- Interactive HUD & satellite telemetry console iframe embeds in chat
- Preset coordinates for iconic global locations, landmarks, military installations, and orbital views
- Autonomous geocoding via Google Maps API or OpenStreetMap Nominatim fallback
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import shutil
import socket
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

try:
    from ..core.config import settings
except Exception:  # pragma: no cover
    settings = None

log = logging.getLogger("zenith.gods_eye_view")

USER_AGENT = "ZenithGodsEyeView/1.0 (Earth Observation Intelligence Console)"

# Iconic presets with coordinates, default altitudes (meters), heading, pitch, and thematic sensor style
PRESETS: dict[str, dict[str, Any]] = {
    "pentagon": {
        "lat": 38.8719, "lon": -77.0563, "alt": 850, "heading": 30, "pitch": -40,
        "style": "flir", "hud": "tactical", "name": "The Pentagon, Arlington, VA, USA"
    },
    "white house": {
        "lat": 38.8977, "lon": -77.0365, "alt": 650, "heading": 0, "pitch": -35,
        "style": "nvg", "hud": "tactical", "name": "The White House, Washington D.C., USA"
    },
    "area 51": {
        "lat": 37.2431, "lon": -115.7930, "alt": 2500, "heading": 45, "pitch": -35,
        "style": "nvg", "hud": "tactical", "name": "Groom Lake / Area 51, Nevada, USA"
    },
    "pyramids": {
        "lat": 29.9792, "lon": 31.1342, "alt": 1100, "heading": 15, "pitch": -35,
        "style": "normal", "hud": "tactical", "name": "Giza Pyramids Complex, Giza, Egypt"
    },
    "pyramids of giza": {
        "lat": 29.9792, "lon": 31.1342, "alt": 1100, "heading": 15, "pitch": -35,
        "style": "normal", "hud": "tactical", "name": "Giza Pyramids Complex, Giza, Egypt"
    },
    "eiffel tower": {
        "lat": 48.8584, "lon": 2.2945, "alt": 600, "heading": 40, "pitch": -30,
        "style": "normal", "hud": "tactical", "name": "Eiffel Tower, Paris, France"
    },
    "taj mahal": {
        "lat": 27.1751, "lon": 78.0421, "alt": 550, "heading": 0, "pitch": -35,
        "style": "normal", "hud": "tactical", "name": "Taj Mahal, Agra, India"
    },
    "tokyo tower": {
        "lat": 35.6586, "lon": 139.7454, "alt": 750, "heading": 45, "pitch": -30,
        "style": "anime", "hud": "tactical", "name": "Tokyo Tower, Minato, Tokyo, Japan"
    },
    "shibuya": {
        "lat": 35.6595, "lon": 139.7005, "alt": 600, "heading": 0, "pitch": -35,
        "style": "anime", "hud": "tactical", "name": "Shibuya Crossing, Tokyo, Japan"
    },
    "kremlin": {
        "lat": 55.7520, "lon": 37.6175, "alt": 700, "heading": 25, "pitch": -35,
        "style": "flir", "hud": "tactical", "name": "The Moscow Kremlin, Moscow, Russia"
    },
    "burj khalifa": {
        "lat": 25.1972, "lon": 55.2744, "alt": 1300, "heading": 30, "pitch": -25,
        "style": "normal", "hud": "tactical", "name": "Burj Khalifa, Dubai, UAE"
    },
    "colosseum": {
        "lat": 41.8902, "lon": 12.4922, "alt": 600, "heading": 10, "pitch": -40,
        "style": "normal", "hud": "tactical", "name": "Colosseum, Rome, Italy"
    },
    "statue of liberty": {
        "lat": 40.6892, "lon": -74.0445, "alt": 500, "heading": 45, "pitch": -30,
        "style": "normal", "hud": "tactical", "name": "Statue of Liberty, New York, USA"
    },
    "sydney opera house": {
        "lat": -33.8568, "lon": 151.2153, "alt": 650, "heading": 135, "pitch": -35,
        "style": "normal", "hud": "tactical", "name": "Sydney Opera House, Sydney, Australia"
    },
    "everest": {
        "lat": 27.9881, "lon": 86.9250, "alt": 9800, "heading": 0, "pitch": -25,
        "style": "snow", "hud": "tactical", "name": "Mount Everest Summit, Himalayas"
    },
    "mount everest": {
        "lat": 27.9881, "lon": 86.9250, "alt": 9800, "heading": 0, "pitch": -25,
        "style": "snow", "hud": "tactical", "name": "Mount Everest Summit, Himalayas"
    },
    "grand canyon": {
        "lat": 36.0544, "lon": -112.1401, "alt": 3500, "heading": 90, "pitch": -30,
        "style": "normal", "hud": "tactical", "name": "Grand Canyon South Rim, Arizona, USA"
    },
    "chernobyl": {
        "lat": 51.2755, "lon": 30.2222, "alt": 1100, "heading": 0, "pitch": -40,
        "style": "flir", "hud": "tactical", "name": "Chernobyl Nuclear Power Plant, Ukraine"
    },
    "bermuda triangle": {
        "lat": 25.0000, "lon": -71.0000, "alt": 85000, "heading": 0, "pitch": -55,
        "style": "nvg", "hud": "tactical", "name": "Bermuda Triangle, Atlantic Ocean"
    },
    "orbit": {
        "lat": 0.0, "lon": 0.0, "alt": 2500000, "heading": 0, "pitch": -90,
        "style": "normal", "hud": "tactical", "name": "Low Earth Orbit (LEO) Global View"
    },
    "iss": {
        "lat": 20.0, "lon": -30.0, "alt": 1800000, "heading": 45, "pitch": -85,
        "style": "normal", "hud": "tactical", "name": "International Space Station Orbital Pass"
    },
    "san francisco": {
        "lat": 37.7946, "lon": -122.3999, "alt": 800, "heading": 30, "pitch": -35,
        "style": "normal", "hud": "tactical", "name": "Financial District, San Francisco, CA, USA"
    },
}

STYLE_ALIASES: dict[str, str] = {
    "nvg": "nvg",
    "night vision": "nvg",
    "nightvision": "nvg",
    "night_vision": "nvg",
    "surveillance": "nvg",
    "recon": "nvg",
    "green": "nvg",
    "flir": "flir",
    "thermal": "flir",
    "infrared": "flir",
    "heat": "flir",
    "predator": "flir",
    "crt": "crt",
    "retro": "crt",
    "terminal": "crt",
    "scanlines": "crt",
    "matrix": "crt",
    "anime": "anime",
    "cel": "anime",
    "toon": "anime",
    "noir": "noir",
    "black and white": "noir",
    "monochrome": "noir",
    "bw": "noir",
    "snow": "snow",
    "blizzard": "snow",
    "winter": "snow",
    "normal": "normal",
    "satellite": "normal",
    "photoreal": "normal",
    "standard": "normal",
    "daylight": "normal",
}

_gev_process: subprocess.Popen | None = None


def normalize_style(style_input: str) -> str:
    """Normalize user or model style input into supported URL style parameter."""
    if not style_input:
        return "normal"
    clean = style_input.strip().lower()
    return STYLE_ALIASES.get(clean, "normal")


def normalize_hud(hud_input: str) -> str:
    """Normalize HUD parameter."""
    if not hud_input:
        return "tactical"
    clean = hud_input.strip().lower()
    if clean in {"tactical", "standard", "minimal", "off"}:
        return clean
    return "tactical"


def parse_raw_coordinates(text: Any) -> tuple[float, float] | None:
    """Parse raw coordinates from text or data structure (e.g. '37.77, -122.42' or '33.85 S, 151.21 E')."""
    if not text:
        return None
    if isinstance(text, (list, tuple)) and len(text) >= 2:
        try:
            lat, lon = float(text[0]), float(text[1])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except (ValueError, TypeError):
            pass
    if isinstance(text, dict):
        lat = text.get("lat") or text.get("latitude")
        lon = text.get("lon") or text.get("lng") or text.get("longitude")
        if lat is not None and lon is not None:
            try:
                flat, flon = float(lat), float(lon)
                if -90 <= flat <= 90 and -180 <= flon <= 180:
                    return flat, flon
            except (ValueError, TypeError):
                pass
        text = str(text.get("location") or text.get("query") or text.get("name") or text)

    s = str(text).strip()
    # 1. Check for compass direction coordinates e.g. "48.8584 N, 2.2945 E" or "33.8568° S, 151.2153° W"
    compass_pattern = r"([0-9]+(?:\.[0-9]+)?)\s*°?\s*([NSns])[,\s]+([0-9]+(?:\.[0-9]+)?)\s*°?\s*([EWew])"
    cm = re.search(compass_pattern, s)
    if cm:
        try:
            lat_val, lat_dir, lon_val, lon_dir = cm.groups()
            lat = float(lat_val) * (-1 if lat_dir.upper() == "S" else 1)
            lon = float(lon_val) * (-1 if lon_dir.upper() == "W" else 1)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except Exception:
            pass

    # 2. Check for standard decimal pairs e.g. "48.8584, 2.2945" or "-37.7749, 144.9631"
    dec_pattern = r"([-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?))[,\s]+([-+]?(?:180(?:\.0+)?|(?:1[0-7]\d|\d{1,2})(?:\.\d+)?))"
    m = re.search(dec_pattern, s)
    if m:
        try:
            lat = float(m.group(1))
            lon = float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except Exception:
            pass
    return None


async def geocode_location(location: Any) -> tuple[float, float, str]:
    """Geocode a place name, address, or preset into (lat, lon, formatted_name)."""
    if isinstance(location, dict):
        coords = parse_raw_coordinates(location)
        if coords:
            return coords[0], coords[1], f"Target ({coords[0]:.4f}, {coords[1]:.4f})"
        loc_str = str(location.get("location") or location.get("name") or location.get("query") or "")
    else:
        loc_str = str(location or "")

    raw_clean = loc_str.strip().lower()
    if not raw_clean:
        p = PRESETS["orbit"]
        return float(p["lat"]), float(p["lon"]), p["name"]

    # 1. Preset lookup
    if raw_clean in PRESETS:
        p = PRESETS[raw_clean]
        return float(p["lat"]), float(p["lon"]), p["name"]

    # Partial preset match
    for k, p in PRESETS.items():
        if k in raw_clean or raw_clean in k:
            return float(p["lat"]), float(p["lon"]), p["name"]

    # 2. Raw coordinate match
    coords = parse_raw_coordinates(loc_str)
    if coords:
        return coords[0], coords[1], f"Target ({coords[0]:.4f}, {coords[1]:.4f})"

    # 3. Google Maps Geocoding API if key configured
    gkey = ""
    if settings and getattr(settings, "google_maps_api_key", None):
        gkey = settings.google_maps_api_key
    else:
        gkey = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

    if gkey:
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            async with httpx.AsyncClient(timeout=8, headers={"User-Agent": USER_AGENT}) as client:
                res = await client.get(url, params={"address": loc_str, "key": gkey})
                res.raise_for_status()
                data = res.json()
            if data.get("status") == "OK" and data.get("results"):
                res0 = data["results"][0]
                loc = res0["geometry"]["location"]
                name = res0.get("formatted_address", loc_str)
                return float(loc["lat"]), float(loc["lng"]), name
        except Exception as e:
            log.warning("Google Geocoding failed for '%s': %s", loc_str, e)

    # 4. Photon (Komoot/OSM) fast geocoder (keyless, sub-200ms)
    try:
        url = "https://photon.komoot.io/api/"
        async with httpx.AsyncClient(timeout=4, headers={"User-Agent": USER_AGENT}) as client:
            res = await client.get(url, params={"q": loc_str, "limit": 1})
            if res.status_code == 200:
                data = res.json()
                features = data.get("features", [])
                if features and isinstance(features, list) and len(features) > 0:
                    feat = features[0]
                    geom = feat.get("geometry", {})
                    coords_pt = geom.get("coordinates", [])
                    if len(coords_pt) >= 2:
                        lon, lat = float(coords_pt[0]), float(coords_pt[1])
                        props = feat.get("properties", {})
                        parts = [props.get(k) for k in ("name", "city", "state", "country") if props.get(k)]
                        name = ", ".join(parts) if parts else props.get("name", loc_str)
                        return lat, lon, name
    except Exception as e:
        log.warning("Photon geocoding failed for '%s': %s", loc_str, e)

    # 5. OpenStreetMap Nominatim fallback (keyless, universal)
    try:
        url = "https://nominatim.openstreetmap.org/search"
        async with httpx.AsyncClient(timeout=6, headers={"User-Agent": USER_AGENT}) as client:
            res = await client.get(url, params={"q": loc_str, "format": "json", "limit": 1})
            res.raise_for_status()
            data = res.json()
        if data and isinstance(data, list) and len(data) > 0:
            item = data[0]
            lat = float(item["lat"])
            lon = float(item["lon"])
            name = item.get("display_name", loc_str)
            return lat, lon, name
    except Exception as e:
        log.warning("Nominatim geocoding failed for '%s': %s", loc_str, e)

    # Default fallback if everything fails
    return 37.7749, -122.4194, loc_str or "San Francisco, CA"


def build_gev_url(
    lat: float,
    lon: float,
    alt: float = 800,
    heading: float = 0,
    pitch: float = -35,
    style: str = "normal",
    hud: str = "tactical",
    map_layer: str = "photoreal",
    celestial_ring: bool = False,
    scope: bool = True,
    base_override: str = "",
    target_name: str = "",
) -> str:
    """Build God's Eye View URL hash state."""
    norm_style = normalize_style(style)
    norm_hud = normalize_hud(hud)

    # Map layer selection: photoreal if Cesium / Google keys present, or specified
    m_layer = map_layer.lower()
    if m_layer not in {"photoreal", "bing", "osm", "esri"}:
        m_layer = "photoreal"

    params = [
        f"lat={lat:.5f}",
        f"lon={lon:.5f}",
        f"alt={int(alt)}",
        f"heading={int(heading)}",
        f"pitch={int(pitch)}",
        f"style={norm_style}",
        f"hud={norm_hud}",
        "hv=1",
        f"map={m_layer}",
        f"cr={1 if celestial_ring else 0}",
        f"sc={1 if scope else 1}",
    ]
    if target_name:
        params.append(f"loc={urllib.parse.quote(target_name)}")
    hash_str = "&".join(params)

    # Base URL resolution
    if base_override:
        base = base_override.rstrip("/")
        return f"{base}/#{hash_str}"

    if settings and getattr(settings, "gev_public_url", None):
        base = settings.gev_public_url.rstrip("/")
        return f"{base}/#{hash_str}"

    # Default relative URL for Zenith reverse proxy / embedding
    return f"/gev/#{hash_str}"


def generate_gev_embed_iframe(url: str, height: int = 420, title: str = "God's Eye View") -> str:
    """Generate responsive iframe HTML embed for God's Eye View satellite console."""
    safe_title = html.escape(title)
    return (
        f'<iframe width="100%" height="{height}" style="border:0; border-radius:12px;" '
        f'loading="lazy" allowfullscreen referrerpolicy="no-referrer-when-downgrade" '
        f'title="{safe_title}" src="{url}"></iframe>'
    )


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check whether the given local port is actively bound and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def is_gev_server_running() -> bool:
    """Check if the God's Eye View server is active and listening."""
    port = 4173
    host = "127.0.0.1"
    if settings:
        port = getattr(settings, "gev_port", 4173)
        host = getattr(settings, "gev_host", "127.0.0.1")
        if host in {"0.0.0.0", "localhost"}:
            host = "127.0.0.1"
    return is_port_in_use(port, host)


async def ensure_gev_server_started() -> tuple[bool, str]:
    """Ensure the God's Eye View server is running. Spawns preview server if offline."""
    global _gev_process

    if is_gev_server_running():
        return True, "God's Eye View server is already running."

    gev_dir = Path(__file__).resolve().parents[2] / "gods-eye-view"
    if settings and getattr(settings, "gev_dir", None):
        gev_dir = settings.gev_dir

    if not gev_dir.exists():
        return False, f"God's Eye View repository not found at {gev_dir}"

    port = 4173
    if settings:
        port = getattr(settings, "gev_port", 4173)

    # Check if npm or npx exists
    npx_bin = shutil.which("npx")
    if not npx_bin:
        return False, "Node.js / npx is not installed on the system."

    # Environment variables for God's Eye View
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = "0.0.0.0"
    if settings:
        if getattr(settings, "cesium_ion_token", ""):
            env["CESIUM_ION_TOKEN"] = settings.cesium_ion_token
        if getattr(settings, "google_maps_api_key", ""):
            env["GOOGLE_MAPS_API_KEY"] = settings.google_maps_api_key
        if getattr(settings, "opensky_client_id", ""):
            env["OPENSKY_CLIENT_ID"] = settings.opensky_client_id
        if getattr(settings, "opensky_client_secret", ""):
            env["OPENSKY_CLIENT_SECRET"] = settings.opensky_client_secret

    dist_index = gev_dir / "dist" / "index.html"
    cmd = [npx_bin, "vite", "preview", "--port", str(port), "--host", "0.0.0.0"] if dist_index.exists() else [
        npx_bin, "vite", "--port", str(port), "--host", "0.0.0.0"
    ]

    try:
        _gev_process = subprocess.Popen(
            cmd,
            cwd=str(gev_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait up to 3 seconds for port to open
        for _ in range(15):
            await asyncio.sleep(0.2)
            if is_port_in_use(port, "127.0.0.1"):
                return True, f"God's Eye View started successfully on port {port}."

        return False, f"Server process started (PID {_gev_process.pid}) but port {port} not responsive yet."
    except Exception as e:
        log.error("Failed to start God's Eye View server: %s", e)
        return False, f"Failed to start server: {e}"


def stop_gev_server() -> None:
    """Terminate the background God's Eye View server process if running."""
    global _gev_process
    if _gev_process and _gev_process.poll() is None:
        try:
            _gev_process.terminate()
            _gev_process.wait(timeout=2)
        except Exception:
            try:
                _gev_process.kill()
            except Exception:
                pass
        _gev_process = None


async def gods_eye_view(
    location: Any = "",
    lat: float | None = None,
    lon: float | None = None,
    alt: float | None = None,
    style: str = "normal",
    hud: str = "tactical",
    heading: float = 0,
    pitch: float = -35,
    map_layer: str = "photoreal",
) -> str:
    """Open God's Eye View 3D Earth Observation console and return an interactive HUD embed."""
    # Check if disabled
    if settings and not getattr(settings, "gev_enabled", True):
        return "God's Eye View is currently disabled. Enable it by setting GEV_ENABLED=yes in configuration."

    # Try starting server in background if not already active
    asyncio.create_task(ensure_gev_server_started())

    if isinstance(location, dict):
        loc_str = str(location.get("location") or location.get("name") or location.get("query") or "")
        target_name = loc_str or "Target"
    else:
        loc_str = str(location or "")
        target_name = loc_str or "Target"

    target_lat = lat
    target_lon = lon
    target_alt = alt if alt is not None else 800.0

    # If coordinates are not provided, geocode location
    if target_lat is None or target_lon is None:
        raw_preset = loc_str.strip().lower()
        if raw_preset in PRESETS:
            p = PRESETS[raw_preset]
            target_lat = float(p["lat"])
            target_lon = float(p["lon"])
            target_name = p["name"]
            if alt is None:
                target_alt = float(p.get("alt", 800.0))
            if heading == 0 and "heading" in p:
                heading = float(p["heading"])
            if pitch == -35 and "pitch" in p:
                pitch = float(p["pitch"])
            if style == "normal" and "style" in p:
                style = p["style"]
            if hud == "tactical" and "hud" in p:
                hud = p["hud"]
        elif loc_str:
            target_lat, target_lon, target_name = await geocode_location(location)
        else:
            # Default to panoramic orbit view
            p = PRESETS["orbit"]
            target_lat = float(p["lat"])
            target_lon = float(p["lon"])
            target_name = p["name"]
            target_alt = float(p["alt"])

    norm_style = normalize_style(style)
    norm_hud = normalize_hud(hud)

    # Generate GEV Hash URL
    gev_url = build_gev_url(
        lat=target_lat,
        lon=target_lon,
        alt=target_alt,
        heading=heading,
        pitch=pitch,
        style=norm_style,
        hud=norm_hud,
        map_layer=map_layer,
        target_name=target_name,
    )

    embed_html = generate_gev_embed_iframe(gev_url, height=420, title=f"God's Eye View: {target_name}")

    style_display = {
        "normal": "Photoreal Optical Satellite",
        "nvg": "Surveillance Night Vision (NVG)",
        "flir": "FLIR Thermal Infrared",
        "crt": "Tactical CRT Terminal",
        "anime": "Cel-Shaded Anime Vector",
        "noir": "Monochrome Noir",
        "snow": "Atmospheric Winter / Blizzard",
    }.get(norm_style, norm_style.upper())

    output = [
        f"🛰️ **God's Eye View — Orbital Satellite Reconnaissance**",
        f"- 🎯 **Target**: {target_name}",
        f"- 📍 **Coordinates**: `{target_lat:.5f}, {target_lon:.5f}` (Altitude: `{int(target_alt):,} m`)",
        f"- 🔭 **Sensor Mode**: {style_display} (`{norm_style}`)",
        f"- 🖥️ **HUD Overlay**: `{norm_hud.upper()}` Tactical Telemetry",
        f"- 🌐 **Console Link**: [Open Fullscreen Console]({gev_url})\n",
        embed_html,
    ]

    return "\n".join(output)


async def gods_eye_view_status() -> str:
    """Inspect God's Eye View server status, configured tokens, and capabilities."""
    running = is_gev_server_running()
    port = 4173
    host = "127.0.0.1"
    enabled = True
    cesium_set = False
    gmaps_set = False
    opensky_set = False

    if settings:
        port = getattr(settings, "gev_port", 4173)
        host = getattr(settings, "gev_host", "127.0.0.1")
        enabled = getattr(settings, "gev_enabled", True)
        cesium_set = bool(getattr(settings, "cesium_ion_token", ""))
        gmaps_set = bool(getattr(settings, "google_maps_api_key", ""))
        opensky_set = bool(getattr(settings, "opensky_client_id", ""))

    gev_dir = Path(__file__).resolve().parents[2] / "gods-eye-view"
    if settings and getattr(settings, "gev_dir", None):
        gev_dir = settings.gev_dir

    dist_exists = (gev_dir / "dist" / "index.html").exists()

    status_icon = "🟢 ACTIVE" if running else "🔴 OFFLINE"

    lines = [
        "🛰️ **God's Eye View Status & Configuration**",
        f"- **Service Status**: {status_icon}",
        f"- **Module Enabled**: {'Yes' if enabled else 'No (set GEV_ENABLED=yes)'}",
        f"- **Port / Endpoint**: `http://{host}:{port}` (Proxied via `/gev`)",
        f"- **Repository Path**: `{gev_dir}`",
        f"- **Production Dist Built**: {'Yes (optimized bundle ready)' if dist_exists else 'No (run npm run build)'}",
        f"- **Cesium Ion Token**: {'Configured ✅ (Photoreal 3D terrain active)' if cesium_set else 'Not configured (using keyless Esri/OSM fallback)'}",
        f"- **Google Maps API**: {'Configured ✅ (Photoreal 3D tiles active)' if gmaps_set else 'Not configured'}",
        f"- **OpenSky Network**: {'Configured ✅ (Live flight telemetry active)' if opensky_set else 'Not configured (using public ADS-B proxy)'}",
    ]

    if not running:
        lines.append("\n*To start the server, Zenith will automatically launch it upon first request, or via `ensure_gev_server_started()`.*")

    return "\n".join(lines)
