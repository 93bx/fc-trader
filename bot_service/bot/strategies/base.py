"""Base strategy interface (run_cycle, should_buy, execute_buy)."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

from bot.models import CycleResult, Listing, Trade
from bot.utils import calculate_profit

if TYPE_CHECKING:
    from bot.config_loader import Config
    from bot.database import Database
    from bot.navigator import Navigator
    from bot.portfolio import Portfolio
    from bot.rate_limiter import RateLimiter

    from bot.market import MarketScanner


class BaseStrategy(ABC):
    """Abstract base for all trading strategies. No device access — use navigator/scanner only."""

    def __init__(
        self,
        navigator: "Navigator",
        scanner: "MarketScanner",
        portfolio: "Portfolio",
        rate_limiter: "RateLimiter",
        db: "Database",
        cfg: "Config",
        dry_run: bool = False,
    ) -> None:
        """Store navigator, scanner, portfolio, rate_limiter, db, config, and dry_run flag."""
        self.navigator = navigator
        self.scanner = scanner
        self.portfolio = portfolio
        self.rate_limiter = rate_limiter
        self.db = db
        self.cfg = cfg
        self.dry_run = dry_run

    @abstractmethod
    def run_cycle(self) -> CycleResult:
        """Execute one full scan-and-trade cycle."""

    def should_buy(self, listing: Listing, player_cfg: dict) -> bool:
        """Universal buy gate: profit check + buy_max check + daily limit check."""
        sell_target = player_cfg.get("sell_target")
        if sell_target is None:
            mp = self.db.get_market_price(listing.player_name, self.cfg.platform)
            sell_target = mp.price if mp else 0
        if sell_target <= 0:
            return False
        profit = calculate_profit(listing.buy_now_price, sell_target)
        min_pct = player_cfg.get("min_profit_pct", self.cfg.sniper.min_profit_pct)
        if profit.roi_pct < min_pct:
            return False
        buy_max = player_cfg.get("buy_max", player_cfg.get("max_buy"))
        if buy_max is not None and listing.buy_now_price > buy_max:
            return False
        if self.rate_limiter.daily_limit_reached():
            return False
        return True

    def execute_buy(self, listing: Listing, list_at: int, strategy_name: str) -> bool:
        """Wraps navigator.buy_now with dry_run gate and full logging/DB updates."""
        if self.dry_run:
            logger.info(
                "[DRY RUN] Would buy {} at {}",
                listing.player_name,
                listing.buy_now_price,
            )
            return True
        success = self.navigator.buy_now(listing)
        if success:
            self.rate_limiter.cooldown_after_buy()
            self.portfolio.record_purchase(
                listing.player_name, listing.buy_now_price, strategy_name
            )
            profit_result = calculate_profit(listing.buy_now_price, list_at)
            trade = Trade(
                player_name=listing.player_name,
                strategy=strategy_name,
                action="buy",
                platform=self.cfg.platform,
                executed_at=datetime.now(timezone.utc),
                buy_price=listing.buy_now_price,
                sell_price=list_at,
                profit_net=profit_result.profit,
                dry_run=False,
            )
            self.db.insert_trade(trade)
            logger.info(
                "BUY | {} | {} | paid={} | list_at={} | expected_profit={}",
                listing.player_name,
                strategy_name,
                listing.buy_now_price,
                list_at,
                profit_result.profit,
            )
        return success
