"""Jellyfin Media & Homelab Manager — server health, active playback sessions, search, and recent media."""
from __future__ import annotations

import os
import httpx
from ..core.config import settings

JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://localhost:8096").rstrip("/")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "")


def _jf_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if JELLYFIN_API_KEY:
        headers["X-Emby-Token"] = JELLYFIN_API_KEY
    return headers


async def jellyfin_status() -> str:
    """Check Jellyfin server status and active playback sessions."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(f"{JELLYFIN_URL}/System/Info/Public", headers=_jf_headers())
            if res.status_code != 200:
                return f"[jellyfin] Server response {res.status_code} at {JELLYFIN_URL}."
            info = res.json()
            server_name = info.get("ServerName", "Jellyfin")
            version = info.get("Version", "unknown")

            # Check active sessions if API key available
            sessions_str = ""
            if JELLYFIN_API_KEY:
                try:
                    s_res = await client.get(f"{JELLYFIN_URL}/Sessions", headers=_jf_headers())
                    if s_res.status_code == 200:
                        sessions = s_res.json()
                        active = [s for s in sessions if s.get("NowPlayingItem")]
                        if active:
                            lines = []
                            for s in active:
                                item = s.get("NowPlayingItem", {})
                                user = s.get("UserName", "Unknown User")
                                device = s.get("DeviceName", "Unknown Device")
                                title = item.get("Name", "Untitled")
                                series = item.get("SeriesName")
                                item_name = f"{series} - {title}" if series else title
                                lines.append(f"- {user} playing '{item_name}' on {device}")
                            sessions_str = "\nNow Playing:\n" + "\n".join(lines)
                        else:
                            sessions_str = "\nNo active playback sessions."
                except Exception:
                    pass

            return f"Jellyfin Server '{server_name}' v{version} is online ({JELLYFIN_URL}).{sessions_str}"
    except Exception as exc:
        return f"[jellyfin] Server unreachable at {JELLYFIN_URL}: {exc}"


async def jellyfin_search(query: str, media_type: str = "") -> str:
    """Search Jellyfin media library for titles (movies, shows, episodes, music)."""
    if not query:
        return "[jellyfin] Provide a search query."
    if not JELLYFIN_API_KEY:
        return "[jellyfin] JELLYFIN_API_KEY environment variable is required to search the library."

    params = {"SearchTerm": query, "Limit": 10}
    if media_type:
        params["IncludeItemTypes"] = media_type

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"{JELLYFIN_URL}/Items", headers=_jf_headers(), params=params)
            if res.status_code != 200:
                return f"[jellyfin] Search failed ({res.status_code})."
            items = res.json().get("Items", [])
            if not items:
                return f"No items found matching '{query}' in Jellyfin library."

            lines = []
            for it in items:
                name = it.get("Name", "?")
                kind = it.get("Type", "?")
                year = it.get("ProductionYear", "")
                year_str = f" ({year})" if year else ""
                lines.append(f"- [{kind}] {name}{year_str}")
            return f"Jellyfin Search results for '{query}':\n" + "\n".join(lines)
    except Exception as exc:
        return f"[jellyfin error] {exc}"


async def jellyfin_recent(limit: int = 8) -> str:
    """List recently added items in Jellyfin library."""
    if not JELLYFIN_API_KEY:
        return "[jellyfin] JELLYFIN_API_KEY environment variable is required to list recent media."

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"{JELLYFIN_URL}/Items/Latest", headers=_jf_headers(), params={"Limit": min(limit, 20)})
            if res.status_code != 200:
                return f"[jellyfin] Recent items request failed ({res.status_code})."
            items = res.json()
            if not items:
                return "No recent items found in Jellyfin."

            lines = []
            for it in items:
                name = it.get("Name", "?")
                kind = it.get("Type", "?")
                lines.append(f"- [{kind}] {name}")
            return "Recently added to Jellyfin:\n" + "\n".join(lines)
    except Exception as exc:
        return f"[jellyfin error] {exc}"
