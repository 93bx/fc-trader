"""FC 26 WEB APP — Playwright browser session lifecycle manager."""

from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from web.anti_detect.fingerprint import FingerprintEngine
from web.anti_detect.proxy import ProxyRotator
from web.anti_detect.stealth import StealthEngine
from web.anti_detect.timing import KSATiming
from web.config_loader import WebConfig

_CHROMIUM_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-notifications",
    "--disable-popup-blocking",
    "--window-size=1920,1080",
    "--start-maximized",
    "--lang=ar-SA",
    "--disable-extensions",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--force-color-profile=srgb",
    "--metrics-recording-only",
    "--disable-default-apps",
    "--mute-audio",
    "--hide-scrollbars",
    "--ignore-certificate-errors",
]


class BrowserSession:
    """Async context manager for a single Playwright Chromium session."""

    def __init__(
        self,
        cfg: WebConfig,
        fingerprint: FingerprintEngine,
        stealth: StealthEngine,
        proxy: ProxyRotator,
        timing: KSATiming,
    ) -> None:
        """Store all dependencies; browser not started until start() is called."""
        self._cfg = cfg
        self._fingerprint = fingerprint
        self._stealth = stealth
        self._proxy = proxy
        self._timing = timing

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._session_start: float = 0.0

    # ── context manager protocol ──────────────────────────────────────────────

    async def __aenter__(self) -> "BrowserSession":
        """Start browser on context entry."""
        if not await self.start():
            raise RuntimeError("BrowserSession failed to start")
        return self

    async def __aexit__(self, *_) -> None:
        """Stop browser on context exit regardless of exceptions."""
        await self.stop()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> bool:
        """Launch Playwright, open Chromium with stealth args, create page."""
        try:
            self._playwright = await async_playwright().start()
            proxy_args = self._proxy.get_current()
            launch_kwargs: dict = {
                "headless": self._cfg.browser.headless,
                "slow_mo": self._cfg.browser.slow_mo,
                "args": _CHROMIUM_ARGS + [f"--user-agent={self._cfg.anti_detect.user_agent}"],
            }
            if proxy_args:
                launch_kwargs["proxy"] = proxy_args

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            ctx_kwargs = self._fingerprint.get_playwright_context_args()

            storage_path = Path(self._cfg.browser.user_data_dir)
            if storage_path.exists():
                ctx_kwargs["storage_state"] = str(storage_path)
                logger.debug("Reloading browser storage state from {}.", storage_path)

            self._context = await self._browser.new_context(**ctx_kwargs)
            self._page = await self._context.new_page()
            await self._stealth.inject(self._page)
            self._session_start = time.monotonic()
            self._timing.reset_session_timer()

            version = self._browser.version
            logger.debug("Browser started: version={} headless={}", version, self._cfg.browser.headless)
            return True

        except Exception as exc:
            logger.error("BrowserSession.start failed: {}", exc)
            return False

    async def stop(self) -> None:
        """Gracefully close page, context, browser, playwright."""
        elapsed = time.monotonic() - self._session_start if self._session_start else 0
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as exc:
            logger.debug("BrowserSession.stop error (ignored): {}", exc)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            logger.info("Browser stopped after {:.0f}s.", elapsed)

    async def save_session(self) -> None:
        """Persist cookies/storage state to disk for session resumption."""
        if self._context is None:
            logger.warning("save_session called but context is not open.")
            return
        path = self._cfg.browser.user_data_dir
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            await self._context.storage_state(path=path)
            logger.debug("Session state saved to {}.", path)
        except Exception as exc:
            logger.warning("save_session failed: {}", exc)

    async def restart(self, reason: str) -> bool:
        """Stop browser, rotate proxy, wait briefly, restart."""
        logger.info("Browser restart: {}", reason)
        await self.stop()
        self._proxy.rotate()
        delay = random.uniform(15, 30)
        await asyncio.sleep(delay)
        ok = await self.start()
        if ok and self._page:
            await self._stealth.inject(self._page)
        return ok

    # ── navigation ────────────────────────────────────────────────────────────

    async def goto(self, url: str, wait_until: str = "networkidle") -> bool:
        """Navigate active page to url; apply page-load pause afterwards."""
        if self._page is None:
            logger.warning("goto called without active page.")
            return False
        try:
            await self._page.goto(url, wait_until=wait_until, timeout=45_000)
            await asyncio.sleep(self._timing.page_load_pause())
            return True
        except Exception as exc:
            logger.debug("goto({}) failed: {}", url, exc)
            return False

    async def new_page(self) -> Page:
        """Create a fresh page in the existing context and inject stealth."""
        if self._context is None:
            raise RuntimeError("No active browser context.")
        page = await self._context.new_page()
        await self._stealth.inject(page)
        return page

    async def screenshot(self, path: Optional[str] = None) -> bytes:
        """Capture full-page PNG; optionally save to path."""
        if self._page is None:
            return b""
        try:
            return await self._page.screenshot(path=path, full_page=True)
        except Exception as exc:
            logger.debug("screenshot failed: {}", exc)
            return b""

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def page(self) -> Optional[Page]:
        """Return the active Playwright page."""
        return self._page

    @property
    def session_age_s(self) -> float:
        """Return elapsed seconds since session start."""
        if self._session_start == 0.0:
            return 0.0
        return time.monotonic() - self._session_start
