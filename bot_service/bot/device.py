"""Raw UI interactions only (tap, swipe, OCR, screenshot) via uiautomator2."""

import io
import random
import time
from typing import Any, Optional

import pytesseract
from loguru import logger
from PIL import Image

from bot.config_loader import AntiDetectConfig

# uiautomator2 is optional at import; connect() will use it
try:
    import uiautomator2 as u2
except ImportError:
    u2 = None  # type: ignore[assignment]


# OCR config for price regions: digits and K/M/,. only (per .cursorrules §5)
TESSERACT_PRICE_CONFIG = "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789KM,."


class Device:
    """Wrapper around uiautomator2: all taps use jitter, all actions preceded by _human_delay()."""

    def __init__(self, cfg: AntiDetectConfig) -> None:
        """Build device from anti-detect config (delays and jitter)."""
        self._cfg = cfg
        self._d: Any = None

    def connect(self) -> bool:
        """Connect to device via uiautomator2. Log device info. Return False on failure."""
        if u2 is None:
            logger.error("uiautomator2 not installed")
            return False
        try:
            self._d = u2.connect()
            info = self._d.info if hasattr(self._d, "info") else {}
            logger.info("Device connected: {}", info.get("productName", "android"))
            return True
        except Exception as e:
            logger.error("Device connect failed: {}", e)
            return False

    def _human_delay(self) -> None:
        """Random delay between action_delay_min and action_delay_max (no bare time.sleep elsewhere)."""
        delay = random.uniform(self._cfg.action_delay_min, self._cfg.action_delay_max)
        time.sleep(delay)

    def _jitter(self, coord: int) -> int:
        """Add random pixel jitter ± tap_jitter_px to coordinate."""
        return coord + random.randint(-self._cfg.tap_jitter_px, self._cfg.tap_jitter_px)

    def _element_exists(self, selector: dict, timeout: int = 5) -> Any:
        """
        Resolve element by selector. Lookup order: resourceId, description, text, XPath last.
        Returns element proxy if found within timeout, else None.
        """
        if self._d is None:
            return None
        # Build kwargs for u2: resourceId, description, text (XPath fragile, use last)
        rid = selector.get("resourceId") or selector.get("resource-id")
        desc = selector.get("description") or selector.get("content-desc")
        text = selector.get("text")
        xpath = selector.get("xpath")
        elapsed = 0
        step = 0.5
        while elapsed < timeout:
            if rid:
                el = self._d(resourceId=rid)
                if el.exists:
                    return el
            if desc:
                el = self._d(description=desc)
                if el.exists:
                    return el
            if text:
                el = self._d(text=text)
                if el.exists:
                    return el
            if xpath:
                el = self._d.xpath(xpath)
                if el.exists:
                    return el
            self._human_delay()
            elapsed += step
        return None

    def tap(self, x: int, y: int) -> None:
        """Tap at (x, y) with jitter. _human_delay() before tap."""
        self._human_delay()
        xj = self._jitter(x)
        yj = self._jitter(y)
        if self._d:
            self._d.click(xj, yj)
        logger.debug("tap at (%s, %s) jittered to (%s, %s)", x, y, xj, yj)

    def tap_element(self, selector: dict) -> bool:
        """Tap element found by selector (resourceId/description/text). Returns False if not found in 5s."""
        self._human_delay()
        el = self._element_exists(selector, timeout=5)
        if el is None:
            logger.debug("tap_element: element not found for selector %s", selector)
            return False
        # Get center of element and tap with jitter
        try:
            info = el.info
            bounds = info.get("bounds", {})
            left = bounds.get("left", 0)
            top = bounds.get("top", 0)
            right = bounds.get("right", left)
            bottom = bounds.get("bottom", top)
            cx = (left + right) // 2
            cy = (top + bottom) // 2
            self._human_delay()
            xj = self._jitter(cx)
            yj = self._jitter(cy)
            self._d.click(xj, yj)
            logger.debug("tap_element at (%s, %s)", xj, yj)
            return True
        except Exception as e:
            logger.debug("tap_element failed: %s", e)
            return False

    def tap_text(self, text: str) -> bool:
        """Tap element with exact text. Returns False if not found within 5s."""
        return self.tap_element({"text": text})

    def type_text(self, text: str, clear_first: bool = True) -> None:
        """Type text char-by-char with 50–150 ms random delay per char. Uses send_keys if available."""
        self._human_delay()
        if self._d is None:
            return
        try:
            if clear_first and hasattr(self._d, "clear_text"):
                self._d.clear_text()
            if hasattr(self._d, "send_keys"):
                # send_keys with clear; add human-like delay per char if we type manually
                self._d.send_keys(text, clear=clear_first)
            else:
                for c in text:
                    time.sleep(random.uniform(0.05, 0.15))
                    self._d.send_keys(c, clear=False)
        except Exception as e:
            logger.debug("type_text failed: %s", e)

    def swipe_up(self, steps: Optional[int] = None) -> None:
        """Swipe up. Steps from config random range if not provided."""
        self._human_delay()
        if steps is None:
            steps = random.randint(10, 25)
        if self._d is None:
            return
        w, h = self._d.window_size()
        cx, cy = w // 2, h // 2
        self._d.swipe(cx, cy * 3 // 4, cx, cy // 4, steps=steps)
        logger.debug("swipe_up steps=%s", steps)

    def swipe_down(self, steps: Optional[int] = None) -> None:
        """Swipe down."""
        self._human_delay()
        if steps is None:
            steps = random.randint(10, 25)
        if self._d is None:
            return
        w, h = self._d.window_size()
        cx, cy = w // 2, h // 2
        self._d.swipe(cx, cy // 4, cx, cy * 3 // 4, steps=steps)
        logger.debug("swipe_down steps=%s", steps)

    def wait_for_text(self, text: str, timeout: int = 10) -> bool:
        """Wait until element with exact text exists. Returns True if found."""
        elapsed = 0
        step = 0.5
        while elapsed < timeout:
            el = self._element_exists({"text": text}, timeout=1)
            if el is not None:
                return True
            self._human_delay()
            elapsed += step
        return False

    def wait_for_element(self, selector: dict, timeout: int = 10) -> bool:
        """Wait until element matching selector exists. Returns True if found."""
        return self._element_exists(selector, timeout=timeout) is not None

    def screenshot(self) -> bytes:
        """Take screenshot; return PNG bytes."""
        self._human_delay()
        if self._d is None:
            return b""
        try:
            img = self._d.screenshot()
            if img is None:
                return b""
            if hasattr(img, "save"):
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
            return b""
        except Exception as e:
            logger.debug("screenshot failed: %s", e)
            return b""

    def get_screen_text(self) -> str:
        """OCR the entire current screen (default tess config)."""
        self._human_delay()
        raw = self.screenshot()
        if not raw:
            return ""
        try:
            img = Image.open(io.BytesIO(raw))
            return pytesseract.image_to_string(img, config="")
        except Exception as e:
            logger.debug("get_screen_text failed: %s", e)
            return ""

    def extract_text_from_region(self, x1: int, y1: int, x2: int, y2: int) -> str:
        """Crop screenshot to region, run OCR with price whitelist (digits, K, M, comma, dot)."""
        self._human_delay()
        raw = self.screenshot()
        if not raw:
            return ""
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            crop = img.crop((x1, y1, x2, y2))
            return pytesseract.image_to_string(crop, config=TESSERACT_PRICE_CONFIG)
        except Exception as e:
            logger.debug("extract_text_from_region failed: %s", e)
            return ""

    def press_back(self) -> None:
        """Press back button."""
        self._human_delay()
        if self._d:
            self._d.press("back")
        logger.debug("press_back")

    def is_text_on_screen(self, text: str) -> bool:
        """True if element with exact text exists."""
        return self._element_exists({"text": text}, timeout=1) is not None
