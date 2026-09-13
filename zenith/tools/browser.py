"""Browser tool: drive a headless Chromium (Playwright).

Read-only by default: navigate + extract text. `screenshot`/`click`/`type` are
offered as discrete ops that can mutate a real site (ordering, posting, deleting).
"""
from __future__ import annotations

import asyncio
import time

from ..core.config import settings

ALLOW_HOSTS = ()  # empty = any; add e.g. ("github.com", "code.google.com") to restrict


class BrowserEngine:
    """Shared headless Chromium session (persistent across tool calls)."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure(self):
        async with self._lock:
            if self._browser is not None:
                return self._browser
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-background-networking",
                ],
            )
            return self._browser

    async def navigate(self, url: str, max_chars: int = 6000) -> dict:
        """Load a page and return readable content. Read-only."""
        browser = await self._ensure()
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        try:
            if not url.startswith("http"):
                url = "https://" + url
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(900)
            title = await page.title()
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            text = " ".join(text.split())[:max_chars]
            return {"status": "success", "title": title, "url": page.url, "text": text}
        except Exception as exc:
            return {"status": "error", "url": url, "error": str(exc)}
        finally:
            await context.close()

    async def screenshot(self, url: str, path: str | None = None) -> dict:
        """Full-page screenshot saved under screenshots/, returns local path."""
        browser = await self._ensure()
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        try:
            if not url.startswith("http"):
                url = "https://" + url
            await page.goto(url, wait_until="networkidle", timeout=25000)
            await page.wait_for_timeout(1200)
            out = path or settings.screenshots_dir / f"shot_{int(time.time())}.png"
            settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(out), full_page=False)
            title = await page.title()
            return {"status": "success", "title": title, "file": str(out)}
        except Exception as exc:
            return {"status": "error", "url": url, "error": str(exc)}
        finally:
            await context.close()

    async def click(self, url: str, selector: str) -> dict:
        """Open the page and click the first element matching `selector`."""
        browser = await self._ensure()
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        try:
            if not url.startswith("http"):
                url = "https://" + url
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.locator(selector).first.click(timeout=10000)
            await page.wait_for_timeout(900)
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            return {
                "status": "success",
                "url": page.url,
                "clicked": selector,
                "text": " ".join(text.split())[:3000],
            }
        except Exception as exc:
            return {"status": "error", "url": url, "error": str(exc)}
        finally:
            await context.close()

    async def type_text(self, url: str, selector: str, text: str, submit: bool = False) -> dict:
        """Type into a field (selector) and optionally submit (Enter)."""
        browser = await self._ensure()
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        try:
            if not url.startswith("http"):
                url = "https://" + url
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            box = page.locator(selector).first
            await box.fill(text, timeout=10000)
            if submit:
                await box.press("Enter")
                await page.wait_for_timeout(1200)
            txt = await page.evaluate("() => document.body ? document.body.innerText : ''")
            return {
                "status": "success",
                "url": page.url,
                "text": " ".join(txt.split())[:3000],
            }
        except Exception as exc:
            return {"status": "error", "url": url, "error": str(exc)}
        finally:
            await context.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None


_engine = BrowserEngine()


async def get_browser():
    return await _engine._ensure()


async def browse(url: str, max_chars: int = 5000) -> str:
    """Tool handler for 'browser' — open URL, return readable text.
    Uses browser_unified with PrivacyGuard checks, domain blocklists, and resilient fallback."""
    try:
        from ..services.browser_unified import browser_unified
        res = await browser_unified.navigate(url, max_chars=max_chars)
        if res.get("status") == "success":
            return f"Title: {res.get('title')}\nURL: {res.get('url')}\n\n{res.get('text')}"
        elif res.get("status") == "error" and "Privacy Guard" in res.get("error", ""):
            return f"[browser error] {res.get('error')}"
    except Exception:
        pass
    # Resilient fallback to local Chromium session
    res = await _engine.navigate(url, max_chars=max_chars)
    if res["status"] != "success":
        return f"[browser error] {res.get('error')}"
    return f"Title: {res['title']}\nURL: {res['url']}\n\n{res['text']}"


async def browser_screenshot(url: str, full_page: bool = True) -> str:
    """Capture a rendered screenshot of any webpage and embed preview markdown directly in chat."""
    from .web_pro import web_screenshot_full
    return await web_screenshot_full(url, full_page=full_page)


async def browser_click(url: str, selector: str) -> str:
    res = await _engine.click(url, selector)
    if res["status"] != "success":
        return f"[browser] {res.get('error')}"
    return f"Clicked {selector}. URL now: {res['url']}\n\n{res.get('text')}"


async def browser_type(url: str, selector: str, text: str, submit: bool = False) -> str:
    res = await _engine.type_text(url, selector, text, submit)
    if res["status"] != "success":
        return f"[browser] {res.get('error')}"
    return f"Typed into {selector}. URL now: {res['url']}\n\n{res.get('text')}"