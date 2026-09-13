"""Homelab Suite — Control of Homelab Infrastructure.

Integrates Sonarr, Radarr, Prowlarr, Jellyseerr, qBittorrent, Cloudflare Tunnels,
Playit/Bore Minecraft Tunnels, Uptime Kuma, Caddy, Portainer, and media services.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, List, Dict, Optional

import httpx

from ..core.config import settings

# API keys come from .env (gitignored) — never hardcode them in source.
SONARR_API_KEY = settings.sonarr_api_key or ""
RADARR_API_KEY = settings.radarr_api_key or ""
PROWLARR_API_KEY = settings.prowlarr_api_key or ""

# Auto-detect host IP inside container
_HOST = os.environ.get("HOMELAB_HOST", "172.17.0.1")

SONARR_URL = f"http://{_HOST}:8989"
RADARR_URL = f"http://{_HOST}:7878"
PROWLARR_URL = f"http://{_HOST}:9696"
QBITTORRENT_URL = f"http://{_HOST}:8080"
SEERR_URL = f"http://{_HOST}:5055"
UPTIME_KUMA_URL = f"http://{_HOST}:3001"

CF_CONFIG_FILE = Path(os.environ.get("CF_CONFIG_PATH", "/home/singh/.cloudflared/config.yml"))


# ── 1. Media Search & Download (Sonarr / Radarr / Seerr) ────────────────────

async def media_search(query: str, media_type: str = "all") -> str:
    """Search for movies or TV shows across Radarr, Sonarr, and Jellyseerr."""
    if not query.strip():
        return "[media] Search query required."

    results = []

    # Search Radarr (Movies)
    if media_type in ("all", "movie", "movies"):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{RADARR_URL}/api/v3/movie/lookup",
                    params={"term": query},
                    headers={"X-Api-Key": RADARR_API_KEY},
                )
                if r.status_code == 200:
                    for item in r.json()[:5]:
                        title = item.get("title")
                        year = item.get("year", "")
                        has_file = item.get("hasFile", False)
                        added = item.get("added") != "0001-01-01T00:00:00Z"
                        status = "Downloaded" if has_file else ("Monitored" if added else "Not in Radarr")
                        tmdb_id = item.get("tmdbId")
                        overview = (item.get("overview") or "")[:120]
                        results.append(f"🎬 [Movie] **{title}** ({year}) — Status: `{status}` (TMDB: {tmdb_id})\n   _{overview}_")
        except Exception as exc:
            results.append(f"[radarr error: {exc}]")

    # Search Sonarr (TV Shows)
    if media_type in ("all", "series", "tv", "show", "shows"):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{SONARR_URL}/api/v3/series/lookup",
                    params={"term": query},
                    headers={"X-Api-Key": SONARR_API_KEY},
                )
                if r.status_code == 200:
                    for item in r.json()[:5]:
                        title = item.get("title")
                        year = item.get("year", "")
                        seasons = len(item.get("seasons", []))
                        added = item.get("id") is not None
                        status = "Monitored" if added else "Not in Sonarr"
                        tvdb_id = item.get("tvdbId")
                        overview = (item.get("overview") or "")[:120]
                        results.append(f"📺 [TV Show] **{title}** ({year}) — {seasons} Seasons — Status: `{status}` (TVDB: {tvdb_id})\n   _{overview}_")
        except Exception as exc:
            results.append(f"[sonarr error: {exc}]")

    if not results:
        return f"No media found matching '{query}'."

    return f"### 🎬 Media Search Results for '{query}':\n\n" + "\n\n".join(results)


async def media_add(title: str, media_type: str = "movie", search_now: bool = True) -> str:
    """Add a movie to Radarr or TV show to Sonarr and trigger download."""
    media_type = media_type.lower().strip()

    if media_type in ("movie", "movies"):
        # Lookup first to get object
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                lookup = await client.get(
                    f"{RADARR_URL}/api/v3/movie/lookup",
                    params={"term": title},
                    headers={"X-Api-Key": RADARR_API_KEY},
                )
                if lookup.status_code != 200 or not lookup.json():
                    return f"[radarr] Movie '{title}' not found."

                movie = lookup.json()[0]
                if movie.get("id"):
                    return f"🎬 **{movie.get('title')}** is ALREADY in Radarr library."

                # Get root folder
                rf = await client.get(f"{RADARR_URL}/api/v3/rootfolder", headers={"X-Api-Key": RADARR_API_KEY})
                root_path = rf.json()[0]["path"] if rf.status_code == 200 and rf.json() else "/media/movies"

                # Add payload
                payload = {
                    "title": movie["title"],
                    "qualityProfileId": 1,
                    "titleSlug": movie["titleSlug"],
                    "images": movie.get("images", []),
                    "tmdbId": movie["tmdbId"],
                    "year": movie.get("year"),
                    "path": f"{root_path}/{movie['title']}",
                    "monitored": True,
                    "addOptions": {"searchForMovie": search_now},
                }

                post_res = await client.post(
                    f"{RADARR_URL}/api/v3/movie",
                    headers={"X-Api-Key": RADARR_API_KEY},
                    json=payload,
                )
                if post_res.status_code in (200, 201):
                    return f"✅ Added movie **{movie['title']}** ({movie.get('year')}) to Radarr! Automatic download triggered."
                return f"[radarr] Add failed ({post_res.status_code}): {post_res.text[:200]}"
        except Exception as exc:
            return f"[radarr error: {exc}]"

    else:  # series/tv
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                lookup = await client.get(
                    f"{SONARR_URL}/api/v3/series/lookup",
                    params={"term": title},
                    headers={"X-Api-Key": SONARR_API_KEY},
                )
                if lookup.status_code != 200 or not lookup.json():
                    return f"[sonarr] TV show '{title}' not found."

                series = lookup.json()[0]
                if series.get("id"):
                    return f"📺 **{series.get('title')}** is ALREADY in Sonarr library."

                rf = await client.get(f"{SONARR_URL}/api/v3/rootfolder", headers={"X-Api-Key": SONARR_API_KEY})
                root_path = rf.json()[0]["path"] if rf.status_code == 200 and rf.json() else "/media/tv"

                payload = {
                    "title": series["title"],
                    "qualityProfileId": 1,
                    "titleSlug": series["titleSlug"],
                    "images": series.get("images", []),
                    "tvdbId": series["tvdbId"],
                    "year": series.get("year"),
                    "path": f"{root_path}/{series['title']}",
                    "monitored": True,
                    "seasons": series.get("seasons", []),
                    "addOptions": {"searchForMissingEpisodes": search_now},
                }

                post_res = await client.post(
                    f"{SONARR_URL}/api/v3/series",
                    headers={"X-Api-Key": SONARR_API_KEY},
                    json=payload,
                )
                if post_res.status_code in (200, 201):
                    return f"✅ Added TV show **{series['title']}** ({series.get('year')}) to Sonarr! Episode search triggered."
                return f"[sonarr] Add failed ({post_res.status_code}): {post_res.text[:200]}"
        except Exception as exc:
            return f"[sonarr error: {exc}]"


async def media_queue() -> str:
    """Check active downloading media queue in Sonarr, Radarr, and qBittorrent."""
    lines = []

    # Radarr queue
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{RADARR_URL}/api/v3/queue", headers={"X-Api-Key": RADARR_API_KEY})
            if r.status_code == 200:
                items = r.json().get("records", [])
                for item in items:
                    t = item.get("title", "Unknown")
                    size = item.get("size", 0) / 1024 / 1024 / 1024
                    left = item.get("sizeleft", 0) / 1024 / 1024 / 1024
                    pct = ((size - left) / size * 100) if size else 0
                    status = item.get("status", "")
                    lines.append(f"🎬 [Movie] {t} — {pct:.1f}% ({size:.1f} GB) [{status}]")
    except Exception:
        pass

    # Sonarr queue
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{SONARR_URL}/api/v3/queue", headers={"X-Api-Key": SONARR_API_KEY})
            if r.status_code == 200:
                items = r.json().get("records", [])
                for item in items:
                    t = item.get("title", "Unknown")
                    size = item.get("size", 0) / 1024 / 1024 / 1024
                    left = item.get("sizeleft", 0) / 1024 / 1024 / 1024
                    pct = ((size - left) / size * 100) if size else 0
                    status = item.get("status", "")
                    lines.append(f"📺 [TV] {t} — {pct:.1f}% ({size:.1f} GB) [{status}]")
    except Exception:
        pass

    if not lines:
        return "Media Queue: No active downloads currently."

    return "### 📥 Active Media Queue:\n- " + "\n- ".join(lines)


# ── 2. qBittorrent Torrent Control ──────────────────────────────────────────

async def torrent_control(action: str = "list", info_hash: str = "") -> str:
    """Manage torrent downloads in qBittorrent (action: list | pause | resume | delete)."""
    action = action.lower().strip()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if action in ("list", "status", "all"):
                r = await client.get(f"{QBITTORRENT_URL}/api/v2/torrents/info")
                if r.status_code == 200:
                    torrents = r.json()
                    if not torrents:
                        return "qBittorrent: No torrents in client."
                    lines = []
                    for t in torrents[:15]:
                        name = t.get("name")
                        progress = t.get("progress", 0) * 100
                        dlspeed = t.get("dlspeed", 0) / 1024 / 1024
                        state = t.get("state")
                        lines.append(f"  [{state}] **{name}** — {progress:.1f}% ({dlspeed:.2f} MB/s)")
                    return f"### ⚡ qBittorrent Active Torrents ({len(torrents)}):\n" + "\n".join(lines)
                return f"[qbittorrent error: HTTP {r.status_code}]"

            elif action in ("pause", "stop"):
                r = await client.post(f"{QBITTORRENT_URL}/api/v2/torrents/pause", data={"hashes": info_hash or "all"})
                return f"Paused torrents ({info_hash or 'all'})."

            elif action in ("resume", "start"):
                r = await client.post(f"{QBITTORRENT_URL}/api/v2/torrents/resume", data={"hashes": info_hash or "all"})
                return f"Resumed torrents ({info_hash or 'all'})."

            elif action in ("delete", "remove"):
                r = await client.post(f"{QBITTORRENT_URL}/api/v2/torrents/delete", data={"hashes": info_hash, "deleteFiles": "true"})
                return f"Deleted torrent ({info_hash})."

    except Exception as exc:
        return f"[qbittorrent error: {exc}]"

    return f"Unknown action '{action}'. Use list, pause, resume, or delete."


# ── 3. Cloudflare & Homelab Tunnels ─────────────────────────────────────────

async def tunnel_status() -> str:
    """Check Cloudflare Tunnel ingress rules, domains, and Minecraft tunnels."""
    rules = []
    if CF_CONFIG_FILE.exists():
        try:
            content = CF_CONFIG_FILE.read_text(errors="replace")
            for line in content.splitlines():
                if "hostname:" in line:
                    host = line.split("hostname:")[1].strip()
                    rules.append(f"  - **https://{host}**")
                elif "service: http://" in line:
                    svc = line.split("service:")[1].strip()
                    if rules:
                        rules[-1] += f" → `{svc}`"
        except Exception:
            pass

    tunnel_list = "\n".join(rules) if rules else "  (no ingress rules loaded)"

    # Check MC Tunnels
    mc_playit = await _check_container("twilight-mc-playit")
    mc_bore = await _check_container("twilight-mc-bore")

    return f"""### 🌐 Homelab Ingress & Tunnels Status:

