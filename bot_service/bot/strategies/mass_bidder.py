"""Mass bidder strategy: bid then relist won items."""

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from bot.models import CycleResult, Trade
from bot.utils import calculate_profit, get_next_bid, get_prev_bid

from bot.strategies.base import BaseStrategy

WON_CHECK_INTERVAL_SEC = 1800
TRANSFER_TARGET_LIMIT = 50


class MassBidder(BaseStrategy):
    """Bid on listings below max_bid; every 30 min check won items and relist at BIN."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_won_check: Optional[datetime] = None

    def run_cycle(self) -> CycleResult:
        """Bid phase every cycle; won-items phase every 30 minutes."""
        buys = 0
        skipped = 0
        errors = 0
        bid_count = 0
        players = self.cfg.mass_bidder.players
        if not players:
            return CycleResult(buys=0, skipped=0, errors=0)

        for player_cfg in players:
            if bid_count >= TRANSFER_TARGET_LIMIT:
                break
            name = player_cfg.get("name") or player_cfg.get("player_name", "")
            if not name:
                continue
            mp = self.db.get_market_price(name, self.cfg.platform)
            if not mp:
                skipped += 1
                continue
            max_bid = get_prev_bid(
                int((mp.price * 0.95) - self.cfg.mass_bidder.min_profit_coins)
            )
            max_bid = max(200, max_bid)
            if not self.navigator.search_player(
                name=name,
                quality=player_cfg.get("quality"),
                position=player_cfg.get("position"),
                max_buy_now=None,
            ):
                errors += 1
                continue
            listings = self.navigator.get_listings(max_results=20, player_name=name)
            for listing in listings:
                if bid_count >= TRANSFER_TARGET_LIMIT:
                    break
                bin_floor = int(listing.buy_now_price * 0.85)
                if listing.current_bid >= max_bid:
                    continue
                if max_bid > bin_floor:
                    continue
                bid_amount = get_next_bid(listing.current_bid)
                if bid_amount > max_bid:
                    bid_amount = max_bid
                if not self.dry_run:
                    if self.navigator.place_bid(listing, bid_amount):
                        bid_count += 1
                    else:
                        errors += 1
                else:
                    logger.info(
                        "[DRY RUN] Would place bid on {} at {}",
                        listing.player_name,
                        bid_amount,
                    )
                    bid_count += 1
            self.navigator.clear_search_filters()

        now = datetime.now(timezone.utc)
        if self._last_won_check is None:
            self._last_won_check = now
        if (now - self._last_won_check).total_seconds() >= WON_CHECK_INTERVAL_SEC:
            if self.navigator.go_to_transfer_list():
                won_items = self.navigator.get_won_items()
                for player_name, win_price in won_items:
                    mp = self.db.get_market_price(player_name, self.cfg.platform)
                    if not mp:
                        continue
                    list_at = mp.price
                    start_price = max(200, get_prev_bid(int(list_at * 0.9)))
                    if not self.dry_run:
                        if self.navigator.list_item(
                            player_name,
                            start_price=start_price,
                            buy_now_price=list_at,
                            duration_hours=1,
                        ):
                            self.portfolio.record_purchase(
                                player_name, win_price, "mass_bidder"
                            )
                            profit_result = calculate_profit(win_price, list_at)
                            trade = Trade(
                                player_name=player_name,
                                strategy="mass_bidder",
                                action="buy",
                                platform=self.cfg.platform,
                                executed_at=now,
                                buy_price=win_price,
                                sell_price=list_at,
                                profit_net=profit_result.profit,
                                dry_run=False,
                            )
                            self.db.insert_trade(trade)
                            buys += 1
                    else:
                        logger.info(
                            "[DRY RUN] Would list won item {} at {}",
                            player_name,
                            list_at,
                        )
            self._last_won_check = now

        return CycleResult(buys=buys, skipped=skipped, errors=errors)
