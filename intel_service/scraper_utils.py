"""Shared helpers for scrapers: random delay and default request headers."""

import random
import time
from typing import Dict

# Realistic browser headers for scrapers (Chrome on Linux)
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def random_delay(min_s: float, max_s: float) -> None:
    """Sleep for a random duration between min_s and max_s (inclusive)."""
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)
