"""Unit tests for bot.rate_limiter: check_and_wait, daily_limit_reached, cooldown_after_buy."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config_loader import DatabaseConfig, RateLimiterConfig
from bot.database import Database
from bot.rate_limiter import ActionType, RateLimiter


@pytest.fixture
def db() -> Database:
    """In-memory SQLite database for tests."""
    d = Database(DatabaseConfig(path=":memory:"))
    d.init()
    return d


@pytest.fixture
def low_limit_config() -> RateLimiterConfig:
    """Config with low limits for fast tests."""
    return RateLimiterConfig(
        max_searches_per_hour=2,
        max_buys_per_hour=2,
        max_lists_per_hour=2,
        cooldown_after_buy_sec=1,
        daily_trade_limit=5,
    )


@pytest.fixture
def rate_limiter(db: Database, low_limit_config: RateLimiterConfig) -> RateLimiter:
    return RateLimiter(low_limit_config, db)


class TestUnderLimit:
    """When under limit, check_and_wait records and returns."""

    def test_first_call_records(self, rate_limiter: RateLimiter, db: Database) -> None:
        rate_limiter.check_and_wait(ActionType.SEARCH)
        state = db.get_rate_state("search")
        assert state is not None
        assert state.count_hour == 1

    def test_second_call_increments(self, rate_limiter: RateLimiter, db: Database) -> None:
        rate_limiter.check_and_wait(ActionType.SEARCH)
        rate_limiter.check_and_wait(ActionType.SEARCH)
        state = db.get_rate_state("search")
        assert state is not None
        assert state.count_hour == 2


class TestHourlyLimit:
    """When at hourly limit, check_and_wait sleeps then returns (mock sleep)."""

    def test_third_call_triggers_wait(self, rate_limiter: RateLimiter, db: Database) -> None:
        rate_limiter.check_and_wait(ActionType.SEARCH)
        rate_limiter.check_and_wait(ActionType.SEARCH)
        with patch("bot.rate_limiter.time.sleep"):
            rate_limiter.check_and_wait(ActionType.SEARCH)
        state = db.get_rate_state("search")
        assert state is not None
        assert state.count_hour == 2


class TestDailyLimitReached:
    """daily_limit_reached returns True when trade count >= limit."""

    def test_initially_false(self, rate_limiter: RateLimiter) -> None:
        assert rate_limiter.daily_limit_reached() is False

    def test_true_after_inserting_trades(self, db: Database, low_limit_config: RateLimiterConfig) -> None:
        from datetime import datetime, timezone

        from bot.models import Trade

        for i in range(5):
            db.insert_trade(
                Trade(
                    player_name="Test",
                    strategy="sniper",
                    action="buy",
                    platform="ps",
                    executed_at=datetime.now(timezone.utc),
                    buy_price=1000,
                    sell_price=1100,
                    profit_net=45,
                )
            )
        rl = RateLimiter(low_limit_config, db)
        assert rl.daily_limit_reached() is True


class TestCooldownAfterBuy:
    """cooldown_after_buy sleeps for configured seconds."""

    def test_sleeps_config_seconds(self, rate_limiter: RateLimiter) -> None:
        with patch("bot.rate_limiter.time.sleep") as mock_sleep:
            rate_limiter.cooldown_after_buy()
        mock_sleep.assert_called_once_with(1)
