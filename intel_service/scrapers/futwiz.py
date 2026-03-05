"""FUTWIZ HTTP scraping only. Player prices and chem style prices for FC 26."""

import re
from datetime import datetime, timezone
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from loguru import logger

from db import MarketPrice
from scraper_utils import DEFAULT_HEADERS, random_delay


class FutwizScraper:
    """Scrapes FUTWIZ for player prices and chem style prices. Never raises; returns None/[] on failure."""

    BASE_URL = "https://www.futwiz.com"
    PLAYERS_PATH = "/en/fc26/players"

    def __init__(
        self,
        base_url: Optional[str] = None,
        delay_min_s: float = 2.0,
        delay_max_s: float = 5.0,
    ) -> None:
        """Optional base URL and delay range for requests to the same domain."""
        self._base = (base_url or self.BASE_URL).rstrip("/")
        self._delay_min = delay_min_s
        self._delay_max = delay_max_s
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

    def _request(self, path: str, params: Optional[dict] = None) -> Optional[BeautifulSoup]:
        """GET path, return BeautifulSoup or None. Applies random delay before request."""
        random_delay(self._delay_min, self._delay_max)
        try:
            url = f"{self._base}{path}"
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.warning(f"FUTWIZ request failed: {e}")
            return None

    @staticmethod
    def _parse_price(text: str) -> Optional[int]:
        """Parse price string like '14.5K' or '14,500' to int. Returns None on failure."""
        if not text:
            return None
        text = text.strip().replace(",", "").upper()
        multiplier = 1
        if text.endswith("K"):
            multiplier = 1000
            text = text[:-1]
        elif text.endswith("M"):
            multiplier = 1_000_000
            text = text[:-1]
        try:
            return int(float(text) * multiplier)
        except (ValueError, TypeError):
            return None

    def scrape_player_price(self, player_name: str, platform: str) -> Optional[MarketPrice]:
        """Scrape current price for one player. Returns None on any failure."""
        try:
            # FUTWIZ search: query param for search (site may use ?search= or similar)
            soup = self._request(
                self.PLAYERS_PATH,
                params={"search": player_name} if player_name else None,
            )
            if soup is None:
                return None
            # Try common patterns: table rows, cards with price
            price_val: Optional[int] = None
            player_id_val = ""
            # Look for price in page (selectors depend on site structure)
            for elem in soup.find_all(string=re.compile(r"[\d,]+\.?\d*[KMB]?")):
                parent = elem.parent
                if parent and "price" in (parent.get("class") or []):
                    parsed = self._parse_price(elem)
                    if parsed and parsed >= 200:
                        price_val = parsed
                        break
            if price_val is None:
                # Fallback: any number that looks like coins (e.g. 4+ digits)
                for elem in soup.find_all(string=re.compile(r"\d{4,}")):
                    parsed = self._parse_price(elem.strip())
                    if parsed and 200 <= parsed <= 15_000_000:
                        price_val = parsed
                        break
            if price_val is None:
                logger.debug(f"FUTWIZ: no price found for {player_name}")
                return None
            now = datetime.now(timezone.utc)
            return MarketPrice(
                player_id=player_id_val or player_name.replace(" ", "-").lower(),
                player_name=player_name,
                source="futwiz",
                platform=platform,
                price=price_val,
                scraped_at=now,
                price_shadow=None,
                price_hunter=None,
            )
        except Exception as e:
            logger.warning(f"FUTWIZ scrape_player_price failed: {e}")
            return None

    def scrape_trending_players(self, platform: str) -> List[MarketPrice]:
        """Scrape trending/popular section; return up to 20 MarketPrice instances. Returns [] on failure."""
        try:
            # Trending may be at /en/fc26/players or a dedicated section
            soup = self._request(self.PLAYERS_PATH)
            if soup is None:
                return []
            results: List[MarketPrice] = []
            now = datetime.now(timezone.utc)
            seen_names: set = set()
            for elem in soup.find_all(string=re.compile(r"[\d,]+\.?\d*[KMB]?")):
                parsed = self._parse_price(elem.strip() if isinstance(elem, str) else "")
                if parsed is None or parsed < 200:
                    continue
                # Try to get player name from nearby element (structure-dependent)
                parent = elem.parent
                name = ""
                for _ in range(5):
                    if parent is None:
                        break
                    name_el = parent.find(class_=re.compile(r"name|player", re.I))
                    if name_el and name_el.get_text(strip=True):
                        name = name_el.get_text(strip=True)
                        break
                    parent = parent.parent
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                results.append(
                    MarketPrice(
                        player_id=name.replace(" ", "-").lower(),
                        player_name=name,
                        source="futwiz",
                        platform=platform,
                        price=parsed,
                        scraped_at=now,
                        price_shadow=None,
                        price_hunter=None,
                    )
                )
                if len(results) >= 20:
                    break
            return results
        except Exception as e:
            logger.warning(f"FUTWIZ scrape_trending_players failed: {e}")
            return []

    def scrape_chem_style_prices(
        self, player_name: str, platform: str
    ) -> Optional[MarketPrice]:
        """Scrape same player with Shadow and Hunter; return MarketPrice with price_shadow/price_hunter set. None on failure."""
        try:
            # Same as player page but with chem filter; site may expose Shadow/Hunter prices on player page
            soup = self._request(
                self.PLAYERS_PATH,
                params={"search": player_name} if player_name else None,
            )
            if soup is None:
                return None
            price_base: Optional[int] = None
            price_shadow: Optional[int] = None
            price_hunter: Optional[int] = None
            # Look for multiple price nodes (base, Shadow, Hunter) - structure is site-specific
            for elem in soup.find_all(string=re.compile(r"[\d,]+\.?\d*[KMB]?")):
                parsed = self._parse_price(elem.strip() if isinstance(elem, str) else "")
                if parsed is None or parsed < 200:
                    continue
                if price_base is None:
                    price_base = parsed
                elif price_shadow is None:
                    price_shadow = parsed
                elif price_hunter is None:
                    price_hunter = parsed
                    break
            if price_base is None:
                return None
            now = datetime.now(timezone.utc)
            return MarketPrice(
                player_id=player_name.replace(" ", "-").lower(),
                player_name=player_name,
                source="futwiz",
                platform=platform,
                price=price_base,
                scraped_at=now,
                price_shadow=price_shadow,
                price_hunter=price_hunter,
            )
        except Exception as e:
            logger.warning(f"FUTWIZ scrape_chem_style_prices failed: {e}")
            return None
