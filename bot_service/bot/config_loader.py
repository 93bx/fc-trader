"""Loads and validates config (YAML + env overrides), returns typed Config."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml
from loguru import logger


class ConfigError(Exception):
    """Raised when config validation fails (missing required field or placeholder value)."""

    pass


@dataclass
class DatabaseConfig:
    """Database section of config."""

    path: str = "/app/data/fc_trader.db"


@dataclass
class RateLimiterConfig:
    """Rate limiter section of config."""

    max_searches_per_hour: int = 40
    max_buys_per_hour: int = 15
    max_lists_per_hour: int = 20
    cooldown_after_buy_sec: int = 30
    daily_trade_limit: int = 100


@dataclass
class EmulatorConfig:
    """Emulator/AVD section of config."""

    avd_name: str = "fc_trader_avd"
    avd_port: int = 5554
    boot_timeout: int = 180
    headless: bool = True

@dataclass
class AntiDetectConfig:
    """Anti-detection delays and jitter for device/navigator."""

    action_delay_min: float = 0.3
    action_delay_max: float = 0.8
    tap_jitter_px: int = 3


@dataclass
class SniperConfig:
    """Sniper strategy section."""

    players: List[dict] = field(default_factory=list)
    min_profit_pct: float = 5.0


@dataclass
class MassBidderConfig:
    """Mass bidder strategy section."""

    players: List[dict] = field(default_factory=list)
    min_profit_coins: int = 200


@dataclass
class ChemStyleConfig:
    """Chemistry style trader strategy section."""

    players: List[dict] = field(default_factory=list)
    min_profit_pct: float = 5.0
    max_premium_coins: int = 500


@dataclass
class AppConfig:
    """App/auth section of config."""

    login_timeout: int = 120


@dataclass
class Config:
    """Top-level config (YAML + env overrides)."""

    database: DatabaseConfig
    rate_limiter: RateLimiterConfig
    emulator: EmulatorConfig
    anti_detect: AntiDetectConfig
    sniper: SniperConfig
    mass_bidder: MassBidderConfig
    chem_style: ChemStyleConfig
    app: AppConfig
    promos: List[dict] = field(default_factory=list)
    active_strategy: str = "auto"
    platform: str = "ps"
    email: str = ""
    password: str = ""
    log_level: str = "INFO"


# Placeholder values that must be replaced (validation)
_PLACEHOLDER_EMAILS = ("your_ea_email@example.com", "example@example.com", "")
_PLACEHOLDER_PASSWORDS = ("your_ea_password", "example", "")


def _apply_env_overrides(raw: dict) -> dict:
    """Merge env vars into raw config dict; log each override at DEBUG."""
    overrides = {}
    if os.environ.get("FC_EMAIL"):
        overrides["email"] = os.environ["FC_EMAIL"]
        logger.debug("Config override: email from FC_EMAIL")
    if os.environ.get("FC_PASSWORD"):
        overrides["password"] = os.environ["FC_PASSWORD"]
        logger.debug("Config override: password from FC_PASSWORD")
    if os.environ.get("FC_STRATEGY"):
        overrides["active_strategy"] = os.environ["FC_STRATEGY"].lower()
        logger.debug("Config override: active_strategy from FC_STRATEGY")
    if os.environ.get("FC_LOG_LEVEL"):
        overrides["log_level"] = os.environ["FC_LOG_LEVEL"].upper()
        logger.debug("Config override: log_level from FC_LOG_LEVEL")
    if os.environ.get("FC_PLATFORM"):
        overrides["platform"] = os.environ["FC_PLATFORM"].lower()
        logger.debug("Config override: platform from FC_PLATFORM")

    result = {**raw}
    for key, value in overrides.items():
        if key in result or key in ("email", "password", "active_strategy", "platform", "log_level"):
            result[key] = value
    return result


def _build_nested(raw: dict) -> Config:
    """Build Config from merged dict with defaults for missing sections."""
    db = raw.get("database") or {}
    rl = raw.get("rate_limiter") or {}
    emu = raw.get("emulator") or {}
    ad = raw.get("anti_detect") or {}
    sniper = raw.get("sniper") or {}
    mb = raw.get("mass_bidder") or {}
    chem = raw.get("chem_style") or {}
    app = raw.get("app") or {}

    return Config(
        database=DatabaseConfig(path=db.get("path", db.get("db_path", "/app/data/fc_trader.db"))),
        rate_limiter=RateLimiterConfig(
            max_searches_per_hour=rl.get("max_searches_per_hour", 40),
            max_buys_per_hour=rl.get("max_buys_per_hour", 15),
            max_lists_per_hour=rl.get("max_lists_per_hour", 20),
            cooldown_after_buy_sec=rl.get("cooldown_after_buy_sec", 30),
            daily_trade_limit=rl.get("daily_trade_limit", 100),
        ),
        emulator=EmulatorConfig(
            avd_name=emu.get("avd_name", "fc_trader_avd"),
            avd_port=emu.get("avd_port", 5554),
            boot_timeout=int(emu.get("boot_timeout", 180)),
            headless=bool(emu.get("headless", True)),
        ),
        anti_detect=AntiDetectConfig(
            action_delay_min=float(ad.get("action_delay_min", 0.3)),
            action_delay_max=float(ad.get("action_delay_max", 0.8)),
            tap_jitter_px=int(ad.get("tap_jitter_px", 3)),
        ),
        sniper=SniperConfig(
            players=sniper.get("players", []),
            min_profit_pct=float(sniper.get("min_profit_pct", 5.0)),
        ),
        mass_bidder=MassBidderConfig(
            players=mb.get("players", []),
            min_profit_coins=int(mb.get("min_profit_coins", 200)),
        ),
        chem_style=ChemStyleConfig(
            players=chem.get("players", []),
            min_profit_pct=float(chem.get("min_profit_pct", 5.0)),
            max_premium_coins=int(chem.get("max_premium_coins", 500)),
        ),
        app=AppConfig(login_timeout=int(app.get("login_timeout", 120))),
        promos=raw.get("promos", []),
        active_strategy=str(raw.get("active_strategy", "auto")).lower(),
        platform=str(raw.get("platform", "ps")).lower(),
        email=str(raw.get("email", "")),
        password=str(raw.get("password", "")),
        log_level=str(raw.get("log_level", "INFO")).upper(),
    )


def _validate(cfg: Config) -> None:
    """Validate required fields and reject placeholders. Raise ConfigError on failure."""
    if not cfg.database.path:
        raise ConfigError("config database.path must be set")

    if cfg.rate_limiter.max_searches_per_hour < 1:
        raise ConfigError("config rate_limiter.max_searches_per_hour must be >= 1")
    if cfg.rate_limiter.max_buys_per_hour < 1:
        raise ConfigError("config rate_limiter.max_buys_per_hour must be >= 1")
    if cfg.rate_limiter.daily_trade_limit < 1:
        raise ConfigError("config rate_limiter.daily_trade_limit must be >= 1")

    dry_run = os.environ.get("FC_DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    if not dry_run:
        if cfg.email.strip() in _PLACEHOLDER_EMAILS:
            raise ConfigError(
                "config email is missing or still set to example value; set FC_EMAIL or email in config"
            )
        if cfg.password.strip() in _PLACEHOLDER_PASSWORDS:
            raise ConfigError(
                "config password is missing or still set to example value; set FC_PASSWORD or password in config"
            )

    allowed = ("auto", "sniper", "mass_bidder", "chem_style", "peak_sell")
    if cfg.active_strategy not in allowed:
        raise ConfigError(f"config active_strategy must be one of {allowed}, got {cfg.active_strategy!r}")

    allowed_platforms = ("ps", "xbox", "pc")
    if cfg.platform not in allowed_platforms:
        raise ConfigError(f"config platform must be one of {allowed_platforms}, got {cfg.platform!r}")


def load_config(path: str) -> Config:
    """Load YAML from path, apply env overrides, validate, and return typed Config.

    Env overrides: FC_EMAIL, FC_PASSWORD, FC_STRATEGY, FC_LOG_LEVEL, FC_PLATFORM.
    Logs each override at DEBUG. Raises ConfigError if validation fails.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"config file not found: {path}")

    with open(config_path, encoding="utf-8") as f:
        raw: dict = yaml.safe_load(f) or {}

    raw = _apply_env_overrides(raw)
    cfg = _build_nested(raw)
    _validate(cfg)
    return cfg
