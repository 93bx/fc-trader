"""Rate limit state and enforcement; persists to DB."""

import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING

from loguru import logger

from bot.config_loader import RateLimiterConfig

if TYPE_CHECKING:
    from bot.database import Database


class ActionType(Enum):
    """Action types tracked by the rate limiter."""

    SEARCH = "search"
    BUY = "buy"
    LIST = "list"
    BID = "bid"


class RateLimiter:
    """Enforces hourly and daily limits; persists state via Database."""

    def __init__(self, cfg: RateLimiterConfig, db: "Database") -> None:
        """Build rate limiter from config and database. No global state."""
        self._cfg = cfg
        self._db = db

    def _hourly_limit_for(self, action: ActionType) -> int:
        """Return the hourly limit for the given action type."""
        if action == ActionType.SEARCH:
            return self._cfg.max_searches_per_hour
        if action == ActionType.BUY:
            return self._cfg.max_buys_per_hour
        if action == ActionType.LIST:
            return self._cfg.max_lists_per_hour
        # BID: use same as search or a reasonable cap
        return self._cfg.max_searches_per_hour

    def check_and_wait(self, action: ActionType) -> None:
        """If under limit: record action and return. If at limit: log WARNING, sleep until reset, then return."""
        if self.daily_limit_reached():
            logger.warning("Daily trade limit reached; sleeping until midnight UTC")
            self._sleep_until_midnight_utc()
            return

        key = action.value
        limit = self._hourly_limit_for(action)
        current = self._db.get_hourly_action_count(key)

        if current >= limit:
            logger.warning(
                "Hourly limit reached for {} ({} >= {}); sleeping until next hour",
                key,
                current,
                limit,
            )
            self._sleep_until_next_hour_utc()
            return

        self._db.update_rate_state(key)

    def cooldown_after_buy(self) -> None:
        """Sleep for the configured cooldown after a buy (seconds)."""
        time.sleep(self._cfg.cooldown_after_buy_sec)

    def daily_limit_reached(self) -> bool:
        """True if daily trade count is at or above the configured limit."""
        return self._db.get_daily_trade_count() >= self._cfg.daily_trade_limit

    def sleep_until_reset(self) -> None:
        """Sleep until the next hour boundary (UTC). Used when hourly limit is hit."""
        self._sleep_until_next_hour_utc()

    def _sleep_until_next_hour_utc(self) -> None:
        """Block until the start of the next hour UTC."""
        now = datetime.now(timezone.utc)
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        delta = (next_hour - now).total_seconds()
        if delta > 0:
            time.sleep(delta)

    def _sleep_until_midnight_utc(self) -> None:
        """Block until the next midnight UTC."""
        now = datetime.now(timezone.utc)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        delta = (midnight - now).total_seconds()
        if delta > 0:
            time.sleep(delta)
