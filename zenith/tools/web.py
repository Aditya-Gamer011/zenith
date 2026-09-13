"""Web tools: weather + search + URL reader.

Search/read_url try the llmsolutions relay first (/v1/search, /v1/read_url on
the same base as the chat fallback), then fall back to a privacy-friendly
ad-free scraper (DuckDuckGo HTML) / the in-process browser so Zenith always has
a working path even if the relay endpoints are down.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape as _unescape_html

import httpx

USER_AGENT = "ZenithAssistant/1.0 (personal assistant)"

try:
    from ..core.config import settings as _settings
except Exception:  # pragma: no cover — config unavailable in tests
    _settings = None


def _llms_base() -> str:
    """Base of the llmsolutions relay (e.g. https://llmsolutions.top) or ''."""
    key = getattr(_settings, "fallback_api_key", "")
    base = getattr(_settings, "fallback_endpoint", "") or ""
    if not key:
        return ""
    base = base.rstrip("/")
    # …/v1/chat/completions -> https://host
    host = re.sub(r"/v1/.*$", "", base)
    return host if host.startswith("http") else ""


async def _llms_get(path: str, params: dict, timeout: float = 25) -> str | None:
    """GET https://<host><path>?<params> with the fallback key; None on failure."""
    base = _llms_base()
    if not base:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={
                "Authorization": f"Bearer {_settings.fallback_api_key}",
                "User-Agent": USER_AGENT}) as client:
            resp = await client.get(f"{base}{path}", params=params)
            if resp.status_code != 200:
                return None
            return resp.text
    except Exception:
        return None


async def get_weather(location: str = "autodetect") -> str:
    """Fetch current weather via wttr.in (no key needed)."""
    loc = location if location and location != "auto" else "Dehradun"
    try:
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(f"https://wttr.in/{loc}?format=j1")
            resp.raise_for_status()
            data = resp.json()
        curr = data.get("current_condition", [{}])[0]
        area = data.get("nearest_area", [{}])[0]
        region = area.get("areaName", [{}])[0].get("value", loc)
        country = area.get("country", [{}])[0].get("value", "")
        lines = [
            f"Weather in {region}, {country}",
            f"Condition: {curr.get('weatherDesc', [{}])[0].get('value', 'unknown')}",
            f"Temp: {curr.get('temp_C', '?')}°C (feels {curr.get('FeelsLikeC', '?')}°C)",
            f"Humidity: {curr.get('humidity', '?')}%",
            f"Wind: {curr.get('windspeedKmph', '?')} km/h",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"[weather error] {exc}"


async def _llms_search(query: str) -> str:
    """Search via llmsolutions /v1/search; '' when unavailable/errors."""
    raw = await _llms_get("/v1/search", {"q": query})
    if not raw:
        return ""
    try:
        data = json.loads(raw)
        items = data.get("results") or data.get("data") or (
            data if isinstance(data, list) else [])
        lines = []
        for it in items[:6]:
            if not isinstance(it, dict):
                continue
            title = re.sub(r"<[^>]+>", "", it.get("title", "")) or it.get("title", "")
            snip = re.sub(r"<[^>]+>", "", it.get("snippet", "") or it.get("description", ""))
            lines.append(f"- {title}\n  {snip}\n  {it.get('url', it.get('link', ''))}")
        if lines:
            return f"Top results for: {query}\n" + "\n".join(lines)
    except Exception:
        pass
    return ""


async def web_search(query: str) -> str:
    """Search the web. Tries the llmsolutions relay, falls back to DDG."""
    via_llms = await _llms_search(query)
    if via_llms:
        return via_llms

    # Fallback: DuckDuckGo HTML scraper.
    url = "https://html.duckduckgo.com/html/"
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url, params={"q": query})
            resp.raise_for_status()
            text = resp.text
    except Exception as exc:
        return f"[search error] {exc}"

    # Parse result links + snippets quickly (no bs4 dependency).
    import re
    import html as html_mod

    results = []
    # Each <a class="result__a" href="...">TITLE</a> + <a class="result__snippet">...</a>
    for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        results.append({"title": html_mod.unescape(title).strip(), "url": href})
        if len(results) >= 6:
            break
    snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', text)
    for i, s in enumerate(snippets[:6]):
        clean = re.sub(r"<[^>]+>", "", s)
        clean = html_mod.unescape(clean).strip()
        if i < len(results):
            results[i]["snippet"] = clean

    if not results:
        return f"No results for '{query}'."
    out = [f"Top results for: {query}"]
    for r in results:
        out.append(f"- {r.get('title')}\n  {r.get('snippet', '')}\n  {r['url']}")
    return "\n".join(out)


async def read_url(url: str) -> str:
    """Read + summarize a URL. Tries llmsolutions /v1/read_url, falls back to
    the in-process browser so the agent can fetch arbitrary pages safely."""
    if not url:
        return "Provide a URL."
    if not (url.startswith("http://") or url.startswith("https://")):
        return "URL must start with http(s)://"
    via_llms = await _llms_get("/v1/read_url", {"url": url})
    if via_llms:
        # Trust the relay's own summary/extraction; strip obvious markup.
        try:
            data = json.loads(via_llms)
            title = data.get("title") or data.get("metadata", {}).get("title", "")
            text = data.get("text") or data.get("content") or data.get("summary", "")
            if not text:
                return via_llms[:2000]
            head = f"Title: {title}\n\n" if title else ""
            return (head + _unescape_html(re.sub(r"<[^>]+>", " ", text)))[-6000:]
        except Exception:
            cleaned = _unescape_html(re.sub(r"<[^>]+>", " ", via_llms))
            return cleaned[-6000:]

    # Fallback: in-process browser read (already SSRF-safe HTTP client).
    try:
        from zenith.tools.browser import browse
        return await browse(url)
    except Exception as exc:
        return f"[read_url error] {exc}"