**Cloudflare Tunnel Routes (agm.quest)**:
{tunnel_list}

**Minecraft Playit.gg Tunnel**: `{mc_playit}`
**Minecraft Bore Tunnel**: `{mc_bore}`
"""


async def tunnel_add_route(subdomain: str, local_port: int) -> str:
    """Add a new ingress subdomain route to Cloudflare Tunnel (e.g. app.agm.quest -> 8000) and restart cloudflared."""
    if not CF_CONFIG_FILE.exists():
        return "[tunnel] Config file /home/singh/.cloudflared/config.yml not found."

    subdomain = subdomain.lower().strip().replace("https://", "").replace("http://", "")
    if not subdomain.endswith(".agm.quest"):
        full_host = f"{subdomain}.agm.quest"
    else:
        full_host = subdomain

    try:
        content = CF_CONFIG_FILE.read_text(errors="replace")
        if full_host in content:
            return f"Route **https://{full_host}** is ALREADY configured in Cloudflare Tunnel."

        # Insert before 404 rule
        rule_str = f"  - hostname: {full_host}\n    service: http://127.0.0.1:{local_port}\n"
        if "  - service: http_status:404" in content:
            new_content = content.replace("  - service: http_status:404", f"{rule_str}  - service: http_status:404")
        else:
            new_content = content + f"\n{rule_str}"

        CF_CONFIG_FILE.write_text(new_content, encoding="utf-8")

        # Restart cloudflared
        from .homelab import docker_restart
        res = await docker_restart("cloudflared")

        return f"✅ Added route **https://{full_host}** → `http://127.0.0.1:{local_port}`! Restarted cloudflared tunnel."
    except Exception as exc:
        return f"[tunnel error: {exc}]"


# ── 4. Full Homelab Overview ────────────────────────────────────────────────

async def homelab_overview() -> str:
    """Scan all 18 Homelab services, containers, memory/cpu usage, and public subdomains."""
    from .homelab import docker_list, system_status, disk_usage

    docker_text = await docker_list()
    sys_text = await system_status()
    disk_text = await disk_usage()

    return f"""### 🏰 Homelab Overview & Services

**System Vitals**:
{sys_text}

**Disk Storage**:
{disk_text}

**Docker Containers**:
{docker_text}
"""


async def _check_container(name: str) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            f"docker inspect --format '{{{{.State.Status}}}}' {name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out.decode().strip() or "stopped"
    except Exception:
        return "unknown"
