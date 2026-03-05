"""Records and aggregates portfolio/trade state after each trade."""

from datetime import datetime, timezone
from typing import List

from loguru import logger

from bot.database import Database
from bot.models import PortfolioItem, PortfolioSummary


class Portfolio:
    """Tracks held/listed/sold items via database. No SQL in this module — all in database.py."""

    def __init__(self, db: Database) -> None:
        """Build portfolio with database (writes via db.insert_portfolio_item, update_portfolio_item)."""
        self._db = db

    def record_purchase(self, player_name: str, buy_price: int, strategy: str) -> None:
        """Insert a new portfolio item (status=held) for the purchase."""
        now = datetime.now(timezone.utc)
        item = PortfolioItem(
            player_name=player_name,
            buy_price=buy_price,
            status="held",
            acquired_at=now,
        )
        self._db.insert_portfolio_item(item)
        logger.info("Portfolio: recorded purchase %s @ %s", player_name, buy_price)

    def record_sale(self, player_name: str, sell_price: int) -> None:
        """Find a held/listed item for player_name and mark sold with sell_price."""
        held = self._db.get_held_items()
        for item in held:
            if item.player_name == player_name and item.id is not None:
                now = datetime.now(timezone.utc)
                self._db.update_portfolio_item(
                    item.id,
                    status="sold",
                    sold_at=now.isoformat(),
                    sell_price=sell_price,
                )
                logger.info("Portfolio: recorded sale %s @ %s", player_name, sell_price)
                return
        logger.warning("Portfolio: no held item found for sale %s", player_name)

    def get_held_items(self) -> List[PortfolioItem]:
        """Return all held and listed portfolio items."""
        return self._db.get_held_items()

    def print_summary(self) -> None:
        """Log full P&L table at INFO using db.get_portfolio_summary()."""
        summary = self._db.get_portfolio_summary()
        logger.info(
            "Portfolio summary: cost=%s listed_value=%s sold_value=%s held=%s listed=%s sold=%s profit=%s roi=%.1f%%",
            summary.total_cost,
            summary.total_listed_value,
            summary.total_sold_value,
            summary.count_held,
            summary.count_listed,
            summary.count_sold,
            summary.total_profit,
            summary.roi_pct,
        )

    def get_total_profit(self) -> int:
        """Return total profit (after EA 5% tax) from portfolio summary."""
        return self._db.get_portfolio_summary().total_profit

    def get_roi_pct(self) -> float:
        """Return ROI percentage from portfolio summary."""
        return self._db.get_portfolio_summary().roi_pct
