"""Google Maps integration for Zenith.

Provides place search, location geocoding, directions/navigation, commute time
matrix calculation, and embed IFRAME / interactive widget generation.
"""
from __future__ import annotations

import html
import json
import urllib.parse
from typing import Any

import httpx

try:
    from ..core.config import settings
except Exception:  # pragma: no cover
    settings = None

USER_AGENT = "ZenithAssistant/1.0 (personal assistant)"


def _get_api_key() -> str:
    """Retrieve Google Maps API Key from Settings or environment."""
    if settings and getattr(settings, "google_maps_api_key", None):
        return settings.google_maps_api_key
    import os
    return os.getenv("GOOGLE_MAPS_API_KEY", "").strip()


def generate_map_embed_iframe(
    q_or_place: str = "",
    embed_type: str = "place",
    origin: str = "",
    destination: str = "",
    mode: str = "driving",
    zoom: int = 14,
    height: int = 380,
) -> str:
    """Generate responsive iframe HTML for embedding Google Maps."""
    key = _get_api_key()
    if not key:
        return "<p><em>[Google Maps API key not configured]</em></p>"

    mode_map = {
        "driving": "driving",
        "transit": "transit",
        "public_transit": "transit",
        "bicycling": "bicycling",
        "walking": "walking",
    }
    nav_mode = mode_map.get(mode.lower(), "driving")

    if embed_type == "directions" or (origin and destination):
        enc_orig = urllib.parse.quote(origin or q_or_place)
        enc_dest = urllib.parse.quote(destination)
        src = f"https://www.google.com/maps/embed/v1/directions?key={key}&origin={enc_orig}&destination={enc_dest}&mode={nav_mode}"
    elif embed_type == "search":
        enc_q = urllib.parse.quote(q_or_place)
        src = f"https://www.google.com/maps/embed/v1/search?key={key}&q={enc_q}&zoom={zoom}"
    else:  # default 'place'
        enc_q = urllib.parse.quote(q_or_place)
        src = f"https://www.google.com/maps/embed/v1/place?key={key}&q={enc_q}&zoom={zoom}"

    return (
        f'<iframe width="100%" height="{height}" style="border:0; border-radius:12px;" '
        f'loading="lazy" allowfullscreen referrerpolicy="no-referrer-when-downgrade" '
        f'src="{src}"></iframe>'
    )


async def maps_geocode(location: str) -> str:
    """Geocode an address or place name to lat/lng and formatted address."""
    key = _get_api_key()
    if not key:
        return "Error: GOOGLE_MAPS_API_KEY is not configured in .env"
    if not location or not location.strip():
        return "Please specify a location to geocode."

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url, params={"address": location, "key": key})
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "OK" or not data.get("results"):
            return f"Geocoding failed for '{location}': {data.get('status')}"

        res = data["results"][0]
        formatted = res.get("formatted_address", location)
        loc = res["geometry"]["location"]
        lat, lng = loc["lat"], loc["lng"]
        place_id = res.get("place_id", "")

        gmaps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
        embed_code = generate_map_embed_iframe(q_or_place=formatted, embed_type="place")

        return (
            f"📍 **Location**: {formatted}\n"
            f"• **Coordinates**: {lat:.5f}, {lng:.5f}\n"
            f"• **Place ID**: `{place_id}`\n"
            f"• **Google Maps**: {gmaps_url}\n\n"
            f"{embed_code}"
        )
    except Exception as exc:
        return f"[maps_geocode error] {exc}"


async def maps_search(query: str, location: str = "") -> str:
    """Search for places or points of interest near a location."""
    key = _get_api_key()
    if not key:
        return "Error: GOOGLE_MAPS_API_KEY is not configured in .env"
    if not query or not query.strip():
        return "Please specify a place or search query."

    full_query = f"{query} near {location}" if location else query
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"

    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url, params={"query": full_query, "key": key})
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "OK" or not data.get("results"):
            # Fallback to geocoding if place search yields no structured results
            return await maps_geocode(full_query)

        places = data["results"][:5]
        out = [f"🔍 **Google Maps search results for '{full_query}'**:\n"]

        for idx, p in enumerate(places, 1):
            name = p.get("name", "Unknown")
            addr = p.get("formatted_address", "")
            rating = p.get("rating", "N/A")
            user_ratings = p.get("user_ratings_total", 0)
            open_now = p.get("opening_hours", {}).get("open_now")
            open_str = "Open now" if open_now is True else ("Closed" if open_now is False else "")
            place_id = p.get("place_id", "")
            loc = p.get("geometry", {}).get("location", {})
            lat, lng = loc.get("lat"), loc.get("lng")

            maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(name)}"

            item = f"{idx}. **{name}**\n"
            if addr:
                item += f"   • Address: {addr}\n"
            item += f"   • Rating: ⭐ {rating} ({user_ratings} reviews)"
            if open_str:
                item += f" · {open_str}"
            item += f"\n   • Link: [View on Google Maps]({maps_url})\n"
            out.append(item)

        top_place = places[0].get("formatted_address") or places[0].get("name")
        embed_code = generate_map_embed_iframe(q_or_place=top_place, embed_type="search")
        out.append(f"\n{embed_code}")

        return "\n".join(out)
    except Exception as exc:
        return f"[maps_search error] {exc}"


