"""FC 26 WEB APP — Sniper strategy: Buy Now only on underpriced listings."""

from __future__ import annotations

from bot.models import CycleResult
from bot.utils import calculate_max_buy, calculate_profit, get_prev_bid
from loguru import logger
from web.strategies.web_base import WebBaseStrategy


class WebSniper(WebBaseStrategy):
    """Buy Now only; never bids; targets listings below calculated max_buy price."""

    async def run_cycle(self) -> CycleResult:
        """Scan configured players and buy profitable underpriced listings."""
        buys = 0
        skipped = 0
        errors = 0

        for player_cfg in self.cfg.sniper.players:
            if self.rate_limiter.daily_limit_reached():
                logger.warning("Daily limit reached — aborting sniper cycle.")
                break

            name = player_cfg.get("name", "")
            if not name:
                continue

            market_price = self.db.get_market_price(name, self.cfg.platform)
            if not market_price:
                skipped += 1
                continue

            max_buy = calculate_max_buy(market_price.price, self.cfg.sniper.min_profit_pct)
            quality = player_cfg.get("quality", "")
            position = player_cfg.get("position", "")

            listings = await self.market.search_with_retry(
                name,
                max_buy_now=max_buy,
                quality=quality if quality else None,
                position=position if position else None,
            )

            if not listings:
                skipped += 1
                continue

            best = min(
                (l for l in listings if l.get("buy_now_price") is not None),
                key=lambda x: x["buy_now_price"],
                default=None,
            )
            if best is None:
                skipped += 1
                continue

            profit = calculate_profit(best["buy_now_price"], market_price.price)
            if profit.roi_pct < self.cfg.sniper.min_profit_pct:
                skipped += 1
                continue

            sell_price = market_price.price - get_prev_bid(market_price.price)
            best["_sell_price"] = sell_price

            bought = await self._execute_buy(best, context="web_sniper")
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
