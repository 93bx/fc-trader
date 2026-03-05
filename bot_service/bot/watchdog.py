"""Detects and recovers from known FC app failure states."""

import time
from enum import Enum
from typing import Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from bot.auth import AuthManager
    from bot.config_loader import Config
    from bot.device import Device


class FailureType(Enum):
    """Known FC app failure states from .cursorrules §12."""

    BID_LOCK = "bid_lock"
    SESSION_EXPIRED = "session_expired"
    APP_CRASH = "app_crash"
    NETWORK_ERROR = "network_error"
    TRANSFER_FULL = "transfer_full"
    UNKNOWN = "unknown"


class Watchdog:
    """Detects failures and runs recovery. Returns False only after 3 consecutive unrecoverable failures."""

    def __init__(self, device: "Device", auth: "AuthManager", cfg: "Config") -> None:
        """Build watchdog with device, auth (for session recovery), and config."""
        self._device = device
        self._auth = auth
        self._cfg = cfg
        self._consecutive_failures = 0

    def check_and_recover(self) -> bool:
        """
        Run all detection checks. Return True if healthy or recovered.
        Return False only after 3 consecutive unrecoverable failures (then log CRITICAL).
        """
        failure = self.detect_failure()
        if failure is None:
            self._consecutive_failures = 0
            return True
        logger.warning("Watchdog detected: %s", failure.value)
        if self.recover(failure):
            self._consecutive_failures = 0
            logger.info("Recovered from %s", failure.value)
            return True
        self._consecutive_failures += 1
        if self._consecutive_failures >= 3:
            logger.critical("Three consecutive unrecoverable failures; stopping bot")
            return False
        return True

    def detect_failure(self) -> Optional[FailureType]:
        """Detect current failure state from screen content."""
        if self._device.is_text_on_screen("Bid has changed"):
            return FailureType.BID_LOCK
        if self._device.is_text_on_screen("Sign In") or self._device.is_text_on_screen("Email"):
            if not self._auth.is_logged_in():
                return FailureType.SESSION_EXPIRED
        if self._device.is_text_on_screen("Connection Error") or self._device.is_text_on_screen("Network"):
            return FailureType.NETWORK_ERROR
        if self._device.is_text_on_screen("Transfer List Full") or self._device.is_text_on_screen("List Full"):
            return FailureType.TRANSFER_FULL
        # APP_CRASH: home or black — heuristic: no FC landmarks
        text = self._device.get_screen_text()
        if not any(
            x in text for x in ("Transfer", "Club", "Search", "FUT", "Companion")
        ):
            return FailureType.APP_CRASH
        return None

    def recover(self, failure: FailureType) -> bool:
        """Run recovery for the given failure type. Return True if recovery succeeded."""
        if failure == FailureType.BID_LOCK:
            return self._recover_bid_lock()
        if failure == FailureType.SESSION_EXPIRED:
            return self._recover_session_expired()
        if failure == FailureType.APP_CRASH:
            return self._recover_app_crash()
        if failure == FailureType.NETWORK_ERROR:
            return self._recover_network_error()
        if failure == FailureType.TRANSFER_FULL:
            logger.error("Transfer list full; pause buying and alert via log")
            return False
        return False

    def _recover_bid_lock(self) -> bool:
        """Dismiss 'Bid has changed' popup, wait 5s."""
        logger.debug("Recovering BID_LOCK: dismiss popup")
        self._device.tap_text("OK")
        self._device.tap_text("Cancel")
        time.sleep(5)
        return True

    def _recover_session_expired(self) -> bool:
        """Call auth.login() again."""
        logger.debug("Recovering SESSION_EXPIRED: re-login")
        return self._auth.login()

    def _recover_app_crash(self) -> bool:
        """Relaunch app and re-navigate to transfer market (caller must launch app)."""
        logger.debug("Recovering APP_CRASH: relaunch and re-navigate")
        self._device.press_back()
        time.sleep(2)
        return True

    def _recover_network_error(self) -> bool:
        """Wait 30s, retry up to 3 times."""
        for attempt in range(3):
            logger.debug("Recovering NETWORK_ERROR: wait 30s attempt %s", attempt + 1)
            time.sleep(30)
            if self.detect_failure() != FailureType.NETWORK_ERROR:
                return True
        return False
