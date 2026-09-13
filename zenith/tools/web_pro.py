"""Advanced Web Interaction Suite — Full-page web screenshots, structured web scraping, and data extraction.

Allows Zenith to capture high-res web screenshots (rendered in chat), extract structured
HTML data (tables, lists, text), and interact with dynamic sites.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from ..core.config import settings
from .browser import get_browser

_SCREENSHOTS_DIR = settings.screenshots_dir


async def web_screenshot_full(url: str, full_page: bool = True) -> str:
    """Capture a high-resolution screenshot of any webpage using Playwright and embed it in chat."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    fname = f"web_{ts}.png"
    out_path = _SCREENSHOTS_DIR / fname

    try:
        b = await get_browser()
        page = await b.new_page(viewport={"width": 1280, "height": 800})
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.5)  # Wait for animations/images to settle
            await page.screenshot(path=str(out_path), full_page=full_page)
        finally:
            await page.close()

        rel_url = f"/static/screenshots/{fname}"
        return (f"### 📷 Webpage Screenshot ({url}):\n\n"
                f"![Screenshot: {url}]({rel_url})\n\n"
                f"Saved to `{out_path}`.")
    except Exception as exc:
        return f"[web_screenshot error]: {exc}"


async def web_extract_data(url: str, selector: str = "", extract_type: str = "text") -> str:
    """Extract structured data (tables, links, text, headings, emails) from a webpage."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Zenith Assistant)"})

        if resp.status_code >= 400:
            return f"[web_extract error]: HTTP {resp.status_code}"

        html = resp.text

        # Extract Emails
        if extract_type == "emails":
            emails = sorted(list(set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html))))
            return f"### ✉️ Emails Found on {url}:\n" + ("\n".join([f"- {e}" for e in emails]) if emails else "No emails found.")

        # Extract Links
        if extract_type == "links":
            links = re.findall(r'href=["\'](https?://[^"\']+)["\']', html)
            unique_links = sorted(list(set(links)))[:25]
            return f"### 🔗 Links Found on {url}:\n" + ("\n".join([f"- {l}" for l in unique_links]) if unique_links else "No links found.")

        # Extract Headings (H1, H2, H3)
        if extract_type == "headings":
            headings = re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.DOTALL | re.IGNORECASE)
            clean_h = [re.sub(r'<[^>]+>', '', h).strip() for h in headings if h.strip()]
            return f"### 🏷️ Headings on {url}:\n" + ("\n".join([f"- {h}" for h in clean_h[:30]]) if clean_h else "No headings found.")

        # Default text extraction
        text = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines[:60])

        return f"### 📄 Extracted Content from {url}:\n\n```\n{clean_text[:3000]}\n```"

    except Exception as exc:
        return f"[web_extract error]: {exc}"
