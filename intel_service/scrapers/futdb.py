"""FutDB fallback API only. Player price when other sources fail; rate-limited."""

import os
from typing import Optional

import requests
from loguru import logger

from scraper_utils import DEFAULT_HEADERS, random_delay


class FutdbScraper:
    """Fetches player price from FutDB API when available. Never raises; returns None on failure/rate limit."""

    # FutDB free tier may not include prices; premium endpoint pattern
    API_BASE = "https://api.futdb.app"
    # Alternative: https://futdb.app/api - document exact endpoint when available

    def __init__(
        self,
        api_key: Optional[str] = None,
        delay_min_s: float = 2.0,
        delay_max_s: float = 5.0,
    ) -> None:
        """Optional API key from env FUTDB_API_KEY; delay between requests."""
        self._api_key = api_key or os.environ.get("FUTDB_API_KEY", "")
        self._delay_min = delay_min_s
        self._delay_max = delay_max_s
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        if self._api_key:
            self._session.headers["X-Auth-Token"] = self._api_key

    def get_player_price(self, player_name: str, platform: str) -> Optional[int]:
        """Fetch price for player and platform. Returns None on rate limit, missing key, or any error."""
        try:
            if not self._api_key:
                logger.debug("FutDB: no API key set; skipping")
                return None
            random_delay(self._delay_min, self._delay_max)
            # FutDB premium: GET /api/players/{id}/price or search then price
            # Free tier has no price; we try a generic players search and price endpoint if documented
            search_url = f"{self.API_BASE}/api/players"
            params = {"name": player_name, "limit": 1}
            resp = self._session.get(search_url, params=params, timeout=10)
            if resp.status_code == 429:
                logger.warning("FutDB: rate limit hit")
                return None
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", data) if isinstance(data, dict) else []
            if isinstance(items, list) and items:
                player_id = items[0].get("id") if isinstance(items[0], dict) else None
                if player_id is None:
                    return None
                price_url = f"{self.API_BASE}/api/players/{player_id}/price"
                random_delay(self._delay_min, self._delay_max)
                price_resp = self._session.get(price_url, params={"platform": platform}, timeout=10)
                if price_resp.status_code == 429:
                    logger.warning("FutDB: rate limit hit")
                    return None
                price_resp.raise_for_status()
                price_data = price_resp.json()
                price = price_data.get("price", price_data.get("ps_price") if platform == "ps" else None)
                if price is not None and isinstance(price, (int, float)):
                    return int(price)
            return None
        except Exception as e:
            logger.warning(f"FutDB get_player_price failed: {e}")
            return None
