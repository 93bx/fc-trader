"""Writes scraper output to DB (market_prices, sbc_signals). No SQL here; uses db methods only."""

from pathlib import Path
from typing import Any, Dict, List

import yaml
from loguru import logger

from db import Database, MarketPrice, SbcSignal


DEFAULT_MAX_PRICE_RECORDS_PER_PLAYER = 50


class IntelWriter:
    """Writes market prices and SBC signals to the shared database. Reads bot config for player list."""

    def __init__(self, db: Database, max_price_records: int = DEFAULT_MAX_PRICE_RECORDS_PER_PLAYER) -> None:
        """db is from intel_service.db; max_price_records used in prune_old_prices after write_prices."""
        self._db = db
        self._max_price_records = max_price_records

    def write_prices(self, prices: List[MarketPrice]) -> None:
        """Insert all prices then prune old records per player to max_price_records."""
        if not prices:
            return
        for price in prices:
            try:
                self._db.insert_market_price(price)
            except Exception as e:
                logger.warning(f"IntelWriter insert_market_price failed: {e}")
        seen_players: set = set()
        for price in prices:
            if price.player_name not in seen_players:
                seen_players.add(price.player_name)
                try:
                    self._db.prune_old_prices(price.player_name, self._max_price_records)
                except Exception as e:
                    logger.warning(f"IntelWriter prune_old_prices failed: {e}")

    def write_sbc_signals(self, signals: List[SbcSignal]) -> None:
        """Insert each signal; skip duplicates by (sbc_name, detected_at) within this batch."""
        seen: set = set()
        for signal in signals:
            key = (signal.sbc_name, signal.detected_at.isoformat())
            if key in seen:
                continue
            seen.add(key)
            try:
                self._db.insert_sbc_signal(signal)
            except Exception as e:
                logger.warning(f"IntelWriter insert_sbc_signal failed: {e}")

    def get_player_list_from_bot_config(
        self, config_path: str = "/app/bot_config/config.yaml"
    ) -> List[Dict[str, Any]]:
        """Load bot config YAML and merge sniper/mass_bidder/chem_style players into a unique list of dicts. Returns [] if file missing or invalid."""
        path = Path(config_path)
        if not path.is_file():
            logger.warning(f"Bot config not found at {config_path}; player list empty")
            return []
        try:
            with open(path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            if not isinstance(cfg, dict):
                logger.warning("Bot config is not a dict; player list empty")
                return []
            result: List[Dict[str, Any]] = []
            seen_names: set = set()
            for section in ("sniper", "mass_bidder", "chem_style"):
                players = cfg.get(section, {}).get("players") if isinstance(cfg.get(section), dict) else cfg.get(section)
                if not isinstance(players, list):
                    continue
                for p in players:
                    if isinstance(p, dict):
                        name = (p.get("name") or p.get("player_name") or "").strip()
                    else:
                        name = str(p).strip()
                    if name and name not in seen_names:
                        seen_names.add(name)
                        result.append(p if isinstance(p, dict) else {"name": name})
            return result
        except Exception as e:
            logger.warning(f"Failed to load bot config from {config_path}: {e}")
            return []
