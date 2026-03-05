"""AVD process lifecycle only (start, boot wait, install APK, launch app, stop)."""

import os
import subprocess
import time
from loguru import logger

from bot.config_loader import EmulatorConfig


class Emulator:
    """Manages Android AVD process: start, wait for boot, install APK, launch app, stop."""

    def __init__(self, cfg: EmulatorConfig) -> None:
        """Build emulator controller from config."""
        self._cfg = cfg
        self._process: subprocess.Popen | None = None

    def _adb(self, *args: str) -> str:
        """Run adb command; timeout 30s. Returns stdout. Raises on non-zero exit."""
        cmd = ["adb", "-s", f"emulator-{self._cfg.avd_port}"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"adb failed: {result.stderr or result.stdout}")
        return result.stdout or ""

    def start(self) -> bool:
        """Launch AVD subprocess. Return False if already running."""
        if self.is_running():
            logger.warning("Emulator already running; skipping start")
            return False
        gpu = "swiftshader_indirect"
        cmd = [
            "emulator",
            "-avd", self._cfg.avd_name,
            "-port", str(self._cfg.avd_port),
            "-no-snapshot",
            "-no-audio",
            "-gpu", gpu,
        ]
        if self._cfg.headless:
            cmd.extend(["-no-window"])
        logger.info("Starting AVD: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )
        if not self._wait_for_boot():
            self.stop()
            return False
        self._unlock_screen()
        return True

    def _wait_for_boot(self) -> bool:
        """Poll adb getprop sys.boot_completed every 5s until '1' or timeout. Log every 30s."""
        start = time.monotonic()
        last_log = start
        while (time.monotonic() - start) < self._cfg.boot_timeout:
            try:
                out = subprocess.run(
                    ["adb", "-s", f"emulator-{self._cfg.avd_port}", "shell", "getprop", "sys.boot_completed"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if out.stdout and "1" in out.stdout.strip():
                    logger.info("AVD boot completed in %.0fs", time.monotonic() - start)
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError, RuntimeError) as e:
                logger.debug("Boot poll failed: %s", e)
            now = time.monotonic()
            if now - last_log >= 30:
                logger.info("Waiting for AVD boot... %.0fs elapsed", now - start)
                last_log = now
            time.sleep(5)
        logger.error("AVD boot timeout after %ds", self._cfg.boot_timeout)
        return False

    def _unlock_screen(self) -> None:
        """Swipe to dismiss lock screen (generic left-to-right then up)."""
        try:
            subprocess.run(
                ["adb", "-s", f"emulator-{self._cfg.avd_port}", "shell", "input", "swipe", "100", "500", "600", "500", "300"],
                capture_output=True,
                timeout=10,
            )
            time.sleep(0.5)
            subprocess.run(
                ["adb", "-s", f"emulator-{self._cfg.avd_port}", "shell", "input", "swipe", "350", "800", "350", "300", "300"],
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("Unlock swipe failed: %s", e)

    def install_apk(self, path: str) -> bool:
        """Install APK with adb install -r -d. Return True if output contains Success."""
        try:
            out = subprocess.run(
                ["adb", "-s", f"emulator-{self._cfg.avd_port}", "install", "-r", "-d", path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if "Success" in (out.stdout or "") or "Success" in (out.stderr or ""):
                logger.info("APK installed: %s", path)
                return True
            logger.error("APK install failed: %s", out.stderr or out.stdout)
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("APK install error: %s", e)
            return False

    def is_running(self) -> bool:
        """True if adb devices shows the emulator."""
        try:
            out = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return f"emulator-{self._cfg.avd_port}" in (out.stdout or "")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def is_app_installed(self, package: str) -> bool:
        """True if the given package is installed on the device."""
        try:
            out = self._adb("shell", "pm", "list", "packages", package)
            return package in (out or "")
        except RuntimeError:
            return False

    def launch_app(self, package: str) -> bool:
        """Launch app by package. Returns True if launch command succeeded."""
        try:
            self._adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
            return True
        except RuntimeError as e:
            logger.error("Launch app failed: %s", e)
            return False

    def stop(self) -> None:
        """Kill emulator via adb emu kill, then kill process group if we started it."""
        try:
            subprocess.run(
                ["adb", "-s", f"emulator-{self._cfg.avd_port}", "emu", "kill"],
                capture_output=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("adb emu kill: %s", e)
        if self._process and self._process.poll() is None:
            try:
                pgid = os.getpgid(self._process.pid)  # type: ignore[union-attr]
                os.killpg(pgid, 9)
            except (ProcessLookupError, OSError, AttributeError) as e:
                logger.debug("Kill process group: %s", e)
            self._process = None
        logger.info("Emulator stopped")
