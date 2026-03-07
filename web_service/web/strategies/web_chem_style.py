"""FC 26 WEB APP — Chemistry Style Trader: buy styled cards priced as unstyled."""

from __future__ import annotations

from bot.models import CycleResult
from bot.utils import calculate_profit, get_prev_bid
from loguru import logger
from web.strategies.web_base import WebBaseStrategy

_CHEM_STYLES = ["Shadow", "Hunter"]


class WebChemStyleTrader(WebBaseStrategy):
    """Buys cards with Shadow/Hunter applied but priced near the unstyled value."""

    async def run_cycle(self) -> CycleResult:
        """Search for each player with each target chem style and buy deals."""
        buys = 0
        skipped = 0
        errors = 0

        for player_cfg in self.cfg.chem_style.players:
            if self.rate_limiter.daily_limit_reached():
                logger.warning("Daily limit reached — aborting chem style cycle.")
                break

            name = player_cfg.get("name", "")
            if not name:
                continue

            market_price = self.db.get_market_price(name, self.cfg.platform)
            if not market_price:
                skipped += 1
                continue

            chem_cost = self.cfg.chem_style.max_premium_coins
            threshold = int(market_price.price + chem_cost * 0.5)

            for style in _CHEM_STYLES:
                listings = await self.market.search_with_retry(name, chem_style=style)
                deals = [
                    l for l in listings
                    if (l.get("buy_now_price") or threshold + 1) <= threshold
                ]
                if not deals:
                    skipped += 1
                    continue

                best = min(deals, key=lambda x: x.get("buy_now_price") or 0)
                profit = calculate_profit(best["buy_now_price"], market_price.price)
                if profit.roi_pct < self.cfg.chem_style.min_profit_pct:
                    skipped += 1
                    continue

                sell_price = market_price.price - get_prev_bid(market_price.price)
                best["_sell_price"] = sell_price

                bought = await self._execute_buy(best, context="web_chem_style")
                if bought:
                    buys += 1
                    self.rate_limiter.cooldown_after_buy()
                    await self._execute_list(
                        name,
                        buy_now=sell_price,
                        start_bid=get_prev_bid(sell_price),
                        duration=1,
                    )
                else:
                    errors += 1

        return CycleResult(buys=buys, skipped=skipped, errors=errors)
