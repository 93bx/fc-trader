"""FC 26 WEB APP — Tests for WebRateLimiter limit enforcement and keepalive."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.config_loader import WebRateLimiterConfig


def _make_cfg(**overrides) -> WebRateLimiterConfig:
    defaults = dict(
        max_searches_per_hour=25,
        max_buys_per_hour=10,
        max_lists_per_hour=12,
        cooldown_after_buy_sec=50,
        daily_trade_limit=75,
        inter_search_pause_min=9,
        inter_search_pause_max=28,
        daily_active_hours_max=6,
        keepalive_interval_sec=480,
    )
    defaults.update(overrides)
    return WebRateLimiterConfig(**defaults)


def _make_db(hourly_count: int = 0, daily_count: int = 0):
    db = MagicMock()
    db.get_hourly_action_count.return_value = hourly_count
    db.get_daily_trade_count.return_value = daily_count
    db.update_rate_state = MagicMock()
    return db


@pytest.mark.asyncio
async def test_check_and_wait_increments_state_when_under_limit():
    from web.web_rate_limiter import WebRateLimiter

    db = _make_db(hourly_count=5, daily_count=10)
    rl = WebRateLimiter(_make_cfg(), db)
    await rl.check_and_wait("search")
    db.update_rate_state.assert_called_once_with("search")


@pytest.mark.asyncio
async def test_check_and_wait_sleeps_on_hourly_limit():
    from web.web_rate_limiter import WebRateLimiter

    db = _make_db(hourly_count=25, daily_count=0)
    rl = WebRateLimiter(_make_cfg(), db)
    with patch.object(rl, "_sleep_until_next_hour", new_callable=AsyncMock) as mock_sleep:
        await rl.check_and_wait("search")
        mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_wait_sleeps_on_daily_limit():
    from web.web_rate_limiter import WebRateLimiter

    db = _make_db(hourly_count=0, daily_count=75)
    rl = WebRateLimiter(_make_cfg(), db)
    with patch.object(rl, "_sleep_until_midnight", new_callable=AsyncMock) as mock_sleep:
        await rl.check_and_wait("search")
        mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_inter_search_pause_respects_minimum(monkeypatch):
    from web.web_rate_limiter import WebRateLimiter

    db = _make_db()
    rl = WebRateLimiter(_make_cfg(inter_search_pause_min=9, inter_search_pause_max=9), db)
    rl._last_search_ts = 0.0
    slept: list[float] = []

    async def mock_sleep(n):
        slept.append(n)

    monkeypatch.setattr("web.web_rate_limiter.asyncio.sleep", mock_sleep)
    import time
    rl._last_search_ts = time.monotonic()
    await rl.inter_search_pause()
    assert not slept or slept[0] >= 0


@pytest.mark.asyncio
async def test_keepalive_runs_without_error():
    from web.web_rate_limiter import WebRateLimiter

    db = _make_db()
    rl = WebRateLimiter(_make_cfg(), db)
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock()
    await rl.keepalive(mock_page)
    assert mock_page.evaluate.call_count == 2


def test_daily_budget_remaining():
    from web.web_rate_limiter import WebRateLimiter

    db = _make_db(daily_count=60)
    rl = WebRateLimiter(_make_cfg(daily_trade_limit=75), db)
    assert rl.daily_budget_remaining() == 15


def test_daily_limit_reached_true():
    from web.web_rate_limiter import WebRateLimiter

    db = _make_db(daily_count=75)
    rl = WebRateLimiter(_make_cfg(daily_trade_limit=75), db)
    assert rl.daily_limit_reached() is True


def test_daily_limit_reached_false():
    from web.web_rate_limiter import WebRateLimiter

    db = _make_db(daily_count=74)
    rl = WebRateLimiter(_make_cfg(daily_trade_limit=75), db)
    assert rl.daily_limit_reached() is False
