# FC Trader — Setup

Step-by-step setup for running the bot and intel services with Docker.

---

## 1. Verify KVM

The bot runs an Android emulator that uses KVM for acceptable performance. On Linux:

```bash
kvm-ok
```

If the command is not found, install the CPU checker:

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install cpu-checker
kvm-ok
```

If KVM is not available, enable virtualization in your BIOS/UEFI (Intel VT-x or AMD-V) and ensure the `kvm` kernel module is loaded.

---

## 2. Add your user to the kvm group

So that Docker can access `/dev/kvm` without root:

```bash
sudo usermod -aG kvm $USER
```

Log out and log back in (or reboot) for the group change to take effect. Verify:

```bash
ls -l /dev/kvm
# Should be crw-rw---- 1 root kvm ...
groups
# Should list kvm
```

---

## 3. Get the FC Companion APK

Obtain the **EA Sports FC 26 Companion** app from the official source (e.g. Google Play Store). The project does not distribute the APK. Options:

- Install the app on a real device, then extract the APK using a backup/APK extractor tool, or
- Use a trusted third-party APK mirror at your own risk.

Place the `.apk` file in the project’s `apk/` directory so the bot container can mount and install it (e.g. `apk/com.ea.gp.futmobile.apk`). Alternatively set the environment variable `FC_APK_PATH` to the full path of the APK inside the container.

---

## 4. Environment and config

- Copy `.env.example` to `.env` and set `FC_EMAIL` and `FC_PASSWORD` (use a secondary/mule account).
- Ensure `bot_service/config/config.yaml` exists. The repo may ship an example; the actual `config.yaml` is gitignored. Configure `sniper.players`, `mass_bidder.players`, and/or `chem_style.players` with the player names (and optional `futbin_id`, etc.) you want to trade.

---

## 5. Run in dry-run first

Before real trading, run the bot in dry-run mode so it executes the full flow but does not confirm any buy or list actions:

```bash
docker compose run --rm fc-trader --dry-run
```

Or with docker-compose v1:

```bash
docker-compose run --rm fc-trader --dry-run
```

Watch the logs to confirm login, navigation, and strategy cycles. Stop with Ctrl+C when satisfied.

---

## 6. Start the stack

```bash
docker compose up -d
```

This starts both `fc-trader` (bot + emulator) and `intel` (scrapers). The intel service fills `market_prices` and `sbc_signals` in the shared DB; the bot reads that data and writes `trades`, `rate_state`, and `portfolio`.

---

## 7. Tail logs

- **Bot (fc-trader):**
  ```bash
  docker compose logs -f fc-trader
  ```
- **Intel (scrapers):**
  ```bash
  docker compose logs -f intel
  ```

Use these to debug startup failures, login issues, rate limits, and scraper errors.
