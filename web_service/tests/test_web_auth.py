"""FC 26 WEB APP — Tests for WebAuthManager session and login logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_timing():
    from web.anti_detect.timing import KSATiming
    from web.config_loader import AntiDetectConfig, GeolocationConfig, ProxyConfig

    cfg = AntiDetectConfig(
        profile="ksa", timezone="Asia/Riyadh", locale="ar-SA",
        accept_language="ar-SA", platform="Win32", os_version="10.0",
        screen_width=1920, screen_height=1080, avail_width=1920, avail_height=1040,
        color_depth=24, pixel_ratio=1.0, device_memory=8, hardware_concurrency=8,
        user_agent="", webgl_vendor="", webgl_renderer="", canvas_noise=True,
        audio_noise=True,
        geolocation=GeolocationConfig(24.6877, 46.7219, 25.0),
        proxy=ProxyConfig(False, "residential", "SA", "Riyadh", 1, []),
        action_delay_min=0.1, action_delay_max=0.1, typing_delay_min=0.01,
        typing_delay_max=0.01, scroll_pause_min=0.1, scroll_pause_max=0.1,
        page_load_pause_min=0.1, page_load_pause_max=0.1, idle_drift_min=1,
        idle_drift_max=2, session_max_duration=5400, daily_active_hours_max=6.0,
    )
    return KSATiming(cfg)


def _make_web_cfg():
    from web.config_loader import (
        BrowserConfig, ChemStyleConfig, EAConfig, MassBidderConfig,
        RewardsConfig, SBCConfig, SniperConfig, WebConfig, WebRateLimiterConfig,
        AntiDetectConfig, GeolocationConfig, ProxyConfig,
    )

    ad = AntiDetectConfig(
        profile="ksa", timezone="Asia/Riyadh", locale="ar-SA", accept_language="ar-SA",
        platform="Win32", os_version="10.0", screen_width=1920, screen_height=1080,
        avail_width=1920, avail_height=1040, color_depth=24, pixel_ratio=1.0,
        device_memory=8, hardware_concurrency=8, user_agent="", webgl_vendor="",
        webgl_renderer="", canvas_noise=True, audio_noise=True,
        geolocation=GeolocationConfig(24.6877, 46.7219, 25.0),
        proxy=ProxyConfig(False, "residential", "SA", "Riyadh", 1, []),
        action_delay_min=0.1, action_delay_max=0.1, typing_delay_min=0.01,
        typing_delay_max=0.01, scroll_pause_min=0.1, scroll_pause_max=0.1,
        page_load_pause_min=0.1, page_load_pause_max=0.1, idle_drift_min=1,
        idle_drift_max=2, session_max_duration=5400, daily_active_hours_max=6.0,
    )
    return WebConfig(
        execution_mode="web",
        ea=EAConfig(email="test@example.com", password="pass", login_timeout=60),
        anti_detect=ad,
        web_rate_limiter=WebRateLimiterConfig(25, 10, 12, 50, 75, 9, 28, 6, 480),
        browser=BrowserConfig(True, 0, 1920, 1080, "/tmp/browser_profile"),
        active_strategy="auto",
        platform="ps",
        sniper=SniperConfig([], 5.0),
        mass_bidder=MassBidderConfig([], 200),
        chem_style=ChemStyleConfig([], 5.0, 500),
        sbc=SBCConfig(True, True, ["Upgrade"]),
        rewards=RewardsConfig(True, True, True, True),
        promos=[],
    )


def _make_auth(page_content="", page_url="https://www.ea.com/ea-sports-fc/ultimate-team/web-app/"):
    from web.web_auth import WebAuthManager

    page = MagicMock()
    page.url = page_url
    page.content = AsyncMock(return_value=page_content)
    page.inner_text = AsyncMock(return_value=page_content)
    page.wait_for_url = AsyncMock()
    page.click = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.locator = MagicMock(return_value=MagicMock(
        first=MagicMock(
            wait_for=AsyncMock(),
            scroll_into_view_if_needed=AsyncMock(),
            hover=AsyncMock(),
            click=AsyncMock(),
            clear=AsyncMock(),
            press_sequentially=AsyncMock(),
            is_visible=AsyncMock(return_value=True),
        )
    ))
    page.wait_for_selector = AsyncMock()

    browser = MagicMock()
    browser.page = page
    browser.goto = AsyncMock(return_value=True)
    browser.save_session = AsyncMock()
    browser.session_age_s = 0.0

    timing = _make_timing()
    cfg = _make_web_cfg()
    return WebAuthManager(browser, cfg, timing), browser, page


@pytest.mark.asyncio
async def test_load_session_returns_true_when_logged_in():
    auth, browser, page = _make_auth(
        page_content="Transfer Market Squad Hub",
        page_url="https://www.ea.com/ea-sports-fc/ultimate-team/web-app/",
    )
    with patch.object(auth, "is_logged_in", AsyncMock(return_value=True)):
        result = await auth.load_session()
    assert result is True


@pytest.mark.asyncio
async def test_load_session_returns_false_when_expired():
    auth, browser, page = _make_auth(page_content="")
    with patch.object(auth, "is_logged_in", AsyncMock(return_value=False)):
        result = await auth.load_session()
    assert result is False


@pytest.mark.asyncio
async def test_refresh_session_skips_when_session_young():
    auth, browser, page = _make_auth()
    browser.session_age_s = 10.0
    result = await auth.refresh_session()
    assert result is True
    browser.goto.assert_not_called()


@pytest.mark.asyncio
async def test_detect_console_conflict_detects_text():
    auth, browser, page = _make_auth(
        page_content="You're already logged into Ultimate Team on console."
    )
    result = await auth.detect_console_conflict()
    assert result is True


@pytest.mark.asyncio
async def test_detect_console_conflict_clean_page():
    auth, browser, page = _make_auth(page_content="Welcome to FUT Web App!")
    result = await auth.detect_console_conflict()
    assert result is False


@pytest.mark.asyncio
async def test_is_logged_in_false_wrong_url():
    auth, browser, page = _make_auth(page_url="https://accounts.ea.com/login")
    result = await auth.is_logged_in()
    assert result is False
