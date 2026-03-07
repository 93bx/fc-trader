"""FC 26 WEB APP — KSA fingerprint and Playwright context argument builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from web.config_loader import AntiDetectConfig


@dataclass(frozen=True)
class KSAFingerprint:
    """Immutable KSA browser identity values."""

    locale: str
    timezone: str
    latitude: float
    longitude: float
    accuracy: float
    user_agent: str
    accept_language: str
    viewport_width: int
    viewport_height: int
    screen_width: int
    screen_height: int
    pixel_ratio: float


class FingerprintEngine:
    """Build Playwright context and proxy args from anti-detection config."""

    def __init__(self, cfg: AntiDetectConfig) -> None:
        """Store anti-detection configuration."""
        self._cfg = cfg
        self._fp = KSAFingerprint(
            locale=cfg.locale,
            timezone=cfg.timezone,
            latitude=cfg.geolocation.latitude,
            longitude=cfg.geolocation.longitude,
            accuracy=cfg.geolocation.accuracy,
            user_agent=cfg.user_agent,
            accept_language=cfg.accept_language,
            viewport_width=cfg.screen_width,
            viewport_height=cfg.screen_height,
            screen_width=cfg.screen_width,
            screen_height=cfg.screen_height,
            pixel_ratio=cfg.pixel_ratio,
        )

    def get_playwright_context_args(self) -> dict:
        """Return full keyword args for browser.new_context()."""
        return {
            "locale": self._fp.locale,
            "timezone_id": self._fp.timezone,
            "geolocation": {
                "latitude": self._fp.latitude,
                "longitude": self._fp.longitude,
                "accuracy": self._fp.accuracy,
            },
            "permissions": ["geolocation"],
            "user_agent": self._fp.user_agent,
            "viewport": {"width": self._fp.viewport_width, "height": self._fp.viewport_height},
            "screen": {"width": self._fp.screen_width, "height": self._fp.screen_height},
            "color_scheme": "light",
            "device_scale_factor": self._fp.pixel_ratio,
            "is_mobile": False,
            "has_touch": False,
            "extra_http_headers": {
                "Accept-Language": self._fp.accept_language,
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        }

    def get_proxy_args(self) -> Optional[dict]:
        """Return Playwright proxy dict when enabled, else None."""
        if not self._cfg.proxy.enabled or not self._cfg.proxy.pool:
            return None
        ep = self._cfg.proxy.pool[0]
        if not ep.host or ep.port <= 0:
            return None
        return {"server": f"http://{ep.host}:{ep.port}", "username": ep.user, "password": ep.password}

