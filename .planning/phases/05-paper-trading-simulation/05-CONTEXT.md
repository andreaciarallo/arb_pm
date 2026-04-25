# Phase 5: Paper Trading Simulation - Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase adds paper trading simulation to the existing dry-run scanner. Every detected opportunity (YES/NO and cross-market) triggers a simulated VWAP + Kelly sizing calculation using cached prices, computes estimated fees and net P&L, and persists the result to a dedicated `paper_trades` SQLite table. Cross-market paper trades simulate N-leg sequential execution with depth-gated partial fill and hedge scenarios. A Python query module provides summary analytics (total P&L, win rate, average spread, per-category breakdown).

</domain>

<decisions>
## Implementation Decisions

### Simulation Architecture (PAPER-01)
- **D-01:** Paper trade simulation runs inline in `dry_run.py` scan loop, immediately after detection and before the existing opportunity SQLite write. For each opportunity in `all_opps`, the simulator computes VWAP fill price from cached `PriceCache` data, runs `kelly_size()` for position sizing, applies `get_taker_fee()` for fee estimation, and calculates net P&L. No separate runner or async task — reuses the existing scan loop.
- **D-02:** VWAP uses cached prices from `PriceCache` — NOT fresh order book fetches. This avoids exhausting the 60 req/10s CLOB rate limit. The existing `simulate_vwap()` function in `engine.py` accepts ask lists and can be reused directly with cached data.
- **D-03:** Paper trade simulation is always enabled in dry-run mode. No separate toggle needed — dry-run already means no real orders.

### Paper Trades Table (PAPER-02)
- **D-04:** New `paper_trades` SQLite table created via `init_paper_trades_table(conn)` in `storage/schema.py`, following the existing `init_trades_table()` / `init_arb_pairs_table()` pattern. Completely isolated from `trades` and `arb_pairs` tables.
- **D-05:** `insert_paper_trade(conn, paper_trade)` function for row insertion, following the existing `insert_trade()` pattern.

### Paper Trade Record Schema (PAPER-03)
- **D-06:** Each paper trade record includes: `paper_trade_id` (UUID), `paper_arb_id` (UUID, groups multi-leg trades), `market_id`, `market_question`, `opportunity_type` (yes_no | cross_market), `category`, `leg` (yes | no | leg_1..leg_N | hedge), `side` (BUY | SELL), `token_id`, `ask_price`, `simulated_size_usd` (kelly output), `size_filled_usd` (actual fill based on depth), `vwap_price`, `kelly_fraction`, `estimated_fees_usd`, `net_pnl_usd`, `depth_available`, `fill_ratio` (size_filled / simulated_size), `simulated_at` (ISO timestamp), `status` (filled | partial | failed | hedged).

### Fill Probability Model (PAPER-01, PAPER-04)
- **D-07:** Depth-gated deterministic model. If cached order book depth >= kelly_size for a leg, simulate full fill (`fill_ratio = 1.0`). If depth < kelly_size, simulate partial fill proportional to available depth (`size_filled = min(kelly_size, depth)`, `fill_ratio = depth / kelly_size`). No stochastic component — deterministic and reproducible.
- **D-08:** Kelly sizing uses the same parameters as live execution: `kelly_size(net_spread, depth, target_size, total_capital, min_order_usd=5.0, max_capital_pct=0.05)`. If kelly returns 0.0, skip the paper trade (same as live — no forced minimum).

### YES/NO Paper Trade P&L Calculation
- **D-09:** For YES/NO arbitrage: `gross_pnl = (1.0 - vwap_yes - vwap_no) * size_filled_shares`. `fees = get_taker_fee(category, config) * size_filled_usd * 2` (both sides). `net_pnl = gross_pnl - fees`. Two paper_trade rows per arb (YES leg + NO leg), linked by `paper_arb_id`.

### Cross-Market Paper Trade Simulation (PAPER-04)
- **D-10:** Simulate legs sequentially matching live execution order. For each leg: compute proportional kelly size (`ask_i * target_shares`), check cached depth, determine fill status. Equal shares sizing: `target_shares = kelly_usd / sum(leg_asks)`.
- **D-11:** If any leg has insufficient depth (fill_ratio < 1.0), simulate hedge for ALL previously "filled" legs at worst-case price ($0.01, matching live hedge behavior). Record each leg as a separate paper_trade row linked by `paper_arb_id`. Hedge legs get `status='hedged'`, `net_pnl = -(fill_price - 0.01) * shares`.
- **D-12:** Cross-market P&L when fully filled: `gross_pnl = (1.0 - total_yes) * target_shares`. Fees = sum of per-leg fees. `net_pnl = gross_pnl - total_fees`.

### Summary Query Module (PAPER-05)
- **D-13:** Dedicated `src/bot/storage/paper_summary.py` module with pure functions accepting `sqlite3.Connection`:
  - `get_total_pnl(conn) -> dict` — total gross P&L, total fees, total net P&L, trade count
  - `get_win_rate(conn) -> dict` — winning trades / total trades, by opportunity_type
  - `get_avg_spread(conn) -> dict` — average net spread captured, by category
  - `get_category_breakdown(conn) -> list[dict]` — per-category: count, total P&L, avg P&L, win rate
- **D-14:** Summary functions aggregate by `paper_arb_id` (not individual legs) to count complete arb attempts. A "win" is a `paper_arb_id` group where sum of `net_pnl_usd` > 0.

