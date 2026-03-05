"""All SQLite access for FC Trader. Schema, parameterised queries, and Database class."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from loguru import logger

from bot.models import (
    MarketPrice,
    PortfolioItem,
    PortfolioSummary,
    RateState,
    SbcSignal,
    Trade,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    source          TEXT NOT NULL,
    platform        TEXT NOT NULL DEFAULT 'ps',
    price           INTEGER NOT NULL,
    price_shadow    INTEGER,
    price_hunter    INTEGER,
    scraped_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_prices_name
    ON market_prices(player_name, platform, scraped_at DESC);

CREATE TABLE IF NOT EXISTS sbc_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sbc_name        TEXT NOT NULL,
    rating_req      INTEGER,
    detected_at     TEXT NOT NULL,
    expires_at      TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name     TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    action          TEXT NOT NULL,
    buy_price       INTEGER,
    sell_price      INTEGER,
    profit_net      INTEGER,
    platform        TEXT NOT NULL DEFAULT 'ps',
    dry_run         INTEGER NOT NULL DEFAULT 0,
    executed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_state (
    action_type     TEXT PRIMARY KEY,
    count_today     INTEGER NOT NULL DEFAULT 0,
    count_hour      INTEGER NOT NULL DEFAULT 0,
    last_action_at  TEXT,
    hour_reset_at   TEXT,
    day_reset_at    TEXT
);

CREATE TABLE IF NOT EXISTS portfolio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name     TEXT NOT NULL,
    buy_price       INTEGER NOT NULL,
    listed_price    INTEGER,
    sell_price      INTEGER,
    status          TEXT NOT NULL DEFAULT 'held',
    acquired_at     TEXT NOT NULL,
    listed_at       TEXT,
    sold_at         TEXT
);
"""


def _dt_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO 8601 string for SQLite TEXT storage."""
    return dt.isoformat()


def _iso_to_dt(iso: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 string from SQLite to datetime. Returns None if iso is None."""
    if iso is None:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


