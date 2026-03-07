"""FC 26 WEB APP — Residential proxy rotation and connectivity checks."""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Optional

import requests
from loguru import logger

from web.config_loader import ProxyConfig

_SA_CIDR_HINTS: tuple[str, ...] = (
    "5.1.0.0/16",
    "37.10.0.0/16",
    "213.0.0.0/8",
)


class ProxyRotator:
    """Manages current proxy endpoint and rotations between sessions."""

    def __init__(self, cfg: ProxyConfig) -> None:
        """Initialize rotator with proxy configuration."""
        self._cfg = cfg
        self._index = 0

    def get_current(self) -> Optional[dict]:
        """Return current Playwright proxy args or None when disabled."""
        if not self._cfg.enabled or not self._cfg.pool:
            return None
        endpoint = self._cfg.pool[self._index % len(self._cfg.pool)]
        if not endpoint.host or endpoint.port <= 0:
            return None
        return {
            "server": f"http://{endpoint.host}:{endpoint.port}",
            "username": endpoint.user,
            "password": endpoint.password,
        }

    def rotate(self) -> None:
        """Rotate to the next proxy in the pool."""
        if not self._cfg.pool:
            return
        self._index = (self._index + 1) % len(self._cfg.pool)
        logger.info("Proxy rotated.")

    def validate_current(self) -> bool:
        """Check connectivity and basic Saudi IP plausibility for active proxy."""
        current = self.get_current()
        if current is None:
            logger.debug("Proxy disabled; skipping proxy validation.")
            return True
        server = current["server"].replace("http://", "")
        user = current.get("username", "")
        password = current.get("password", "")
        auth_prefix = f"{user}:{password}@" if user or password else ""
        proxy_url = f"http://{auth_prefix}{server}"
        proxies = {"http": proxy_url, "https": proxy_url}
        try:
            resp = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=12)
            resp.raise_for_status()
            origin = str(resp.json().get("origin", "")).split(",")[0].strip()
            if not origin:
                logger.warning("Proxy validation failed: no IP origin in response.")
                return False
            ip_ok = self._is_sa_ip(origin)
            logger.info("Proxy validation origin={} sa_match={}", origin, ip_ok)
            return ip_ok
        except requests.RequestException as exc:
            logger.warning("Proxy validation request failed: {}", exc)
            return False

    def _is_sa_ip(self, ip_raw: str) -> bool:
        """Heuristic check for likely Saudi address blocks."""
        try:
            ip_obj = ip_address(ip_raw)
        except ValueError:
            return False
        return any(ip_obj in ip_network(cidr) for cidr in _SA_CIDR_HINTS)

