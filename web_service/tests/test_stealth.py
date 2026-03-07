"""FC 26 WEB APP — Tests for StealthEngine JS patch correctness."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.config_loader import AntiDetectConfig, GeolocationConfig, ProxyConfig


def _make_cfg() -> AntiDetectConfig:
    return AntiDetectConfig(
        profile="ksa_riyadh_win11",
        timezone="Asia/Riyadh",
        locale="ar-SA",
        accept_language="ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7",
        platform="Win32",
        os_version="10.0",
        screen_width=1920,
        screen_height=1080,
        avail_width=1920,
        avail_height=1040,
        color_depth=24,
        pixel_ratio=1.0,
        device_memory=8,
        hardware_concurrency=8,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 630)",
        canvas_noise=True,
        audio_noise=True,
        geolocation=GeolocationConfig(latitude=24.6877, longitude=46.7219, accuracy=25.0),
        proxy=ProxyConfig(
            enabled=False,
            proxy_type="residential",
            country_code="SA",
            city="Riyadh",
            rotate_every_n_sessions=1,
            pool=[],
        ),
        action_delay_min=1.0,
        action_delay_max=3.2,
        typing_delay_min=0.07,
        typing_delay_max=0.21,
        scroll_pause_min=0.5,
        scroll_pause_max=1.5,
        page_load_pause_min=2.0,
        page_load_pause_max=5.0,
        idle_drift_min=240,
        idle_drift_max=900,
        session_max_duration=5400,
        daily_active_hours_max=6.0,
    )


@pytest.fixture()
def stealth_engine():
    from web.anti_detect.stealth import StealthEngine

    return StealthEngine(_make_cfg())


@pytest.fixture()
def mock_page():
    page = MagicMock()
    page.add_init_script = AsyncMock()
    return page


@pytest.mark.asyncio
async def test_inject_calls_all_patches(stealth_engine, mock_page):
    """inject() must invoke all 11 _patch_* methods."""
    patch_names = [
        "_patch_webdriver",
        "_patch_navigator",
        "_patch_screen",
        "_patch_timezone",
        "_patch_webgl",
        "_patch_canvas",
        "_patch_audio",
        "_patch_chrome_runtime",
        "_patch_plugins",
        "_patch_permissions",
        "_patch_mouse_movement",
    ]
    called = []
    original_apply = stealth_engine._apply_script

    async def tracking_apply(page, js, name):
        called.append(name)
        await original_apply(page, js, name)

    stealth_engine._apply_script = tracking_apply
    await stealth_engine.inject(mock_page)
    for name in patch_names:
        short = name.replace("_patch_", "")
        assert any(short in c for c in called), f"Patch '{name}' not applied"


@pytest.mark.asyncio
async def test_patch_webdriver_uses_undefined(stealth_engine, mock_page):
    """Webdriver patch must set property to undefined, not false."""
    await stealth_engine._patch_webdriver(mock_page)
    call_args = mock_page.add_init_script.call_args[0][0]
    assert "undefined" in call_args
    assert "false" not in call_args.lower().replace("undefined", "")


@pytest.mark.asyncio
async def test_patch_timezone_offset_minus_180(stealth_engine, mock_page):
    """Timezone patch must set getTimezoneOffset to return -180 (UTC+3)."""
    await stealth_engine._patch_timezone(mock_page)
    call_args = mock_page.add_init_script.call_args[0][0]
    assert "-180" in call_args
    assert "Asia/Riyadh" in call_args


@pytest.mark.asyncio
async def test_patch_navigator_win32(stealth_engine, mock_page):
    """Navigator patch must advertise Win32 platform."""
    await stealth_engine._patch_navigator(mock_page)
    call_args = mock_page.add_init_script.call_args[0][0]
    assert "Win32" in call_args


@pytest.mark.asyncio
async def test_patch_chrome_runtime_present(stealth_engine, mock_page):
    """Chrome runtime patch must define window.chrome with runtime object."""
    await stealth_engine._patch_chrome_runtime(mock_page)
    call_args = mock_page.add_init_script.call_args[0][0]
    assert "window.chrome" in call_args
    assert "runtime" in call_args


@pytest.mark.asyncio
async def test_session_noise_is_consistent(stealth_engine):
    """Same engine instance produces same noise seed across calls."""
    noise1 = stealth_engine._session_noise
    noise2 = stealth_engine._session_noise
    assert noise1 == noise2
    assert 1.111111 <= noise1 <= 1.999999


@pytest.mark.asyncio
async def test_failed_patch_does_not_raise(stealth_engine, mock_page):
    """If add_init_script raises, _apply_script must swallow and not propagate."""
    mock_page.add_init_script = AsyncMock(side_effect=Exception("playwright error"))
    await stealth_engine._patch_webdriver(mock_page)
