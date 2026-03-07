"""FC 26 WEB APP — Tests for WebWatchdog ban and session detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_page(url: str = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/", content: str = "") -> MagicMock:
    page = MagicMock()
    page.url = url
    page.content = AsyncMock(return_value=content)
    return page


def _make_browser(page) -> MagicMock:
    browser = MagicMock()
    browser.page = page
    return browser


def _make_watchdog(page=None, content=""):
    from web.anti_detect.timing import KSATiming
    from web.config_loader import AntiDetectConfig, GeolocationConfig, ProxyConfig
    from web.web_watchdog import WebWatchdog

    if page is None:
        page = _make_page(content=content)
    browser = _make_browser(page)
    auth = MagicMock()
    cfg = MagicMock()

    ad_cfg = AntiDetectConfig(
        profile="ksa", timezone="Asia/Riyadh", locale="ar-SA", accept_language="ar-SA",
        platform="Win32", os_version="10.0", screen_width=1920, screen_height=1080,
        avail_width=1920, avail_height=1040, color_depth=24, pixel_ratio=1.0,
        device_memory=8, hardware_concurrency=8, user_agent="", webgl_vendor="",
        webgl_renderer="", canvas_noise=True, audio_noise=True,
        geolocation=GeolocationConfig(24.6877, 46.7219, 25.0),
        proxy=ProxyConfig(False, "residential", "SA", "Riyadh", 1, []),
        action_delay_min=1.0, action_delay_max=3.2, typing_delay_min=0.07,
        typing_delay_max=0.21, scroll_pause_min=0.5, scroll_pause_max=1.5,
        page_load_pause_min=2.0, page_load_pause_max=5.0, idle_drift_min=240,
        idle_drift_max=900, session_max_duration=5400, daily_active_hours_max=6.0,
    )
    timing = KSATiming(ad_cfg)
    return WebWatchdog(browser, auth, cfg, timing)


@pytest.mark.asyncio
async def test_detect_hard_ban_by_url():
    page = _make_page(url="https://ea.com/banned")
    wd = _make_watchdog(page=page)
    assert await wd.detect_hard_ban() is True


@pytest.mark.asyncio
async def test_detect_hard_ban_by_text():
    page = _make_page(content="Your account has been banned from EA services.")
    wd = _make_watchdog(page=page)
    assert await wd.detect_hard_ban() is True


@pytest.mark.asyncio
async def test_no_hard_ban_on_clean_page():
    page = _make_page(content="Transfer Market is open.")
    wd = _make_watchdog(page=page)
    assert await wd.detect_hard_ban() is False


@pytest.mark.asyncio
async def test_detect_soft_ban_tm_block():
    page = _make_page(
        content="Your account has been blocked from using the Transfer Market on the Web and Companion Apps."
    )
    wd = _make_watchdog(page=page)
    assert await wd.detect_soft_ban() is True


@pytest.mark.asyncio
async def test_no_soft_ban_on_clean_page():
    page = _make_page(content="Transfer Market search available.")
    wd = _make_watchdog(page=page)
    assert await wd.detect_soft_ban() is False


@pytest.mark.asyncio
async def test_detect_console_conflict():
    page = _make_page(content="You're already logged into Ultimate Team on another device.")
    wd = _make_watchdog(page=page)
    assert await wd.detect_console_conflict() is True


@pytest.mark.asyncio
async def test_detect_console_conflict_variant():
    page = _make_page(content="Please log out of Ultimate Team first before accessing the web app.")
    wd = _make_watchdog(page=page)
    assert await wd.detect_console_conflict() is True


@pytest.mark.asyncio
async def test_no_console_conflict_on_clean_page():
    page = _make_page(content="Welcome to the web app.")
    wd = _make_watchdog(page=page)
    assert await wd.detect_console_conflict() is False


@pytest.mark.asyncio
async def test_detect_rate_limit_signal_slow_down():
    page = _make_page(content="Slow down. You are making requests too quickly.")
    wd = _make_watchdog(page=page)
    assert await wd.detect_rate_limit_signal() is True


@pytest.mark.asyncio
async def test_detect_session_expiry_by_url():
    page = _make_page(url="https://accounts.ea.com/connect/auth")
    wd = _make_watchdog(page=page)
    assert await wd.detect_session_expiry() is True


@pytest.mark.asyncio
async def test_detect_session_expiry_by_text():
    page = _make_page(content="Your session has expired. Please sign in again.")
    wd = _make_watchdog(page=page)
    assert await wd.detect_session_expiry() is True


@pytest.mark.asyncio
async def test_check_and_recover_returns_false_on_hard_ban():
    page = _make_page(url="https://ea.com/account-suspended")
    wd = _make_watchdog(page=page)
    result = await wd.check_and_recover()
    assert result is False
