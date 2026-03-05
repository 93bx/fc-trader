"""FUTBIN price graph HTTP fetching only. Price history and latest price by platform."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from scraper_utils import DEFAULT_HEADERS, random_delay


class FutbinGraphScraper:
    """Fetches FUTBIN price history and latest price. Never raises; returns []/None on failure."""

    BASE_URL = "https://www.futbin.com"
    GRAPH_PATH = "/26/playerGraph"

    def __init__(
        self,
        base_url: Optional[str] = None,
        delay_min_s: float = 2.0,
        delay_max_s: float = 5.0,
    ) -> None:
        """Optional base URL and delay range for requests."""
        self._base = (base_url or self.BASE_URL).rstrip("/")
        self._delay_min = delay_min_s
        self._delay_max = delay_max_s
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

    def fetch_price_history(self, player_id: str, platform: str) -> List[Dict[str, Any]]:
        """GET price history JSON; return list of {date, ps_price, xbox_price, pc_price}. Returns [] on failure."""
        try:
            random_delay(self._delay_min, self._delay_max)
            url = f"{self._base}{self.GRAPH_PATH}"
            params = {"type": "daily_graph", "player": player_id}
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "data" in data:
                return data["data"] if isinstance(data["data"], list) else []
            return []
        except Exception as e:
            logger.warning(f"FUTBIN fetch_price_history failed: {e}")
            return []

    def get_latest_price(self, player_id: str, platform: str) -> Optional[int]:
        """Return the most recent price for the given platform from price history. None on failure."""
        try:
            history = self.fetch_price_history(player_id, platform)
            if not history:
                return None
            # Platform key: ps, xbox, pc (FUTBIN often uses ps_price, xbox_price, pc_price)
            key_map = {"ps": "ps_price", "xbox": "xbox_price", "pc": "pc_price"}
            key = key_map.get(platform.lower(), "ps_price")
            # Assume list is ordered by date; take last
            latest = history[-1] if history else {}
            val = latest.get(key)
            if val is not None and isinstance(val, (int, float)):
                return int(val)
            return None
        except Exception as e:
            logger.warning(f"FUTBIN get_latest_price failed: {e}")
            return None
