"""Entry point only; wires config, DB, emulator, device, auth, navigator, strategies, and main loop."""

import argparse
import os
import random
import sys
import time
from pathlib import Path

from loguru import logger

from bot.auth import AuthManager
from bot.calendar_engine import CalendarEngine
from bot.config_loader import ConfigError, load_config
from bot.database import Database
from bot.device import Device
from bot.emulator import Emulator
from bot.market import MarketScanner
from bot.navigator import Navigator
from bot.portfolio import Portfolio
from bot.rate_limiter import RateLimiter
from bot.strategies import (
    BaseStrategy,
    ChemStyleTrader,
    MassBidder,
    PeakSellStrategy,
    Sniper,
)
from bot.strategy_selector import StrategySelector
from bot.watchdog import Watchdog

DEFAULT_CONFIG_PATH = "/app/config/config.yaml"
DEFAULT_APK_DIR = "/app/apk"
FC_PACKAGE = "com.ea.gp.futmobile"
HEARTBEAT_PATH = "/app/data/heartbeat"
CYCLE_INTERVAL_SEC = 60
CYCLE_JITTER_SEC = 30


def _parse_args() -> argparse.Namespace:
    """Parse CLI: --strategy, --dry-run, --config."""
    p = argparse.ArgumentParser(description="FC Trader bot")
    p.add_argument(
        "--strategy",
        default=None,
        help="Override strategy: sniper, mass_bidder, chem_style, peak_sell (default: from config)",
    )
    p.add_argument("--dry-run", action="store_true", help="Simulate buys/lists only")
    p.add_argument(
        "--config",
        default=os.environ.get("FC_CONFIG", DEFAULT_CONFIG_PATH),
        help="Path to config.yaml",
    )
    return p.parse_args()


def _setup_logging(log_level: str) -> None:
    """Configure loguru level and format."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="{time:HH:mm:ss} | {level:<8} | {module}:{line} | {message}",
        level=log_level,
    )


def _find_apk(apk_dir: str) -> str | None:
    """Return path to first .apk in apk_dir, or None."""
    apk_path = os.environ.get("FC_APK_PATH")
    if apk_path and Path(apk_path).exists():
        return apk_path
    dir_path = Path(apk_dir)
    if not dir_path.is_dir():
        return None
    apks = list(dir_path.glob("*.apk"))
    return str(apks[0]) if apks else None


def _touch_heartbeat(path: str) -> None:
    """Touch heartbeat file for healthcheck."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).touch()
    except OSError as e:
        logger.warning("Could not touch heartbeat {}: {}", path, e)


def _strategy_factory(
    name: str,
    navigator: Navigator,
    scanner: MarketScanner,
    portfolio: Portfolio,
    rate_limiter: RateLimiter,
    db: Database,
    cfg,
    dry_run: bool,
) -> BaseStrategy:
    """Instantiate strategy by name."""
    mapping = {
        "sniper": Sniper,
        "mass_bidder": MassBidder,
        "chem_style": ChemStyleTrader,
        "peak_sell": PeakSellStrategy,
    }
    cls = mapping.get(name, Sniper)
    return cls(
        navigator=navigator,
        scanner=scanner,
        portfolio=portfolio,
        rate_limiter=rate_limiter,
        db=db,
        cfg=cfg,
        dry_run=dry_run,
    )


