"""Trading strategies: Sniper, Mass Bidder, Chemistry Style Trader, Peak Sell."""

from bot.strategies.base import BaseStrategy
from bot.strategies.chem_style import ChemStyleTrader
from bot.strategies.mass_bidder import MassBidder
from bot.strategies.peak_sell import PeakSellStrategy
from bot.strategies.sniper import Sniper

__all__ = [
    "BaseStrategy",
    "Sniper",
    "MassBidder",
    "ChemStyleTrader",
    "PeakSellStrategy",
]
