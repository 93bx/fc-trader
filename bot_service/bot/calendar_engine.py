"""Time/phase awareness only (UTC, market phases, no trading logic)."""

from datetime import datetime, timedelta, time, timezone
from enum import Enum
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from bot.config_loader import Config


class MarketPhase(Enum):
    """Market phases from .cursorrules section 8; all UTC."""

    RIVALS_REWARDS = "rivals_rewards"
    PROMO_DROP = "promo_drop"
    PEAK_SELL = "peak_sell"
    WEEKEND_BUY = "weekend_buy"
    OVERNIGHT = "overnight"
    MIDWEEK_DIP = "midweek_dip"
    SQUAD_BATTLES = "squad_battles"
    STANDARD = "standard"


# Weekday: Monday=0, Sunday=6
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def _utc_now() -> datetime:
    """Current time in UTC (testable by patching)."""
    return datetime.now(timezone.utc)


class CalendarEngine:
    """Determines current market phase and recommended strategy from UTC time and config."""

    def __init__(self, cfg: "Config") -> None:
        """Store config for promo windows and any overrides."""
        self._cfg = cfg

    def get_current_phase(self) -> MarketPhase:
        """Current phase from UTC time and day; checks config promos second, then STANDARD."""
        now = _utc_now()
        weekday = now.weekday()
        t = now.time()

        # OVERNIGHT: 00:00–07:00 any day
        if time(0, 0) <= t < time(7, 0):
            return MarketPhase.OVERNIGHT

        # RIVALS_REWARDS: Thursday 07:00–10:00 UTC
        if weekday == THU and time(7, 0) <= t < time(10, 0):
            return MarketPhase.RIVALS_REWARDS

        # PEAK_SELL: Thursday 18:00 – Friday 16:00 UTC (inclusive of Fri 16:00)
        if weekday == THU and t >= time(18, 0):
            return MarketPhase.PEAK_SELL
        if weekday == FRI and t < time(17, 0):
            return MarketPhase.PEAK_SELL

        # PROMO_DROP: Friday 17:00–20:00 UTC
        if weekday == FRI and time(17, 0) <= t < time(20, 0):
            return MarketPhase.PROMO_DROP

        # WEEKEND_BUY: Friday 20:00 – Saturday 10:00 UTC
        if weekday == FRI and t >= time(20, 0):
            return MarketPhase.WEEKEND_BUY
        if weekday == SAT and t < time(10, 0):
            return MarketPhase.WEEKEND_BUY

        # SQUAD_BATTLES: Sunday 07:00–10:00 UTC
        if weekday == SUN and time(7, 0) <= t < time(10, 0):
            return MarketPhase.SQUAD_BATTLES

        # MIDWEEK_DIP: Wednesday all day (remaining part after OVERNIGHT already handled)
        if weekday == WED:
            return MarketPhase.MIDWEEK_DIP

        return MarketPhase.STANDARD

    def get_recommended_strategy(self, phase: MarketPhase) -> str:
        """Return strategy name for the phase (authoritative mapping from .cursorrules)."""
        if phase == MarketPhase.RIVALS_REWARDS:
            return "mass_bidder"
        if phase == MarketPhase.PROMO_DROP:
            return "chem_style"
        if phase == MarketPhase.PEAK_SELL:
            return "peak_sell"
        if phase == MarketPhase.WEEKEND_BUY:
            return "sniper"
        if phase == MarketPhase.OVERNIGHT:
            return "mass_bidder"
        if phase == MarketPhase.MIDWEEK_DIP:
            return "sniper"
        if phase == MarketPhase.SQUAD_BATTLES:
            return "mass_bidder"
        return "sniper"

    def is_promo_active(self) -> bool:
        """True if any config promo window contains current UTC time."""
        if not self._cfg.promos:
            return False
        now = _utc_now()
        for promo in self._cfg.promos:
            start_s = promo.get("start")
            end_s = promo.get("end")
            if not start_s or not end_s:
                continue
            try:
                start_dt = datetime.fromisoformat(start_s.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_s.replace("Z", "+00:00"))
                if start_dt <= now <= end_dt:
                    return True
            except (ValueError, TypeError):
                logger.warning("Invalid promo window in config: start={!r} end={!r}", start_s, end_s)
        return False

    def get_phase_description(self, phase: MarketPhase) -> str:
        """Human-readable description of what the bot should do in this phase."""
        desc = {
            MarketPhase.RIVALS_REWARDS: "Rivals rewards drop; run Mass Bidder.",
            MarketPhase.PROMO_DROP: "Promo pack drop; run Chem Style Trader.",
            MarketPhase.PEAK_SELL: "Peak sell window; sell/relist only, no buying.",
            MarketPhase.WEEKEND_BUY: "Weekend buy window; run Sniper.",
            MarketPhase.OVERNIGHT: "Overnight low activity; run Mass Bidder.",
            MarketPhase.MIDWEEK_DIP: "Midweek dip; run Sniper (selector may alternate with Chem Style).",
            MarketPhase.SQUAD_BATTLES: "Squad Battles rewards; run Mass Bidder.",
            MarketPhase.STANDARD: "Standard market; run Sniper.",
        }
        return desc.get(phase, "Unknown phase.")

    def time_until_next_phase(self) -> timedelta:
        """Time until the next phase boundary (next hour UTC for simplicity)."""
        now = _utc_now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        delta = next_hour - now
        return delta if delta.total_seconds() > 0 else timedelta(seconds=60)
