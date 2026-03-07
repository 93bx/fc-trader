"""FC 26 WEB APP — Android anti-detection retrofit for KSA profile."""

from __future__ import annotations

import subprocess

from loguru import logger

from web.config_loader import AntiDetectConfig


class AndroidKSAStealth:
    """Applies KSA locale/timezone/network/operator hints to Android emulator."""

    def __init__(self, cfg: AntiDetectConfig) -> None:
        """Store anti-detection profile used for Android retrofit."""
        self._cfg = cfg
        self._serial = ""

    def apply(self, emulator_port: int) -> None:
        """Apply all Android anti-detection sub-steps without raising."""
        self._serial = f"emulator-{emulator_port}"
        logger.info("Applying Android KSA stealth profile to {}.", self._serial)
        self._set_locale()
        self._set_timezone()
        self._set_geolocation()
        self._spoof_build_props()
        self._set_network_operator()

    def _run_adb(self, args: list[str], step: str) -> None:
        """Execute one adb command with warning-only failure handling."""
        command = ["adb", "-s", self._serial] + args
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            logger.debug("Android stealth step applied: {}", step)
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            logger.warning("Android stealth step failed ({}): {}", step, exc)

    def _set_locale(self) -> None:
        """Configure Arabic Saudi locale on the device."""
        self._run_adb(["shell", "setprop", "persist.sys.locale", "ar-SA"], "set_locale")
        self._run_adb(["shell", "setprop", "persist.sys.language", "ar"], "set_language")
        self._run_adb(["shell", "setprop", "persist.sys.country", "SA"], "set_country")

    def _set_timezone(self) -> None:
        """Set device timezone to Riyadh."""
        self._run_adb(["shell", "setprop", "persist.sys.timezone", "Asia/Riyadh"], "set_timezone")

    def _set_geolocation(self) -> None:
        """Broadcast Riyadh mock coordinates."""
        self._run_adb(
            [
                "shell",
                "am",
                "broadcast",
                "-a",
                "android.intent.action.MOCK_LOCATION",
                "--es",
                "lat",
                "24.6877",
                "--es",
                "lon",
                "46.7219",
            ],
            "set_geolocation",
        )

    def _spoof_build_props(self) -> None:
        """Spoof Android build properties to Samsung Galaxy A54 identifiers."""
        props = {
            "ro.product.brand": "samsung",
            "ro.product.model": "SM-A546B",
            "ro.product.manufacturer": "samsung",
            "ro.product.locale": "ar-SA",
            "ro.product.name": "a54xnsxx",
        }
        for key, value in props.items():
            self._run_adb(["shell", "setprop", key, value], f"build_prop:{key}")

    def _set_network_operator(self) -> None:
        """Set STC operator properties for KSA network profile."""
        props = {
            "gsm.operator.alpha": "STC",
            "gsm.operator.iso-country": "sa",
            "gsm.operator.numeric": "42001",
        }
        for key, value in props.items():
            self._run_adb(["shell", "setprop", key, value], f"operator:{key}")

