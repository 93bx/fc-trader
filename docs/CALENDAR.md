# FC Trader — Market Calendar

The bot uses a **UTC-based market calendar** to choose which strategy to run. All times below are **UTC**.

---

## Phase → Strategy mapping

| Phase            | UTC window                    | Strategy      | Notes |
|------------------|-------------------------------|---------------|--------|
| RIVALS_REWARDS   | Thursday 07:00 – 10:00        | Mass Bidder   | Rivals rewards drop; more supply. |
| PROMO_DROP       | Friday 17:00 – 20:00         | Chem Style    | Promo pack drop; chem-style deals. |
| PEAK_SELL        | Thursday 18:00 – Friday 16:00| Peak Sell     | Sell/relist only; no buying. |
| WEEKEND_BUY      | Friday 20:00 – Saturday 10:00| Sniper        | Weekend buy window. |
| OVERNIGHT         | 00:00 – 07:00 (any day)      | Mass Bidder   | Low activity; bidding. |
| MIDWEEK_DIP      | Wednesday (all day)           | Sniper        | Selector may alternate with Chem Style. |
| SQUAD_BATTLES    | Sunday 07:00 – 10:00         | Mass Bidder   | Squad Battles rewards. |
| STANDARD         | All other times               | Sniper        | Default. |

Boundaries are implemented in `bot/calendar_engine.py`. Order of checks matters: e.g. OVERNIGHT (00:00–07:00) is evaluated first, so Wednesday 03:00 is OVERNIGHT, not MIDWEEK_DIP; Wednesday 08:00 is MIDWEEK_DIP.

---

## Promo override

When a **promo is active** (configured in `config.yaml` under `promos` with `start` and `end` ISO timestamps), the bot **forces Mass Bidder + Sniper** and does **not** run Chem Style during the pack flood (too much supply of styled cards). The calendar engine’s `is_promo_active()` checks current UTC against these windows.

---

## Seasonal / one-off events

EA promo dates (e.g. Team of the Year, seasonal promos) are **not** hardcoded. Add them to `config.yaml` under `promos`, for example:

```yaml
promos:
  - start: "2025-01-15T17:00:00+00:00"
    end:   "2025-01-22T20:00:00+00:00"
```

The calendar engine uses these to set phase overrides and strategy selection. Keep times in UTC.

---

## Weekly sketch (UTC)

```
Mon 00:00–07:00  OVERNIGHT   → Mass Bidder
Mon 07:00–24:00  STANDARD   → Sniper

Tue 00:00–07:00  OVERNIGHT   → Mass Bidder
Tue 07:00–24:00  STANDARD   → Sniper

Wed 00:00–07:00  OVERNIGHT   → Mass Bidder
Wed 07:00–24:00  MIDWEEK_DIP → Sniper (or alternate with Chem Style)

Thu 00:00–07:00  OVERNIGHT     → Mass Bidder
Thu 07:00–10:00  RIVALS_REWARDS → Mass Bidder
Thu 10:00–18:00  STANDARD      → Sniper
Thu 18:00–24:00  PEAK_SELL     → Peak Sell (relist only)

Fri 00:00–16:00  PEAK_SELL    → Peak Sell
Fri 17:00–20:00  PROMO_DROP   → Chem Style
Fri 20:00–24:00  WEEKEND_BUY  → Sniper

Sat 00:00–10:00  WEEKEND_BUY  → Sniper
Sat 10:00–24:00  STANDARD     → Sniper

Sun 00:00–07:00  OVERNIGHT    → Mass Bidder
Sun 07:00–10:00  SQUAD_BATTLES → Mass Bidder
Sun 10:00–24:00  STANDARD     → Sniper
```

This matches the implementation in `calendar_engine.get_current_phase()` and the strategy map in `get_recommended_strategy()`.
