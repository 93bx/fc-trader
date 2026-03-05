"""Peak-sell strategy: sell/relist only, no buying."""

from loguru import logger

from bot.models import CycleResult
from bot.utils import get_prev_bid

from bot.strategies.base import BaseStrategy


class PeakSellStrategy(BaseStrategy):
    """During PEAK_SELL phase: list held items and relist expired; no buying."""

    def run_cycle(self) -> CycleResult:
        """List unlisted held items at market price; relist expired if detected."""
        skipped = 0
        errors = 0
        listed = 0
        items = self.portfolio.get_held_items()
        for item in items:
            if item.status != "held":
                continue
            mp = self.db.get_market_price(item.player_name, self.cfg.platform)
            if not mp:
                logger.debug("PeakSell: no market price for {}", item.player_name)
                skipped += 1
                continue
            list_at = mp.price
            start_price = max(200, get_prev_bid(int(list_at * 0.9)))
            if self.dry_run:
                logger.info(
                    "[DRY RUN] Would list {} at {}",
                    item.player_name,
                    list_at,
                )
                listed += 1
                continue
            if self.navigator.list_item(
                item.player_name,
                start_price=start_price,
                buy_now_price=list_at,
                duration_hours=1,
            ):
                listed += 1
                if item.id is not None:
                    self.db.update_portfolio_item(item.id, "listed")
            else:
                errors += 1
        return CycleResult(buys=0, skipped=skipped, errors=errors)
