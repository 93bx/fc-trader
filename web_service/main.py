"""FC 26 WEB APP — Entry point only; no business logic."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

DEFAULT_CONFIG = os.environ.get("FC_WEB_CONFIG", "/app/config/web_config.yaml")
HEARTBEAT_PATH = "/app/data/web_heartbeat"
MAINTENANCE_INTERVAL_S = 1800


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for config path, strategy override, and dry-run."""
    p = argparse.ArgumentParser(description="FC Trader Web Bot")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="Path to web_config.yaml")
    p.add_argument("--strategy", default=None, help="Override active strategy")
    p.add_argument("--dry-run", action="store_true", help="Simulate buys/lists")
    p.add_argument("--mode", default=None, help="Override execution mode")
    return p.parse_args()


def _setup_logging(log_level: str) -> None:
    """Configure loguru format."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="{time:HH:mm:ss} | {level:<8} | {module}:{line} | {message}",
        level=log_level,
    )


def _touch_heartbeat() -> None:
    """Update the Docker healthcheck heartbeat file."""
    try:
        Path(HEARTBEAT_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(HEARTBEAT_PATH).touch()
    except OSError as exc:
        logger.warning("Could not touch heartbeat: {}", exc)


def _seconds_until_midnight_utc() -> float:
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1.0, (midnight - now).total_seconds())


def _instantiate_strategy(name: str, market, navigator, db, rate_limiter, timing, cfg, dry_run):
    """Return the correct web strategy instance by name."""
    from web.strategies.web_chem_style import WebChemStyleTrader
    from web.strategies.web_mass_bidder import WebMassBidder
    from web.strategies.web_sniper import WebSniper

    mapping = {
        "sniper": WebSniper,
        "mass_bidder": WebMassBidder,
        "chem_style": WebChemStyleTrader,
    }
    cls = mapping.get(name, WebSniper)
    return cls(market, navigator, db, rate_limiter, timing, cfg, dry_run)


async def run(args: argparse.Namespace) -> None:
    """Main async entry point: bootstrap components, run trading loop."""
    from bot.calendar_engine import CalendarEngine
    from bot.config_loader import Config as BotConfig
    from bot.database import Database
    from bot.strategy_selector import StrategySelector
    from web.anti_detect.fingerprint import FingerprintEngine
    from web.anti_detect.proxy import ProxyRotator
    from web.anti_detect.stealth import StealthEngine
    from web.anti_detect.timing import KSATiming
    from web.browser import BrowserSession
    from web.config_loader import ConfigError, load_config
    from web.web_auth import WebAuthManager
    from web.web_market import WebMarket
    from web.web_navigator import WebNavigator
    from web.web_rate_limiter import WebRateLimiter
    from web.web_rewards import WebRewards
    from web.web_sbc import WebSBC
    from web.web_watchdog import WebWatchdog

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        logger.critical("Config load failed: {}", exc)
        sys.exit(1)

    _setup_logging(cfg.log_level)

    if args.mode:
        object.__setattr__(cfg, "execution_mode", args.mode)

    db = Database(type("DB", (), {"path": "/app/data/fc_trader.db"})())
    db.init()

    proxy = ProxyRotator(cfg.anti_detect.proxy)
    fingerprint = FingerprintEngine(cfg.anti_detect)
    stealth = StealthEngine(cfg.anti_detect)
    timing = KSATiming(cfg.anti_detect)
    rate_limiter = WebRateLimiter(cfg.web_rate_limiter, db)

    dry_run = args.dry_run
    if dry_run:
        logger.info("DRY RUN: no real buys or lists will execute.")

    bot_cfg = type("FakeBotCfg", (), {"promos": cfg.promos, "active_strategy": cfg.active_strategy})()
    calendar = CalendarEngine(bot_cfg)
    selector = StrategySelector(calendar, bot_cfg)

    hours_run_today = 0.0
    last_maintenance = 0.0
    strategy_name_override = args.strategy

    async with BrowserSession(cfg, fingerprint, stealth, proxy, timing) as browser:
        auth = WebAuthManager(browser, cfg, timing)

        if not await auth.load_session():
            if not await auth.login():
                logger.critical("Login failed — cannot start.")
                sys.exit(1)

        navigator = WebNavigator(browser, db, cfg, timing)
        market = WebMarket(navigator, db, rate_limiter, timing, cfg)
        sbc = WebSBC(navigator, db, timing, cfg)
        rewards = WebRewards(navigator, timing, cfg)
        watchdog = WebWatchdog(browser, auth, cfg, timing)
        session_cycle_start = time.monotonic()

        while True:
            _touch_heartbeat()

            if not timing.is_active_window():
                wait = timing.seconds_until_next_active()
                logger.info(
                    "Outside KSA active window — sleeping {:.0f}min.", wait / 60
                )
                await asyncio.sleep(wait)
                continue

            if timing.daily_hours_exhausted(hours_run_today):
                sleep_s = _seconds_until_midnight_utc()
                logger.info(
                    "Daily active hour cap reached. Offline for {:.0f}min.", sleep_s / 60
                )
                await asyncio.sleep(sleep_s)
                hours_run_today = 0.0
                continue

            if not await watchdog.check_and_recover():
                logger.critical("Watchdog: unrecoverable state — stopping.")
                break

            if await auth.detect_console_conflict():
                logger.critical("Console session active — stopping.")
                break

            await auth.refresh_session()

            now_mono = time.monotonic()
            if now_mono - last_maintenance >= MAINTENANCE_INTERVAL_S:
                await rewards.claim_all()
                await sbc.run_sbc_cycle()
                last_maintenance = now_mono

            if rate_limiter.daily_limit_reached():
                await rate_limiter._sleep_until_midnight()
                continue

            phase = calendar.get_current_phase()
            strat_name = (
                strategy_name_override
                or (cfg.active_strategy if cfg.active_strategy != "auto" else selector.get_strategy_name(phase))
            )

            strategy = _instantiate_strategy(
                strat_name, market, navigator, db, rate_limiter, timing, cfg, dry_run
            )
            result = await strategy.run_cycle()
            logger.info(
                "Cycle: phase={} strategy={} buys={} skipped={} errors={}",
                phase.value,
                strat_name,
                result.buys,
                result.skipped,
                result.errors,
            )

            await market.execute_relist_cycle()
            await rate_limiter.keepalive(browser.page)

            idle = timing.idle_drift()
            logger.debug("Idle drift: {:.0f}s", idle)
            cycle_elapsed = time.monotonic() - session_cycle_start
            hours_run_today += cycle_elapsed / 3600
            session_cycle_start = time.monotonic()
            await asyncio.sleep(idle)


def main() -> None:
    """Sync entry point; delegates to async run()."""
    args = _parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
