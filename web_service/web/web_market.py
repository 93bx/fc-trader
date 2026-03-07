"""FC 26 WEB APP — Transfer Market coordination layer (search + buy + relist)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from loguru import logger

from web.anti_detect.timing import KSATiming
from web.config_loader import WebConfig
from web.web_navigator import BuyResult, WebNavigator

if TYPE_CHECKING:
    from web.database_proxy import Database
    from web.web_rate_limiter import WebRateLimiter


class WebMarket:
    """Thin orchestration layer above WebNavigator for Transfer Market operations."""

    def __init__(
        self,
        navigator: WebNavigator,
        db: "Database",
        rate_limiter: "WebRateLimiter",
        timing: KSATiming,
        cfg: WebConfig,
    ) -> None:
        """Store navigator, database, rate limiter, timing and config."""
        self._nav = navigator
        self._db = db
        self._rl = rate_limiter
        self._timing = timing
        self._cfg = cfg

    async def search_with_retry(self, player_name: str, **kwargs) -> list[dict]:
        """Rate-gate search, apply inter-search pause, retry once on failure."""
        await self._rl.check_and_wait("search")
        await self._rl.inter_search_pause()
        success = await self._nav.search_player(player_name, **kwargs)
        if not success:
            logger.warning("Search for '{}' failed, retrying in 15s.", player_name)
            await asyncio.sleep(15)
            success = await self._nav.search_player(player_name, **kwargs)
        if not success:
            return []
        return await self._nav.get_search_results()

    async def buy_best_listing(
        self, listings: list[dict], max_price: int
    ) -> Optional[dict]:
        """Buy the cheapest listing at or below max_price; skip sold; handle rate limit."""
        eligible = sorted(
            [l for l in listings if (l.get("buy_now_price") or 0) <= max_price],
            key=lambda x: x.get("buy_now_price") or 0,
        )
        for listing in eligible:
            await self._rl.check_and_wait("buy")
            result = await self._nav.buy_now(listing["card_index"])
            if result == BuyResult.SUCCESS:
                logger.info(
                    "Purchased: {} at {}",
                    listing.get("player_name"),
                    listing.get("buy_now_price"),
                )
                return listing
            if result == BuyResult.ALREADY_SOLD:
                logger.debug("Listing already sold, trying next.")
                continue
            if result == BuyResult.RATE_LIMITED:
                logger.warning("Rate limited during buy — sleeping 300s.")
                await asyncio.sleep(300)
                return None
            if result == BuyResult.NOT_ENOUGH_COINS:
                logger.warning("Not enough coins to buy listing.")
                return None
        return None

    async def execute_relist_cycle(self) -> int:
        """Relist expired items and clear sold listings; returns total actions."""
        relisted = await self._nav.relist_expired()
        cleared = await self._nav.clear_sold()
        total = relisted + cleared
        if total > 0:
            logger.info("Relist cycle: relisted={} cleared={}", relisted, cleared)
        return total
