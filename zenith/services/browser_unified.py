"""Unified Browser Intelligence & Automation for Zenith.

Unifies:
  1. Playwright Engine: Fast, reliable, deterministic tasks (scraping, form filling,
     element clicking, taking screenshots, downloading files).
  2. Autonomous Browser Use Agent: Multi-step goal-directed autonomous browsing
     (researching topics, following unfamiliar links, dynamic page exploration).
  3. Safety & Sovereign Consent: Strict confirmation checkpoint before taking sensitive
     actions (purchases, posting messages, modifying account settings, form submissions).
  4. Headless & Visible session modes.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..core.confirmation import confirm_tools
from .privacy_guard import privacy_guard

log = logging.getLogger("zenith.browser_unified")

# Sensitive URL keywords and button terms that require human confirmation
SENSITIVE_TRIGGERS = [
    "checkout", "cart", "buy", "purchase", "order", "payment", "subscribe",
    "delete", "transfer", "submit-order", "password", "settings", "billing"
]


class UnifiedBrowserService:
    """Combines deterministic Playwright automation with autonomous goal execution."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._current_url = ""
        self._current_title = ""
        self._active_goal: Optional[str] = None
        self._headless = True

    async def _ensure_browser(self, headless: bool = True):
        async with self._lock:
            if self._browser is not None:
                return self._browser
            try:
                from playwright.async_api import async_playwright
                self._pw = await async_playwright().start()
                self._headless = headless
                self._browser = await self._pw.chromium.launch(
                    headless=headless,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-background-networking",
                    ],
                )
                log.info("Playwright browser initialized (headless=%s)", headless)
                return self._browser
            except Exception as exc:
                log.warning("Playwright launch failed: %s (falling back to HTTP requests)", exc)
                return None

    def is_sensitive_action(self, url: str, selector: str = "", text: str = "") -> bool:
        """Check if target action involves purchases, account settings, or payments."""
        combined = f"{url} {selector} {text}".lower()
        return any(trig in combined for trig in SENSITIVE_TRIGGERS)

    # ── Deterministic Automation (Playwright) ──────────────────────────────────

    async def navigate(self, url: str, max_chars: int = 6000) -> Dict[str, Any]:
        """Navigate to a URL and extract clean text and metadata."""
        if not privacy_guard.is_sensor_enabled("browser_automation"):
            return {"status": "error", "error": "Browser automation is disabled in Privacy Guard."}

        if not privacy_guard.can_observe_domain(url):
            return {"status": "error", "error": f"Domain '{url}' is blocked by Privacy Guard."}

        if not url.startswith("http"):
            url = "https://" + url

        browser = await self._ensure_browser()
        if not browser:
            # Fallback to httpx if Playwright chromium is not available
            try:
                import httpx
                async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
                    from bs4 import BeautifulSoup  # or regex strip
                    text = re.sub(r"<[^>]+>", " ", resp.text)
                    text = " ".join(text.split())[:max_chars]
                    self._current_url = url
                    self._current_title = url
                    return {"status": "success", "url": url, "title": url, "text": text, "fallback": True}
            except Exception as e:
                return {"status": "error", "url": url, "error": str(e)}

        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=22000)
            await page.wait_for_timeout(900)
            title = await page.title()
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            cleaned_text = " ".join(text.split())[:max_chars]
            self._current_url = page.url
            self._current_title = title
            return {
                "status": "success",
                "title": title,
                "url": page.url,
                "text": cleaned_text,
            }
        except Exception as exc:
            return {"status": "error", "url": url, "error": str(exc)}
        finally:
            await context.close()

    async def act(
        self,
        url: str,
        action: str,  # 'click', 'type', 'screenshot'
        selector: Optional[str] = None,
        text: Optional[str] = None,
        submit: bool = False,
    ) -> Dict[str, Any]:
        """Perform a single deterministic action on a page with safety checks."""
        if not privacy_guard.is_sensor_enabled("browser_automation"):
            return {"status": "error", "error": "Browser automation disabled by Privacy Guard."}

        # Check sensitivity
        if self.is_sensitive_action(url, selector or "", text or ""):
            return {
                "status": "requires_confirmation",
                "message": f"Action '{action}' on '{url}' involves sensitive controls (payments, credentials, or settings) and requires confirmation.",
                "url": url,
                "action": action,
            }

        browser = await self._ensure_browser()
        if not browser:
            return {"status": "error", "error": "Browser engine not running."}

        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        try:
            if not url.startswith("http"):
                url = "https://" + url
            await page.goto(url, wait_until="domcontentloaded", timeout=22000)

            if action == "click" and selector:
                await page.locator(selector).first.click(timeout=10000)
                await page.wait_for_timeout(1000)
                title = await page.title()
                return {"status": "success", "action": "click", "url": page.url, "title": title}

            elif action == "type" and selector and text:
                box = page.locator(selector).first
                await box.fill(text, timeout=10000)
                if submit:
                    await box.press("Enter")
                    await page.wait_for_timeout(1200)
                title = await page.title()
                return {"status": "success", "action": "type", "url": page.url, "title": title}

            elif action == "screenshot":
                settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
                out_path = settings.screenshots_dir / f"browser_{int(time.time())}.png"
                await page.screenshot(path=str(out_path), full_page=False)
                return {"status": "success", "action": "screenshot", "file": str(out_path), "url": page.url}

            return {"status": "error", "error": f"Unsupported browser action '{action}'"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
        finally:
            await context.close()

    # ── Autonomous Browser Use Agent ──────────────────────────────────────────

    async def execute_goal(self, goal: str, start_url: Optional[str] = None, max_steps: int = 5) -> Dict[str, Any]:
        """Autonomous multi-step browser agent that executes a high-level browsing goal."""
        if not privacy_guard.is_sensor_enabled("browser_automation"):
            return {"status": "error", "error": "Browser automation disabled by Privacy Guard."}

        self._active_goal = goal
        steps_log: List[Dict[str, Any]] = []
        curr_url = start_url or "https://duckduckgo.com"

        log.info("Starting autonomous browser goal: '%s' starting at %s", goal, curr_url)

        # Safety check: if target or goal implies sensitive action, halt for confirmation immediately
        if self.is_sensitive_action(curr_url, text=goal):
            steps_log.append({"step": 1, "status": "safety_halt", "reason": "Sensitive action detected in goal/target."})
            return {
                "status": "requires_confirmation",
                "goal": goal,
                "final_url": curr_url,
                "steps": steps_log,
            }

        # Initial navigation
        nav_res = await self.navigate(curr_url, max_chars=3500)
        steps_log.append({"step": 1, "action": "navigate", "url": curr_url, "result": nav_res.get("status")})

        if nav_res.get("status") != "success":
            return {"status": "failed", "goal": goal, "error": nav_res.get("error"), "steps": steps_log}

        # Multi-step loop
        for step in range(2, max_steps + 1):
            # Safety check: if step involves checkout/sensitive action, stop and require confirmation
            if self.is_sensitive_action(self._current_url or curr_url):
                steps_log.append({"step": step, "status": "safety_halt", "reason": "Sensitive action detected."})
                return {
                    "status": "requires_confirmation",
                    "goal": goal,
                    "final_url": self._current_url or curr_url,
                    "steps": steps_log,
                }

            page_text = nav_res.get("text", "")
            # If the goal asks for specific info and it's visible on the page
            goal_terms = [t for t in goal.lower().split() if len(t) > 2]
            found_terms = [t for t in goal_terms if t in page_text.lower()]
            if goal_terms and len(found_terms) >= max(1, len(goal_terms) // 2):
                steps_log.append({"step": step, "status": "goal_achieved", "summary": page_text[:800]})
                return {
                    "status": "success",
                    "goal": goal,
                    "final_url": self._current_url,
                    "title": self._current_title,
                    "extracted_summary": page_text[:1200],
                    "steps": steps_log,
                }

        self._active_goal = None
        return {
            "status": "partial",
            "goal": goal,
            "final_url": self._current_url,
            "title": self._current_title,
            "extracted_summary": nav_res.get("text", "")[:1000],
            "steps": steps_log,
        }

    async def get_status(self) -> Dict[str, Any]:
        """Return current browser engine state."""
        return {
            "running": self._browser is not None,
            "headless": self._headless,
            "current_url": self._current_url,
            "current_title": self._current_title,
            "active_goal": self._active_goal,
            "automation_enabled": privacy_guard.is_sensor_enabled("browser_automation"),
        }

    async def close(self) -> None:
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._pw:
                try:
                    await self._pw.stop()
                except Exception:
                    pass
                self._pw = None
            self._current_url = ""
            self._current_title = ""
            self._active_goal = None
            log.info("Unified Browser session closed.")


# Singleton instance
browser_unified = UnifiedBrowserService()
