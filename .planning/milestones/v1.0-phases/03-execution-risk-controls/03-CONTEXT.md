# Phase 3: Execution & Risk Controls - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement automated trade execution and risk management. Bot transitions from dry-run detection to live arbitrage execution on Polymarket's CLOB API. Every trade goes through position sizing (modified Kelly), pre-execution VWAP validation, IOC order submission, partial fill handling, and REST verification.

Risk controls run as a parallel layer: daily stop-loss, circuit breaker, and kill switch operate independently of the execution path and can halt trading at any point.

Phase ends when bot executes arbitrage trades automatically with all risk controls verified by simulated error injection.

No dashboard, no alerts, no observability beyond loguru logs. That is Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Position Sizing (RISK-01)
- **D-01:** Use **modified Kelly formula** for position sizing: `f = (b × p - q) / b × √p`
  - `b` = net spread (arbitrage profit % from detection engine)
  - `p` = execution probability, estimated from order book depth: `min(1.0, depth / target_size)`
  - `q` = 1 - p
  - **Hard cap:** 50% of order book depth (never move the market against yourself)
  - **Absolute floor:** $5 minimum order (Polymarket minimum threshold)
  - **Safety ceiling:** 5% of total capital (prevents over-concentration in one trade)
  - Source: Modified Kelly from "Unravelling the Probabilistic Forest" (arxiv 2508.03474)
  - Replaces simpler confidence-tiered sizing — accounts for execution risk directly

### Order Type (EXEC-01, EXEC-02)
- **D-02:** All orders use **IOC (Immediate-or-Cancel)** type.
  - Fill as much as possible immediately, cancel the rest.
  - GTC explicitly excluded — dangerous for arb (opportunity disappears while order sits in book).
  - FOK excluded — too conservative, kills fill rate on thin markets.
  - Partial fills handled by retry-then-hedge logic (D-04).

### One-Leg Execution Risk (EXEC-03)
- **D-03:** **Retry-then-hedge** strategy for one-leg failure.
  - YES leg fills → attempt NO leg up to **3 retries** with **500ms between attempts**.
  - If NO leg still unfilled after 3 retries → immediately **sell YES at market** (hedge).
  - Maximum naked exposure window: ~1.5 seconds.
  - This is the standard production approach — balances fill rate vs. exposure duration.
  - Immediate hedge (0 retries) gives up too easily. Cancel-and-reprice adds a third round-trip.

### Order Verification (EXEC-04)
- **D-04:** **Dual verification** for every filled order.
  - Primary: WebSocket fill confirmation (real-time).
  - Secondary: REST API verification via `get_order(order_id)` after WebSocket fill event.
  - If REST and WebSocket disagree → treat as unfilled, log discrepancy, do not proceed with second leg.
  - Verification timeout: 5 seconds (same as ws_stale_threshold_seconds from Phase 2).

### Pre-Execution VWAP Simulation (EXEC-01)
- **D-05:** Before submitting any order, **simulate the trade against the current order book**.
  - Calculate expected VWAP given our target size and current order book depth levels.
  - Check: is VWAP-adjusted net spread still ≥ `min_net_profit_pct` threshold?
  - If not → skip this opportunity (market moved since detection).
  - Source: Paper's "execution validation layer" — only execute if all pre-checks pass.
  - Prevents executing on stale detections (detection lag + CLOB movement).

### Daily Stop-Loss (RISK-02)
- **D-06:** Daily stop-loss = **5% of total capital** ($50 at $1k).
  - Measured as cumulative realized losses since midnight UTC.
  - Trigger: loss counter hits threshold → pause all new order submission.
  - Reset: automatically resumes at midnight UTC (no manual restart required).
  - Unrealized positions (open orders) are not counted until filled or cancelled.

### Circuit Breaker (RISK-03)
- **D-07:** Circuit breaker pauses trading on high error rates.
  - Trigger: **5 consecutive order errors** (rejections, timeouts, auth failures) within **60 seconds**.
  - Cooldown: **5 minutes** before resuming. Exponential backoff on repeat triggers: 5m → 10m → 20m (cap 20m).
  - Error types counted: API rejections, order timeouts, WebSocket disconnects during order flow, auth failures.
  - Connection errors during idle scanning do NOT count (only order-phase errors).

### Kill Switch (RISK-04)
- **D-08:** **Active close** — sell all held YES/NO token positions immediately when triggered.
  - Does NOT just pause new orders — actively closes open positions via market sell orders.
  - Two trigger paths (both converge to the same shutdown coroutine):
    1. **SIGTERM** — Docker `docker compose stop` sends SIGTERM naturally.
    2. **File-based** — bot checks for `/app/data/KILL` file every scan cycle (≤30s detection lag).
  - Sequence: cancel all pending orders → sell all positions → stop scan loop → flush SQLite writer → exit.
  - Kill switch cannot be overridden by circuit breaker or stop-loss state.

