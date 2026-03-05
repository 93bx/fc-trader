"""FUT.GG SBC page scraping only. Active SBCs and new SBC detection."""

import re
from datetime import datetime, timezone
from typing import List

import requests
from bs4 import BeautifulSoup
from loguru import logger

from db import SbcSignal
from scraper_utils import DEFAULT_HEADERS, random_delay


class FutGGSbcScraper:
    """Scrapes FUT.GG for active SBCs. Never raises; returns [] on failure."""

    SBC_URL = "https://fut.gg/sbc/"

    def __init__(
        self,
        url: str = "",
        delay_min_s: float = 2.0,
        delay_max_s: float = 5.0,
    ) -> None:
        """Optional SBC page URL and delay range."""
        self._url = url or self.SBC_URL
        self._delay_min = delay_min_s
        self._delay_max = delay_max_s
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

    def get_active_sbcs(self) -> List[SbcSignal]:
        """Fetch SBC page, parse SBC name, rating_req, expiry. Returns list of SbcSignal; [] on failure."""
        try:
            random_delay(self._delay_min, self._delay_max)
            resp = self._session.get(self._url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            now = datetime.now(timezone.utc)
            signals: List[SbcSignal] = []
            seen_names: set = set()
            # Common patterns: cards/sections with SBC name, rating, expiry
            for link in soup.find_all("a", href=re.compile(r"sbc|challenge", re.I)):
                name_el = link.find(class_=re.compile(r"name|title|sbc", re.I)) or link
                name = (name_el.get_text(strip=True) or "").strip()[:200]
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                rating_req: int | None = None
                for elem in link.find_all(string=re.compile(r"\d+")):
                    try:
                        rating_req = int(elem.strip())
                        if 50 <= rating_req <= 99:
                            break
                    except ValueError:
                        continue
                signals.append(
                    SbcSignal(
                        sbc_name=name,
                        detected_at=now,
                        rating_req=rating_req,
                        expires_at=None,
                    )
                )
            # Fallback: any heading or title that looks like SBC name
            if not signals:
                for tag in soup.find_all(["h2", "h3", "h4"]):
                    name = tag.get_text(strip=True)
                    if name and len(name) > 2 and ("sbc" in name.lower() or "challenge" in name.lower()):
                        if name not in seen_names:
                            seen_names.add(name)
                            signals.append(
                                SbcSignal(sbc_name=name, detected_at=now, rating_req=None, expires_at=None)
                            )
            return signals
        except Exception as e:
            logger.warning(f"FUT.GG get_active_sbcs failed: {e}")
            return []

    def has_new_sbcs(self, last_check: datetime) -> bool:
        """Return True if any SBC was detected after last_check."""
        try:
            signals = self.get_active_sbcs()
            return any(s.detected_at > last_check for s in signals)
        except Exception as e:
            logger.warning(f"FUT.GG has_new_sbcs failed: {e}")
            return False