class Database:
    """SQLite wrapper for FC Trader. All queries and schema live here."""

    def __init__(self, cfg: dict) -> None:
        """Open or create DB at path from config (e.g. cfg['path'] or cfg['db_path'])."""
        path = cfg.get("path") or cfg.get("db_path", "/app/data/fc_trader.db")
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        """Return existing connection or open one."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init(self) -> None:
        """Create all tables and indexes. Idempotent."""
        conn = self._get_conn()
        conn.executescript(SCHEMA)
        conn.commit()
        logger.debug("Database schema initialised")

    def get_market_price(self, player_name: str, platform: str) -> Optional[MarketPrice]:
        """Return the most recent market price row for the given player and platform."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, player_id, player_name, source, platform, price, price_shadow, "
            "price_hunter, scraped_at FROM market_prices "
            "WHERE player_name = ? AND platform = ? ORDER BY scraped_at DESC LIMIT 1",
            (player_name, platform),
        ).fetchone()
        if row is None:
            return None
        return MarketPrice(
            id=row["id"],
            player_id=row["player_id"],
            player_name=row["player_name"],
            source=row["source"],
            platform=row["platform"],
            price=row["price"],
            price_shadow=row["price_shadow"],
            price_hunter=row["price_hunter"],
            scraped_at=_iso_to_dt(row["scraped_at"]) or datetime.now(timezone.utc),
        )

    def get_market_price_with_chem(
        self, player_name: str, platform: str
    ) -> Optional[MarketPrice]:
        """Return the most recent market price row that has price_shadow or price_hunter set."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, player_id, player_name, source, platform, price, price_shadow, "
            "price_hunter, scraped_at FROM market_prices "
            "WHERE player_name = ? AND platform = ? AND (price_shadow IS NOT NULL OR price_hunter IS NOT NULL) "
            "ORDER BY scraped_at DESC LIMIT 1",
            (player_name, platform),
        ).fetchone()
        if row is None:
            return None
        return MarketPrice(
            id=row["id"],
            player_id=row["player_id"],
            player_name=row["player_name"],
            source=row["source"],
            platform=row["platform"],
            price=row["price"],
            price_shadow=row["price_shadow"],
            price_hunter=row["price_hunter"],
            scraped_at=_iso_to_dt(row["scraped_at"]) or datetime.now(timezone.utc),
        )

    def insert_market_price(self, price: MarketPrice) -> None:
        """Insert one market price record. scraped_at stored as ISO string."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO market_prices (player_id, player_name, source, platform, price, "
            "price_shadow, price_hunter, scraped_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                price.player_id,
                price.player_name,
                price.source,
                price.platform,
                price.price,
                price.price_shadow,
                price.price_hunter,
                _dt_to_iso(price.scraped_at),
            ),
        )
        conn.commit()

    def insert_trade(self, trade: Trade) -> None:
        """Insert one trade record. executed_at stored as ISO string."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO trades (player_name, strategy, action, buy_price, sell_price, "
            "profit_net, platform, dry_run, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trade.player_name,
                trade.strategy,
                trade.action,
                trade.buy_price,
                trade.sell_price,
                trade.profit_net,
                trade.platform,
                1 if trade.dry_run else 0,
                _dt_to_iso(trade.executed_at),
            ),
        )
        conn.commit()

    def get_daily_trade_count(self) -> int:
        """Return count of trades executed today (by executed_at date in UTC)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE date(executed_at) = date('now')"
        ).fetchone()
        return row["n"] if row else 0

    def get_hourly_action_count(self, action_type: str) -> int:
        """Return count for this action_type in the current hour from rate_state."""
        state = self.get_rate_state(action_type)
        if state is None:
            return 0
        now = datetime.now(timezone.utc)
        # hour_reset_at is start of current window; window is [hour_reset_at, hour_reset_at+1h)
        if state.hour_reset_at is not None and now >= state.hour_reset_at + timedelta(hours=1):
            return 0
        return state.count_hour

    def update_rate_state(self, action_type: str) -> None:
        """Increment counts for action_type, set last_action_at; reset hour/day if crossed."""
        now = datetime.now(timezone.utc)
        state = self.get_rate_state(action_type)
        conn = self._get_conn()

        if state is None:
            conn.execute(
                "INSERT INTO rate_state (action_type, count_today, count_hour, last_action_at, "
                "hour_reset_at, day_reset_at) VALUES (?, 1, 1, ?, ?, ?)",
                (
                    action_type,
                    _dt_to_iso(now),
                    _dt_to_iso(now.replace(minute=0, second=0, microsecond=0)),
                    _dt_to_iso(now.replace(hour=0, minute=0, second=0, microsecond=0)),
                ),
            )
            conn.commit()
            return

        # Reset hour if we passed the current window (hour_reset_at is start of window)
        hour_reset = state.hour_reset_at
        day_reset = state.day_reset_at
        count_today = state.count_today
        count_hour = state.count_hour

        if hour_reset is not None and now >= hour_reset + timedelta(hours=1):
            count_hour = 1
            hour_reset = now.replace(minute=0, second=0, microsecond=0)
        else:
            count_hour += 1

        if day_reset is not None and now >= day_reset + timedelta(days=1):
            count_today = 1
            day_reset = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            count_today += 1

        conn.execute(
            "UPDATE rate_state SET count_today = ?, count_hour = ?, last_action_at = ?, "
            "hour_reset_at = ?, day_reset_at = ? WHERE action_type = ?",
            (
                count_today,
                count_hour,
                _dt_to_iso(now),
                _dt_to_iso(hour_reset) if hour_reset else None,
                _dt_to_iso(day_reset) if day_reset else None,
                action_type,
            ),
        )
        conn.commit()

    def get_rate_state(self, action_type: str) -> Optional[RateState]:
        """Return rate state for the given action_type, or None."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT action_type, count_today, count_hour, last_action_at, hour_reset_at, day_reset_at "
            "FROM rate_state WHERE action_type = ?",
            (action_type,),
        ).fetchone()
        if row is None:
            return None
        return RateState(
            action_type=row["action_type"],
            count_today=row["count_today"],
            count_hour=row["count_hour"],
            last_action_at=_iso_to_dt(row["last_action_at"]),
            hour_reset_at=_iso_to_dt(row["hour_reset_at"]),
            day_reset_at=_iso_to_dt(row["day_reset_at"]),
        )

    def insert_portfolio_item(self, item: PortfolioItem) -> None:
        """Insert one portfolio item. Datetimes stored as ISO strings."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO portfolio (player_name, buy_price, listed_price, sell_price, status, acquired_at, "
            "listed_at, sold_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.player_name,
                item.buy_price,
                item.listed_price,
                item.sell_price,
                item.status,
                _dt_to_iso(item.acquired_at),
                _dt_to_iso(item.listed_at) if item.listed_at else None,
                _dt_to_iso(item.sold_at) if item.sold_at else None,
            ),
        )
        conn.commit()

    def update_portfolio_item(
        self,
        id: int,
        status: str,
        sold_at: Optional[str] = None,
        sell_price: Optional[int] = None,
    ) -> None:
        """Update portfolio row by id. sold_at/sell_price optional (e.g. when just listing)."""
        conn = self._get_conn()
        if sold_at is not None and sell_price is not None:
            conn.execute(
                "UPDATE portfolio SET status = ?, sold_at = ?, sell_price = ? WHERE id = ?",
                (status, sold_at, sell_price, id),
            )
        else:
            conn.execute("UPDATE portfolio SET status = ? WHERE id = ?", (status, id))
        conn.commit()

    def get_held_items(self) -> List[PortfolioItem]:
        """Return portfolio items with status 'held' or 'listed'."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, player_name, buy_price, listed_price, sell_price, status, acquired_at, listed_at, sold_at "
            "FROM portfolio WHERE status IN ('held', 'listed') ORDER BY acquired_at DESC"
        ).fetchall()
        return [
            PortfolioItem(
                id=row["id"],
                player_name=row["player_name"],
                buy_price=row["buy_price"],
                listed_price=row["listed_price"],
                sell_price=row["sell_price"],
                status=row["status"],
                acquired_at=_iso_to_dt(row["acquired_at"]) or datetime.now(timezone.utc),
                listed_at=_iso_to_dt(row["listed_at"]),
                sold_at=_iso_to_dt(row["sold_at"]),
            )
            for row in rows
        ]

    def get_portfolio_summary(self) -> PortfolioSummary:
        """Return aggregate summary of portfolio (cost, value, counts, profit, ROI)."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT status, buy_price, listed_price, sell_price, sold_at FROM portfolio"
        ).fetchall()
        total_cost = 0
        total_listed_value = 0
        total_sold_value = 0
        count_held = 0
        count_listed = 0
        count_sold = 0
        for row in rows:
            status = row["status"]
            buy = row["buy_price"] or 0
            listed = row["listed_price"] or 0
            total_cost += buy
            if status == "held":
                count_held += 1
            elif status == "listed":
                count_listed += 1
                total_listed_value += listed
            elif status == "sold":
                count_sold += 1
                total_sold_value += row["sell_price"] or 0  # stored as sell price when sold
        # EA tax: net_received = sell_price * 0.95; profit = net_received - buy_price
        total_profit = 0
        total_invested_sold = 0
        for r in rows:
            if r["status"] == "sold":
                buy = r["buy_price"] or 0
                sell = r["sell_price"] or 0
                total_invested_sold += buy
                total_profit += int(sell * 0.95) - buy
        roi_pct = (
            (total_profit / total_invested_sold * 100) if total_invested_sold else 0.0
        )
        return PortfolioSummary(
            total_cost=total_cost,
            total_listed_value=total_listed_value,
            total_sold_value=total_sold_value,
            count_held=count_held,
            count_listed=count_listed,
            count_sold=count_sold,
            total_profit=total_profit,
            roi_pct=roi_pct,
        )

    def insert_sbc_signal(self, signal: SbcSignal) -> None:
        """Insert one SBC signal. Datetimes stored as ISO strings."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO sbc_signals (sbc_name, rating_req, detected_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (
                signal.sbc_name,
                signal.rating_req,
                _dt_to_iso(signal.detected_at),
                _dt_to_iso(signal.expires_at) if signal.expires_at else None,
            ),
        )
        conn.commit()

    def get_active_sbc_signals(self) -> List[SbcSignal]:
        """Return SBC signals that are active (expires_at null or in the future)."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, sbc_name, rating_req, detected_at, expires_at FROM sbc_signals "
            "WHERE expires_at IS NULL OR expires_at > datetime('now') ORDER BY detected_at DESC"
        ).fetchall()
        return [
            SbcSignal(
                id=row["id"],
                sbc_name=row["sbc_name"],
                rating_req=row["rating_req"],
                detected_at=_iso_to_dt(row["detected_at"]) or datetime.now(timezone.utc),
                expires_at=_iso_to_dt(row["expires_at"]),
            )
            for row in rows
        ]

    def prune_old_prices(self, player_name: str, max_records: int) -> None:
        """Keep only the most recent max_records market_prices for this player; delete older."""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM market_prices WHERE player_name = ? AND id NOT IN ("
            "SELECT id FROM (SELECT id FROM market_prices WHERE player_name = ? "
            "ORDER BY scraped_at DESC LIMIT ?) AS keep)",
            (player_name, player_name, max_records),
        )
        conn.commit()

    def close(self) -> None:
        """Close the SQLite connection if open. Call this in tests and on shutdown."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")