### What is NOT in Phase 3
- **D-09:** Full **Bregman projection + Frank-Wolfe algorithm** stays deferred.
  - Requires Gurobi (commercial solver, ~$10k/year) or equivalent.
  - Designed for institutional systems analyzing 17,000+ conditions simultaneously.
  - At <$1k capital with 1–3 simultaneous trades at $10–15 each, complexity is not justified.
  - Modified Kelly (D-01) captures the execution-risk-aware sizing without the solver dependency.
- **D-10:** **LLM-based market dependency detection** stays deferred (Phase 3 CONTEXT carried it forward from Phase 2 D-03). Cross-market arb found 13 exploitable pairs in a year at research scale — API costs exceed returns at our capital level.
- **D-11:** **Telegram/Discord alerts** are Phase 4 (OBS-02). Phase 3 logs to loguru only.
- **D-12:** **Dashboard** is Phase 4 (OBS-03).

### Claude's Discretion
- SQLite `trades` table schema (columns beyond the obvious: trade_id, market_id, leg, side, price, size, filled, fees, timestamp)
- Retry logic implementation details (asyncio task, timeout handling)
- Kelly formula edge cases (b ≤ 0, p = 0, result < floor → skip trade)
- Circuit breaker state persistence across scan cycles (in-memory counter, reset on clean cycle)
- SIGTERM handler registration (Python `signal` module, asyncio-safe)

</decisions>

<open_topics>
## Open Topics

All topics resolved as of 2026-03-28. See D-01 through D-12.

</open_topics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Research papers
- "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets" (arxiv 2508.03474) — Modified Kelly formula, VWAP execution validation, non-atomic execution risk
- "Arbitrage-Free Combinatorial Market Making via Integer Programming" (arxiv 1606.02825) — Theoretical foundation (Bregman/Frank-Wolfe, deferred)

### Project files
- `CLAUDE.md` — Tech stack (py-clob-client, websockets 16.0, httpx, loguru, SQLite)
- `.planning/REQUIREMENTS.md` §EXEC and §RISK — EXEC-01 through EXEC-04, RISK-01 through RISK-04
- `.planning/phases/02-market-data-detection/02-CONTEXT.md` — Detection engine decisions, fee model, category-aware thresholds
- `.planning/phases/01-infrastructure-foundation/01-CONTEXT.md` — BotConfig, build_client(), secrets injection

### Existing code to build on
- `src/bot/config.py` — BotConfig with Phase 2 fields; Phase 3 adds capital, stop-loss, circuit breaker params
- `src/bot/detection/opportunity.py` — ArbitrageOpportunity dataclass (input to execution engine)
- `src/bot/detection/fee_model.py` — get_taker_fee(), get_min_profit_threshold() — reuse for execution cost calc
- `src/bot/scanner/price_cache.py` — PriceCache.get() — used for pre-execution VWAP simulation
- `src/bot/dry_run.py` — Scan loop structure to extend for live execution
- `src/bot/storage/writer.py` — AsyncWriter pattern to reuse for trade logging

</canonical_refs>

<specifics>
## Specific Behaviors

- **Execution must be gated**: every opportunity goes through Kelly sizing → VWAP simulation → IOC submit → verify → retry-hedge if needed. No shortcuts.
- **Stop-loss is cumulative realized loss only**: open positions don't count until closed.
- **Kill switch takes absolute priority**: overrides stop-loss pause, circuit breaker cooldown, everything.
- **Modified Kelly can return 0 or negative**: when `b × p < q`, formula result is ≤ 0. Treat as "skip trade" — never force a minimum allocation when Kelly says no.
- **Phase 2 dry_run.py stays intact**: live execution is a new `live_run.py` module. Dry-run mode must remain functional for rollback and comparison.
- **All trades logged to SQLite**: even failed/rejected orders get a row with status='failed'.

</specifics>

<deferred>
## Deferred to Later Phases

- **Phase 4:** Telegram/Discord alerts (OBS-02)
- **Phase 4:** Local dashboard (OBS-03)
- **Phase 4:** Per-arb analytics and capital efficiency tracking (OBS-04)
- **V2+:** Full Bregman projection + Frank-Wolfe + Gurobi optimization
- **V2+:** LLM-based market dependency detection (DeepSeek-R1 screening)
- **V2+:** Kelly Criterion standard form (current: modified Kelly from paper)
- **V2+:** Multi-wallet, cross-platform arbitrage

</deferred>

---

*Phase: 03-execution-risk-controls*
*Context gathered: 2026-03-28*
