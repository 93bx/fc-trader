"""FC 26 WEB APP — Tests for KSATiming active-window and delay logic."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from web.config_loader import AntiDetectConfig, GeolocationConfig, ProxyConfig


def _make_cfg(daily_hours_max: float = 6.0) -> AntiDetectConfig:
    return AntiDetectConfig(
        profile="ksa",
        timezone="Asia/Riyadh",
        locale="ar-SA",
        accept_language="ar-SA",
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
        user_agent="Mozilla",
        webgl_vendor="Google Inc.",
        webgl_renderer="ANGLE",
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
        daily_active_hours_max=daily_hours_max,
    )


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 7, hour, minute, 0, tzinfo=timezone.utc)


@pytest.fixture()
def timing():
    from web.anti_detect.timing import KSATiming

    return KSATiming(_make_cfg())


def test_is_active_morning_session(timing):
    """UTC 06:00 is inside first active window (05:00–08:30)."""
    with patch.object(timing, "_now_utc", return_value=_dt(6, 0)):
        assert timing.is_active_window() is True


def test_is_active_afternoon_session(timing):
    """UTC 12:00 is inside second active window (10:00–14:30)."""
    with patch.object(timing, "_now_utc", return_value=_dt(12, 0)):
        assert timing.is_active_window() is True


def test_is_active_evening_session(timing):
    """UTC 19:00 is inside third active window (17:00–21:30)."""
    with patch.object(timing, "_now_utc", return_value=_dt(19, 0)):
        assert timing.is_active_window() is True


def test_is_quiet_early_morning(timing):
    """UTC 03:00 (Fajr/sleep) is NOT an active window."""
    with patch.object(timing, "_now_utc", return_value=_dt(3, 0)):
        assert timing.is_active_window() is False


def test_is_quiet_midday_break(timing):
    """UTC 09:00 (midday gap) is NOT an active window."""
    with patch.object(timing, "_now_utc", return_value=_dt(9, 0)):
        assert timing.is_active_window() is False


def test_is_quiet_afternoon_gap(timing):
    """UTC 15:30 (Asr gap) is NOT an active window."""
    with patch.object(timing, "_now_utc", return_value=_dt(15, 30)):
        assert timing.is_active_window() is False


def test_is_quiet_midnight(timing):
    """UTC 23:00 (late night) is NOT an active window."""
    with patch.object(timing, "_now_utc", return_value=_dt(23, 0)):
        assert timing.is_active_window() is False


def test_seconds_until_next_active_during_quiet_window(timing):
    """During a quiet window, seconds_until_next_active must be > 0."""
    with patch.object(timing, "_now_utc", return_value=_dt(9, 0)):
        secs = timing.seconds_until_next_active()
        assert secs > 0


def test_seconds_until_next_active_at_end_of_last_window(timing):
    """After the last window, next active is tomorrow morning — still > 0."""
    with patch.object(timing, "_now_utc", return_value=_dt(22, 0)):
        secs = timing.seconds_until_next_active()
        assert secs > 0


def test_human_delay_within_range(timing):
    """human_delay() always returns value within configured bounds."""
    for _ in range(20):
        d = timing.human_delay()
        assert d >= timing._cfg.action_delay_min


def test_daily_hours_not_exhausted(timing):
    assert timing.daily_hours_exhausted(5.9) is False


def test_daily_hours_exhausted_at_cap(timing):
    assert timing.daily_hours_exhausted(6.0) is True


def test_daily_hours_exhausted_over_cap(timing):
    assert timing.daily_hours_exhausted(7.0) is True


def test_session_rotation_false_when_young(timing):
    assert timing.session_should_rotate() is False
