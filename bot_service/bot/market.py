"""Search execution and listing scraping only."""

from typing import TYPE_CHECKING, List

from loguru import logger

from bot.models import Listing

if TYPE_CHECKING:
    from bot.config_loader import Config
    from bot.database import Database
    from bot.navigator import Navigator


class MarketScanner:
    """Runs search via navigator, gets listings, filters by price and chem style using DB prices."""

    def __init__(self, navigator: "Navigator", db: "Database", cfg: "Config") -> None:
        """Build scanner with navigator, database (read-only), and config."""
        self._navigator = navigator
        self._db = db
        self._cfg = cfg

    def scan_for_player(self, player_cfg: dict, strategy_name: str) -> List[Listing]:
        """
        Call navigator.search_player() then navigator.get_listings().
        Strategies get market price via db.get_market_price() for profit calculation.
        """
        name = player_cfg.get("name") or player_cfg.get("player_name", "")
        quality = player_cfg.get("quality")
        position = player_cfg.get("position")
        max_buy = player_cfg.get("max_buy") or player_cfg.get("buy_max")
        chem_style = player_cfg.get("chem_style")
        if not name:
            logger.warning("scan_for_player: no player name in config")
            return []
        if not self._navigator.search_player(
            name=name,
            quality=quality,
            position=position,
            max_buy_now=max_buy,
            chem_style=chem_style,
        ):
            return []
        return self._navigator.get_listings(max_results=20, player_name=name)

    def find_underpriced(self, listings: List[Listing], max_buy: int) -> List[Listing]:
        """Filter to listings where Buy Now <= max_buy; sort by (max_buy - price) descending."""
        out = [l for l in listings if l.buy_now_price <= max_buy]
        out.sort(key=lambda l: max_buy - l.buy_now_price, reverse=True)
        return out

    def find_chem_style_deals(self, listings: List[Listing], player_name: str) -> List[Listing]:
        """
        Filter listings where card has chem style but is priced at or below unstyled level.
        Uses db.get_market_price_with_chem for price_shadow/price_hunter comparison.
        """
        mp = self._db.get_market_price_with_chem(player_name, self._cfg.platform)
        if not mp:
            return []
        # Styled price to compare: prefer shadow/hunter for this player
        styled_price = mp.price_shadow or mp.price_hunter or mp.price
        base_price = mp.price
        # Deal: listing BN is below base (unstyled) + small buffer — seller priced as unstyled
        buffer = getattr(self._cfg.chem_style, "max_premium_coins", 500)
        threshold = base_price + buffer
        return [l for l in listings if l.buy_now_price <= threshold and l.buy_now_price >= 200]
