# Strategy & Configuration Guide

This document covers how the bot works, every parameter you can tune, and a roadmap of possible improvements.

---

## Current Strategy

### Overview

The bot exploits two types of mispricing on Polymarket's Central Limit Order Book (CLOB):

1. **YES/NO structural arbitrage** — within a single binary market, when `best_ask(YES) + best_ask(NO) < $1.00` by enough to cover fees and a profit margin.
2. **Cross-market arbitrage** — across a group of mutually exclusive markets (e.g. "Will Alice win?", "Will Bob win?"), when the sum of all YES asks is < $1.00, meaning you can buy all of them for guaranteed profit if exactly one must resolve YES.

Both are deterministic, risk-free on paper: if the combined cost to buy all outcomes is less than the guaranteed $1.00 payout, the difference is locked-in profit.

---

### Data Pipeline

```
WebSocket (real-time)
  └─ market price updates (YES/NO asks + depth)
  └─ stored in PriceCache (in-memory, keyed by token_id)

HTTP Poller (fallback)
  └─ polls 50 tokens/cycle via REST if WS data goes stale (>5s)
  └─ rotates through all subscribed tokens via _poll_offset

Market Filter
  └─ only markets with active=True, enable_order_book=True, accepting_orders=True
  └─ paginated at startup, refreshed periodically
```

### Detection Loop (every 30 seconds)

1. Pull the current price snapshot from `PriceCache` for all active markets.
2. Run `detect_yes_no_opportunities()` — scans each binary market for YES+NO arb.
3. Run `detect_cross_market_opportunities()` — groups markets by keyword overlap, checks mutual exclusivity.
4. For each opportunity passing all gates, call the execution engine (live mode only).

### Detection Gates (YES/NO arb)

All four must pass before an opportunity is acted on:

| Gate | Check |
|------|-------|
| **Cache presence** | Both YES and NO prices exist in cache and are not stale |
| **Resolved market guard** | Neither ask price is ≥ $1.00 (near-resolved markets excluded) |
| **Depth gate** | `min(yes_depth, no_depth) ≥ min_order_book_depth` (default $50) |
| **Profit threshold** | `net_spread ≥ category-specific threshold` (see fee model) |

`net_spread = (1.0 - yes_ask - no_ask) - fees`

### Category-Aware Fee Model

Polymarket charges different taker fees by market category. The bot classifies each market using official tags first, then keyword fallback on the question text.

| Category | Detection tags / keywords | Taker fee (per side) | Min profit threshold |
|----------|--------------------------|----------------------|----------------------|
| **Crypto** | bitcoin, eth, defi, nft, … | 1.8% | 2.0% |
| **Politics / Finance / Tech** | politics, election, finance, … | 1.0% | 1.5% |
| **Sports** | nfl, nba, fifa, world cup, … | 0.75% | 1.5% |
| **Geopolitics** | nato, war, ceasefire, sanction, … | 0% (fee-free) | 0.75% |
| **Other** | anything unmatched | 1.0% (fallback) | 1.5% |

Fees are applied to both legs: `estimated_fees = (yes_ask + no_ask) × fee_rate`.

### Execution Pipeline (live mode only)

Once an opportunity passes detection, the engine runs five sequential gates before placing orders:

```
1. VWAP gate
   └─ Simulate multi-level fill price against the live order book
   └─ vwap_spread = 1.0 - vwap_yes - vwap_no
   └─ Skip if vwap_spread < min_net_profit_pct

2. Kelly gate
   └─ Modified Kelly formula → position size in USD
   └─ Skip if Kelly returns 0.0 (spread too thin or depth too low)

3. YES leg — FAK BUY order
   └─ Place Fill-or-Kill at yes_ask price for kelly_usd
   └─ If None returned → abort (no NO exposure incurred)

4. YES fill verification (REST polling)
   └─ Poll get_order() every 500ms × 10 attempts (5s timeout)
   └─ If unconfirmed → record_order_error(), abort

5. NO leg — FAK BUY with retry-then-hedge
   └─ 3 attempts × 500ms delay
   └─ If all fail → emergency SELL YES at $0.01 (hedge)
```

### Modified Kelly Formula

```
f = (b × p − q) / (b × √p)

b = net_spread        (profit fraction, e.g. 0.03 for 3%)
p = min(1.0, depth / target_size)   (execution probability)
q = 1 − p

Hard caps applied after Kelly:
  size = min(kelly_result, depth × 0.5, capital × max_capital_pct)
```

The `depth × 0.5` cap prevents the bot from moving the market against itself. The `capital × max_capital_pct` cap (default 5%) prevents over-concentration in a single trade.

### Risk Controls

| Control | Trigger | Effect |
|---------|---------|--------|
| **Daily stop-loss** | Realized losses reach `daily_stop_loss_pct × capital` | Trading halted until midnight UTC |
| **Circuit breaker** | `circuit_breaker_error_count` order errors within `circuit_breaker_window_seconds` | Trading paused for cooldown (doubles on repeat trips: 5m → 10m → 20m, max) |
| **Kill switch** | SIGTERM signal or `/app/data/KILL` file | All trading stopped permanently until restart; open positions closed |