### BotConfig
- **D-15:** No new BotConfig fields needed for Phase 5. Paper trading reuses existing execution parameters (`total_capital_usd`, `kelly_*`, `fee_pct_*`). Paper trading is always-on in dry-run mode.

### Claude's Discretion
- Whether to add a `paper_trade_enabled` BotConfig toggle (may not be needed since dry-run implies paper trading)
- Whether to log a per-cycle paper trade summary line in the scan loop (similar to existing dep_flags/dedup_suppressed counters)
- Whether to create a thin CLI entrypoint for querying paper trade summaries from the command line
- Exact column types and indexes for the paper_trades table (optimize for summary query patterns)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — PAPER-01 through PAPER-05 define simulation, storage, record schema, cross-market simulation, and summary query requirements

### Phase 5 Description
- `.planning/ROADMAP.md` — Phase 5 section defines goal, dependencies, success criteria

### Prior Phase Context
- `.planning/phases/04-dependency-integration/04-CONTEXT.md` — Phase 4 decisions (BotConfig field conventions, FilterDiagnostics patterns, gate insertion patterns)
- `.planning/phases/02-detection-quality-filters/02-CONTEXT.md` — Phase 2 decisions (filter patterns, BotConfig conventions, diagnostic counter approach)

### Execution Engine (reuse VWAP + Kelly)
- `src/bot/execution/engine.py` — `simulate_vwap()` function (reuse for paper trade VWAP calculation), `ExecutionResult` dataclass (reference for paper trade record design)
- `src/bot/execution/kelly.py` — `kelly_size()` pure function (reuse directly for paper trade sizing)

### Fee Model
- `src/bot/detection/fee_model.py` — `get_taker_fee()` and `get_market_category()` (reuse for paper trade fee estimation)

### Detection Output
- `src/bot/detection/opportunity.py` — `ArbitrageOpportunity` dataclass (paper trade simulator input)
- `src/bot/detection/cross_market.py` — `detect_cross_market_opportunities()` (produces cross-market opps with `.legs` list)
- `src/bot/detection/yes_no_arb.py` — `detect_yes_no_opportunities()` (produces YES/NO opps)

### Storage (follow existing patterns)
- `src/bot/storage/schema.py` — Existing `init_trades_table()`, `insert_trade()`, `init_arb_pairs_table()` patterns to follow for paper_trades
- `src/bot/storage/writer.py` — `AsyncWriter` for non-blocking SQLite writes

### Scanner (cached price data)
- `src/bot/scanner/price_cache.py` — `PriceCache` class (source of cached asks/bids for VWAP simulation without API calls)

### Dry Run Loop (integration point)
- `src/bot/dry_run.py` — Main scan loop where paper trade simulation hooks in (after detection, before opportunity write)

### Configuration
- `src/bot/config.py` — `BotConfig` frozen dataclass (existing execution parameters reused by paper trader)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `simulate_vwap(asks, target_size_usd)` in `engine.py`: Pure function, accepts ask list + target size, returns VWAP price. Can be reused directly with cached price data for paper trade simulation.
- `kelly_size(net_spread, depth, target_size, total_capital, ...)` in `kelly.py`: Pure function, returns position size in USD. Reuse directly for paper trade sizing.
- `get_taker_fee(category, config)` in `fee_model.py`: Returns per-side taker fee rate. Reuse for paper trade fee estimation.
- `get_market_category(market)` in `fee_model.py`: Detects market category from tags/keywords. Reuse for paper trade categorization.
- `PriceCache` in `price_cache.py`: Already populated by WebSocket + HTTP polling. Contains cached asks/bids — use as VWAP input without fresh API calls.
- `AsyncWriter` in `writer.py`: Async queue writer for SQLite — can be extended or a second instance created for paper_trades writes.
- `ArbitrageOpportunity` dataclass: Detection output with all fields needed for simulation (market_id, net_spread, depth, legs, yes_ask, no_ask, category, etc.)

### Established Patterns
- `init_*_table(conn)` + `insert_*(conn, data)` functions in `schema.py` for each table
- `BotConfig` frozen dataclass with individual float fields (not nested dicts)
- Gate-style sequential processing in execution engine
- AsyncWriter non-blocking queue pattern for SQLite writes
- Loguru structured logging with pipe-separated fields
- UUID-based trade/arb identifiers

### Integration Points
- `dry_run.py` line ~113-118: After `all_opps = yes_no_opps + cross_opps`, before `writer.enqueue(opp)` — insert paper trade simulation here
- `storage/schema.py`: Add `paper_trades` table, `init_paper_trades_table()`, `insert_paper_trade()`
- New module `storage/paper_summary.py`: Summary query functions
- `dry_run.py` init section: Call `init_paper_trades_table(conn)` alongside `init_db()`

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- Dashboard panel for paper-trading metrics (PAPER-F01) — future requirement, not v1.2
- Paper-trade vs live-trade comparison analytics (PAPER-F02) — future requirement
- Stochastic fill probability model (random partial fills based on market conditions) — overkill for MVP paper trading
- WebSocket-based real-time paper trade notifications — future enhancement
- Historical backtesting mode using stored order book snapshots — requires TimescaleDB, out of scope

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-paper-trading-simulation*
*Context gathered: 2026-04-26*
