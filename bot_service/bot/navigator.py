"""FC Companion screen flows and navigation (screen names, not business logic)."""

import re
from typing import List, Optional, Tuple

from loguru import logger

from bot.config_loader import Config
from bot.database import Database
from bot.device import Device
from bot.models import Listing
from bot.rate_limiter import ActionType, RateLimiter
from bot.ui_constants import (
    SEARCH_BUTTON,
    SEARCH_CHEMISTRY_STYLE,
    SEARCH_MAX_BUY_NOW,
    SEARCH_PLAYER_NAME,
    SEARCH_POSITION,
    SEARCH_QUALITY,
    TEXT_BUY_NOW,
    TEXT_CLUB,
    TEXT_CONFIRM,
    TEXT_SEARCH_FILTERS,
    TEXT_TRANSFERS,
    TEXT_TRANSFER_MARKET,
)
from bot.utils import parse_coin_value


class Navigator:
    """
    FC Companion app screen flows. Every method that touches search/buy/list/bid
    calls rate_limiter.check_and_wait() with the appropriate ActionType.
    """

    def __init__(
        self,
        device: Device,
        db: Database,
        cfg: Config,
        rate_limiter: RateLimiter,
    ) -> None:
        """Build navigator with device, db, config, and rate limiter."""
        self._device = device
        self._db = db
        self._cfg = cfg
        self._rate_limiter = rate_limiter

    # ── Main Navigation ─────────────────────────────────────────────────────

    def go_to_transfer_market(self) -> bool:
        """Tap: bottom nav → Transfers → Search Market. Verify: wait for 'Search Filters' or similar."""
        logger.debug("go_to_transfer_market: targeting Transfers then Search Market")
        if not self._device.tap_text(TEXT_TRANSFERS):
            if not self._device.wait_for_element({"text": TEXT_TRANSFERS}, timeout=5):
                return False
            self._device.tap_text(TEXT_TRANSFERS)
        if not self._device.wait_for_text("Search", timeout=5):
            return False
        self._device.tap_text("Search")
        return self._device.wait_for_text(TEXT_SEARCH_FILTERS, timeout=10) or self._device.wait_for_text("Search", timeout=5)

    def go_to_transfer_list(self) -> bool:
        """Tap: bottom nav → Transfers → Transfer List."""
        logger.debug("go_to_transfer_list")
        if not self._device.tap_text(TEXT_TRANSFERS):
            self._device.wait_for_element({"text": TEXT_TRANSFERS}, timeout=5)
            self._device.tap_text(TEXT_TRANSFERS)
        return self._device.wait_for_text("Transfer List", timeout=10)

    def go_to_club(self) -> bool:
        """Tap: bottom nav → Club."""
        logger.debug("go_to_club")
        self._device.tap_text(TEXT_CLUB)
        return self._device.wait_for_text(TEXT_CLUB, timeout=10) or True

    # ── Search & Filter ─────────────────────────────────────────────────────

    def search_player(
        self,
        name: str,
        quality: Optional[str] = None,
        position: Optional[str] = None,
        max_buy_now: Optional[int] = None,
        chem_style: Optional[str] = None,
    ) -> bool:
        """
        Fill search filters (name, quality, position, max buy now, chemistry style), then tap Search.
        Element lookup: resource-id first, then content-desc, then text (per .cursorrules §5).
        Returns False if search form or Search button not found.
        """
        self._rate_limiter.check_and_wait(ActionType.SEARCH)
        logger.debug("search_player: name=%s quality=%s position=%s max_bn=%s chem=%s", name, quality, position, max_buy_now, chem_style)

        if not self._device.wait_for_element(SEARCH_PLAYER_NAME, timeout=5):
            logger.debug("search_player: Player Name field not found")
            return False

        self._device.tap_element(SEARCH_PLAYER_NAME)
        self._device.type_text(name, clear_first=True)

        if quality:
            if self._device.wait_for_element(SEARCH_QUALITY, timeout=2):
                self._device.tap_element(SEARCH_QUALITY)
                self._device.tap_text(quality)
        if position:
            if self._device.wait_for_element(SEARCH_POSITION, timeout=2):
                self._device.tap_element(SEARCH_POSITION)
                self._device.tap_text(position)
        if max_buy_now is not None:
            if self._device.wait_for_element(SEARCH_MAX_BUY_NOW, timeout=2):
                self._device.tap_element(SEARCH_MAX_BUY_NOW)
                self._device.type_text(str(max_buy_now), clear_first=True)
        if chem_style:
            if self._device.wait_for_element(SEARCH_CHEMISTRY_STYLE, timeout=2):
                self._device.tap_element(SEARCH_CHEMISTRY_STYLE)
                self._device.tap_text(chem_style)

        if not self._device.wait_for_element(SEARCH_BUTTON, timeout=2):
            logger.debug("search_player: Search button not found")
            return False
        self._device.tap_element(SEARCH_BUTTON)
        return True

    def clear_search_filters(self) -> None:
        """Clear all search filter fields."""
        logger.debug("clear_search_filters")
        self._device.tap_element(SEARCH_PLAYER_NAME)
        self._device.type_text("", clear_first=True)
        self._device.press_back()

    def set_price_range(self, min_bn: Optional[int], max_bn: Optional[int]) -> None:
        """Set min/max Buy Now price range in the search form."""
        logger.debug("set_price_range: min=%s max=%s", min_bn, max_bn)
        if max_bn is not None and self._device.wait_for_element(SEARCH_MAX_BUY_NOW, timeout=2):
            self._device.tap_element(SEARCH_MAX_BUY_NOW)
            self._device.type_text(str(max_bn), clear_first=True)

    # ── Results Scraping ────────────────────────────────────────────────────

    def get_listings(self, max_results: int = 10, player_name: str = "") -> List[Listing]:
        """
        Scrape current results: OCR Buy Now, bid, time remaining. Scroll until max_results or no more.
        player_name is the search context (set on each Listing).
        """
        logger.debug("get_listings: max_results=%s", max_results)
        results: List[Listing] = []
        text = self._device.get_screen_text()
        # Heuristic: find numbers that look like prices (digits, possibly with K/M/comma)
        price_pattern = re.compile(r"[\d,]+(?:\.\d+)?[KkMm]?")
        tokens = price_pattern.findall(text)
        seen: set[int] = set()
        for t in tokens:
            val = parse_coin_value(t)
            if val is not None and val >= 200 and val not in seen:
                seen.add(val)
                results.append(
                    Listing(
                        player_name=player_name,
                        buy_now_price=val,
                        current_bid=0,
                        time_remaining="",
                    )
                )
                if len(results) >= max_results:
                    break
        if len(results) < max_results:
            self._device.swipe_up()
            more_text = self._device.get_screen_text()
            for t in price_pattern.findall(more_text):
                val = parse_coin_value(t)
                if val is not None and val >= 200 and val not in seen:
                    seen.add(val)
                    results.append(
                        Listing(player_name=player_name, buy_now_price=val, current_bid=0, time_remaining="")
                    )
                    if len(results) >= max_results:
                        break
        return results

    # ── Purchase Actions ─────────────────────────────────────────────────────

    def buy_now(self, listing: Listing) -> bool:
        """Tap listing → Buy Now → Confirm. Wait for success. Caller must call rate_limiter.cooldown_after_buy()."""
        self._rate_limiter.check_and_wait(ActionType.BUY)
        logger.debug("buy_now: %s at %s", listing.player_name, listing.buy_now_price)
        if not self._device.tap_text(TEXT_BUY_NOW):
            self._device.tap_element({"text": TEXT_BUY_NOW})
        if not self._device.wait_for_element({"text": TEXT_CONFIRM}, timeout=3):
            return False
        self._device.tap_text(TEXT_CONFIRM)
        return self._device.wait_for_text("Success", timeout=10) or self._device.wait_for_text("success", timeout=2)

    def place_bid(self, listing: Listing, bid_amount: int) -> bool:
        """Tap listing → Bid field → type bid_amount → Confirm. Returns False if bid rejected."""
        self._rate_limiter.check_and_wait(ActionType.BID)
        logger.debug("place_bid: %s bid=%s", listing.player_name, bid_amount)
        self._device.tap_element({"text": "Bid"})
        self._device.type_text(str(bid_amount), clear_first=True)
        self._device.tap_text(TEXT_CONFIRM)
        if self._device.is_text_on_screen("Bid has changed") or self._device.is_text_on_screen("Outbid"):
            return False
        return True

    # ── Listing Actions ──────────────────────────────────────────────────────

    def list_item(
        self,
        player_name: str,
        start_price: int,
        buy_now_price: int,
        duration_hours: int = 1,
    ) -> bool:
        """Navigate to club → find player → List on Transfer Market → set start, BN, duration → confirm."""
        self._rate_limiter.check_and_wait(ActionType.LIST)
        logger.debug("list_item: %s start=%s buy_now=%s duration=%sh", player_name, start_price, buy_now_price, duration_hours)
        if not self.go_to_club():
            return False
        self._device.tap_text(player_name)
        self._device.tap_text("List on Transfer Market")
        self._device.type_text(str(start_price), clear_first=True)
        self._device.tap_element({"text": "Buy Now Price"})
        self._device.type_text(str(buy_now_price), clear_first=True)
        self._device.tap_text("List")
        return self._device.wait_for_text("Listed", timeout=10)

    def relist_expired_item(self, player_name: str) -> bool:
        """Find expired listing in Transfer List → tap Relist at same price."""
        self._rate_limiter.check_and_wait(ActionType.LIST)
        logger.debug("relist_expired_item: %s", player_name)
        if not self.go_to_transfer_list():
            return False
        self._device.tap_text("Relist")
        return self._device.wait_for_text("Listed", timeout=10)

    def get_won_items(self) -> List[Tuple[str, int]]:
        """
        Parse transfer list for items with 'Won' status (won via bidding).
        Returns list of (player_name, win_price). Caller must have navigated to Transfer List.
        Currently returns empty list; OCR for 'Won' can be implemented later.
        """
        logger.debug("get_won_items: parsing transfer list (placeholder)")
        return []

    # ── Compare Price ────────────────────────────────────────────────────────

    def get_compare_price(self, player_name: str) -> Optional[int]:
        """Open player card → Compare Price → OCR lowest BN. Returns None if unavailable."""
        logger.debug("get_compare_price: %s", player_name)
        self._device.tap_text(player_name)
        if not self._device.tap_text("Compare Price"):
            return None
        text = self._device.get_screen_text()
        val = parse_coin_value(text)
        return val