---

## Tunable Parameters

All parameters live in `secrets.env` (environment variables) or have defaults in `src/bot/config.py`. Restart the Docker container after any change.

### Required Secrets (not tunable — just set once)

| Variable | Description |
|----------|-------------|
| `POLY_API_KEY` | Polymarket CLOB API key |
| `POLY_API_SECRET` | Polymarket CLOB API secret |
| `POLY_API_PASSPHRASE` | Polymarket CLOB API passphrase |
| `WALLET_PRIVATE_KEY` | EOA wallet private key for signing |
| `POLYGON_RPC_HTTP` | Alchemy (or other) Polygon RPC HTTP URL |
| `POLYGON_RPC_WS` | Alchemy (or other) Polygon RPC WebSocket URL |

### Optional Secrets

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | None | If set, enables Telegram alerts |
| `TELEGRAM_CHAT_ID` | None | Numeric Telegram chat ID to send alerts to |

---

### Scanning Parameters

These control how aggressively the bot scans and what markets it considers liquid enough to trade.

| Parameter | Default | Description | Tuning notes |
|-----------|---------|-------------|--------------|
| `scan_interval_seconds` | `30` | Seconds between full detection cycles | Lower = more responsive, but detection is compute-light — 10–15s is safe |
| `ws_stale_threshold_seconds` | `5` | Seconds before WebSocket price data is considered stale and HTTP polling kicks in | Raise if you see excessive HTTP fallback in logs; lower only if latency is critical |
| `min_order_book_depth` | `50.0` | Minimum USD depth at best ask on *each* side | Raise (e.g. $100–200) to filter illiquid markets and reduce slippage risk; lower increases opportunity count but execution quality drops |
| `min_market_volume` | `1000.0` | 24h volume filter (currently informational — CLOB volume field is often None) | Has no practical effect right now; reserved for when the API reliably returns volume |

---

### Profit Thresholds

These are the minimum net spreads (after fees) required to act on an opportunity. The most important levers for filtering signal from noise.

| Parameter | Default | Applies to | Tuning notes |
|-----------|---------|------------|--------------|
| `min_net_profit_pct` | `0.015` (1.5%) | Politics, Sports, Other | The base threshold. Lowering below 1% risks false positives from stale prices. Raising above 2.5% will likely produce zero opportunities. |
| `min_net_profit_pct_crypto` | `0.020` (2.0%) | Crypto markets | Higher because crypto fees are 1.8%/side — anything below 2% barely covers costs. |
| `min_net_profit_pct_geopolitics` | `0.0075` (0.75%) | Geopolitics | Low because these markets have 0% fees — even a thin spread is pure profit. |

**Rule of thumb:** `min_net_profit_pct ≥ 2 × taker_fee_rate` for a category ensures the bot never takes fee-losing trades.

---

### Fee Rates

Update these if Polymarket changes its fee structure. Wrong fee rates cause the bot to either miss opportunities (rates too high) or enter unprofitable trades (rates too low).

| Parameter | Default | Category |
|-----------|---------|----------|
| `fee_pct_crypto` | `0.018` (1.8%) | Crypto |
| `fee_pct_politics` | `0.010` (1.0%) | Politics / Finance / Tech |
| `fee_pct_sports` | `0.0075` (0.75%) | Sports |
| `fee_pct_geopolitics` | `0.0` (0%) | Geopolitics |
| `fee_pct_default` | `0.010` (1.0%) | Unclassified / Other |

---

### Position Sizing (Kelly)

| Parameter | Default | Description | Tuning notes |
|-----------|---------|-------------|--------------|
| `total_capital_usd` | `1000.0` | Total capital deployed. Used by Kelly and stop-loss calculations. | Set this to the actual balance in your wallet. Mismatching it causes stop-loss and sizing to be wrong. |
| `kelly_min_order_usd` | `5.0` | Polymarket's minimum order floor. Kelly returns 0.0 if size < this. | Do not lower below $5 — Polymarket will reject smaller orders. |
| `kelly_max_capital_pct` | `0.05` (5%) | Hard ceiling: no single trade can exceed this fraction of capital. | At $1k capital, this caps each trade at $50. Raising above 10% increases concentration risk significantly. Lower (2–3%) for more conservative sizing. |

**How Kelly interacts with depth:** The formula automatically scales down toward zero as order book depth shrinks relative to target size. You don't need to manually tune for depth — the formula handles it.

---

### Risk Controls

| Parameter | Default | Description | Tuning notes |
|-----------|---------|-------------|--------------|
| `daily_stop_loss_pct` | `0.05` (5%) | Fraction of `total_capital_usd` lost before trading stops for the day | At $1k, this is a $50 daily loss limit. Lower (3%) for more protection; higher (8%) if you want the bot to push through rough patches. |
| `circuit_breaker_error_count` | `5` | Number of order errors within the window before the circuit trips | Lower (3) for hair-trigger protection; higher (8–10) if the exchange is occasionally flaky and you're seeing false trips. |
| `circuit_breaker_window_seconds` | `60` | Sliding window for counting order errors | Wider window (120s) is more lenient; narrower (30s) is stricter. |
| `circuit_breaker_cooldown_seconds` | `300` (5 min) | Base cooldown after circuit trips. Doubles on each subsequent trip (5m → 10m → 20m max). | Raise to 600s (10 min base) if you want the bot to back off more aggressively after errors. |