async def maps_directions(origin: str, destination: str, mode: str = "driving") -> str:
    """Get directions, distance, and duration between origin and destination."""
    key = _get_api_key()
    if not key:
        return "Error: GOOGLE_MAPS_API_KEY is not configured in .env"
    if not origin or not destination:
        return "Please specify both origin and destination."

    mode_map = {
        "driving": "driving",
        "transit": "transit",
        "public_transit": "transit",
        "bicycling": "bicycling",
        "walking": "walking",
    }
    nav_mode = mode_map.get(mode.lower(), "driving")

    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": nav_mode,
        "key": key,
    }

    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "OK" or not data.get("routes"):
            return f"Could not find directions from '{origin}' to '{destination}': {data.get('status')}"

        route = data["routes"][0]
        leg = route["legs"][0]

        dist_text = leg.get("distance", {}).get("text", "Unknown")
        dur_text = leg.get("duration", {}).get("text", "Unknown")
        dur_in_traffic = leg.get("duration_in_traffic", {}).get("text")
        start_addr = leg.get("start_address", origin)
        end_addr = leg.get("end_address", destination)

        mode_titles = {
            "driving": "🚗 Driving",
            "transit": "🚌 Public Transit",
            "bicycling": "🚲 Bicycling",
            "walking": "🚶 Walking",
        }
        mode_title = mode_titles.get(nav_mode, "🚗 Directions")

        out = [
            f"🗺️ **{mode_title} Directions**",
            f"• **From**: {start_addr}",
            f"• **To**: {end_addr}",
            f"• **Distance**: {dist_text}",
            f"• **Duration**: {dur_text}" + (f" (Traffic: {dur_in_traffic})" if dur_in_traffic else ""),
        ]

        steps = leg.get("steps", [])
        if steps:
            out.append("\n**Key Navigation Steps**:")
            for idx, s in enumerate(steps[:6], 1):
                clean_instr = html.unescape(s.get("html_instructions", "")).replace("<b>", "**").replace("</b>", "**").replace("<div style=\"font-size:0.9em\">", " (").replace("</div>", ")")
                clean_instr = "".join(c for c in clean_instr if c not in "<>")
                s_dist = s.get("distance", {}).get("text", "")
                s_dur = s.get("duration", {}).get("text", "")
                out.append(f"{idx}. {clean_instr} [{s_dist}, {s_dur}]")
            if len(steps) > 6:
                out.append(f"... and {len(steps) - 6} more steps.")

        maps_url = f"https://www.google.com/maps/dir/?api=1&origin={urllib.parse.quote(origin)}&destination={urllib.parse.quote(destination)}&travelmode={nav_mode}"
        out.append(f"\n🔗 [Open Route in Google Maps]({maps_url})")

        embed_code = generate_map_embed_iframe(origin=start_addr, destination=end_addr, mode=nav_mode, embed_type="directions")
        out.append(f"\n{embed_code}")

        return "\n".join(out)
    except Exception as exc:
        return f"[maps_directions error] {exc}"


async def maps_commute(origin: str, destinations: list[str] | str, mode: str = "driving") -> str:
    """Calculate commute times and distance from an origin to single or multiple destinations."""
    key = _get_api_key()
    if not key:
        return "Error: GOOGLE_MAPS_API_KEY is not configured in .env"

    if isinstance(destinations, str):
        # comma or pipe separated list
        dest_list = [d.strip() for d in destinations.replace("|", ",").split(",") if d.strip()]
    else:
        dest_list = destinations

    if not origin or not dest_list:
        return "Please specify an origin and at least one destination."

    mode_map = {
        "driving": "driving",
        "transit": "transit",
        "public_transit": "transit",
        "bicycling": "bicycling",
        "walking": "walking",
    }
    nav_mode = mode_map.get(mode.lower(), "driving")

    dest_str = "|".join(dest_list)
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": dest_str,
        "mode": nav_mode,
        "key": key,
    }

    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "OK" or not data.get("rows"):
            return f"Distance Matrix calculation failed: {data.get('status')}"

        origin_addr = data.get("origin_addresses", [origin])[0]
        dest_addrs = data.get("destination_addresses", dest_list)
        elements = data["rows"][0]["elements"]

        mode_icon = {"driving": "🚗", "transit": "🚌", "bicycling": "🚲", "walking": "🚶"}.get(nav_mode, "🚘")

        out = [
            f"⏱️ **Commute Times & Distance Summary** ({mode_icon} {nav_mode.capitalize()})",
            f"**Origin**: {origin_addr}\n",
        ]

        first_valid_dest = ""
        for idx, elem in enumerate(elements):
            d_addr = dest_addrs[idx] if idx < len(dest_addrs) else dest_list[idx]
            status = elem.get("status")
            if status == "OK":
                dist = elem.get("distance", {}).get("text", "N/A")
                dur = elem.get("duration", {}).get("text", "N/A")
                dur_in_traffic = elem.get("duration_in_traffic", {}).get("text")
                traffic_str = f" (in traffic: {dur_in_traffic})" if dur_in_traffic else ""
                out.append(f"• **{d_addr}**: {dur}{traffic_str} · {dist}")
                if not first_valid_dest:
                    first_valid_dest = d_addr
            else:
                out.append(f"• **{d_addr}**: Unavailable ({status})")

        target_dest = first_valid_dest or (dest_addrs[0] if dest_addrs else "")
        if target_dest:
            embed_code = generate_map_embed_iframe(origin=origin_addr, destination=target_dest, mode=nav_mode, embed_type="directions")
            out.append(f"\n{embed_code}")

        return "\n".join(out)
    except Exception as exc:
        return f"[maps_commute error] {exc}"


async def maps_embed(
    query_or_place: str = "",
    embed_type: str = "place",
    origin: str = "",
    destination: str = "",
    mode: str = "driving",
) -> str:
    """Generate embed code / snippet for a Google Map."""
    key = _get_api_key()
    if not key:
        return "Error: GOOGLE_MAPS_API_KEY is not configured in .env"

    iframe_code = generate_map_embed_iframe(
        q_or_place=query_or_place,
        embed_type=embed_type,
        origin=origin,
        destination=destination,
        mode=mode,
    )
    return f"Here is your interactive map embed:\n\n{iframe_code}"