def main() -> None:
    """Load config, init all components, run main loop; exit(1) on setup failure."""
    args = _parse_args()
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        logger.error("Config load failed: {}", e)
        sys.exit(1)
    _setup_logging(cfg.log_level)

    execution_mode = os.environ.get("FC_EXECUTION_MODE", getattr(cfg, "execution_mode", "android")).lower()
    if execution_mode == "web":
        logger.info("Execution mode: WEB (default). Android service inactive.")
        sys.exit(0)

    android_stealth = None
    try:
        from anti_detect.android_stealth import AndroidKSAStealth
        from web.config_loader import AntiDetectConfig as WebAD, GeolocationConfig, ProxyConfig
        web_ad = WebAD(
            profile="ksa_riyadh_win11", timezone="Asia/Riyadh", locale="ar-SA",
            accept_language="ar-SA", platform="Win32", os_version="10.0",
            screen_width=1920, screen_height=1080, avail_width=1920, avail_height=1040,
            color_depth=24, pixel_ratio=1.0, device_memory=8, hardware_concurrency=8,
            user_agent="", webgl_vendor="", webgl_renderer="", canvas_noise=True,
            audio_noise=True,
            geolocation=GeolocationConfig(latitude=24.6877, longitude=46.7219, accuracy=25.0),
            proxy=ProxyConfig(enabled=False, proxy_type="residential", country_code="SA",
                              city="Riyadh", rotate_every_n_sessions=1, pool=[]),
            action_delay_min=0.3, action_delay_max=0.8, typing_delay_min=0.07,
            typing_delay_max=0.21, scroll_pause_min=0.5, scroll_pause_max=1.5,
            page_load_pause_min=2.0, page_load_pause_max=5.0, idle_drift_min=240,
            idle_drift_max=900, session_max_duration=5400, daily_active_hours_max=6.0,
        )
        android_stealth = AndroidKSAStealth(web_ad)
        android_stealth.apply(cfg.emulator.avd_port)
        logger.info("Android KSA stealth profile applied.")
    except Exception as exc:
        logger.debug("Android KSA stealth not applied (optional): {}", exc)

    apk_path = _find_apk(DEFAULT_APK_DIR)
    if not apk_path:
        logger.error(
            "APK not found: set FC_APK_PATH or place a .apk file in {}",
            DEFAULT_APK_DIR,
        )
        sys.exit(1)

    db = Database(cfg.database)
    db.init()
    rate_limiter = RateLimiter(cfg.rate_limiter, db)

    emulator = Emulator(cfg.emulator)
    if not emulator.start():
        logger.error("Emulator start failed")
        sys.exit(1)
    device = Device(cfg.anti_detect)
    if not device.connect():
        logger.error("Device connect failed")
        emulator.stop()
        sys.exit(1)
    if not emulator.install_apk(apk_path):
        logger.error("APK install failed")
        emulator.stop()
        sys.exit(1)
    package = os.environ.get("FC_PACKAGE", FC_PACKAGE)
    if not emulator.launch_app(package):
        logger.warning("Launch app returned False; continuing")
    auth = AuthManager(device, cfg)
    if not auth.login():
        logger.error("Login failed")
        emulator.stop()
        sys.exit(1)

    navigator = Navigator(device, db, cfg, rate_limiter)
    portfolio = Portfolio(db)
    scanner = MarketScanner(navigator, db, cfg)
    watchdog = Watchdog(device, auth, cfg)
    calendar = CalendarEngine(cfg)
    selector = StrategySelector(calendar, cfg)

    dry_run = args.dry_run
    if dry_run:
        logger.info("DRY RUN: no real buys or lists will be executed")

    try:
        while True:
            _touch_heartbeat(HEARTBEAT_PATH)
            if rate_limiter.daily_limit_reached():
                logger.warning("Daily trade limit reached; sleeping until reset")
                rate_limiter.sleep_until_reset()
                continue
            if not watchdog.check_and_recover():
                logger.critical("Watchdog unrecoverable; stopping bot")
                break
            phase = calendar.get_current_phase()
            strategy_name = (
                args.strategy
                if args.strategy
                else (
                    cfg.active_strategy
                    if cfg.active_strategy != "auto"
                    else selector.get_strategy_name(phase)
                )
            )
            strategy = _strategy_factory(
                strategy_name,
                navigator,
                scanner,
                portfolio,
                rate_limiter,
                db,
                cfg,
                dry_run=dry_run,
            )
            result = strategy.run_cycle()
            logger.info(
                "Cycle {}: buys={} skipped={} errors={}",
                strategy_name,
                result.buys,
                result.skipped,
                result.errors,
            )
            interval = CYCLE_INTERVAL_SEC + random.uniform(0, CYCLE_JITTER_SEC)
            time.sleep(interval)
    finally:
        portfolio.print_summary()
        emulator.stop()
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
