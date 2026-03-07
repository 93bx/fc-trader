"""FC 26 WEB APP — Mass Bidder strategy: place bids below max_bid, collect won items."""

from __future__ import annotations

from bot.models import CycleResult
from bot.utils import get_prev_bid
from loguru import logger
from web.strategies.web_base import WebBaseStrategy


class WebMassBidder(WebBaseStrategy):
    """Bids below calculated max_bid; collects and relists won items."""

    async def run_cycle(self) -> CycleResult:
        """Collect won items, relist, then place bids on all configured players."""
        buys = 0
        skipped = 0
        errors = 0

        await self.navigator.collect_won_items()
        await self.market.execute_relist_cycle()

        for player_cfg in self.cfg.mass_bidder.players:
            if self.rate_limiter.daily_limit_reached():
                logger.warning("Daily limit reached — aborting mass bidder cycle.")
                break

            name = player_cfg.get("name", "")
            if not name:
                continue

            market_price = self.db.get_market_price(name, self.cfg.platform)
            if not market_price:
                skipped += 1
                continue

            max_bid = int((market_price.price * 0.95) - self.cfg.mass_bidder.min_profit_coins)
            max_bid = min(max_bid, int(market_price.price * 0.85))
            max_bid = get_prev_bid(max_bid)
            if max_bid <= 0:
                skipped += 1
                continue

            listings = await self.market.search_with_retry(name)
            if not listings:
                skipped += 1
                continue

            for listing in listings:
                current_bid = listing.get("current_bid") or 0
                if current_bid >= max_bid:
                    continue
                await self.rate_limiter.check_and_wait("bid")
                result = await self.navigator.place_bid(listing["card_index"], max_bid)
                from web.web_navigator import BidResult
                if result == BidResult.SUCCESS:
                    buys += 1
                elif result == BidResult.RATE_LIMITED:
                    logger.warning("Bid rate limited — aborting player {} cycle.", name)
                    errors += 1
                    break
                else:
                    skipped += 1

        return CycleResult(buys=buys, skipped=skipped, errors=errors)
