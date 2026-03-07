"""FC 26 WEB APP — Abstract base for all web trading strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

from bot.models import CycleResult, Trade
from bot.utils import calculate_profit

if TYPE_CHECKING:
    from bot.database import Database
    from web.anti_detect.timing import KSATiming
    from web.config_loader import WebConfig
    from web.web_market import WebMarket
    from web.web_navigator import WebNavigator
    from web.web_rate_limiter import WebRateLimiter


class WebBaseStrategy(ABC):
    """Abstract base class for all web trading strategies."""

    def __init__(
        self,
        market: "WebMarket",
        navigator: "WebNavigator",
        db: "Database",
        rate_limiter: "WebRateLimiter",
        timing: "KSATiming",
        cfg: "WebConfig",
        dry_run: bool = False,
    ) -> None:
        """Store all shared dependencies."""
        self.market = market
        self.navigator = navigator
        self.db = db
        self.rate_limiter = rate_limiter
        self.timing = timing
        self.cfg = cfg
        self.dry_run = dry_run

    @abstractmethod
    async def run_cycle(self) -> CycleResult:
        """Execute one full strategy cycle."""

    async def _execute_buy(self, listing: dict, context: str) -> bool:
        """Execute buy with dry-run gate, logging, and trade DB write."""
        player = listing.get("player_name", "unknown")
        price = listing.get("buy_now_price", 0)
        if self.dry_run:
            logger.info("[DRY RUN] WEB BUY {} | paid={} | context={}", player, price, context)
            return True
        bought = await self.market.buy_best_listing([listing], price)
        if bought is not None:
            sell_price = listing.get("_sell_price", price)
            profit = calculate_profit(price, sell_price)
            trade = Trade(
                player_name=player,
                strategy=context,
                action="buy",
                platform=self.cfg.platform,
                executed_at=datetime.now(timezone.utc),
                buy_price=price,
                sell_price=sell_price,
                profit_net=profit.profit,
                dry_run=False,
            )
            self.db.insert_trade(trade)
            logger.info(
                "WEB BUY | {} | {} | paid={} | list_at={} | expected_profit={}",
                player,
                context,
                price,
                sell_price,
                profit.profit,
            )
            return True
        return False

    async def _execute_list(
        self, player: str, buy_now: int, start_bid: int, duration: int = 1
    ) -> bool:
        """Execute list with dry-run gate and logging."""
        if self.dry_run:
            logger.info("[DRY RUN] WEB LIST {} at {} (bid={})", player, buy_now, start_bid)
            return True
        ok = await self.navigator.list_item(player, start_bid, buy_now, duration)
        if ok:
            logger.info("WEB LIST | {} | buy_now={} | start_bid={}", player, buy_now, start_bid)
        return ok
