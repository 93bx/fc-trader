# FC Trader — Web App Service

## 1. Prerequisites

- **EA Account Requirements (Graduated Access)**
  - Must be a returning FC 25 player with a club created before August 1, 2025 in good standing.
  - Transfer Market must already be unlocked. New or non-eligible accounts cannot access the Transfer Market immediately.
  - The bot will NOT attempt to unlock the Transfer Market on a fresh account. Only launch with an account where Transfer Market is already available.

- **Mutual Exclusion — Console/PC**
  EA enforces strict mutual exclusion: the web app and a console/PC Ultimate Team session cannot run simultaneously on the same account. Before starting the bot, ensure no active UT session exists on any console or PC logged into that account.

- **Docker with at least 2 GB RAM** allocated to the `web-trader` container.

---

## 2. Default Mode — Web First

From FC Trader v2 onwards, the web service is the **primary and default** trading interface. The Android emulator is available as failover only.

Set `COMPOSE_PROFILES=web` in your `.env` (already the default in `.env.example`) and run:

```bash
docker compose up -d
```

Only the `web-trader`, `intel`, and associated services start. The Android emulator (`fc-trader`) remains dormant unless you set `COMPOSE_PROFILES=android` or `COMPOSE_PROFILES=web,android`.

---

## 3. KSA Proxy Setup

For production use, a **residential proxy** in Saudi Arabia is strongly recommended.

- Datacenter IPs are instantly flagged by EA.
- Recommended cities: Riyadh, Jeddah, Dammam.
- Recommended providers: Bright Data, Oxylabs, Smartproxy (SA residential pool).

Configure in `.env`:

```
PROXY_HOST_1=<your-sa-residential-host>
PROXY_PORT_1=<port>
PROXY_USER_1=<username>
PROXY_PASS_1=<password>
```

And in `web_service/config/web_config.yaml`, set:

```yaml
anti_detect:
  proxy:
    enabled: true
```

---

## 4. 2FA First-Login Flow

On first run (no stored cookies), the bot will:
1. Navigate to `https://www.ea.com/ea-sports-fc/ultimate-team/web-app/`
2. Click Sign In and fill credentials.
3. If 2FA is triggered, it logs `"2FA required — waiting for code input"` and polls for the redirect.
4. **You must complete 2FA manually** within `ea.login_timeout` seconds (default 180s). Enter the code in the EA app or email before the timeout.
5. After successful login, session cookies are saved to `/app/data/browser_profile` and reused on subsequent runs without needing to log in again.

---

## 5. Session Rotation

The browser session rotates every `session_max_duration` seconds (default 90 minutes). On rotation:
1. Browser closes, proxy rotates to the next pool entry (if enabled).
2. A 15–30 second random pause.
3. Browser relaunches with full stealth re-injection.

This mimics natural human browser restarts and prevents EA's session analysis from detecting a permanently running session.

---

## 6. Switching to Android Mode

To fall back to the Android emulator:

```bash
FC_EXECUTION_MODE=android docker compose --profile android up -d
```

Or set `FC_EXECUTION_MODE=android` in `.env`.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Login button not found` | EA changed SPA selectors | Update `_SIGN_IN_SELECTORS` in `web_auth.py` |
| `Cached session expired` on every start | Cookies not persisting | Check `/app/data/browser_profile` mount in `docker-compose.yml` |
| `Proxy validation failed` | Proxy is down or not SA-based | Rotate to next proxy endpoint |
| `Console session conflict detected` | Console UT is active | Log out of UT on all consoles/PC first |
| `Soft ban detected` | Too many rapid searches | Increase `inter_search_pause_min` in config; bot auto-pauses 2h |
| Headless Chrome crashes | Missing system libraries | Ensure `playwright install-deps chromium` ran in Docker build |
