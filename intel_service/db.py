"""Minimal DB layer for intel service. Writes market_prices and sbc_signals only; schema matches bot."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


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
"""


def _dt_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO 8601 string for SQLite TEXT storage."""
    return dt.isoformat()


@dataclass
class MarketPrice:
    """Single market price record from intel (FUTWIZ/FUTBIN/etc). Compatible with bot.models.MarketPrice."""

    player_id: str
    player_name: str
    source: str
    platform: str
    price: int
    scraped_at: datetime
    price_shadow: Optional[int] = None
    price_hunter: Optional[int] = None
    id: Optional[int] = None


@dataclass
class SbcSignal:
    """SBC detected by intel (FUT.GG etc). Compatible with bot.models.SbcSignal."""

    sbc_name: str
    detected_at: datetime
    rating_req: Optional[int] = None
    expires_at: Optional[datetime] = None
    id: Optional[int] = None


class Database:
    """SQLite wrapper for intel service. Only market_prices and sbc_signals; schema matches bot."""

    def __init__(self, db_path: str) -> None:
        """Open or create DB at db_path (e.g. /app/data/fc_trader.db)."""
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        """Return existing connection or open one."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init(self) -> None:
        """Create market_prices and sbc_signals tables and index. Idempotent."""
        conn = self._get_conn()
        conn.executescript(SCHEMA)
        conn.commit()
        logger.debug("Intel database schema initialised")

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
