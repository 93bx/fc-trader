"""Selects strategy by market phase (calendar) and config; handles promo override and MIDWEEK_DIP alternating."""

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from bot.calendar_engine import CalendarEngine, MarketPhase
    from bot.config_loader import Config


class StrategySelector:
    """Returns the appropriate strategy name for the given phase per .cursorrules section 8."""

    def __init__(self, calendar: "CalendarEngine", cfg: "Config") -> None:
        """Store calendar engine and config."""
        self._calendar = calendar
        self._cfg = cfg
        self._midweek_cycle = 0
        self._promo_cycle = 0

    def get_strategy_name(self, phase: "MarketPhase") -> str:
        """
        Return strategy name for the given phase.
        Promo active: force mass_bidder or sniper (no ChemStyle). MIDWEEK_DIP: alternate sniper/chem_style.
        """
        from bot.calendar_engine import MarketPhase

        if self._calendar.is_promo_active():
            self._promo_cycle += 1
            name = "sniper" if self._promo_cycle % 2 == 0 else "mass_bidder"
            logger.info(
                "StrategySelector: promo active → {} (phase={})",
                name,
                phase.value,
            )
            return name

        if phase == MarketPhase.RIVALS_REWARDS:
            name = "mass_bidder"
        elif phase == MarketPhase.PROMO_DROP:
            name = "chem_style"
        elif phase == MarketPhase.PEAK_SELL:
            name = "peak_sell"
        elif phase == MarketPhase.WEEKEND_BUY:
            name = "sniper"
        elif phase == MarketPhase.OVERNIGHT:
            name = "mass_bidder"
        elif phase == MarketPhase.MIDWEEK_DIP:
            self._midweek_cycle += 1
            name = "chem_style" if self._midweek_cycle % 2 == 0 else "sniper"
        elif phase == MarketPhase.SQUAD_BATTLES:
            name = "mass_bidder"
        elif phase == MarketPhase.STANDARD:
            name = "sniper"
        else:
            name = "sniper"

        logger.info(
            "StrategySelector: phase={} → {}",
            phase.value,
            name,
        )
        return name
