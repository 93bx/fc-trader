# FC Trader

Fully automated trading bot for the **EA Sports FC 26 Ultimate Team Web App** (primary) and FC 26 Companion Android app (failover). Runs inside Docker, executes three trading strategies (Sniper, Mass Bidder, Chemistry Style Trader) via Playwright browser automation with KSA-Riyadh anti-detection, and is driven by a real-time market calendar and intel sidecar that scrapes FUTWIZ, FUTBIN, and FUT.GG.

**Default mode: Web App (Playwright).** The Android emulator is available as failover only. See [docs/WEB_APP.md](docs/WEB_APP.md) and [docs/ANTI_DETECTION.md](docs/ANTI_DETECTION.md).

---

## Prerequisites

- **Docker** and **Docker Compose** (v2+).
- **EA Account** with Transfer Market already unlocked (Graduated Access — returning FC 25 player). See [docs/WEB_APP.md](docs/WEB_APP.md#1-prerequisites).
- **For Android failover only:** Linux or WSL2 with KVM. See [docs/SETUP.md](docs/SETUP.md).
- **Residential SA proxy** (optional but recommended for production). See [docs/ANTI_DETECTION.md](docs/ANTI_DETECTION.md).

---

## Quick start (Web mode — default)

1. **Clone the repo**
   ```bash
   git clone <repo-url>
   cd fc-trader
   ```

2. **Configure environment**  
   Copy `.env.example` to `.env` and fill in your EA credentials:
   ```bash
   cp .env.example .env
   # Edit .env: set FC_EMAIL and FC_PASSWORD
   # COMPOSE_PROFILES=web is already the default
   ```

3. **Configure players** (optional)  
   Edit `web_service/config/web_config.yaml` and add player names under `sniper.players`, `mass_bidder.players`, or `chem_style.players`.

4. **Run**
   ```bash
   docker compose up -d
   ```
   Web trader starts automatically (profile `web` is the default).  
   For dry-run testing: `docker compose run --rm web-trader --dry-run`

5. **First login / 2FA**  
   On first run, if 2FA is triggered you have `ea.login_timeout` seconds (default 180s) to complete it. Check your email or authenticator app and approve. Subsequent runs reuse saved cookies.

### Android failover mode

```bash
FC_EXECUTION_MODE=android COMPOSE_PROFILES=android docker compose up -d fc-trader intel
```

Requires KVM. Place the FC Companion APK in `apk/`.

---

## Configuration reference

All tuneable parameters live in `bot_service/config/config.yaml`. Environment variables override YAML for sensitive or override-only values.

| Section / key       | Description |
|---------------------|-------------|
| `database.path`     | SQLite DB path; default `/app/data/fc_trader.db` (shared volume). |
| `rate_limiter`      | `max_searches_per_hour`, `max_buys_per_hour`, `max_lists_per_hour`, `cooldown_after_buy_sec`, `daily_trade_limit`. |
| `emulator`          | `avd_name`, `avd_port`, `boot_timeout`, `headless`. |
| `anti_detect`       | `action_delay_min`, `action_delay_max`, `tap_jitter_px` for UI jitter and delays. |
| `sniper.players`     | List of player configs (name, quality, position, etc.). `sniper.min_profit_pct` for minimum ROI. |
| `mass_bidder.players`| Same; `mass_bidder.min_profit_coins` for minimum profit per card. |
| `chem_style.players`| Same; `chem_style.min_profit_pct`, `chem_style.max_premium_coins`. |
| `app.login_timeout` | Seconds to wait for 2FA / login. |
| `promos`            | List of promo windows (from config); when active, strategy is forced to Mass Bidder + Sniper. |
| `active_strategy`   | `auto` (calendar-driven), or `sniper`, `mass_bidder`, `chem_style`, `peak_sell`. |
| `platform`          | `ps`, `xbox`, or `pc` for price lookups. |
| `email` / `password`| Overridden by `FC_EMAIL`, `FC_PASSWORD`; do not commit real values. |
| `log_level`         | `DEBUG`, `INFO`, `WARNING`, `ERROR`; overridable by `FC_LOG_LEVEL`. |

**Env overrides:** `FC_EMAIL`, `FC_PASSWORD`, `FC_STRATEGY`, `FC_LOG_LEVEL`, `FC_PLATFORM`, `FC_CONFIG`, `FC_APK_PATH`, `FC_PACKAGE`, `FC_DB_PATH` (intel).

---

## Strategies

- **Sniper** — Buy Now only. Max buy price is derived from FUTWIZ market price and `min_profit_pct` (after EA 5% tax). Lists at market price minus one bid increment. Runs in WEEKEND_BUY and STANDARD (and when auto-selected).
- **Mass Bidder** — Places bids below a computed max (sell price × 0.95 minus desired profit). Never bids above 85% of BIN. Checks won items periodically and relists at FUTWIZ BIN. Runs in RIVALS_REWARDS, OVERNIGHT, SQUAD_BATTLES (and promo).
- **Chemistry Style Trader** — Buys cards that already have Shadow or Hunter applied but are priced near unstyled level; lists at FUTWIZ styled price. Runs in PROMO_DROP and MIDWEEK_DIP (alternating with Sniper when auto).
- **Peak Sell** — Sell/relist only; no buying. Used during PEAK_SELL phase (Thursday 18:00 – Friday 16:00 UTC).

Profit mechanics: EA takes 5% on sales (`net = sell_price * 0.95`). All strategies use `utils.calculate_profit()` and bid increments from `utils.get_next_bid()` / `get_prev_bid()`.

See [docs/STRATEGIES.md](docs/STRATEGIES.md) for detailed formulas and examples.

---

## Architecture

```
+------------------+     shared-data (volume)      +------------------+
|   fc-trader      |     /app/data                |     intel        |
|   (bot + AVD)    |<---------------------------->|   (scrapers)     |
|                  |   fc_trader.db               |                  |
|  writes:         |                             |  writes:         |
|   trades         |   market_prices (intel)      |   market_prices  |
|   rate_state     |   sbc_signals (intel)       |   sbc_signals    |
|   portfolio      |   read by bot strategies    |                  |
|  reads:          |                             |  schedule:       |
|   market_prices  |                             |   FUTWIZ 15m     |
|   (from intel)   |                             |   FUTBIN 30m     |
|                  |                             |   FUT.GG SBC 10m |
|  main loop:      |                             |   FutDB 60m      |
|   calendar →     |                             |                  |
|   strategy →     |                             |                  |
|   run_cycle()    |                             |                  |
+------------------+                             +------------------+
```

Both services use the same SQLite file on `shared-data`. The bot never writes to `market_prices` or `sbc_signals`; the intel service never writes to `trades`, `rate_state`, or `portfolio`.

---

## Troubleshooting

- **KVM not available** — Run `kvm-ok`; if it fails, enable virtualization in BIOS and install `cpu-checker`. Add your user to the `kvm` group and re-login. See [docs/SETUP.md](docs/SETUP.md).
- **APK install failed** — Ensure the APK path is correct (`apk/` directory or `FC_APK_PATH`), the file is readable inside the container, and the APK is compatible with the emulator API level.
- **Login / 2FA** — Use an account with 2FA; complete 2FA within `app.login_timeout` seconds when the bot launches the app. For headless runs, consider a mule account with 2FA disabled if acceptable for your risk.
- **Logs** — Bot: `docker compose logs -f fc-trader`. Intel: `docker compose logs -f intel`.

---

## Teaching notes (module roles)

| Module           | Role |
|------------------|------|
| `emulator.py`    | AVD process lifecycle (start, boot wait, install APK, launch app, stop). |
| `device.py`      | Raw UI (tap, swipe, OCR, screenshot) with jitter and human delays. |
| `navigator.py`   | FC app screen flows (transfer market, search, buy now, place bid, list, relist). |
| `market.py`      | Search execution and listing scraping; filters (underpriced, chem style deals). |
| `strategies/*`   | Buy/sell decision logic; call navigator and DB only. |
| `calendar_engine.py` | UTC market phases and strategy mapping; no trading logic. |
| `database.py`    | All SQLite queries; single place for schema and SQL. |
| `watchdog.py`    | Detects and recovers from BID_LOCK, SESSION_EXPIRED, APP_CRASH, NETWORK_ERROR, TRANSFER_FULL. |
| `rate_limiter.py`| Hourly/daily limits and cooldown; state in DB. |
| Intel scrapers   | HTTP fetch only; return data to `intel_writer`, which writes to DB. |
