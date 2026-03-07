"""FC 26 WEB APP — KSA timing windows and human-like action pacing."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone

from loguru import logger

from web.config_loader import AntiDetectConfig

ACTIVE_WINDOWS_UTC: tuple[tuple[int, int], ...] = (
    (5 * 60, 8 * 60 + 30),
    (10 * 60, 14 * 60 + 30),
    (17 * 60, 21 * 60 + 30),
)


class KSATiming:
    """Provides delay/jitter values and active-window checks in UTC."""

    def __init__(self, cfg: AntiDetectConfig) -> None:
        """Initialize timing engine with anti-detection configuration."""
        self._cfg = cfg
        self._session_start = time.monotonic()

    def _now_utc(self) -> datetime:
        """Return current UTC datetime for internal calculations."""
        return datetime.now(timezone.utc)

    def _minute_of_day(self, dt: datetime) -> int:
        """Convert UTC datetime to minute index in the day."""
        return dt.hour * 60 + dt.minute

    def is_active_window(self) -> bool:
        """Return True if now falls inside one of KSA-active UTC windows."""
        now = self._now_utc()
        minute = self._minute_of_day(now)
        for start, end in ACTIVE_WINDOWS_UTC:
            if start <= minute < end:
                return True
        return False

    def seconds_until_next_active(self) -> int:
        """Return strictly positive seconds until next active window starts."""
        now = self._now_utc()
        minute = self._minute_of_day(now)
        for start, _ in ACTIVE_WINDOWS_UTC:
            if minute < start:
                seconds = int((start - minute) * 60 - now.second)
                return max(1, seconds)
        tomorrow = now + timedelta(days=1)
        start = ACTIVE_WINDOWS_UTC[0][0]
        first_active = datetime(
            year=tomorrow.year,
            month=tomorrow.month,
            day=tomorrow.day,
            hour=start // 60,
            minute=start % 60,
            tzinfo=timezone.utc,
        )
        seconds = int((first_active - now).total_seconds())
        return max(1, seconds)

    def human_delay(self) -> float:
        """Return randomized action delay, slower during quiet windows."""
        delay = random.uniform(self._cfg.action_delay_min, self._cfg.action_delay_max)
        if not self.is_active_window():
            delay *= 1.5
        return delay

    def typing_delay(self) -> float:
        """Return randomized per-keystroke delay."""
        return random.uniform(self._cfg.typing_delay_min, self._cfg.typing_delay_max)

    def scroll_pause(self) -> float:
        """Return randomized pause after a scroll operation."""
        return random.uniform(self._cfg.scroll_pause_min, self._cfg.scroll_pause_max)

    def page_load_pause(self) -> float:
        """Return randomized pause after navigation/content loads."""
        return random.uniform(self._cfg.page_load_pause_min, self._cfg.page_load_pause_max)

    def idle_drift(self) -> float:
        """Return randomized long idle gap between cycles."""
        return random.uniform(self._cfg.idle_drift_min, self._cfg.idle_drift_max)

    def session_should_rotate(self) -> bool:
        """Return True when session age exceeds configured limit."""
        return (time.monotonic() - self._session_start) > self._cfg.session_max_duration

    def reset_session_timer(self) -> None:
        """Reset session age baseline after restart."""
        self._session_start = time.monotonic()

    def daily_hours_exhausted(self, hours_run_today: float) -> bool:
        """Return True when daily active hours cap has been reached."""
        exhausted = hours_run_today >= self._cfg.daily_active_hours_max
        if exhausted:
            logger.warning("Daily active hours cap reached — bot going offline.")
        return exhausted

