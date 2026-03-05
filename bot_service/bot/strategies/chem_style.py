"""Chemistry style trader: Shadow/Hunter deals."""

from typing import List

from loguru import logger

from bot.models import CycleResult
from bot.utils import calculate_profit, get_prev_bid

from bot.strategies.base import BaseStrategy

DEFENDER_POSITIONS: List[str] = ["CB", "LB", "RB", "LWB", "RWB"]
SHADOW = "Shadow"
HUNTER = "Hunter"


class ChemStyleTrader(BaseStrategy):
    """Buy cards with Shadow/Hunter applied but priced as unstyled; list at styled price."""

    def run_cycle(self) -> CycleResult:
        """Scan each chem_style player for styled deals; buy and list at styled market price."""
        buys = 0
        skipped = 0
        errors = 0
        players = self.cfg.chem_style.players
        if not players:
            return CycleResult(buys=0, skipped=0, errors=0)

        for player_cfg in players:
            name = player_cfg.get("name") or player_cfg.get("player_name", "")
            if not name:
                continue
            mp = self.db.get_market_price_with_chem(name, self.cfg.platform)
            if not mp:
                logger.debug("ChemStyle: no market price with chem for {}", name)
                skipped += 1
                continue
            price_no_chem = mp.price
            styled_market_price = mp.price_shadow or mp.price_hunter
            if not styled_market_price:
                skipped += 1
                continue
            position = player_cfg.get("position", "")
            target_chem = SHADOW if position in DEFENDER_POSITIONS else HUNTER
            buy_max_cfg = player_cfg.get("buy_max", player_cfg.get("max_buy"))
            if buy_max_cfg is None:
                buy_max_cfg = price_no_chem + self.cfg.chem_style.max_premium_coins
            max_buy = get_prev_bid(
                min(buy_max_cfg, price_no_chem + self.cfg.chem_style.max_premium_coins)
            )
            max_buy = max(200, max_buy)
            if not self.navigator.search_player(
                name=name,
                quality=player_cfg.get("quality"),
                position=position or None,
                max_buy_now=max_buy,
                chem_style=target_chem,
            ):
                errors += 1
                continue
            listings = self.navigator.get_listings(max_results=20, player_name=name)
            deals = self.scanner.find_chem_style_deals(listings, name)
            bought = False
            for listing in deals:
                if self.rate_limiter.daily_limit_reached():
                    break
                profit = calculate_profit(listing.buy_now_price, styled_market_price)
                if profit.roi_pct < self.cfg.chem_style.min_profit_pct:
                    continue
                if listing.buy_now_price > max_buy:
                    continue
                if self.execute_buy(listing, styled_market_price, "chem_style"):
                    buys += 1
                    if not self.dry_run:
                        start_price = max(
                            200, get_prev_bid(int(styled_market_price * 0.9))
                        )
                        self.navigator.list_item(
                            name,
                            start_price=start_price,
                            buy_now_price=styled_market_price,
                            duration_hours=1,
                        )
                    bought = True
                    break
                else:
                    errors += 1
            if not bought:
                skipped += 1
            self.navigator.clear_search_filters()

        return CycleResult(buys=buys, skipped=skipped, errors=errors)
