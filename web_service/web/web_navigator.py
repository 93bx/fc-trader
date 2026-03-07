"""FC 26 WEB APP — Full DOM navigation for EA FC 26 Transfer Market and app sections."""

from __future__ import annotations

import asyncio
import re
from enum import Enum
from typing import TYPE_CHECKING, Optional

from loguru import logger

from web.anti_detect.timing import KSATiming
from web.browser import BrowserSession
from web.config_loader import WebConfig

if TYPE_CHECKING:
    from web.database_proxy import Database

WEB_APP_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/"

_NAV_TRANSFERS = ["[class*='Nav'] a:has-text('Transfers')", "nav a:has-text('Transfers')"]
_NAV_CLUB = ["[class*='Nav'] a:has-text('Club')", "nav a:has-text('Club')"]
_NAV_SBC = [
    "[class*='Nav'] a:has-text('SBC')",
    "nav a:has-text('SBC')",
    "a:has-text('Squad Building Challenges')",
]
_NAV_OBJECTIVES = ["[class*='Nav'] a:has-text('Objectives')", "a:has-text('Objectives')"]
_NAV_STORE = ["[class*='Nav'] a:has-text('Store')", "a:has-text('Store')"]


class BuyResult(Enum):
    """Possible outcomes of a Buy Now attempt."""

    SUCCESS = "success"
    NOT_ENOUGH_COINS = "not_enough_coins"
    ALREADY_SOLD = "already_sold"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class BidResult(Enum):
    """Possible outcomes of a bid placement."""

    SUCCESS = "success"
    OUTBID = "outbid"
    NOT_ENOUGH_COINS = "not_enough_coins"
    EXPIRED = "expired"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


def _parse_price(text: str) -> Optional[int]:
    """Parse coin values like '14,500', '14.5K', '1.2M' into integers."""
    if not text:
        return None
    s = text.strip().replace(",", "").replace(" ", "")
    s_lower = s.lower()
    try:
        if s_lower.endswith("m"):
            return int(float(s_lower[:-1]) * 1_000_000)
        if s_lower.endswith("k"):
            return int(float(s_lower[:-1]) * 1_000)
        return int(float(s))
    except (ValueError, TypeError):
        return None


