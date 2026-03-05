"""Intel sidecar entry point. Runs all scrapers once on startup, then APScheduler at intervals."""

import os
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from db import Database, MarketPrice
from scrapers.futbin_graph import FutbinGraphScraper
from scrapers.futdb import FutdbScraper
from scrapers.futgg_sbc import FutGGSbcScraper
from scrapers.futwiz import FutwizScraper
from scrapers.intel_writer import IntelWriter


HEARTBEAT_PATH = "/app/data/intel_heartbeat"
DEFAULT_DB_PATH = "/app/data/fc_trader.db"
DEFAULT_PLATFORM = "ps"

# Set by main() so job functions can use them
_writer: IntelWriter
_futwiz: FutwizScraper
_futbin: FutbinGraphScraper
_futgg: FutGGSbcScraper
_futdb: FutdbScraper
_platform: str


def run_futwiz() -> None:
    """Fetch FUTWIZ prices for config players + trending; write to DB. Never raises."""
    try:
        players = _writer.get_player_list_from_bot_config()
        prices: list[MarketPrice] = []
        for p in players:
            name = p.get("name") or p.get("player_name") or ""
            if isinstance(name, str) and name.strip():
                name = name.strip()
                mp = _futwiz.scrape_player_price(name, _platform)
                if mp:
                    prices.append(mp)
                chem_mp = _futwiz.scrape_chem_style_prices(name, _platform)
                if chem_mp:
                    prices.append(chem_mp)
        trending = _futwiz.scrape_trending_players(_platform)
        prices.extend(trending)
        if prices:
            _writer.write_prices(prices)
        logger.info(f"FUTWIZ: wrote {len(prices)} price(s)")
    except Exception as e:
        logger.warning(f"run_futwiz failed: {e}")


def run_futbin() -> None:
    """Fetch FUTBIN latest price for players that have futbin_id; write to DB. Never raises."""
    try:
        players = _writer.get_player_list_from_bot_config()
        prices: list[MarketPrice] = []
        for p in players:
            player_id = p.get("futbin_id") or p.get("id") if isinstance(p, dict) else None
            if player_id is None:
                continue
            pid_str = str(player_id).strip()
            if not pid_str:
                continue
            name = (p.get("name") or p.get("player_name") or "").strip() or pid_str
            latest = _futbin.get_latest_price(pid_str, _platform)
            if latest is not None:
                prices.append(
                    MarketPrice(
                        player_id=pid_str,
                        player_name=name,
                        source="futbin",
                        platform=_platform,
                        price=latest,
                        scraped_at=datetime.now(timezone.utc),
                        price_shadow=None,
                        price_hunter=None,
                    )
                )
        if prices:
            _writer.write_prices(prices)
        logger.info(f"FUTBIN: wrote {len(prices)} price(s)")
    except Exception as e:
        logger.warning(f"run_futbin failed: {e}")


def run_futgg_sbc() -> None:
    """Fetch active SBCs from FUT.GG; write signals to DB. Never raises."""
    try:
        signals = _futgg.get_active_sbcs()
        if signals:
            _writer.write_sbc_signals(signals)
        logger.info(f"FUT.GG SBC: wrote {len(signals)} signal(s)")
    except Exception as e:
        logger.warning(f"run_futgg_sbc failed: {e}")


def run_futdb() -> None:
    """Fetch FutDB prices for config players (fallback); write to DB. Never raises."""
    try:
        players = _writer.get_player_list_from_bot_config()
        prices: list[MarketPrice] = []
        for p in players:
            name = (p.get("name") or p.get("player_name") or "").strip() if isinstance(p, dict) else ""
            if not name:
                continue
            price_val = _futdb.get_player_price(name, _platform)
            if price_val is not None:
                prices.append(
                    MarketPrice(
                        player_id=name.replace(" ", "-").lower(),
                        player_name=name,
                        source="futdb",
                        platform=_platform,
                        price=price_val,
                        scraped_at=datetime.now(timezone.utc),
                        price_shadow=None,
                        price_hunter=None,
                    )
                )
        if prices:
            _writer.write_prices(prices)
        logger.info(f"FutDB: wrote {len(prices)} price(s)")
    except Exception as e:
        logger.warning(f"run_futdb failed: {e}")


def update_heartbeat() -> None:
    """Write current time to heartbeat file for healthcheck. Never raises."""
    try:
        path = HEARTBEAT_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.warning(f"update_heartbeat failed: {e}")


def run_all_scrapers() -> None:
    """Run all scrapers and heartbeat once (e.g. on startup before scheduler)."""
    run_futwiz()
    run_futbin()
    run_futgg_sbc()
    run_futdb()
    update_heartbeat()


def main() -> None:
    """Initialise DB, writer, scrapers; run scrapers once; then start scheduler."""
    global _writer, _futwiz, _futbin, _futgg, _futdb, _platform
    db_path = os.environ.get("FC_DB_PATH", DEFAULT_DB_PATH)
    _platform = os.environ.get("FC_PLATFORM", DEFAULT_PLATFORM)
    logger.info(f"Intel service starting; db={db_path}, platform={_platform}")

    db = Database(db_path)
    db.init()
    _writer = IntelWriter(db)

    _futwiz = FutwizScraper()
    _futbin = FutbinGraphScraper()
    _futgg = FutGGSbcScraper()
    _futdb = FutdbScraper()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_futwiz, "interval", minutes=15, id="futwiz")
    scheduler.add_job(run_futbin, "interval", minutes=30, id="futbin")
    scheduler.add_job(run_futgg_sbc, "interval", minutes=10, id="futgg_sbc")
    scheduler.add_job(run_futdb, "interval", minutes=60, id="futdb")
    scheduler.add_job(update_heartbeat, "interval", minutes=1, id="heartbeat")

    run_all_scrapers()
    scheduler.start()


if __name__ == "__main__":
    main()
