"""Dataclasses for FC Trader: market prices, trades, rate state, portfolio, SBC signals, listings, profit and cycle results."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class MarketPrice:
    """Single market price record from intel (FUTWIZ/FUTBIN/etc)."""

    player_id: str
    player_name: str
    source: str
    platform: str
    price: int
    scraped_at: datetime
    price_shadow: Optional[int] = None
    price_hunter: Optional[int] = None
    id: Optional[int] = None


@dataclass
class Trade:
    """Record of a single buy or sell executed by the bot."""

    player_name: str
    strategy: str
    action: str
    platform: str
    executed_at: datetime
    buy_price: Optional[int] = None
    sell_price: Optional[int] = None
    profit_net: Optional[int] = None
    dry_run: bool = False
    id: Optional[int] = None


@dataclass
class RateState:
    """Persisted rate limit state for one action type (search, buy, list, bid)."""

    action_type: str
    count_today: int
    count_hour: int
    last_action_at: Optional[datetime] = None
    hour_reset_at: Optional[datetime] = None
    day_reset_at: Optional[datetime] = None


@dataclass
class PortfolioItem:
    """Single item in the bot's portfolio (bought, held, listed, or sold)."""

    player_name: str
    buy_price: int
    status: str
    acquired_at: datetime
    listed_price: Optional[int] = None
    listed_at: Optional[datetime] = None
    sold_at: Optional[datetime] = None
    id: Optional[int] = None


@dataclass
class PortfolioSummary:
    """Aggregate summary of portfolio for get_portfolio_summary()."""

    total_cost: int
    total_listed_value: int
    total_sold_value: int
    count_held: int
    count_listed: int
    count_sold: int
    total_profit: int
    roi_pct: float


@dataclass
class SbcSignal:
    """SBC detected by intel (FUT.GG etc); may drive fodder signals."""

    sbc_name: str
    detected_at: datetime
    rating_req: Optional[int] = None
    expires_at: Optional[datetime] = None
    id: Optional[int] = None


@dataclass
class Listing:
    """Single transfer market listing scraped from the app (for strategies/market/navigator)."""

    player_name: str
    buy_now_price: int
    current_bid: int
    time_remaining: str


@dataclass
class ProfitResult:
    """Result of profit calculation (EA 5% tax applied)."""

    net_received: int
    profit: int
    roi_pct: float


@dataclass
class CycleResult:
    """Result of one strategy run_cycle()."""

    buys: int
    skipped: int
    errors: int
