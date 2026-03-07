"""FC 26 WEB APP — Load, validate, and type web_service configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from loguru import logger


class ConfigError(Exception):
    """Raised when web config validation fails."""


@dataclass(frozen=True)
class ProxyEndpoint:
    """One proxy endpoint in the pool."""

    host: str
    port: int
    user: str
    password: str


@dataclass(frozen=True)
class ProxyConfig:
    """Proxy settings for anti-detection."""

    enabled: bool
    proxy_type: str
    country_code: str
    city: str
    rotate_every_n_sessions: int
    pool: list[ProxyEndpoint] = field(default_factory=list)


@dataclass(frozen=True)
class GeolocationConfig:
    """Geolocation tuple used by browser context."""

    latitude: float
    longitude: float
    accuracy: float


@dataclass(frozen=True)
class AntiDetectConfig:
    """Anti-detection profile for the web browser."""

    profile: str
    timezone: str
    locale: str
    accept_language: str
    platform: str
    os_version: str
    screen_width: int
    screen_height: int
    avail_width: int
    avail_height: int
    color_depth: int
    pixel_ratio: float
    device_memory: int
    hardware_concurrency: int
    user_agent: str
    webgl_vendor: str
    webgl_renderer: str
    canvas_noise: bool
    audio_noise: bool
    geolocation: GeolocationConfig
    proxy: ProxyConfig
    action_delay_min: float
    action_delay_max: float
    typing_delay_min: float
    typing_delay_max: float
    scroll_pause_min: float
    scroll_pause_max: float
    page_load_pause_min: float
    page_load_pause_max: float
    idle_drift_min: float
    idle_drift_max: float
    session_max_duration: int
    daily_active_hours_max: float


@dataclass(frozen=True)
class WebRateLimiterConfig:
    """Rate-limiter bounds specific to web automation."""

    max_searches_per_hour: int
    max_buys_per_hour: int
    max_lists_per_hour: int
    cooldown_after_buy_sec: int
    daily_trade_limit: int
    inter_search_pause_min: float
    inter_search_pause_max: float
    daily_active_hours_max: float
    keepalive_interval_sec: int


@dataclass(frozen=True)
class BrowserConfig:
    """Playwright browser runtime options."""

    headless: bool
    slow_mo: int
    viewport_width: int
    viewport_height: int
    user_data_dir: str


@dataclass(frozen=True)
class EAConfig:
    """EA account credentials and login behavior."""

    email: str
    password: str
    login_timeout: int


@dataclass(frozen=True)
class SniperConfig:
    """Sniper strategy config."""

    players: list[dict]
    min_profit_pct: float


@dataclass(frozen=True)
class MassBidderConfig:
    """Mass bidder strategy config."""

    players: list[dict]
    min_profit_coins: int


@dataclass(frozen=True)
class ChemStyleConfig:
    """Chem style strategy config."""

    players: list[dict]
    min_profit_pct: float
    max_premium_coins: int


@dataclass(frozen=True)
class SBCConfig:
    """SBC automation options."""

    enabled: bool
    only_use_club_players: bool
    target_categories: list[str]


@dataclass(frozen=True)
class RewardsConfig:
    """Auto-claim reward toggles."""

    auto_claim: bool
    claim_rivals: bool
    claim_squad_battles: bool
    claim_champions: bool


@dataclass(frozen=True)
class WebConfig:
    """Top-level web_service configuration."""

    execution_mode: str
    ea: EAConfig
    anti_detect: AntiDetectConfig
    web_rate_limiter: WebRateLimiterConfig
    browser: BrowserConfig
    active_strategy: str
    platform: str
    sniper: SniperConfig
    mass_bidder: MassBidderConfig
    chem_style: ChemStyleConfig
    sbc: SBCConfig
    rewards: RewardsConfig
    promos: list[dict]
    log_level: str = "INFO"


def _read_proxy_pool(raw_pool: list[dict]) -> list[ProxyEndpoint]:
    pool: list[ProxyEndpoint] = []
    for row in raw_pool:
        pool.append(
            ProxyEndpoint(
                host=str(row.get("host", "")).strip(),
                port=int(row.get("port", 0)),
                user=str(row.get("user", "")).strip(),
                password=str(row.get("pass", "")).strip(),
            )
        )
    return pool


def _with_env_overrides(raw: dict) -> dict:
    out = dict(raw)
    ea = dict(out.get("ea", {}))
    if os.environ.get("FC_EMAIL"):
        ea["email"] = os.environ["FC_EMAIL"]
        logger.debug("Config override: ea.email from FC_EMAIL")
    if os.environ.get("FC_PASSWORD"):
        ea["password"] = os.environ["FC_PASSWORD"]
        logger.debug("Config override: ea.password from FC_PASSWORD")
    out["ea"] = ea

    if os.environ.get("FC_EXECUTION_MODE"):
        out["execution_mode"] = os.environ["FC_EXECUTION_MODE"].lower()
        logger.debug("Config override: execution_mode from FC_EXECUTION_MODE")
    if os.environ.get("FC_STRATEGY"):
        out["active_strategy"] = os.environ["FC_STRATEGY"].lower()
        logger.debug("Config override: active_strategy from FC_STRATEGY")
    if os.environ.get("FC_LOG_LEVEL"):
        out["log_level"] = os.environ["FC_LOG_LEVEL"].upper()
        logger.debug("Config override: log_level from FC_LOG_LEVEL")

    ad = dict(out.get("anti_detect", {}))
    proxy = dict(ad.get("proxy", {}))
    pool = list(proxy.get("pool", []))
    if pool:
        p0 = dict(pool[0])
        if os.environ.get("PROXY_HOST_1"):
            p0["host"] = os.environ["PROXY_HOST_1"]
        if os.environ.get("PROXY_PORT_1"):
            p0["port"] = int(os.environ["PROXY_PORT_1"])
        if os.environ.get("PROXY_USER_1"):
            p0["user"] = os.environ["PROXY_USER_1"]
        if os.environ.get("PROXY_PASS_1"):
            p0["pass"] = os.environ["PROXY_PASS_1"]
        pool[0] = p0
    proxy["pool"] = pool
    ad["proxy"] = proxy
    out["anti_detect"] = ad
    return out


def _build(raw: dict) -> WebConfig:
    ea = raw.get("ea", {})
    ad = raw.get("anti_detect", {})
    geo = ad.get("geolocation", {})
    proxy = ad.get("proxy", {})
    wr = raw.get("web_rate_limiter", {})
    browser = raw.get("browser", {})
    sniper = raw.get("sniper", {})
    bidder = raw.get("mass_bidder", {})
    chem = raw.get("chem_style", {})
    sbc = raw.get("sbc", {})
    rewards = raw.get("rewards", {})

    return WebConfig(
        execution_mode=str(raw.get("execution_mode", "web")).lower(),
        ea=EAConfig(
            email=str(ea.get("email", "")),
            password=str(ea.get("password", "")),
            login_timeout=int(ea.get("login_timeout", 180)),
        ),
        anti_detect=AntiDetectConfig(
            profile=str(ad.get("profile", "ksa_riyadh_win11")),
            timezone=str(ad.get("timezone", "Asia/Riyadh")),
            locale=str(ad.get("locale", "ar-SA")),
            accept_language=str(ad.get("accept_language", "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7")),
            platform=str(ad.get("platform", "Win32")),
            os_version=str(ad.get("os_version", "10.0")),
            screen_width=int(ad.get("screen_width", 1920)),
            screen_height=int(ad.get("screen_height", 1080)),
            avail_width=int(ad.get("avail_width", 1920)),
            avail_height=int(ad.get("avail_height", 1040)),
            color_depth=int(ad.get("color_depth", 24)),
            pixel_ratio=float(ad.get("pixel_ratio", 1.0)),
            device_memory=int(ad.get("device_memory", 8)),
            hardware_concurrency=int(ad.get("hardware_concurrency", 8)),
            user_agent=str(ad.get("user_agent", "")),
            webgl_vendor=str(ad.get("webgl_vendor", "Google Inc. (Intel)")),
            webgl_renderer=str(ad.get("webgl_renderer", "")),
            canvas_noise=bool(ad.get("canvas_noise", True)),
            audio_noise=bool(ad.get("audio_noise", True)),
            geolocation=GeolocationConfig(
                latitude=float(geo.get("latitude", 24.6877)),
                longitude=float(geo.get("longitude", 46.7219)),
                accuracy=float(geo.get("accuracy", 25.0)),
            ),
            proxy=ProxyConfig(
                enabled=bool(proxy.get("enabled", False)),
                proxy_type=str(proxy.get("type", "residential")),
                country_code=str(proxy.get("country_code", "SA")),
                city=str(proxy.get("city", "Riyadh")),
                rotate_every_n_sessions=int(proxy.get("rotate_every_n_sessions", 1)),
                pool=_read_proxy_pool(list(proxy.get("pool", []))),
            ),
            action_delay_min=float(ad.get("action_delay_min", 1.0)),
            action_delay_max=float(ad.get("action_delay_max", 3.2)),
            typing_delay_min=float(ad.get("typing_delay_min", 0.07)),
            typing_delay_max=float(ad.get("typing_delay_max", 0.21)),
            scroll_pause_min=float(ad.get("scroll_pause_min", 0.5)),
            scroll_pause_max=float(ad.get("scroll_pause_max", 1.5)),
            page_load_pause_min=float(ad.get("page_load_pause_min", 2.0)),
            page_load_pause_max=float(ad.get("page_load_pause_max", 5.0)),
            idle_drift_min=float(ad.get("idle_drift_min", 240)),
            idle_drift_max=float(ad.get("idle_drift_max", 900)),
            session_max_duration=int(ad.get("session_max_duration", 5400)),
            daily_active_hours_max=float(ad.get("daily_active_hours_max", 6)),
        ),
        web_rate_limiter=WebRateLimiterConfig(
            max_searches_per_hour=int(wr.get("max_searches_per_hour", 25)),
            max_buys_per_hour=int(wr.get("max_buys_per_hour", 10)),
            max_lists_per_hour=int(wr.get("max_lists_per_hour", 12)),
            cooldown_after_buy_sec=int(wr.get("cooldown_after_buy_sec", 50)),
            daily_trade_limit=int(wr.get("daily_trade_limit", 75)),
            inter_search_pause_min=float(wr.get("inter_search_pause_min", 9)),
            inter_search_pause_max=float(wr.get("inter_search_pause_max", 28)),
            daily_active_hours_max=float(wr.get("daily_active_hours_max", 6)),
            keepalive_interval_sec=int(wr.get("keepalive_interval_sec", 480)),
        ),
        browser=BrowserConfig(
            headless=bool(browser.get("headless", True)),
            slow_mo=int(browser.get("slow_mo", 0)),
            viewport_width=int(browser.get("viewport_width", 1920)),
            viewport_height=int(browser.get("viewport_height", 1080)),
            user_data_dir=str(browser.get("user_data_dir", "/app/data/browser_profile")),
        ),
        active_strategy=str(raw.get("active_strategy", "auto")).lower(),
        platform=str(raw.get("platform", "ps")).lower(),
        sniper=SniperConfig(
            players=list(sniper.get("players", [])),
            min_profit_pct=float(sniper.get("min_profit_pct", 5.0)),
        ),
        mass_bidder=MassBidderConfig(
            players=list(bidder.get("players", [])),
            min_profit_coins=int(bidder.get("min_profit_coins", 200)),
        ),
        chem_style=ChemStyleConfig(
            players=list(chem.get("players", [])),
            min_profit_pct=float(chem.get("min_profit_pct", 5.0)),
            max_premium_coins=int(chem.get("max_premium_coins", 500)),
        ),
        sbc=SBCConfig(
            enabled=bool(sbc.get("enabled", True)),
            only_use_club_players=bool(sbc.get("only_use_club_players", True)),
            target_categories=list(sbc.get("target_categories", ["Upgrade", "Foundation"])),
        ),
        rewards=RewardsConfig(
            auto_claim=bool(rewards.get("auto_claim", True)),
            claim_rivals=bool(rewards.get("claim_rivals", True)),
            claim_squad_battles=bool(rewards.get("claim_squad_battles", True)),
            claim_champions=bool(rewards.get("claim_champions", True)),
        ),
        promos=list(raw.get("promos", [])),
        log_level=str(raw.get("log_level", "INFO")).upper(),
    )


def _validate(cfg: WebConfig) -> None:
    if cfg.execution_mode not in {"web", "android", "both"}:
        raise ConfigError("execution_mode must be one of: web, android, both")
    if cfg.platform not in {"ps", "xbox", "pc"}:
        raise ConfigError("platform must be one of: ps, xbox, pc")
    if cfg.active_strategy not in {"auto", "sniper", "mass_bidder", "chem_style", "peak_sell"}:
        raise ConfigError("active_strategy is invalid")
    if cfg.anti_detect.action_delay_min > cfg.anti_detect.action_delay_max:
        raise ConfigError("anti_detect.action_delay_min must be <= action_delay_max")
    if cfg.web_rate_limiter.inter_search_pause_min > cfg.web_rate_limiter.inter_search_pause_max:
        raise ConfigError("web_rate_limiter.inter_search_pause_min must be <= max")
    if cfg.ea.login_timeout < 30:
        raise ConfigError("ea.login_timeout must be >= 30")
    if cfg.web_rate_limiter.daily_trade_limit < 1:
        raise ConfigError("web_rate_limiter.daily_trade_limit must be >= 1")


def load_config(path: str) -> WebConfig:
    """Load YAML config and apply environment overrides."""
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise ConfigError(f"config file not found: {path}")
    with cfg_path.open(encoding="utf-8") as f:
        raw: dict = yaml.safe_load(f) or {}
    merged = _with_env_overrides(raw)
    cfg = _build(merged)
    _validate(cfg)
    return cfg

