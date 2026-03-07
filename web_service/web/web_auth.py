"""FC 26 WEB APP — EA Web App login, 2FA, session management, conflict detection."""

from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger

from web.anti_detect.timing import KSATiming
from web.browser import BrowserSession
from web.config_loader import WebConfig

WEB_APP_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/"
EA_LOGIN_HOST = "accounts.ea.com"

_SIGN_IN_SELECTORS = [
    "button:has-text('Sign In')",
    "[data-component-id='Login'] button",
    ".btn-standard:has-text('Sign In')",
    "a:has-text('Sign In')",
]

_COOKIE_SELECTORS = [
    "button:has-text('Accept All')",
    "button:has-text('قبول الكل')",
    "[data-testid='cookie-accept-all']",
    ".onetrust-accept-btn-handler",
    "#onetrust-accept-btn-handler",
]

_LOGGED_IN_SELECTORS = [
    "[class*='NavLink']",
    "[class*='coin-count']",
    "text=Transfer Market",
    "text=سوق النقل",
    "text=Squad Hub",
    "text=مركز الفريق",
]

_CONSOLE_CONFLICT_TEXTS = [
    "You're already logged into Ultimate Team",
    "log out of Ultimate Team first",
    "active session on another device",
]


class WebAuthManager:
    """Handles EA login flow, session keep-alive, and conflict detection."""

    def __init__(self, browser: BrowserSession, cfg: WebConfig, timing: KSATiming) -> None:
        """Store browser session and web configuration."""
        self._browser = browser
        self._cfg = cfg
        self._timing = timing

    async def load_session(self) -> bool:
        """Navigate to web app and check if cached cookies are still valid."""
        page = self._browser.page
        if page is None:
            return False
        try:
            await self._browser.goto(WEB_APP_URL)
            await asyncio.sleep(5)
            if await self.is_logged_in():
                logger.info("Session resumed from cache.")
                return True
            logger.info("Cached session expired.")
            return False
        except Exception as exc:
            logger.debug("load_session error: {}", exc)
            return False

    async def login(self) -> bool:
        """Full EA login flow including 2FA wait."""
        page = self._browser.page
        if page is None:
            return False

        if not await self._browser.goto(WEB_APP_URL):
            return False
        await asyncio.sleep(self._timing.human_delay())

        if await self.is_logged_in():
            return True

        sign_in_sel = await self._find_first_visible(_SIGN_IN_SELECTORS, timeout_ms=20_000)
        if sign_in_sel is None:
            logger.error("Login button not found.")
            return False
        await self._human_click(sign_in_sel)
        await asyncio.sleep(self._timing.human_delay())

        try:
            await page.wait_for_url(f"**{EA_LOGIN_HOST}**", timeout=15_000)
        except Exception:
            logger.debug("EA login URL not reached within timeout.")

        if not await self._human_type('input[type="email"], #email', self._cfg.ea.email):
            return False

        next_sel = await self._find_first_visible(
            ["button:has-text('Next')", "button:has-text('Continue')", 'button[type="submit"]'],
            timeout_ms=10_000,
        )
        if next_sel:
            await self._human_click(next_sel)
        await asyncio.sleep(self._timing.human_delay())

        pw_found = await self._human_type(
            'input[type="password"], #password', self._cfg.ea.password
        )
        if not pw_found:
            return False

        submit_sel = await self._find_first_visible(
            ["button:has-text('Sign In')", 'button[type="submit"]'], timeout_ms=8_000
        )
        if submit_sel:
            await self._human_click(submit_sel)
        await asyncio.sleep(self._timing.human_delay())

        otp_found = await self._wait_for_selector_ms(
            'input[name="otp"], input[placeholder*="code"]', timeout_ms=5_000
        )
        if otp_found:
            logger.info(
                "2FA required — waiting for code input (check email/authenticator). "
                "Timeout: {}s.", self._cfg.ea.login_timeout
            )
            deadline = self._cfg.ea.login_timeout
            elapsed = 0
            while elapsed < deadline:
                await asyncio.sleep(4)
                elapsed += 4
                if await self.is_logged_in():
                    break
                try:
                    await page.wait_for_url(f"**ea-sports-fc**", timeout=2_000)
                    break
                except Exception:
                    pass

        try:
            await page.wait_for_url("**ea-sports-fc**", timeout=60_000)
        except Exception:
            pass

        await self._accept_cookies()

        if await self.is_logged_in():
            await self._browser.save_session()
            logger.info("Login successful.")
            return True
        logger.error("Login failed: not logged in after flow completed.")
        return False

    async def _accept_cookies(self) -> None:
        """Try common cookie-consent selectors silently."""
        page = self._browser.page
        if page is None:
            return
        for sel in _COOKIE_SELECTORS:
            try:
                await page.locator(sel).first.click(timeout=8_000)
                logger.debug("Cookie consent accepted via: {}", sel)
                return
            except Exception:
                pass

    async def is_logged_in(self) -> bool:
        """Return True if web app nav/coin indicators are visible."""
        page = self._browser.page
        if page is None:
            return False
        url = page.url
        if "ea-sports-fc" not in url and "ea.com/ea-sports-fc" not in url:
            return False
        for sel in _LOGGED_IN_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=2_000):
                    return True
            except Exception:
                pass
        return False

    async def refresh_session(self) -> bool:
        """Re-navigate to web app to refresh session cookies if near expiry."""
        if self._browser.session_age_s < 50 * 60:
            return True
        logger.debug("Refreshing session to prevent expiry.")
        if not await self._browser.goto(WEB_APP_URL):
            return False
        if self._browser.page:
            await self._browser._stealth.inject(self._browser.page)
        return await self.is_logged_in()

    async def detect_console_conflict(self) -> bool:
        """Return True if page indicates account is active on console/PC."""
        page = self._browser.page
        if page is None:
            return False
        try:
            content = await page.content()
        except Exception:
            return False
        for text in _CONSOLE_CONFLICT_TEXTS:
            if text.lower() in content.lower():
                logger.critical("Console session conflict detected: '{}'", text)
                return True
        return False

    # ── internal helpers ──────────────────────────────────────────────────────

    async def _find_first_visible(
        self, selectors: list[str], timeout_ms: int = 10_000
    ) -> Optional[str]:
        """Return the first selector that is visible within timeout_ms."""
        page = self._browser.page
        if page is None:
            return None
        for sel in selectors:
            try:
                await page.wait_for_selector(sel, state="visible", timeout=timeout_ms)
                return sel
            except Exception:
                pass
        return None

    async def _wait_for_selector_ms(self, selector: str, timeout_ms: int = 5_000) -> bool:
        """Return True if selector becomes visible within timeout_ms."""
        page = self._browser.page
        if page is None:
            return False
        try:
            await page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
            return True
        except Exception:
            return False

    async def _human_click(self, selector: str, timeout_ms: int = 10_000) -> bool:
        """Hover then click a selector with human timing."""
        page = self._browser.page
        if page is None:
            return False
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            await loc.scroll_into_view_if_needed()
            await loc.hover()
            await asyncio.sleep(self._timing.human_delay())
            await loc.click()
            logger.debug("click: {}", selector)
            return True
        except Exception as exc:
            logger.debug("_human_click({}) failed: {}", selector, exc)
            return False

    async def _human_type(self, selector: str, text: str, clear: bool = True) -> bool:
        """Type text character-by-character into a selector."""
        page = self._browser.page
        if page is None:
            return False
        for sel in selector.split(","):
            sel = sel.strip()
            try:
                loc = page.locator(sel).first
                await loc.wait_for(state="visible", timeout=8_000)
                if clear:
                    await loc.clear()
                delay_ms = int(self._timing.typing_delay() * 1000)
                await loc.press_sequentially(text, delay=delay_ms)
                return True
            except Exception:
                pass
        return False
