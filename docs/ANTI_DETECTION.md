# FC Trader — Anti-Detection Guide

## 1. Threat Model

EA's web detection is **purely behavioral and JS-fingerprint based** on the Angular SPA. There is no Javelin/anti-cheat on the web app. Detection vectors:

| Vector | Risk | Mitigation in FC Trader |
|---|---|---|
| `navigator.webdriver = true` | Instant flag | Patched to `undefined` via `_patch_webdriver` |
| Wrong/missing `window.chrome.runtime` | Flag | Added via `_patch_chrome_runtime` |
| Impossible geolocation for claimed locale | Flag | KSA Riyadh coordinates set in browser context |
| Wrong timezone for locale | Flag | UTC+3 patched via `_patch_timezone` |
| Inhuman search timing | Ban | `inter_search_pause` min 9s; random spread 9–28s |
| 24/7 continuous activity | Soft ban | KSA active windows + daily hour cap |
| No mouse movement | Flag | Synthetic `mousemove` events via `_patch_mouse_movement` |
| Uniform filter patterns | Flag | Random search parameter variation per player config |
| VPN/datacenter IP | Flag | Residential SA proxy required |
| Canvas/audio fingerprint uniformity | Flag | Per-session noise seed applied |

---

## 2. KSA Riyadh Profile Rationale

The KSA profile was chosen because:
- **Dominant OS**: Windows 11 (NT 10.0) — over 70% market share in Saudi Arabia.
- **Dominant browser**: Google Chrome — consistent with user_agent string.
- **Dominant carrier**: STC (Saudi Telecom, MCC 42001) — largest mobile operator.
- **Dominant device brand (Android)**: Samsung Galaxy (A-series most common).
- **Time zone**: AST (UTC+3) — no daylight savings, consistent year-round.
- **Language**: `ar-SA` primary with English fallback — mirrors a bilingual Saudi player.

---

## 3. JS Fingerprint Patches

All patches are injected via Playwright `page.add_init_script()` — they run before any page script.

| Patch | What it defeats |
|---|---|
| `_patch_webdriver` | Sets `navigator.webdriver` to `undefined` (not `false` — real Chrome has `undefined`) |
| `_patch_navigator` | Spoofs platform, language, deviceMemory, hardwareConcurrency, vendor |
| `_patch_screen` | Spoofs screen dimensions (1920×1080), pixel ratio 1.0, color depth 24 |
| `_patch_timezone` | Forces `getTimezoneOffset()` → -180 (UTC+3), `resolvedOptions().timeZone` → 'Asia/Riyadh' |
| `_patch_webgl` | Spoofs WebGL1+2 RENDERER (Intel UHD 630 ANGLE) and VENDOR strings |
| `_patch_canvas` | Adds fixed per-session ±2px noise to canvas toDataURL output |
| `_patch_audio` | Adds ±1e-7 noise to AudioBuffer channel data |
| `_patch_chrome_runtime` | Installs `window.chrome.runtime` object EA's SPA checks for |
| `_patch_plugins` | Returns 3 PDF Viewer plugins matching real Chrome on Windows |
| `_patch_permissions` | Returns `granted` for notifications permission query |
| `_patch_mouse_movement` | Dispatches synthetic `mousemove` events every 15–45 seconds |

---

## 4. KSA Active Windows (UTC / AST)

| UTC Window | AST Equivalent | Activity |
|---|---|---|
| 05:00–08:30 | 08:00–11:30 | Morning session |
| 10:00–14:30 | 13:00–17:30 | Afternoon session |
| 17:00–21:30 | 20:00–00:30 | Evening/night peak (highest FUT activity) |
| 02:00–05:00 | 05:00–08:00 | Fajr/sleep — bot fully offline |
| 08:30–10:00 | 11:30–13:00 | Midday gap |
| 14:30–17:00 | 17:30–20:00 | Asr prayer + rest |
| 21:30–02:00 | 00:30–05:00 | Late night/sleep |

---

## 5. EA Ban Taxonomy

| Type | Scope | Duration | Primary Triggers |
|---|---|---|---|
| **Soft ban** | Transfer Market locked only | 12–72 hours | Rapid searches, suspicious filter patterns, unusual timing |
| **Hard ban** | Account suspended | Permanent | Coin distribution, bot farming, trading exploit |
| **TM block** | Transfer Market web/companion | Variable | Too-fast SBC completion, high bid frequency |

FC Trader responses:
- Soft ban → sleep 7200s (2 hrs minimum), then re-check.
- Hard ban → `CRITICAL` log, bot halts permanently, does not restart.

---

## 6. Session Hygiene

- **90-minute rotation**: browser restarts and proxy rotates to prevent persistent session detection.
- **Idle drift**: 4–15 minute random idle between cycles simulates human stepping away.
- **Daily active cap**: ≤6 hours of bot activity per calendar day; rest mirrors offline human player.
- **Keepalive**: lightweight DOM scroll event every 8 minutes prevents EA's 10-minute session expiry.
- **Session persistence**: cookies stored in `/app/data/browser_profile`; avoids re-login every run.

---

## 7. Graduated Access — Why Account Must Be Pre-Unlocked

EA's Graduated Access system (new for FC 26) gates Transfer Market access for new/non-returning accounts. Requirements for immediate access:
- FC 25 club created before August 1, 2025.
- Account in good standing.

Non-eligible accounts must complete "Foundation Objectives" and log 2+ active days before Transfer Market is unlocked. The bot does NOT automate this — attempting market actions on a locked account triggers errors. Only use fully-unlocked accounts.

---

## 8. Android Stealth Retrofit

When `execution_mode: android`, the `AndroidKSAStealth` class applies:

| Property | Value |
|---|---|
| Locale | ar-SA |
| Timezone | Asia/Riyadh |
| GPS coordinates | 24.6877°N, 46.7219°E (Riyadh) |
| Device model | Samsung Galaxy A54 (SM-A546B) |
| Network operator | STC (MCC=420, MNC=01) |

All applied via `adb setprop` at emulator startup. Failures are logged as warnings only — they do not crash the bot.

---

## 9. What Is NOT Covered

- **EA server-side ML**: EA's backend models analyze trade patterns, win rates, and coin flows over time. No client-side technique defeats server-side pattern analysis. The rate limits and daily caps are designed to keep volume below ML detection thresholds.
- **Account age signals**: Older accounts with organic trade history are lower-risk. Fresh mule accounts have higher detection risk.
- **Simultaneous multi-account**: Running multiple accounts from the same IP greatly increases ban risk. Use separate proxies per account.
- **Pack opening automation**: The Store section is navigated for human-breadth sessions only; pack opening is not automated.
