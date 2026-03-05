"""Unit tests for bot.calendar_engine: phase boundaries, strategy mapping, descriptions."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.calendar_engine import CalendarEngine, MarketPhase


@pytest.fixture
def config_empty_promos() -> MagicMock:
    """Config with no promos."""
    cfg = MagicMock()
    cfg.promos = []
    return cfg


@pytest.fixture
def engine(config_empty_promos: MagicMock) -> CalendarEngine:
    return CalendarEngine(config_empty_promos)


class TestPhaseBoundaries:
    """Phase boundaries (UTC)."""

    @freeze_time("2025-03-06 12:00:00+00:00")  # Thursday 12:00 UTC (between RIVALS and PEAK_SELL)
    def test_thursday_1200_standard(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.STANDARD

    @freeze_time("2025-03-06 07:00:00+00:00")  # Thursday 07:00 UTC
    def test_thursday_0700_rivals_rewards(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.RIVALS_REWARDS

    @freeze_time("2025-03-06 09:30:00+00:00")  # Thursday 09:30
    def test_thursday_0930_rivals_rewards(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.RIVALS_REWARDS

    @freeze_time("2025-03-07 17:00:00+00:00")  # Friday 17:00
    def test_friday_1700_promo_drop(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.PROMO_DROP

    @freeze_time("2025-03-05 12:00:00+00:00")  # Wednesday 12:00
    def test_wednesday_midweek_dip(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.MIDWEEK_DIP

    @freeze_time("2025-03-09 07:00:00+00:00")  # Sunday 07:00
    def test_sunday_0700_squad_battles(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.SQUAD_BATTLES

    @freeze_time("2025-03-06 03:00:00+00:00")  # Thursday 03:00 -> overnight
    def test_0300_overnight(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.OVERNIGHT

    @freeze_time("2025-03-10 12:00:00+00:00")  # Monday 12:00
    def test_monday_standard(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.STANDARD

    @freeze_time("2025-03-06 18:00:00+00:00")  # Thursday 18:00 -> peak sell
    def test_thursday_1800_peak_sell(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.PEAK_SELL

    @freeze_time("2025-03-07 15:00:00+00:00")  # Friday 15:00 -> still peak sell (boundary is 16:00 / 17:00)
    def test_friday_1500_peak_sell(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.PEAK_SELL

    @freeze_time("2025-03-07 16:30:00+00:00")  # Friday 16:30 -> should be PEAK_SELL, not STANDARD
    def test_friday_1630_peak_sell_gap(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.PEAK_SELL

    @freeze_time("2025-03-07 20:00:00+00:00")  # Friday 20:00 -> weekend buy
    def test_friday_2000_weekend_buy(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.WEEKEND_BUY

    @freeze_time("2025-03-08 09:00:00+00:00")  # Saturday 09:00 -> weekend buy
    def test_saturday_0900_weekend_buy(self, engine: CalendarEngine) -> None:
        assert engine.get_current_phase() == MarketPhase.WEEKEND_BUY


class TestGetRecommendedStrategy:
    """Strategy name for each phase."""

    def test_rivals_rewards(self, engine: CalendarEngine) -> None:
        assert engine.get_recommended_strategy(MarketPhase.RIVALS_REWARDS) == "mass_bidder"

    def test_promo_drop(self, engine: CalendarEngine) -> None:
        assert engine.get_recommended_strategy(MarketPhase.PROMO_DROP) == "chem_style"

    def test_peak_sell(self, engine: CalendarEngine) -> None:
        assert engine.get_recommended_strategy(MarketPhase.PEAK_SELL) == "peak_sell"

    def test_weekend_buy(self, engine: CalendarEngine) -> None:
        assert engine.get_recommended_strategy(MarketPhase.WEEKEND_BUY) == "sniper"

    def test_overnight(self, engine: CalendarEngine) -> None:
        assert engine.get_recommended_strategy(MarketPhase.OVERNIGHT) == "mass_bidder"

    def test_midweek_dip(self, engine: CalendarEngine) -> None:
        assert engine.get_recommended_strategy(MarketPhase.MIDWEEK_DIP) == "sniper"

    def test_squad_battles(self, engine: CalendarEngine) -> None:
        assert engine.get_recommended_strategy(MarketPhase.SQUAD_BATTLES) == "mass_bidder"

    def test_standard(self, engine: CalendarEngine) -> None:
        assert engine.get_recommended_strategy(MarketPhase.STANDARD) == "sniper"


class TestIsPromoActive:
    """Promo active from config windows."""

    def test_empty_promos_false(self, engine: CalendarEngine) -> None:
        assert engine.is_promo_active() is False

    @freeze_time("2025-03-07 18:00:00+00:00")
    def test_promo_window_active_true(self, config_empty_promos: MagicMock) -> None:
        config_empty_promos.promos = [
            {"start": "2025-03-07T17:00:00Z", "end": "2025-03-07T20:00:00Z"},
        ]
        engine = CalendarEngine(config_empty_promos)
        assert engine.is_promo_active() is True


class TestGetPhaseDescription:
    """Human-readable description for each phase."""

    def test_each_phase_has_description(self, engine: CalendarEngine) -> None:
        for phase in MarketPhase:
            desc = engine.get_phase_description(phase)
            assert isinstance(desc, str)
            assert len(desc) > 0


class TestTimeUntilNextPhase:
    """time_until_next_phase returns positive timedelta."""

    def test_returns_positive_delta(self, engine: CalendarEngine) -> None:
        delta = engine.time_until_next_phase()
        assert delta.total_seconds() > 0
