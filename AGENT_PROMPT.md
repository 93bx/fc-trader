# FC TRADER — CURSOR AGENT PLAN MODE PROMPT
# Paste this entire prompt into Cursor Agent (Plan mode) to build the full project.
# ============================================================================


## OBJECTIVE

Build the complete FC Trader project as specified in `.cursorrules`. This is a
fully automated trading bot for the EA Sports FC 26 Companion Android app. It
runs entirely inside Docker, spins up a headless Android emulator, and executes
three market strategies (Sniper, Mass Bidder, Chemistry Style Trader) driven by
a real-time market calendar and an external market intelligence sidecar service.

Read `.cursorrules` completely before writing a single line of code. Every rule
there is authoritative. This prompt provides the build sequence and detail.


---

## PHASE 1 — PROJECT SCAFFOLD

Create the complete directory structure exactly as defined in `.cursorrules`
section 2. Create every directory and an `__init__.py` in every Python package
directory. Create placeholder files for every module listed — empty but with the
module docstring already written (explaining the module's single responsibility).

After scaffolding, create these project-root files:

### `.gitignore`
Exclude: `.env`, `config/config.yaml`, `*.db`, `logs/`, `apk/`, `__pycache__/`,
`*.pyc`, `.pytest_cache/`, `*.egg-info/`, `dist/`, `.DS_Store`

### `.env.example`
```
# EA Account — use a secondary/mule account, never your main
FC_EMAIL=your_ea_email@example.com
FC_PASSWORD=your_ea_password

# Strategy override (sniper | mass_bidder | chem_style | auto)
# auto = calendar-driven automatic selection
FC_STRATEGY=auto

# Logging level (DEBUG | INFO | WARNING | ERROR)
FC_LOG_LEVEL=INFO

# Platform for price lookups (ps | xbox | pc)
FC_PLATFORM=ps
```

### `docker-compose.yml`
Two services: `fc-trader` and `intel`. Rules:
- `fc-trader` uses `./bot_service` build context
- `fc-trader` has `devices: [/dev/kvm:/dev/kvm]` and `privileged: true`
- `fc-trader` mounts: `./bot_service/config:/app/config`, `./logs:/app/logs`,
  `./apk:/app/apk`, named volume `shared-data:/app/data`
- `fc-trader` mem_limit: 4g, cpus: "4"
- `intel` uses `./intel_service` build context  
- `intel` mounts: named volume `shared-data:/app/data`
- `intel` mem_limit: 256m, cpus: "0.5"
- Named volume `shared-data` declared at bottom
- Both services: `restart: unless-stopped`
- Both services: env vars from `.env` file
- Healthcheck on both: bot checks `/app/data/heartbeat` file,
  intel checks `/app/data/intel_heartbeat` file
- Log driver: json-file, max-size 50m, max-file 5


---

## PHASE 2 — SHARED INFRASTRUCTURE

### `bot_service/bot/database.py`

This is the most critical shared module. Build it completely first.

The `Database` class wraps SQLite with `sqlite3`. Constructor takes `cfg: dict`
(the database section of config). All methods are synchronous.

SCHEMA constant must define ALL four tables:

```sql
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
    status          TEXT NOT NULL DEFAULT 'held',
    acquired_at     TEXT NOT NULL,
    listed_at       TEXT,
    sold_at         TEXT
);
```

Implement these methods (all with full type hints and docstrings):
- `init() -> None` — creates all tables
- `get_market_price(player_name: str, platform: str) -> Optional[MarketPrice]`
  Returns the most recent price record for the player
- `get_market_price_with_chem(player_name: str, platform: str) -> Optional[MarketPrice]`
  Returns most recent record that has price_shadow or price_hunter populated
- `insert_market_price(price: MarketPrice) -> None`
- `insert_trade(trade: Trade) -> None`
- `get_daily_trade_count() -> int`
- `get_hourly_action_count(action_type: str) -> int`
- `update_rate_state(action_type: str) -> None`
- `get_rate_state(action_type: str) -> Optional[RateState]`
- `insert_portfolio_item(item: PortfolioItem) -> None`
- `update_portfolio_item(id: int, status: str, sold_at: str, sell_price: int) -> None`
- `get_held_items() -> List[PortfolioItem]`
- `get_portfolio_summary() -> PortfolioSummary`
- `insert_sbc_signal(signal: SbcSignal) -> None`
- `get_active_sbc_signals() -> List[SbcSignal]`
- `prune_old_prices(player_name: str, max_records: int) -> None`

Define these dataclasses in `bot/models.py`:
  `MarketPrice`, `Trade`, `RateState`, `PortfolioItem`, `PortfolioSummary`,
  `SbcSignal`, `Listing`, `ProfitResult`, `CycleResult`

Every dataclass field must have a type. Use `datetime` for timestamps, convert
to ISO string for SQLite storage.


---

## PHASE 3 — BOT SERVICE: CORE MODULES

Build these in order (each depends on the previous):

### `bot_service/bot/config_loader.py`
- `load_config(path: str) -> Config` — loads YAML, applies env overrides
- `Config` dataclass with nested dataclasses for each section
- Validate required fields; raise `ConfigError` (custom exception) with
  descriptive message if anything is missing or still set to example value
- Log each env override applied at DEBUG level

### `bot_service/bot/utils.py`
This file must contain:

```python
EA_BID_INCREMENTS = [
    (200,    1_000,   50),
    (1_000,  10_000,  100),
    (10_000, 50_000,  250),
    (50_000, 100_000, 500),
    (100_000, None,   1_000),
]

def get_next_bid(current_price: int) -> int:
    """Return the next valid bid above current_price using EA's increment table."""

def get_prev_bid(current_price: int) -> int:
    """Return the nearest valid bid at or below current_price."""

def calculate_profit(buy_price: int, sell_price: int) -> ProfitResult:
    """Calculate net profit after EA 5% tax."""
    # net_received = sell_price * 0.95
    # profit = net_received - buy_price
    # roi_pct = profit / buy_price * 100

def calculate_max_buy(target_sell: int, min_profit_pct: float) -> int:
    """
    Work backwards from desired sell price to maximum buy price.
    max_buy = (target_sell * 0.95) * (1 - min_profit_pct/100)
    Then round DOWN to nearest valid bid increment.
    """

def parse_coin_value(text: str) -> Optional[int]:
    """
    Parse FC coin display strings to integer.
    Handles: "14,500" → 14500, "14.5K" → 14500, "1.2M" → 1200000
    Returns None if parsing fails.
    """

def random_delay(min_s: float, max_s: float) -> None:
    """Sleep for a random duration between min_s and max_s."""
```

Write exhaustive unit tests in `bot_service/tests/test_utils.py` covering:
  - get_next_bid at every bracket boundary
  - calculate_profit with zero profit, positive profit, negative profit
  - calculate_max_buy at various margins
  - parse_coin_value with all formats including edge cases


### `bot_service/bot/rate_limiter.py`

`RateLimiter` class, constructor takes `(cfg: RateLimiterConfig, db: Database)`.

`ActionType` enum: SEARCH, BUY, LIST, BID

Methods:
- `check_and_wait(action: ActionType) -> None`
  If under limit: record action, return immediately.
  If at hourly limit: log WARNING, sleep until hour resets, then return.
  If at daily limit: log WARNING, sleep until midnight UTC, then return.
- `cooldown_after_buy() -> None` — sleep cfg.cooldown_after_buy_sec seconds
- `daily_limit_reached() -> bool`
- `sleep_until_reset() -> None`

All limit state is persisted to `rate_state` table via `db`.
On init: load existing state from DB, reset stale hour/day windows.

Write tests in `bot_service/tests/test_rate_limiter.py`.


### `bot_service/bot/calendar_engine.py`

`MarketPhase` enum with all phases from `.cursorrules` section 8.

`CalendarEngine` class, constructor takes `(cfg: Config)`.

Methods:
- `get_current_phase() -> MarketPhase`
  Implements the full UTC time + day-of-week logic from `.cursorrules`.
  Checks active promos from cfg.promos list second.
  Falls back to STANDARD.
- `get_recommended_strategy(phase: MarketPhase) -> str`
  Returns strategy name string from the authoritative mapping.
- `is_promo_active() -> bool`
- `get_phase_description(phase: MarketPhase) -> str`
  Human-readable explanation of what the bot should do in this phase.
- `time_until_next_phase() -> timedelta`

All times handled in UTC. Use `datetime.now(timezone.utc)` always.

Write tests in `bot_service/tests/test_calendar_engine.py` — test each phase
boundary (e.g., Thursday 06:59 UTC → STANDARD, 07:00 → RIVALS_REWARDS).


---

## PHASE 4 — ANDROID AUTOMATION LAYER

### `bot_service/bot/emulator.py`

`Emulator` class, constructor takes `(cfg: EmulatorConfig)`.

Methods:
- `start() -> bool` — launch AVD subprocess, return False if already running
- `_wait_for_boot() -> bool` — poll `adb shell getprop sys.boot_completed`
  every 5 seconds until "1" or timeout. Log elapsed time every 30s.
- `_unlock_screen() -> None` — adb shell input swipe to dismiss lock
- `install_apk(path: str) -> bool` — `adb install -r -d {path}`, check "Success"
- `is_running() -> bool` — check `adb devices` output for "emulator"
- `is_app_installed(package: str) -> bool`
- `launch_app(package: str) -> bool`
- `stop() -> None` — `adb emu kill` then kill process group
- `_adb(*args: str) -> str` — internal wrapper, timeout=30s, returns stdout

All subprocess calls: stdout/stderr to DEVNULL unless capturing output.
Emulator process started with `preexec_fn=os.setsid` for clean kill.
GPU mode: `swiftshader_indirect` (works on all servers, no GPU required).


### `bot_service/bot/device.py`

`Device` class, constructor takes `(cfg: AntiDetectConfig)`.

`connect() -> bool` — `u2.connect()`, log device info, return False on failure.

ALL UI interaction methods must apply jitter and call `_human_delay()` first:

- `tap(x: int, y: int) -> None`
- `tap_element(selector: dict) -> bool`
  selector dict: `{"text": "..."} | {"resourceId": "..."} | {"description": "..."}`
  Returns False if element not found within 5 seconds.
- `tap_text(text: str) -> bool`
- `type_text(text: str, clear_first: bool = True) -> None`
  Type char-by-char with 50–150ms random delay per char.
- `swipe_up(steps: int = None) -> None` — steps from cfg random range
- `swipe_down(steps: int = None) -> None`
- `wait_for_text(text: str, timeout: int = 10) -> bool`
- `wait_for_element(selector: dict, timeout: int = 10) -> bool`
- `screenshot() -> bytes` — returns PNG bytes
- `get_screen_text() -> str` — OCR the entire current screen
- `extract_text_from_region(x1: int, y1: int, x2: int, y2: int) -> str`
  Crops screenshot to region, runs pytesseract, returns raw string.
- `press_back() -> None`
- `is_text_on_screen(text: str) -> bool`

`_human_delay() -> None` — random.uniform(cfg.action_delay_min, cfg.action_delay_max)
`_jitter(coord: int) -> int` — coord + random.randint(-cfg.tap_jitter_px, cfg.tap_jitter_px)

OCR configuration: `pytesseract.image_to_string` with config
`--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789KM,.`
for price regions (digits and suffix only).


### `bot_service/bot/navigator.py`

`Navigator` class, constructor takes `(device: Device, db: Database, cfg: Config)`.

This module knows the FC Companion app's UI flow. Every method represents one
named screen transition or user action within the app. Add a comment above each
method with the exact screen name it navigates to.

Methods:

```
# ── Main Navigation ─────────────────────────────────────────────────────────

go_to_transfer_market() -> bool
  Tap: bottom nav → Transfers → Search Market
  Verify arrival: wait_for_text("Search Filters") or similar landmark

go_to_transfer_list() -> bool
  Tap: bottom nav → Transfers → Transfer List

go_to_club() -> bool
  Tap: bottom nav → Club

# ── Search & Filter ─────────────────────────────────────────────────────────

search_player(name: str, quality: str, position: str, max_buy_now: int) -> bool
  Fills all search filters, taps Search.
  max_buy_now sets the Max Buy Now price field.
  Returns False if search fails to execute.

clear_search_filters() -> None

set_price_range(min_bn: Optional[int], max_bn: Optional[int]) -> None

# ── Results Scraping ────────────────────────────────────────────────────────

get_listings(max_results: int = 10) -> List[Listing]
  Scrapes the current results page.
  For each visible card: OCR the Buy Now price, bid price, time remaining.
  Scroll and repeat until max_results reached or no more listings.
  Returns list of Listing dataclass instances.

# ── Purchase Actions ────────────────────────────────────────────────────────

buy_now(listing: Listing) -> bool
  Tap the listing → tap Buy Now → tap Confirm.
  Wait for success confirmation text.
  Returns False if confirmation not seen within 10 seconds.

place_bid(listing: Listing, bid_amount: int) -> bool
  Tap the listing → tap Bid field → type bid_amount → tap Confirm.
  Returns False if bid rejected (bid changed popup, etc).

# ── Listing Actions ─────────────────────────────────────────────────────────

list_item(player_name: str, start_price: int, buy_now_price: int,
          duration_hours: int) -> bool
  Navigate to club → find player → tap List on Transfer Market →
  Set start price, BN price, duration → confirm.

relist_expired_item(player_name: str) -> bool
  Find expired listing in Transfer List → tap Relist at same price.

# ── Compare Price ───────────────────────────────────────────────────────────

get_compare_price(player_name: str) -> Optional[int]
  Open player card → tap Compare Price →
  OCR the lowest BN shown → return as int.
  Returns None if Compare Price unavailable.
```

IMPORTANT: Every method that touches the app must:
1. Call `rate_limiter.check_and_wait()` where appropriate (search/buy/list)
2. Return False (not raise) on failure
3. Log the action at DEBUG level with element names being targeted


### `bot_service/bot/market.py`

`MarketScanner` class, constructor takes
`(navigator: Navigator, db: Database, cfg: Config)`.

Methods:
- `scan_for_player(player_cfg: dict, strategy_name: str) -> List[Listing]`
  Calls navigator.search_player(), then navigator.get_listings().
  Enriches each Listing with market_price from DB (for profit calculation).
- `find_underpriced(listings: List[Listing], max_buy: int) -> List[Listing]`
  Filters to listings where BN price <= max_buy.
  Sorts by profit margin descending.
- `find_chem_style_deals(listings: List[Listing]) -> List[Listing]`
  Filters listings where chem style is applied but price is at unstyled level.
  Uses DB market_prices.price_shadow / price_hunter for comparison.


### `bot_service/bot/auth.py`

`AuthManager` class, constructor takes `(device: Device, cfg: Config)`.

Methods:
- `login() -> bool`
  Detects if on login screen (wait_for_text "Sign In" or "Email").
  Types email, taps Next, types password, taps Sign In.
  Handles 2FA prompt: wait up to cfg.app.login_timeout for manual 2FA entry,
  then check if login succeeded.
  Returns True when Transfer Market is accessible.
- `is_logged_in() -> bool` — check for logged-in landmark text
- `logout() -> None`


### `bot_service/bot/watchdog.py`

`Watchdog` class, constructor takes
`(device: Device, auth: AuthManager, cfg: Config)`.

`FailureType` enum: BID_LOCK, SESSION_EXPIRED, APP_CRASH, NETWORK_ERROR,
TRANSFER_FULL, UNKNOWN.

Methods:
- `check_and_recover() -> bool`
  Runs all detection checks. Returns True if state is healthy or recovered.
  Returns False only after 3 consecutive unrecoverable failures.
- `detect_failure() -> Optional[FailureType]`
- `recover(failure: FailureType) -> bool`
- `_recover_bid_lock() -> bool`
- `_recover_session_expired() -> bool`
- `_recover_app_crash() -> bool`
- `_recover_network_error() -> bool`

Consecutive failure counter resets on any successful cycle.
After 3 failures: logger.critical() and return False.


### `bot_service/bot/portfolio.py`

`Portfolio` class, constructor takes `(db: Database)`.

Methods:
- `record_purchase(player_name: str, buy_price: int, strategy: str) -> None`
- `record_sale(player_name: str, sell_price: int) -> None`
- `get_held_items() -> List[PortfolioItem]`
- `print_summary() -> None` — logs full P&L table at INFO level
- `get_total_profit() -> int`
- `get_roi_pct() -> float`


---

## PHASE 5 — STRATEGIES

### `bot_service/bot/strategies/base.py`

```python
from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    def __init__(self, device, navigator, scanner, portfolio,
                 rate_limiter, db, cfg, dry_run=False):
        ...

    @abstractmethod
    def run_cycle(self) -> CycleResult:
        """Execute one full scan-and-trade cycle."""

    def should_buy(self, listing: Listing, player_cfg: dict) -> bool:
        """Universal buy gate: profit check + rate limit check + budget check."""
        profit = calculate_profit(listing.buy_now_price, player_cfg['sell_target'])
        if profit.roi_pct < player_cfg.get('min_profit_pct', cfg.min_profit_pct):
            return False
        if listing.buy_now_price > player_cfg['buy_max']:
            return False
        if rate_limiter.daily_limit_reached():
            return False
        return True

    def execute_buy(self, listing: Listing) -> bool:
        """Wraps navigator.buy_now() with dry_run gate and full logging."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would buy {listing.player_name} at {listing.buy_now_price}")
            return True
        success = self.navigator.buy_now(listing)
        if success:
            self.rate_limiter.cooldown_after_buy()
            self.portfolio.record_purchase(...)
            self.db.insert_trade(...)
        return success
```


### `bot_service/bot/strategies/sniper.py`

`Sniper(BaseStrategy)` — implement `run_cycle()`:

```
For each player in cfg.sniper.players:
  1. Get market price from DB (from intel sidecar)
  2. Calculate max_buy using utils.calculate_max_buy()
  3. rate_limiter.check_and_wait(ActionType.SEARCH)
  4. navigator.search_player(name, quality, position, max_bn=max_buy)
  5. listings = scanner.find_underpriced(all_listings, max_buy)
  6. For first listing in listings (best deal first):
       if should_buy(listing, player_cfg):
           execute_buy(listing)
           list_at = db.get_market_price(name) - get_next_bid(0)  # undercut by 1 step
           navigator.list_item(name, start=list_at*0.9, buy_now=list_at, duration=1)
           break  # one buy per player per cycle
  7. navigator.clear_search_filters()
Return CycleResult(buys=n, skipped=m, errors=e)
```


### `bot_service/bot/strategies/mass_bidder.py`

`MassBidder(BaseStrategy)` — implement `run_cycle()`:

```
BID PHASE (run every cycle):
  For each player in cfg.mass_bidder.players:
    market_price = db.get_market_price(player)
    max_bid = (market_price * 0.95) - cfg.min_profit_coins
    Round max_bid DOWN to nearest valid bid increment
    rate_limiter.check_and_wait(ActionType.SEARCH)
    navigator.search_player(player, ...)
    listings = navigator.get_listings(max_results=20)
    For each listing where listing.current_bid < max_bid:
      if not dry_run: navigator.place_bid(listing, max_bid)
      bid_count += 1
      if bid_count >= 50: break  (respect transfer target limit)

CHECK WON ITEMS PHASE (run every 30 minutes only):
  if time_since_last_check < 1800: return
  navigator.go_to_transfer_list()
  won_items = get_won_items()  (OCR transfer list for "Won" status)
  For each won item:
    list_at = db.get_market_price(item.player_name)
    navigator.list_item(item.player_name, start=list_at*0.9, buy_now=list_at, duration=1)
    portfolio.record_purchase(...)
```


### `bot_service/bot/strategies/chem_style.py`

`ChemStyleTrader(BaseStrategy)` — implement `run_cycle()`:

```
TARGET CHEM STYLES: Shadow (defenders), Hunter (attackers)

For each player in cfg.chem_style.players:
  price_no_chem = db.get_market_price(player.name).price
  price_with_shadow = db.get_market_price(player.name).price_shadow
  price_with_hunter = db.get_market_price(player.name).price_hunter
  
  # Bot looks for cards already styled but priced as if unstyled
  # This happens when sellers don't know the chem style adds value
  target_chem = Shadow if player.position in DEFENDER_POSITIONS else Hunter
  styled_market_price = price_with_shadow or price_with_hunter
  
  # Max we'll pay: price_no_chem + buffer (the style is "free bonus")
  max_buy = min(player.buy_max, price_no_chem + cfg.chem_style.max_premium_coins)
  
  rate_limiter.check_and_wait(ActionType.SEARCH)
  # Search with Chemistry Style filter set to the target chem style
  navigator.search_player(player.name, chem_style=target_chem, max_bn=max_buy)
  listings = navigator.get_listings()
  
  For best listing:
    profit = calculate_profit(listing.buy_now_price, styled_market_price)
    if profit.roi_pct >= cfg.chem_style.min_profit_pct:
      execute_buy(listing)
      navigator.list_item(player.name, buy_now=styled_market_price, duration=1)
```


---

## PHASE 6 — STRATEGY SELECTOR & MAIN LOOP

### `bot_service/bot/strategy_selector.py`

```python
class StrategySelector:
    def get_strategy(self, phase: MarketPhase, cfg: Config,
                     ...) -> BaseStrategy:
        """
        Returns the appropriate instantiated strategy for the given phase.
        Uses the authoritative mapping from .cursorrules section 8.
        Logs phase name and reason for selection at INFO level.
        """
```

### `bot_service/main.py`

Orchestrator — no business logic here, just wiring:

```
1. parse_args()  → --strategy override, --dry-run, --config path
2. load_config() → validate
3. setup_logging()
4. check APK exists → exit(1) with clear message if not
5. db = Database(cfg); db.init()
6. rate_limiter = RateLimiter(cfg, db)
7. emulator = Emulator(cfg); emulator.start() → exit(1) if fails
8. device = Device(cfg); device.connect() → exit(1) if fails
9. emulator.install_apk() → exit(1) if fails
10. emulator.launch_app()
11. auth = AuthManager(device, cfg); auth.login() → exit(1) if fails
12. navigator = Navigator(device, db, cfg)
13. portfolio = Portfolio(db)
14. scanner = MarketScanner(navigator, db, cfg)
15. watchdog = Watchdog(device, auth, cfg)
16. calendar = CalendarEngine(cfg)
17. selector = StrategySelector()

MAIN LOOP (while True):
  touch /app/data/heartbeat
  if rate_limiter.daily_limit_reached(): sleep_until_reset(); continue
  watchdog.check_and_recover() → if False: break
  phase = calendar.get_current_phase()
  strategy_name = cfg.active_strategy if not auto else selector.get_strategy(phase)
  strategy = instantiate(strategy_name, all deps)
  result = strategy.run_cycle()
  log cycle result
  handle long pause every N actions
  sleep(interval + jitter)

finally: portfolio.print_summary(); emulator.stop()
```


---

## PHASE 7 — INTEL SIDECAR SERVICE

### `intel_service/scrapers/futwiz.py`

`FutwizScraper` class.

Target URL: `https://www.futwiz.com/en/fc26/players`

Use `requests.Session` with headers:
```python
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
```

`scrape_player_price(player_name: str, platform: str) -> Optional[MarketPrice]`
  - GET the search URL with player name query param
  - Parse with BeautifulSoup('html.parser')
  - Extract: player name, rating, position, current price
  - 2–5 second random delay before each request (class-level, not per-call)
  - Return None on any exception — log WARNING with exception message

`scrape_trending_players(platform: str) -> List[MarketPrice]`
  - Scrapes the trending/popular section of FUTWIZ
  - Returns up to 20 player prices

`scrape_chem_style_prices(player_name: str, platform: str) -> Optional[MarketPrice]`
  - Finds the same player with Shadow and Hunter applied
  - Returns MarketPrice with price_shadow and price_hunter populated


### `intel_service/scrapers/futbin_graph.py`

`FutbinGraphScraper` class.

`fetch_price_history(player_id: str, platform: str) -> List[dict]`
  GET: `https://www.futbin.com/26/playerGraph?type=daily_graph&player={player_id}`
  Returns raw JSON list: `[{date, ps_price, xbox_price, pc_price}, ...]`
  Returns [] on any failure.

`get_latest_price(player_id: str, platform: str) -> Optional[int]`
  Calls fetch_price_history, returns the most recent price for the platform.


### `intel_service/scrapers/futgg_sbc.py`

`FutGGSbcScraper` class.

`get_active_sbcs() -> List[SbcSignal]`
  GET: `https://fut.gg/sbc/`
  Parse with BeautifulSoup.
  Extract: SBC name, rating requirement, expiry date.
  Returns list of SbcSignal dataclass instances.
  Returns [] on failure.

`has_new_sbcs(last_check: datetime) -> bool`
  Returns True if any SBC was detected after last_check.


### `intel_service/scrapers/futdb.py`

`FutdbScraper` class (fallback source).

`get_player_price(player_name: str, platform: str) -> Optional[int]`
  Uses FutDB free API if available.
  Returns None on rate limit or failure.


### `intel_service/scrapers/intel_writer.py`

`IntelWriter` class, constructor takes `(db: Database)`.

`write_prices(prices: List[MarketPrice]) -> None`
  Batch inserts all prices. Calls `db.prune_old_prices()` after insert.

`write_sbc_signals(signals: List[SbcSignal]) -> None`
  Insert new signals, skip duplicates (by sbc_name + detected_at).

`get_player_list_from_bot_config() -> List[dict]`
  Reads the bot_service config.yaml to know WHICH players to scrape.
  This keeps the intel sidecar in sync with the bot's target list.


### `intel_service/main.py`

```python
from apscheduler.schedulers.blocking import BlockingScheduler

scheduler = BlockingScheduler(timezone="UTC")

# Register jobs
scheduler.add_job(run_futwiz,      'interval', minutes=15,  id='futwiz')
scheduler.add_job(run_futbin,      'interval', minutes=30,  id='futbin')
scheduler.add_job(run_futgg_sbc,   'interval', minutes=10,  id='futgg_sbc')
scheduler.add_job(run_futdb,       'interval', minutes=60,  id='futdb')
scheduler.add_job(update_heartbeat,'interval', minutes=1,   id='heartbeat')

# Run all scrapers once on startup before bot begins trading
run_all_scrapers()

scheduler.start()
```

Each `run_*` function: try/except everything, log WARNING on failure, never raise.


---

## PHASE 8 — DOCKERFILES

### `bot_service/Dockerfile`
```dockerfile
FROM budtmo/docker-android:emulator_13.0
USER root
RUN apt-get update -qq && apt-get install -y -qq \
    python3.11 python3.11-pip \
    tesseract-ocr tesseract-ocr-eng \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    sqlite3 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN python3.11 -m pip install --no-cache-dir -r requirements.txt
COPY . /app/
RUN mkdir -p /app/logs /app/apk /app/data
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["python3.11", "main.py"]
```

### `intel_service/Dockerfile`
```dockerfile
FROM python:3.11-slim
RUN apt-get update -qq && apt-get install -y -qq sqlite3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
RUN mkdir -p /app/data
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
CMD ["python3", "main.py"]
```


---

## PHASE 9 — DOCUMENTATION

### `README.md`
Full project README covering:
1. Prerequisites (Linux, KVM, Docker, Docker Compose, the APK)
2. Quick start (5 steps: clone, drop APK, fill .env, docker-compose up)
3. Configuration reference (every config.yaml field explained)
4. Strategy descriptions with profit mechanics
5. Architecture diagram (ASCII)
6. Troubleshooting (KVM not available, APK install failed, login issues)
7. Class teaching notes — what each module teaches

### `docs/SETUP.md`
Step-by-step setup including:
- How to verify KVM: `kvm-ok`
- How to add user to kvm group
- Where to get the FC Companion APK
- How to run in dry-run mode first
- How to tail logs: `docker-compose logs -f fc-trader`

### `docs/STRATEGIES.md`
Deep explanation of each strategy:
- How it works, when it runs (calendar phase)
- Profit formula with worked examples
- Config parameters explained
- Anti-detection considerations

### `docs/CALENDAR.md`
Full weekly market calendar table, all phases explained, seasonal events list.


---

## BUILD SEQUENCE — FOLLOW THIS ORDER EXACTLY

Do NOT skip phases or build out of order. Each phase depends on the previous.

1. Phase 1 — Scaffold (all dirs, init files, docker-compose, .env.example, .gitignore)
2. Phase 2 — database.py + models.py (foundation everything else reads/writes)
3. Phase 3 — config_loader.py, utils.py, rate_limiter.py, calendar_engine.py
4. Phase 4 — emulator.py, device.py, navigator.py, market.py, auth.py, watchdog.py, portfolio.py
5. Phase 5 — base.py, sniper.py, mass_bidder.py, chem_style.py
6. Phase 6 — strategy_selector.py, main.py (bot_service)
7. Phase 7 — all intel_service scrapers, intel_writer.py, main.py (intel_service)
8. Phase 8 — both Dockerfiles, requirements.txt files
9. Phase 9 — README.md, docs/

After each phase: verify no import errors by checking all imports resolve.
After Phase 3: run the unit tests before proceeding.
After Phase 9: do a final pass — check every file in the repo has a docstring,
every function has type hints, no bare `except`, no hardcoded credentials,
no SQL outside database.py, no `print()` statements.


---

## FINAL CHECKLIST (agent must verify before declaring done)

- [ ] Every Python file has a module-level docstring
- [ ] Every class has a class-level docstring
- [ ] Every public method has a docstring
- [ ] Every function has complete type hints (params + return)
- [ ] No `print()` anywhere — only loguru logger
- [ ] No SQL strings outside database.py
- [ ] No bare `except:` or `except Exception: pass`
- [ ] No hardcoded credentials, prices, or magic numbers
- [ ] No `time.sleep()` in UI automation code (only in _human_delay and watchdog)
- [ ] utils.get_next_bid() used for ALL bid calculations
- [ ] EA 5% tax applied in ALL profit calculations
- [ ] rate_limiter.check_and_wait() called before every search, buy, and list
- [ ] dry_run flag respected in every execute_buy() and execute_list() call
- [ ] Both Dockerfiles build cleanly (no missing packages)
- [ ] docker-compose.yml has shared-data volume on both services
- [ ] .gitignore excludes .env, config.yaml, *.db, logs/, apk/
- [ ] Unit tests exist for utils.py, rate_limiter.py, calendar_engine.py
- [ ] README.md has complete quick-start section