---

### Hardcoded Execution Constants

These are not in `secrets.env` — they require a code change to modify (`src/bot/execution/engine.py`).

| Constant | Value | Description |
|----------|-------|-------------|
| `_NO_RETRY_COUNT` | `3` | Number of times to retry the NO leg before hedging |
| `_NO_RETRY_DELAY` | `0.5s` | Delay between NO leg retry attempts |
| `_HEDGE_PRICE` | `$0.01` | Price at which to emergency-sell the YES position if all NO retries fail. Market-aggressive — designed to hit the best bid. |

### Hardcoded Scanner Constants

In `src/bot/scanner/http_poller.py` and related files:

| Constant | Value | Description |
|----------|-------|-------------|
| HTTP poll batch size | `50` tokens/cycle | How many tokens are polled per HTTP fallback cycle |
| WS subscription limit | `~2000` token IDs | Server silently drops subscriptions beyond this |
| Cross-market cap | `100` markets | Only the first 100 priced markets are used for cross-market O(n²) grouping |
| HTTP inter-page delay | `200ms` | Rate-limit buffer between market filter pagination requests |

---

## Possible Improvements

### Near-Term (ready to implement)

**1. LLM mutual-exclusivity validation for cross-market detection**
The current cross-market grouping uses keyword overlap only. This produces false positives — markets that share words but are not mutually exclusive (e.g. "Will GDP grow?" and "Will GDP shrink?" are both GDP questions, but the $1.00 constraint doesn't hold). Adding a cheap LLM call (Claude Haiku or GPT-4o-mini) to validate each detected group before execution would eliminate false positives entirely.

**2. Multi-level VWAP in detection (not just execution)**
The detection engine currently uses the single best-ask price. The execution engine does a multi-level VWAP simulation, but only after detection. Promoting VWAP simulation to the detection stage would give a more accurate spread estimate and reduce the number of opportunities that are detected but then rejected by the VWAP gate.

**3. WebSocket user-channel fill verification**
YES fill verification currently uses REST polling (500ms × 10 polls = 5s timeout). The Polymarket user WebSocket channel delivers fill events in ~50ms. Switching to WebSocket verification would cut fill confirmation time from 5s to under 100ms, significantly reducing the window of one-leg exposure.

**4. Per-category opportunity logging**
The dashboard currently shows all trades in one flat table. Adding a category breakdown (crypto vs. politics vs. geopolitics) would make it easy to see which market types are generating the most flow and whether fee-model parameters are well-calibrated.

**5. Dynamic scan interval based on opportunity rate**
If zero opportunities are detected for N consecutive cycles, increase the scan interval (e.g. 30s → 60s) to reduce unnecessary CPU. If an opportunity is found, snap back to the minimum interval immediately. This is a simple exponential backoff that adapts to market conditions.

**6. Kill-switch via Telegram command**
Currently the kill switch requires SSH access to create the `/app/data/KILL` file. Adding a Telegram bot command (`/kill`) that writes the file remotely would make emergency stops possible from a phone.

---

### Long-Term (larger architectural changes)

**7. Order book depth tracking beyond best ask**
The current scanner only caches the best ask price and the depth at that level. Storing the full order book snapshot (top 5–10 levels) would enable more accurate VWAP calculations and let the bot detect opportunities that only exist if you're willing to walk up the book slightly.

**8. Backtesting harness with TimescaleDB**
Storing historical order book snapshots in TimescaleDB would allow replaying market data to test new parameter values, fee-model changes, or detection thresholds offline before deploying to live capital. Currently no historical data is collected.

**9. Portfolio-level position limits**
The bot currently applies Kelly sizing per-trade independently. A portfolio-level view — tracking total open exposure across all active positions — would prevent the bot from simultaneously entering many trades during a burst of detected opportunities and breaching total capital risk targets.

**10. Stale price degradation model**
If a token's last price update was 4 seconds ago (just under the 5s staleness threshold), the price might still be valid, or it might be about to go stale. A confidence-weighted staleness penalty — reducing the effective spread proportionally as the timestamp ages — would be more accurate than the current hard 5s cutoff.

**11. Multi-exchange arbitrage**
Polymarket operates its own CLOB, but some markets have equivalent contracts on other prediction market platforms. Cross-platform arb (buying on one exchange and selling on another) would open a much larger opportunity set, at the cost of significantly higher implementation complexity (multiple API clients, cross-chain settlement risk, different fee structures).

**12. Automated parameter optimization**
With a backtesting harness in place (#8), parameters like `min_net_profit_pct`, `min_order_book_depth`, and `kelly_max_capital_pct` could be grid-searched or Bayesian-optimized against historical data rather than set by hand. This is meaningful only once a few months of live data accumulate.
