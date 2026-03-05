"""Sniper strategy: Buy Now only, undercut list price."""

from typing import List

from loguru import logger

from bot.models import CycleResult, Listing
from bot.utils import calculate_max_buy, get_prev_bid

from bot.strategies.base import BaseStrategy


class Sniper(BaseStrategy):
    """Buy Now only; list at FUTWIZ market minus one bid increment."""

    def run_cycle(self) -> CycleResult:
        """Scan each configured player, buy first underpriced listing, list at undercut."""
        buys = 0
        skipped = 0
        errors = 0
        players: List[dict] = self.cfg.sniper.players
        if not players:
            return CycleResult(buys=0, skipped=0, errors=0)

        for player_cfg in players:
            name = player_cfg.get("name") or player_cfg.get("player_name", "")
            if not name:
                continue
            mp = self.db.get_market_price(name, self.cfg.platform)
            if not mp:
                logger.debug("Sniper: no market price for {}", name)
                skipped += 1
                continue
            max_buy = calculate_max_buy(mp.price, self.cfg.sniper.min_profit_pct)
            pcfg = {
                "name": name,
                "player_name": name,
                "quality": player_cfg.get("quality"),
                "position": player_cfg.get("position"),
                "sell_target": mp.price,
                "min_profit_pct": self.cfg.sniper.min_profit_pct,
                "buy_max": max_buy,
                "max_buy": max_buy,
            }
            if not self.navigator.search_player(
                name=name,
                quality=pcfg.get("quality"),
                position=pcfg.get("position"),
                max_buy_now=max_buy,
            ):
                errors += 1
                continue
            listings = self.navigator.get_listings(max_results=10, player_name=name)
            underpriced = self.scanner.find_underpriced(listings, max_buy)
            bought = False
            for listing in underpriced:
                if self.should_buy(listing, pcfg):
                    list_at = max(200, get_prev_bid(mp.price - 1))
                    start_price = max(200, get_prev_bid(int(list_at * 0.9)))
                    if self.execute_buy(listing, list_at, "sniper"):
                        buys += 1
                        if not self.dry_run:
                            self.navigator.list_item(
                                name,
                                start_price=start_price,
                                buy_now_price=list_at,
                                duration_hours=1,
                            )
                        bought = True
                    else:
                        errors += 1
                    break
            if not bought:
                skipped += 1
            self.navigator.clear_search_filters()

        return CycleResult(buys=buys, skipped=skipped, errors=errors)
