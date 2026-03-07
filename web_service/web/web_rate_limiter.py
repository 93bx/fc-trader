"""FC 26 WEB APP — Web-specific rate limiter with inter-search pause and keepalive."""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from loguru import logger

from web.config_loader import WebRateLimiterConfig

if TYPE_CHECKING:
    from web.database_proxy import Database

_ACTION_HOURLY_LIMITS = {
    "search": "max_searches_per_hour",
    "buy": "max_buys_per_hour",
    "list": "max_lists_per_hour",
    "bid": "max_searches_per_hour",
}


class WebRateLimiter:
    """Enforces hourly/daily limits and mandatory inter-search pauses for web trading."""

    def __init__(self, cfg: WebRateLimiterConfig, db: "Database") -> None:
        """Initialize with config and database for persistent rate state."""
        self._cfg = cfg
        self._db = db
        self._last_search_ts: float = 0.0

    async def check_and_wait(self, action: str) -> None:
        """Enforce hourly and daily limits; sleep until reset window if needed."""
        if self.daily_limit_reached():
            logger.warning("Daily trade limit reached; sleeping until midnight UTC.")
            await self._sleep_until_midnight()
            return

        limit_attr = _ACTION_HOURLY_LIMITS.get(action, "max_searches_per_hour")
        limit = getattr(self._cfg, limit_attr)
        current = self._db.get_hourly_action_count(action)

        if current >= limit:
            logger.warning(
                "Hourly limit for {} reached ({}/{}); sleeping until next hour.",
                action,
                current,
                limit,
            )
            await self._sleep_until_next_hour()
            return

        self._db.update_rate_state(action)

    def check_and_wait_sync(self, action: str) -> None:
        """Synchronous wrapper; schedules coroutine in calling event loop context."""
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.check_and_wait(action))

    async def inter_search_pause(self) -> None:
        """Sleep the mandatory inter-search gap to avoid rapid-fire detection."""
        elapsed = time.monotonic() - self._last_search_ts
        required = random.uniform(
            self._cfg.inter_search_pause_min, self._cfg.inter_search_pause_max
        )
        remaining = required - elapsed
        if remaining > 0:
            logger.debug("Inter-search pause: {:.1f}s.", remaining)
            await asyncio.sleep(remaining)
        self._last_search_ts = time.monotonic()

    async def keepalive(self, page) -> None:
        """Trigger a lightweight DOM interaction to prevent EA session expiry."""
        if page is None:
            return
        try:
            await page.evaluate("window.scrollBy(0, 1)")
            await asyncio.sleep(0.2)
            await page.evaluate("window.scrollBy(0, -1)")
            logger.debug("Session keepalive.")
        except Exception as exc:
            logger.debug("keepalive failed (ignored): {}", exc)

    def cooldown_after_buy(self) -> None:
        """Synchronous post-buy cooldown sleep as required by EA safe limits."""
        import time as _time
        _time.sleep(self._cfg.cooldown_after_buy_sec)

    def daily_limit_reached(self) -> bool:
        """Return True if today's trade count is at or above the daily limit."""
        return self._db.get_daily_trade_count() >= self._cfg.daily_trade_limit

    def daily_budget_remaining(self) -> int:
        """Return trades remaining before daily cap is hit."""
        used = self._db.get_daily_trade_count()
        return max(0, self._cfg.daily_trade_limit - used)

    async def _sleep_until_next_hour(self) -> None:
        now = datetime.now(timezone.utc)
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        delta = (next_hour - now).total_seconds()
        if delta > 0:
            await asyncio.sleep(delta)

    async def _sleep_until_midnight(self) -> None:
        now = datetime.now(timezone.utc)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        delta = (midnight - now).total_seconds()
        if delta > 0:
            await asyncio.sleep(delta)
