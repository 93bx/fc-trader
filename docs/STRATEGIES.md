# FC Trader — Strategies

Deep explanation of each trading strategy: how it works, when it runs, profit formulas, config, and anti-detection behaviour.

---

## EA rules (apply to all strategies)

- **Tax:** EA takes 5% on every sale. You receive `sell_price * 0.95`. Profit = net_received - buy_price.
- **Bid increments:** Bids must follow EA’s brackets (e.g. 200–1k step 50, 1k–10k step 100, …). The bot uses `utils.get_next_bid()` and `get_prev_bid()` everywhere.
- **Minimum price:** Never buy or list below 200 coins (EA floor).
- **Transfer list:** Max 100 active listings; transfer targets max 50.

---

## Sniper

**What it does:** Uses **Buy Now only** (no bidding). Searches for a player with a max Buy Now filter, picks the best underpriced listing, buys it, then lists it at market price minus one bid increment (minimum undercut).

**When it runs:** WEEKEND_BUY, STANDARD, and (when auto) MIDWEEK_DIP. Selected by the calendar when the market is suitable for quick flip.

**Profit formula:**

- From FUTWIZ we get a **market price** (target sell price).
- **Max buy price** (so that after 5% tax we still meet `min_profit_pct`):
  - `net_after_tax = sell_price * 0.95`
  - We want `(net_after_tax - buy_price) / buy_price * 100 >= min_profit_pct`
  - So: `max_buy = (sell_price * 0.95) * (1 - min_profit_pct/100)`, then round **down** to a valid bid.
- **List price:** `market_price - get_prev_bid(0)` or equivalent (one increment below market).

**Worked example:** Market price 10,000, min_profit_pct 5%.

- Net if we sell at 10,000 = 9,500.
- max_buy = 9,500 * (1 - 0.05) = 9,025 → round down to valid bid, e.g. 9,000.
- We only Buy Now if listing ≤ 9,000. We then list at 9,900 (one step below 10,000 in the 10k bracket).
- Profit = 9,405 - 9,000 = 405; ROI ≈ 4.5% (slightly under 5% because of rounding).

**Config:** `sniper.players` (list of player configs with name, quality, position, etc.), `sniper.min_profit_pct` (default 5.0).

**Anti-detection:** Rate limiter is checked before every search; after every Buy Now the bot enforces `cooldown_after_buy` (e.g. 30 s). All taps use jitter and human-like delays from `anti_detect`.

---

## Mass Bidder

**What it does:** Places **bids** (no Buy Now) below a computed max bid. Max bid is set so that if we win and relist at FUTWIZ BIN, we still make at least `min_profit_coins` after tax. The bot never bids above 85% of BIN to leave room for profit. After bidding, it periodically checks for won items (e.g. every 30 minutes) and relists them at FUTWIZ BIN.

**When it runs:** RIVALS_REWARDS, OVERNIGHT, SQUAD_BATTLES. Also forced (with Sniper) when a promo is active (pack flood).

**Profit formula:**

- **max_bid** so that: `(sell_price * 0.95) - max_bid >= min_profit_coins`  
  So: `max_bid = (sell_price * 0.95) - min_profit_coins`, rounded **down** to a valid bid.  
  And: `max_bid <= BIN * 0.85` (never bid above 85% of BIN).

**Worked example:** Sell price 5,000, min_profit_coins 200.

- Net after tax = 4,750. max_bid = 4,750 - 200 = 4,550 (then round down to valid increment).
- We only place bids at or below 4,550. When we win, we relist at 5,000; profit ≥ 200.

**Config:** `mass_bidder.players`, `mass_bidder.min_profit_coins` (default 200).

**Anti-detection:** Same as Sniper: rate limiter before search/bid, cooldown after buys (when relisting won items), jitter and delays.

---

## Chemistry Style Trader

**What it does:** Buys cards that **already have Shadow or Hunter** applied but are listed at or near the **unstyled** market price (sellers not pricing the chem style). Lists at FUTWIZ price for the card **with** that chem style (Shadow or Hunter).

**When it runs:** PROMO_DROP, and (when auto) can alternate with Sniper during MIDWEEK_DIP. **Not** used during promo pack flood (too much supply of styled cards); then Mass Bidder + Sniper are forced.

**Profit formula:**

- From DB: `price` (no chem), `price_shadow`, `price_hunter` (from intel).
- For each player we decide target style: Shadow for defenders, Hunter for attackers.
- **Max we pay:** `min(player.buy_max, price_no_chem + max_premium_coins)`. We only buy if the listing’s Buy Now is below that and ROI (vs styled price) meets `chem_style.min_profit_pct`.
- **List price:** FUTWIZ price with Shadow or Hunter (whichever is on the card).

**Config:** `chem_style.players`, `chem_style.min_profit_pct`, `chem_style.max_premium_coins` (default 500).

**Anti-detection:** Same pattern: rate limiter, cooldown after buy, jitter and delays.

---

## Peak Sell

**What it does:** **Sell and relist only;** no buying. Used when the calendar is in PEAK_SELL (Thursday 18:00 – Friday 16:00 UTC) to clear and relist inventory at good prices.

**When it runs:** Only during PEAK_SELL phase.

**Config:** No dedicated player list; it operates on current transfer list and portfolio.

---

## Summary table

| Strategy   | Action        | When (examples)        | Key config                          |
|-----------|----------------|-------------------------|-------------------------------------|
| Sniper    | Buy Now, list  | WEEKEND_BUY, STANDARD  | min_profit_pct, players             |
| Mass Bidder | Bid, relist  | RIVALS, OVERNIGHT, SB   | min_profit_coins, players           |
| Chem Style | Buy Now (styled), list | PROMO_DROP, MIDWEEK_DIP | min_profit_pct, max_premium_coins, players |
| Peak Sell | Relist only    | PEAK_SELL              | —                                   |

All strategies respect `daily_trade_limit`, hourly search/buy/list limits, and the `--dry-run` flag (no real buy/list confirmations).