class WebNavigator:
    """Full DOM navigation layer for FC 26 Web App; no strategy or DB SQL logic."""

    def __init__(
        self,
        browser: BrowserSession,
        db: "Database",
        cfg: WebConfig,
        timing: KSATiming,
    ) -> None:
        """Store browser session, database proxy, config, and timing engine."""
        self._browser = browser
        self._db = db
        self._cfg = cfg
        self._timing = timing

    # ── internal helpers ──────────────────────────────────────────────────────

    async def _human_click(self, selector: str, timeout: int = 10_000) -> bool:
        """Scroll, hover, pause, click a selector. Returns False if not found."""
        page = self._browser.page
        if page is None:
            return False
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.scroll_into_view_if_needed()
            await loc.hover()
            await asyncio.sleep(self._timing.human_delay())
            await loc.click()
            logger.debug("click: {}", selector)
            return True
        except Exception as exc:
            logger.debug("_human_click({}) failed: {}", selector, exc)
            return False

    async def _human_type(self, selector: str, text: str, clear: bool = True) -> bool:
        """Type char-by-char with timing delay into a visible selector."""
        page = self._browser.page
        if page is None:
            return False
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=8_000)
            if clear:
                await loc.clear()
            delay_ms = int(self._timing.typing_delay() * 1000)
            await loc.press_sequentially(text, delay=delay_ms)
            return True
        except Exception as exc:
            logger.debug("_human_type({}) failed: {}", selector, exc)
            return False

    async def _scroll_to(self, selector: str) -> None:
        """Smooth-scroll element into view."""
        page = self._browser.page
        if page is None:
            return
        try:
            await page.evaluate(
                "document.querySelector(arguments[0])?.scrollIntoView({behavior:'smooth'})",
                selector,
            )
            await asyncio.sleep(self._timing.scroll_pause())
        except Exception as exc:
            logger.debug("_scroll_to({}) failed: {}", selector, exc)

    async def _wait_for_any(
        self, selectors: list[str], timeout: int = 10
    ) -> Optional[str]:
        """Return first selector that becomes visible, or None."""
        page = self._browser.page
        if page is None:
            return None
        for sel in selectors:
            try:
                await page.wait_for_selector(sel, state="visible", timeout=timeout * 1000)
                return sel
            except Exception:
                pass
        return None

    async def _page_text(self) -> str:
        """Return full page text content for toast/state detection."""
        page = self._browser.page
        if page is None:
            return ""
        try:
            return await page.inner_text("body")
        except Exception:
            return ""

    # ── section navigation ────────────────────────────────────────────────────

    async def go_home(self) -> bool:
        """Navigate to the web app hub page."""
        await asyncio.sleep(self._timing.human_delay())
        return await self._browser.goto(WEB_APP_URL)

    async def go_to_transfer_market(self) -> bool:
        """Open Transfers menu then click Transfer Market sub-link."""
        await asyncio.sleep(self._timing.human_delay())
        if not await self._human_click(_NAV_TRANSFERS[0]):
            await self._human_click(_NAV_TRANSFERS[1])
        await asyncio.sleep(self._timing.human_delay())
        await self._human_click("a:has-text('Transfer Market')")
        result = await self._wait_for_any(
            ["[class*='SearchFilters']", "[class*='search-filter']", "[class*='transferSearch']"],
            timeout=15,
        )
        if result is None:
            logger.warning("Transfer Market search form not found.")
            return False
        return True

    async def go_to_transfer_targets(self) -> bool:
        """Navigate to Transfer Targets (won items)."""
        await asyncio.sleep(self._timing.human_delay())
        if not await self._human_click(_NAV_TRANSFERS[0]):
            await self._human_click(_NAV_TRANSFERS[1])
        await asyncio.sleep(self._timing.human_delay())
        await self._human_click("a:has-text('Transfer Targets')")
        result = await self._wait_for_any(
            ["[class*='transfer-target']", "[class*='TransferTarget']", "[class*='auction']"],
            timeout=15,
        )
        return result is not None

    async def go_to_transfer_list(self) -> bool:
        """Navigate to Transfer List (active and expired listings)."""
        await asyncio.sleep(self._timing.human_delay())
        if not await self._human_click(_NAV_TRANSFERS[0]):
            await self._human_click(_NAV_TRANSFERS[1])
        await asyncio.sleep(self._timing.human_delay())
        await self._human_click("a:has-text('Transfer List')")
        result = await self._wait_for_any(
            ["[class*='transfer-list']", "[class*='TransferList']", "[class*='listed']"],
            timeout=15,
        )
        return result is not None

    async def go_to_club(self) -> bool:
        """Navigate to the Club section."""
        await asyncio.sleep(self._timing.human_delay())
        for sel in _NAV_CLUB:
            if await self._human_click(sel):
                break
        result = await self._wait_for_any(
            ["[class*='club']", "[class*='ClubView']", "[class*='item-list']"], timeout=15
        )
        return result is not None

    async def go_to_sbc(self) -> bool:
        """Navigate to Squad Building Challenges."""
        await asyncio.sleep(self._timing.human_delay())
        for sel in _NAV_SBC:
            if await self._human_click(sel):
                break
        result = await self._wait_for_any(
            ["[class*='sbc']", "[class*='SBC']", "[class*='challenge']"], timeout=15
        )
        return result is not None

    async def go_to_objectives(self) -> bool:
        """Navigate to Objectives section."""
        await asyncio.sleep(self._timing.human_delay())
        for sel in _NAV_OBJECTIVES:
            if await self._human_click(sel):
                break
        return True

    async def go_to_store(self) -> bool:
        """Navigate to the Store section."""
        await asyncio.sleep(self._timing.human_delay())
        for sel in _NAV_STORE:
            if await self._human_click(sel):
                break
        return True

    async def go_to_squad_hub(self) -> bool:
        """Navigate to My Squad / Squad Hub."""
        await asyncio.sleep(self._timing.human_delay())
        await self._human_click("a:has-text('Squad Hub')")
        return True

    # ── Transfer Market — search ──────────────────────────────────────────────

    async def search_player(
        self,
        name: str,
        quality: str = "",
        position: str = "",
        max_buy_now: Optional[int] = None,
        min_buy_now: Optional[int] = None,
        chem_style: Optional[str] = None,
        nationality: Optional[str] = None,
        league: Optional[str] = None,
    ) -> bool:
        """Fill all search filters and click Search. Returns False on failure."""
        page = self._browser.page
        if page is None:
            return False
        await asyncio.sleep(self._timing.human_delay())
        try:
            await page.click("[class*='clear'], button:has-text('Clear')", timeout=3_000)
        except Exception:
            pass

        name_box = await self._wait_for_any(
            ["[class*='playerSearch'] input", "input[placeholder*='player']", "input[class*='search']"],
            timeout=8,
        )
        if name_box:
            await self._human_type(name_box, name)
            await asyncio.sleep(1.0)
            try:
                await page.locator("[class*='suggestion'], [class*='dropdown'] li").first.click(timeout=4_000)
            except Exception:
                try:
                    await page.keyboard.press("Enter")
                except Exception:
                    pass

        if quality:
            await self._select_dropdown("Quality", quality)
        if position:
            await self._select_dropdown("Position", position)
        if max_buy_now is not None:
            await self._human_type("[class*='maxBuy'], input[data-id*='maxBuy']", str(max_buy_now))
        if min_buy_now is not None:
            await self._human_type("[class*='minBuy'], input[data-id*='minBuy']", str(min_buy_now))
        if chem_style:
            await self._select_dropdown("Chemistry Style", chem_style)
        if nationality:
            await self._select_dropdown("Nationality", nationality)
        if league:
            await self._select_dropdown("League", league)

        await self._human_click(
            "button:has-text('Search'), [class*='search-btn'], [class*='button-search']"
        )
        await asyncio.sleep(self._timing.human_delay())
        found = await self._wait_for_any(
            ["[class*='ResultsList']", "[class*='auction-item']", "[class*='listFUTItem']"], timeout=10
        )
        return found is not None

    async def _select_dropdown(self, label: str, value: str) -> None:
        """Open a labeled dropdown and select value option."""
        page = self._browser.page
        if page is None:
            return
        try:
            await page.click(f"[class*='dropdown']:has-text('{label}')", timeout=4_000)
            await asyncio.sleep(0.3)
            await page.click(
                f"[class*='dropdown-list'] li:has-text('{value}'), "
                f"[class*='option']:has-text('{value}')",
                timeout=4_000,
            )
        except Exception as exc:
            logger.debug("_select_dropdown({}, {}) failed: {}", label, value, exc)

    async def get_search_results(self) -> list[dict]:
        """Parse visible auction listing cards and return structured list."""
        page = self._browser.page
        if page is None:
            return []
        results: list[dict] = []
        try:
            items = await page.locator("[class*='auction-item'], [class*='listFUTItem']").all()
            for idx, item in enumerate(items):
                try:
                    raw = await item.inner_text()
                    name = await self._extract_card_text(item, "[class*='name'], [class*='playerName']")
                    buy_now_raw = await self._extract_card_text(item, "[class*='buyNow'] span, [class*='buy-now'] span")
                    bid_raw = await self._extract_card_text(item, "[class*='bid'] span, [class*='currentBid'] span")
                    time_raw = await self._extract_card_text(item, "[class*='time'], [class*='auction-time']")
                    rating_raw = await self._extract_card_text(item, "[class*='rating'], [class*='ovr']")

                    results.append(
                        {
                            "player_name": name.strip(),
                            "rating": _parse_price(rating_raw),
                            "buy_now_price": _parse_price(buy_now_raw),
                            "current_bid": _parse_price(bid_raw),
                            "start_bid": None,
                            "time_left": time_raw.strip(),
                            "card_index": idx,
                            "element_selector": f"([class*='auction-item']):nth-child({idx + 1})",
                        }
                    )
                except Exception as exc:
                    logger.debug("Error parsing listing {}: {}", idx, exc)
        except Exception as exc:
            logger.debug("get_search_results error: {}", exc)
        return results

    async def _extract_card_text(self, parent, selector: str) -> str:
        """Extract text from a sub-element; empty string on miss."""
        try:
            el = parent.locator(selector).first
            return await el.inner_text(timeout=1_500)
        except Exception:
            return ""

    async def next_results_page(self) -> bool:
        """Click next pagination button; return False if not present."""
        try:
            await self._human_click(
                "button:has-text('>'), button[class*='next'], [class*='paginationNext']",
                timeout=5_000,
            )
            return True
        except Exception:
            return False

    # ── Transfer Market — buy / bid ───────────────────────────────────────────

    async def buy_now(self, card_index: int) -> BuyResult:
        """Attempt Buy Now on listing at card_index; handle confirmation and result toast."""
        await asyncio.sleep(self._timing.human_delay())
        page = self._browser.page
        if page is None:
            return BuyResult.ERROR
        try:
            items = await page.locator("[class*='auction-item'], [class*='listFUTItem']").all()
            if card_index >= len(items):
                return BuyResult.ERROR
            await items[card_index].click()
            await asyncio.sleep(self._timing.human_delay())

            buy_btn = await self._wait_for_any(
                ["button:has-text('Buy Now')", "[class*='buyNow'] button"], timeout=8
            )
            if not buy_btn:
                return BuyResult.ERROR
            await self._human_click(buy_btn)
            await asyncio.sleep(self._timing.human_delay())

            confirm_btn = await self._wait_for_any(
                ["button:has-text('Ok')", "button:has-text('Confirm')", "button:has-text('Yes')"],
                timeout=6,
            )
            await asyncio.sleep(self._timing.human_delay())
            if confirm_btn:
                await self._human_click(confirm_btn)
            await asyncio.sleep(self._timing.human_delay())

            return await self._detect_buy_result()
        except Exception as exc:
            logger.debug("buy_now({}) error: {}", card_index, exc)
            return BuyResult.ERROR

    async def _detect_buy_result(self) -> BuyResult:
        """Read page text to classify buy outcome."""
        text = await self._page_text()
        lower = text.lower()
        if any(s in lower for s in ["not enough", "insufficient", "no coins"]):
            return BuyResult.NOT_ENOUGH_COINS
        if any(s in lower for s in ["no longer available", "item sold", "sold"]):
            return BuyResult.ALREADY_SOLD
        if any(s in lower for s in ["slow down", "too many", "please wait"]):
            return BuyResult.RATE_LIMITED
        if any(s in lower for s in ["congratulations", "added to", "item purchased", "success"]):
            return BuyResult.SUCCESS
        try:
            page = self._browser.page
            if page:
                await page.wait_for_selector(
                    "[class*='transfer-target'], [class*='won']", timeout=4_000
                )
                return BuyResult.SUCCESS
        except Exception:
            pass
        return BuyResult.ERROR

    async def place_bid(self, card_index: int, bid_amount: int) -> BidResult:
        """Place bid of bid_amount on listing at card_index."""
        await asyncio.sleep(self._timing.human_delay())
        page = self._browser.page
        if page is None:
            return BidResult.ERROR
        try:
            items = await page.locator("[class*='auction-item'], [class*='listFUTItem']").all()
            if card_index >= len(items):
                return BidResult.ERROR
            await items[card_index].click()
            await asyncio.sleep(self._timing.human_delay())

            bid_input = await self._wait_for_any(
                ["[class*='bidInput'] input", "input[class*='bid']"], timeout=6
            )
            if not bid_input:
                return BidResult.ERROR
            await self._human_type(bid_input, str(bid_amount))

            bid_btn = await self._wait_for_any(
                ["button:has-text('Bid')", "[class*='bid-btn']", "button:has-text('Make Bid')"], timeout=5
            )
            if not bid_btn:
                return BidResult.ERROR
            await self._human_click(bid_btn)
            await asyncio.sleep(self._timing.human_delay())

            return await self._detect_bid_result()
        except Exception as exc:
            logger.debug("place_bid({}) error: {}", card_index, exc)
            return BidResult.ERROR

    async def _detect_bid_result(self) -> BidResult:
        """Read page text to classify bid outcome."""
        text = await self._page_text()
        lower = text.lower()
        if "outbid" in lower:
            return BidResult.OUTBID
        if any(s in lower for s in ["not enough", "insufficient"]):
            return BidResult.NOT_ENOUGH_COINS
        if "expired" in lower or "auction ended" in lower:
            return BidResult.EXPIRED
        if any(s in lower for s in ["slow down", "too many"]):
            return BidResult.RATE_LIMITED
        if any(s in lower for s in ["bid placed", "success", "highest bidder"]):
            return BidResult.SUCCESS
        return BidResult.ERROR

    # ── Transfer Market — list / relist ───────────────────────────────────────

    async def list_item(
        self,
        item_name: str,
        start_bid: int,
        buy_now: int,
        duration_hours: int = 1,
    ) -> bool:
        """Find item in club/unassigned and list it on Transfer Market."""
        if not await self.go_to_transfer_list():
            return False
        await asyncio.sleep(self._timing.human_delay())
        try:
            page = self._browser.page
            if page is None:
                return False
            await page.click(
                f"[class*='item-list'] [class*='item']:has-text('{item_name}'), "
                f"[class*='listItem']:has-text('{item_name}')",
                timeout=6_000,
            )
            await asyncio.sleep(self._timing.human_delay())

            list_btn = await self._wait_for_any(
                ["button:has-text('List on Transfer Market')", "button:has-text('List')"], timeout=8
            )
            if list_btn:
                await self._human_click(list_btn)
            await asyncio.sleep(0.5)

            await self._human_type("[class*='startBid'] input, input[data-id*='startBid']", str(start_bid))
            await self._human_type("[class*='buyNow'] input, input[data-id*='buyNow']", str(buy_now))

            dur_map = {1: "1 Hour", 3: "3 Hours", 6: "6 Hours", 12: "12 Hours", 24: "1 Day"}
            dur_label = dur_map.get(duration_hours, "1 Hour")
            await self._select_dropdown("Duration", dur_label)

            confirm = await self._wait_for_any(
                ["button:has-text('List')", "button:has-text('Confirm')"], timeout=5
            )
            if confirm:
                await self._human_click(confirm)
            await asyncio.sleep(self._timing.human_delay())
            return True
        except Exception as exc:
            logger.debug("list_item({}) error: {}", item_name, exc)
            return False

    async def relist_expired(self) -> int:
        """Relist all expired listings; returns count relisted."""
        if not await self.go_to_transfer_list():
            return 0
        await asyncio.sleep(self._timing.human_delay())
        page = self._browser.page
        if page is None:
            return 0
        count = 0
        try:
            relist_all = page.locator("button:has-text('Relist All')")
            if await relist_all.is_visible(timeout=3_000):
                await relist_all.click()
                logger.info("Relist All clicked.")
                count = 1
                return count
        except Exception:
            pass
        try:
            expired = await page.locator("[class*='expired'] button:has-text('Relist')").all()
            for btn in expired:
                try:
                    await btn.click()
                    await asyncio.sleep(self._timing.human_delay())
                    count += 1
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("relist_expired error: {}", exc)
        return count

    async def clear_sold(self) -> int:
        """Clear sold items from Transfer List; returns count cleared."""
        if not await self.go_to_transfer_list():
            return 0
        page = self._browser.page
        if page is None:
            return 0
        try:
            btn = page.locator("button:has-text('Clear Sold'), button:has-text('Clear All')")
            if await btn.is_visible(timeout=3_000):
                sold_count_text = await page.locator("[class*='sold'] [class*='count']").inner_text(timeout=2_000)
                count = int(re.sub(r"\D", "", sold_count_text) or "0")
                await btn.click()
                logger.info("Cleared {} sold item(s).", count)
                return count
        except Exception as exc:
            logger.debug("clear_sold error: {}", exc)
        return 0

    async def get_transfer_list_summary(self) -> dict:
        """Return active/expired/sold counts from Transfer List page."""
        summary = {"active": 0, "expired": 0, "sold": 0, "total_capacity": 100}
        if not await self.go_to_transfer_list():
            return summary
        page = self._browser.page
        if page is None:
            return summary
        try:
            text = await page.inner_text("[class*='transferList'], [class*='transfer-list']", timeout=5_000)
            for label, key in [("Active", "active"), ("Expired", "expired"), ("Sold", "sold")]:
                match = re.search(rf"{label}[^\d]*(\d+)", text, re.IGNORECASE)
                if match:
                    summary[key] = int(match.group(1))
        except Exception as exc:
            logger.debug("get_transfer_list_summary error: {}", exc)
        return summary

    # ── Transfer Targets ──────────────────────────────────────────────────────

    async def collect_won_items(self) -> int:
        """Send all won items to club; returns count collected."""
        if not await self.go_to_transfer_targets():
            return 0
        await asyncio.sleep(self._timing.human_delay())
        page = self._browser.page
        if page is None:
            return 0
        count = 0
        try:
            send_all = page.locator("button:has-text('Send All to Club')")
            if await send_all.is_visible(timeout=3_000):
                await send_all.click()
                logger.info("Send All to Club clicked.")
                return 1
        except Exception:
            pass
        try:
            won_items = await page.locator(
                "[class*='won'] button:has-text('Send to Club'), "
                "[class*='transfer-target'] button:has-text('Send to Club')"
            ).all()
            for btn in won_items:
                try:
                    await btn.click()
                    await asyncio.sleep(self._timing.human_delay())
                    count += 1
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("collect_won_items error: {}", exc)
        return count

    async def get_won_items(self) -> list[dict]:
        """Parse won items list and return details."""
        if not await self.go_to_transfer_targets():
            return []
        page = self._browser.page
        if page is None:
            return []
        items: list[dict] = []
        try:
            cards = await page.locator("[class*='won'] [class*='item'], [class*='transfer-target'] [class*='item']").all()
            for card in cards:
                name = await self._extract_card_text(card, "[class*='name']")
                price = await self._extract_card_text(card, "[class*='price'], [class*='coins']")
                items.append({"name": name.strip(), "buy_now_price": _parse_price(price), "time_won": ""})
        except Exception as exc:
            logger.debug("get_won_items error: {}", exc)
        return items

    # ── Club ──────────────────────────────────────────────────────────────────

    async def quick_sell_fodder(self, min_rating: int = 0, max_rating: int = 64) -> int:
        """Select and quick-sell all club cards within rating range."""
        if not await self.go_to_club():
            return 0
        await asyncio.sleep(self._timing.human_delay())
        page = self._browser.page
        if page is None:
            return 0
        count = 0
        try:
            cards = await page.locator("[class*='club-item'], [class*='FUTItem']").all()
            selected = 0
            for card in cards:
                try:
                    ovr_text = await self._extract_card_text(card, "[class*='rating']")
                    ovr = int(ovr_text.strip()) if ovr_text.strip().isdigit() else 0
                    if min_rating <= ovr <= max_rating:
                        await card.click()
                        await asyncio.sleep(0.15)
                        selected += 1
                except Exception:
                    pass
            if selected > 0:
                await page.click("button:has-text('Quick Sell')", timeout=5_000)
                await asyncio.sleep(self._timing.human_delay())
                await page.click(
                    "button:has-text('Ok'), button:has-text('Confirm'), button:has-text('Yes')",
                    timeout=5_000,
                )
                count = selected
                logger.info("Quick-sold {} fodder item(s).", count)
        except Exception as exc:
            logger.debug("quick_sell_fodder error: {}", exc)
        return count
