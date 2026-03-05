"""EA login/logout and session detection."""

import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from bot.config_loader import Config
    from bot.device import Device


class AuthManager:
    """Handles EA sign-in, session detection, and logout via device UI."""

    def __init__(self, device: "Device", cfg: "Config") -> None:
        """Build auth manager with device and full config (email, password, app timeout)."""
        self._device = device
        self._cfg = cfg

    def login(self) -> bool:
        """
        Detect login screen (Sign In / Email), enter email → Next → password → Sign In.
        Wait up to app.login_timeout for 2FA if prompted. Return True when Transfer Market is reachable.
        """
        if not self._device.wait_for_text("Sign In", timeout=5) and not self._device.wait_for_text("Email", timeout=3):
            if self.is_logged_in():
                logger.info("Already logged in")
                return True
            logger.warning("Login screen not detected")
            return False

        logger.debug("Login screen detected; entering email")
        self._device.type_text(self._cfg.email, clear_first=True)
        self._device.tap_text("Next")
        if not self._device.wait_for_text("Password", timeout=5):
            self._device.wait_for_element({"text": "Password"}, timeout=5)
        self._device.type_text(self._cfg.password, clear_first=True)
        self._device.tap_text("Sign In")

        # 2FA: wait for user to complete manually, up to login_timeout
        deadline = time.monotonic() + self._cfg.app.login_timeout
        while time.monotonic() < deadline:
            if self.is_logged_in():
                logger.info("Login succeeded")
                return True
            time.sleep(2)
        logger.error("Login timeout; 2FA may be required")
        return False

    def is_logged_in(self) -> bool:
        """True if a logged-in landmark (e.g. Transfer Market, Transfers) is visible."""
        return (
            self._device.is_text_on_screen("Transfer Market")
            or self._device.is_text_on_screen("Transfers")
            or self._device.is_text_on_screen("Search the Transfer Market")
        )

    def logout(self) -> None:
        """Navigate to sign out if the app supports it; otherwise log only."""
        logger.debug("logout requested")
        # FC Companion may not expose in-app logout; caller can close app
        self._device.press_back()
