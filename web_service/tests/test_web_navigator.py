"""FC 26 WEB APP — Tests for WebNavigator result parsing and BuyResult detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from web.web_navigator import BuyResult, BidResult, _parse_price


def test_parse_price_comma_format():
    assert _parse_price("14,500") == 14500


def test_parse_price_k_suffix():
    assert _parse_price("14.5K") == 14500


def test_parse_price_m_suffix():
    assert _parse_price("1.2M") == 1_200_000


def test_parse_price_plain_int():
    assert _parse_price("5000") == 5000


def test_parse_price_empty():
    assert _parse_price("") is None


def test_parse_price_invalid():
    assert _parse_price("abc") is None


def test_parse_price_with_spaces():
    assert _parse_price(" 3 500 ") == 3500


def test_buy_result_enum_values():
    assert BuyResult.SUCCESS.value == "success"
    assert BuyResult.NOT_ENOUGH_COINS.value == "not_enough_coins"
    assert BuyResult.ALREADY_SOLD.value == "already_sold"
    assert BuyResult.RATE_LIMITED.value == "rate_limited"
    assert BuyResult.ERROR.value == "error"


def test_bid_result_enum_values():
    assert BidResult.SUCCESS.value == "success"
    assert BidResult.OUTBID.value == "outbid"
    assert BidResult.RATE_LIMITED.value == "rate_limited"
    assert BidResult.ERROR.value == "error"


def _make_navigator():
    from web.anti_detect.timing import KSATiming
    from web.config_loader import (
        AntiDetectConfig, BrowserConfig, ChemStyleConfig, EAConfig,
        GeolocationConfig, MassBidderConfig, ProxyConfig, RewardsConfig,
        SBCConfig, SniperConfig, WebConfig, WebRateLimiterConfig,
    )
    from web.web_navigator import WebNavigator

    ad = AntiDetectConfig(
        profile="ksa", timezone="Asia/Riyadh", locale="ar-SA", accept_language="ar-SA",
        platform="Win32", os_version="10.0", screen_width=1920, screen_height=1080,
        avail_width=1920, avail_height=1040, color_depth=24, pixel_ratio=1.0,
        device_memory=8, hardware_concurrency=8, user_agent="", webgl_vendor="",
        webgl_renderer="", canvas_noise=True, audio_noise=True,
        geolocation=GeolocationConfig(24.6877, 46.7219, 25.0),
        proxy=ProxyConfig(False, "residential", "SA", "Riyadh", 1, []),
        action_delay_min=0.01, action_delay_max=0.01, typing_delay_min=0.01,
        typing_delay_max=0.01, scroll_pause_min=0.01, scroll_pause_max=0.01,
        page_load_pause_min=0.01, page_load_pause_max=0.01, idle_drift_min=1,
        idle_drift_max=2, session_max_duration=5400, daily_active_hours_max=6.0,
    )
    cfg = WebConfig(
        execution_mode="web",
        ea=EAConfig(email="", password="", login_timeout=60),
        anti_detect=ad,
        web_rate_limiter=WebRateLimiterConfig(25, 10, 12, 50, 75, 9, 28, 6, 480),
        browser=BrowserConfig(True, 0, 1920, 1080, "/tmp"),
        active_strategy="auto",
        platform="ps",
        sniper=SniperConfig([], 5.0),
        mass_bidder=MassBidderConfig([], 200),
        chem_style=ChemStyleConfig([], 5.0, 500),
        sbc=SBCConfig(True, True, ["Upgrade"]),
        rewards=RewardsConfig(True, True, True, True),
        promos=[],
    )
    timing = KSATiming(ad)
    browser = MagicMock()
    db = MagicMock()
    return WebNavigator(browser, db, cfg, timing)


@pytest.mark.asyncio
async def test_detect_buy_result_success():
    nav = _make_navigator()
    nav._page_text = AsyncMock(return_value="Congratulations! Item added to Transfer Targets.")
    nav._browser.page = MagicMock()
    nav._browser.page.wait_for_selector = AsyncMock()
    result = await nav._detect_buy_result()
    assert result == BuyResult.SUCCESS


@pytest.mark.asyncio
async def test_detect_buy_result_not_enough_coins():
    nav = _make_navigator()
    nav._page_text = AsyncMock(return_value="Not enough coins to complete this purchase.")
    result = await nav._detect_buy_result()
    assert result == BuyResult.NOT_ENOUGH_COINS


@pytest.mark.asyncio
async def test_detect_buy_result_already_sold():
    nav = _make_navigator()
    nav._page_text = AsyncMock(return_value="This item is no longer available.")
    result = await nav._detect_buy_result()
    assert result == BuyResult.ALREADY_SOLD


@pytest.mark.asyncio
async def test_detect_buy_result_rate_limited():
    nav = _make_navigator()
    nav._page_text = AsyncMock(return_value="Slow down. Too many requests.")
    result = await nav._detect_buy_result()
    assert result == BuyResult.RATE_LIMITED


@pytest.mark.asyncio
async def test_detect_bid_result_outbid():
    nav = _make_navigator()
    nav._page_text = AsyncMock(return_value="You have been outbid on this item.")
    result = await nav._detect_bid_result()
    assert result == BidResult.OUTBID


@pytest.mark.asyncio
async def test_detect_bid_result_success():
    nav = _make_navigator()
    nav._page_text = AsyncMock(return_value="Bid placed. You are the highest bidder.")
    result = await nav._detect_bid_result()
    assert result == BidResult.SUCCESS
