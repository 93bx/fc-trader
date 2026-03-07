"""FC 26 WEB APP — Session health monitoring, ban detection, and recovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from web.anti_detect.timing import KSATiming
from web.browser import BrowserSession
from web.config_loader import WebConfig
from web.web_auth import WebAuthManager

if TYPE_CHECKING:
    pass

_HARD_BAN_TEXTS = [
    "account has been banned",
    "account has been suspended",
    "account action",
    "permanently banned",
]
_HARD_BAN_URLS = ["banned", "suspended", "security-lock"]

_SOFT_BAN_TEXTS = [
    "your account has been blocked from using the Transfer Market",
    "blocked from the Transfer Market on the Web and Companion Apps",
]

_CONSOLE_CONFLICT_TEXTS = [
    "You're already logged into Ultimate Team",
    "log out of Ultimate Team first",
    "active session on another device",
]

_RATE_LIMIT_TEXTS = [
    "slow down",
    "too many requests",
    "please wait",
    "حاول مرة أخرى",
    "انتظر قليلاً",
]

_SESSION_EXPIRY_TEXTS = [
    "your session has expired",
    "sign in",
]


class WebWatchdog:
    """Monitors page state and orchestrates recovery from common failure modes."""

    def __init__(
        self,
        browser: BrowserSession,
        auth: WebAuthManager,
        cfg: WebConfig,
        timing: KSATiming,
    ) -> None:
        """Store all session components needed for health checks and recovery."""
        self._browser = browser
        self._auth = auth
        self._cfg = cfg
        self._timing = timing
        self._consecutive_failures = 0

    async def check_and_recover(self) -> bool:
        """Run all checks in priority order; return False only on unrecoverable state."""
        if await self.detect_hard_ban():
            logger.critical("Account hard banned — stopping bot permanently.")
            return False

        if await self.detect_console_conflict():
            logger.critical("Console/PC session active — stopping to prevent EA ban.")
            return False

        if await self.detect_rate_limit_signal():
            logger.warning("Rate limit signal — pausing 10 minutes.")
            await asyncio.sleep(600)
            self._consecutive_failures += 1

        if await self.detect_soft_ban():
            logger.warning("Soft ban detected (Transfer Market locked) — pausing 2 hours.")
            await asyncio.sleep(7200)
            self._consecutive_failures += 1

        if self._consecutive_failures >= 3:
            logger.critical("3 consecutive recovery failures — halting.")
            return False

        if await self.detect_session_expiry():
            logger.info("Session expired — re-logging in.")
            ok = await self._auth.login()
            if not ok:
                self._consecutive_failures += 1
                return self._consecutive_failures < 3
            self._consecutive_failures = 0

        if self._timing.session_should_rotate():
            logger.info("Session age exceeded limit — rotating browser.")
            ok = await self._browser.restart("session rotation")
            if ok:
                self._timing.reset_session_timer()
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1

        return True

    async def detect_hard_ban(self) -> bool:
        """Return True when hard-ban signals are present."""
        page = self._browser.page
        if page is None:
            return False
        url = page.url.lower()
        for fragment in _HARD_BAN_URLS:
            if fragment in url:
                logger.critical("Hard ban signal in URL: {}", url)
                return True
        content = await self._safe_content()
        lower = content.lower()
        for text in _HARD_BAN_TEXTS:
            if text.lower() in lower:
                logger.critical("Hard ban text detected: '{}'", text)
                return True
        return False

    async def detect_soft_ban(self) -> bool:
        """Return True when Transfer Market block messages are present."""
        content = await self._safe_content()
        lower = content.lower()
        for text in _SOFT_BAN_TEXTS:
            if text.lower() in lower:
                logger.warning("Soft ban text detected: '{}'", text)
                return True
        return False

    async def detect_console_conflict(self) -> bool:
        """Return True when mutual-exclusion conflict with console session is detected."""
        content = await self._safe_content()
        lower = content.lower()
        for text in _CONSOLE_CONFLICT_TEXTS:
            if text.lower() in lower:
                logger.critical("Console conflict text detected: '{}'", text)
                return True
        return False

    async def detect_rate_limit_signal(self) -> bool:
        """Return True on HTTP 429 or rate-limit toast text."""
        page = self._browser.page
        if page is None:
            return False
        content = await self._safe_content()
        lower = content.lower()
        for text in _RATE_LIMIT_TEXTS:
            if text.lower() in lower:
                logger.warning("Rate-limit text detected: '{}'", text)
                return True
        return False

    async def detect_session_expiry(self) -> bool:
        """Return True when login page or session-expired message is visible."""
        page = self._browser.page
        if page is None:
            return False
        url = page.url.lower()
        if "accounts.ea.com" in url:
            return True
        content = await self._safe_content()
        lower = content.lower()
        for text in _SESSION_EXPIRY_TEXTS:
            if text.lower() in lower:
                return True
        return False

    async def _safe_content(self) -> str:
        """Return page body text without raising on failure."""
        page = self._browser.page
        if page is None:
            return ""
        try:
            return await page.content()
        except Exception:
            return ""
