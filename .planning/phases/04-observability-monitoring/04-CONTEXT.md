# Phase 4: Observability & Monitoring - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Add the full observability layer on top of the working execution engine. Phase 4 delivers:
1. Real PnL trade logging with accurate fees and per-arb analytics (OBS-01, OBS-04)
2. Telegram alerts for key trading events (OBS-02)
3. FastAPI web dashboard with live metrics (OBS-03)

Phase ends when: all trades logged with correct fees, Telegram sending alerts for completed arbs and errors, dashboard accessible in browser showing live bot status + P&L + positions.

No changes to execution logic, risk controls, or detection. This phase is additive only.

</domain>

<decisions>
## Implementation Decisions

### Notification Channel (OBS-02)
- **D-01:** **Telegram only.** Use `python-telegram-bot` 21+ (async, official wrapper).
- **D-02:** Remove `discord_webhook_url` from `BotConfig` entirely — clean codebase, no Discord code or config noise.
- **D-03:** Alert sending is **fire-and-forget non-critical**: if Telegram API fails (timeout, network error), log the failure via Loguru and continue bot operation. No retry. Trading never pauses for an alert failure.
- **D-04:** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` become optional env vars (not added to `REQUIRED_SECRETS`). If absent, alerts silently no-op.

### Alert Triggers (OBS-02)
- **D-05:** Alerts fire on these events (and ONLY these):
  1. **Completed arb pair** — both YES + NO legs confirmed filled. Include: market question, net P&L estimate, gross spread, fees, hold time.
  2. **Circuit breaker trip** — include error count, cooldown duration.
  3. **Critical API failure** — include error message and context.
  4. **Kill switch activation** — fires before position close loop begins. Include trigger reason (SIGTERM or KILL file).
  5. **Daily P&L summary** — one message at midnight UTC. Include: total profit/loss, trade count, win rate, capital efficiency.
- **D-06:** Individual leg fills do NOT trigger alerts (too noisy).

### Dashboard (OBS-03)
- **D-07:** **FastAPI** web server — asyncio-native, integrates cleanly with the bot's async scan loop. Runs as a background task within the same process (or a sidecar container).
- **D-08:** **Auto-refresh every 10 seconds** via JS `setInterval` polling JSON API endpoints. No WebSocket server needed. Data staleness ≤ one scan cycle (30s max, typically 10s).
- **D-09:** Dashboard port: **8080** (exposed in docker-compose.yml). No auth in Phase 4 — VPS firewall provides access control.
- **D-10:** Dashboard metrics scope — **core + extended**:
  - Bot status (running / paused / stopped, circuit breaker state)
  - Daily P&L (realized, unrealized)
  - Open positions (token, size, entry price, current price if available)
  - Last 20 trades (time, market, leg, size, price, status, fees, net P&L)
  - Per-arb analytics (entry/exit prices, hold time, gross P&L, fees, net P&L)
  - Execution cost breakdown (total fees paid, fee rate by category)
  - Capital efficiency over time (rolling 7-day, 30-day)

### Per-Arb Analytics Schema (OBS-01, OBS-04)
- **D-11:** New **`arb_pairs` table** in SQLite, separate from `trades` table. Schema:
  ```
  arb_id TEXT PRIMARY KEY        -- shared UUID generated at execution start
  yes_trade_id TEXT NOT NULL     -- FK → trades.trade_id (YES leg)
  no_trade_id TEXT NOT NULL      -- FK → trades.trade_id (NO leg)
  market_id TEXT NOT NULL
  market_question TEXT NOT NULL
  yes_entry_price REAL
  no_entry_price REAL
  size_usd REAL
  gross_pnl REAL
  fees_usd REAL                  -- sum of both legs' fees
  net_pnl REAL                   -- gross_pnl - fees_usd
  entry_time TEXT                -- YES leg submitted_at
  exit_time TEXT                 -- NO leg filled_at
  hold_seconds REAL
  ```
- **D-12:** `arb_pairs` row is written **only after both legs are confirmed filled**. No partial rows. One-leg failures (retry-then-hedge path) do NOT write to `arb_pairs` — they stay in `trades` table only.

### Fee Calculation (OBS-01)
- **D-13:** `fees_usd` computed **at fill time**: `fees_usd = size_filled × relevant_fee_pct` where `relevant_fee_pct` comes from `BotConfig` based on market category (same fee logic as `fee_model.py`). Written into `trades.fees_usd` immediately on fill confirmation. The `0.0` placeholder from Phase 3 `insert_trade()` is replaced.
- **D-14:** `arb_pairs.fees_usd` = sum of YES leg fees + NO leg fees from `trades` table.

### What is NOT in Phase 4
- **D-15:** No WebSocket push to dashboard — polling only.
- **D-16:** No Telegram retry logic — fire-and-forget (D-03).
- **D-17:** No Discord support (removed from BotConfig).
- **D-18:** Dashboard has no auth — rely on VPS firewall.
- **D-19:** One-leg failures (hedge path) not tracked in `arb_pairs`.

### Claude's Discretion
- FastAPI app structure (single file vs. routers, lifespan vs. startup/shutdown events)
- HTML/JS dashboard design and layout (single-page app, inline CSS/JS acceptable)
- Telegram message formatting (Markdown vs HTML parse mode, emoji usage)
- Daily summary cron trigger implementation (asyncio task with UTC midnight check)
- `arb_id` generation strategy (uuid4 generated by `execute_opportunity()` at start of trade)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project requirements
- `.planning/REQUIREMENTS.md` §OBS — OBS-01 through OBS-04 (all four Phase 4 requirements)

### Prior phase context
- `.planning/phases/03-execution-risk-controls/03-CONTEXT.md` — Execution decisions (D-01 through D-12), including deferred OBS items (D-11, D-12)
- `.planning/phases/01-infrastructure-foundation/01-CONTEXT.md` — BotConfig structure, secrets injection, Docker volume setup

### Existing code to build on
- `src/bot/config.py` — BotConfig dataclass; Phase 4 removes `discord_webhook_url`, adds `telegram_chat_id`
- `src/bot/storage/schema.py` — `init_trades_table()`, `insert_trade()` — Phase 4 adds `arb_pairs` table and fixes `fees_usd`
- `src/bot/storage/writer.py` — AsyncWriter pattern for non-blocking DB writes
- `src/bot/execution/engine.py` — `execute_opportunity()` — Phase 4 adds `arb_id` generation, `arb_pairs` write, Telegram alert call
- `src/bot/live_run.py` — Scan loop — Phase 4 adds FastAPI background server, daily summary scheduler
- `src/bot/detection/fee_model.py` — `get_taker_fee()` — reuse for accurate `fees_usd` calculation

### No external specs — requirements fully captured in decisions above

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AsyncWriter` (`storage/writer.py`): Non-blocking queue-based SQLite writer. Phase 4 extends it for `arb_pairs` inserts.
- `BotConfig` (`config.py`): Frozen dataclass. Phase 4 removes `discord_webhook_url`, adds `telegram_chat_id: str | None = None`.
- `fee_model.py` `get_taker_fee()`: Already handles category-based fee rates. Reuse to compute `fees_usd` at fill time.
- `RiskGate` (`risk/gate.py`): Circuit breaker state is in-memory. Phase 4 reads its state for dashboard display and alert on trip.

### Established Patterns
- All I/O is async (`asyncio`) — FastAPI must integrate as a background task without blocking scan loop.
- SQLite writes go through `AsyncWriter` — new `arb_pairs` writes should follow the same pattern.
- `BotConfig` is frozen — new fields added with defaults (no breaking changes to existing env setup).

### Integration Points
- `execute_opportunity()` (`execution/engine.py`): Phase 4 hooks here to: generate `arb_id`, call Telegram alert after successful arb pair, write `arb_pairs` row.
- `live_run.py` scan loop: Phase 4 starts FastAPI server as background task, adds daily summary scheduler.
- `insert_trade()` (`storage/schema.py`): Phase 4 updates to compute real `fees_usd` instead of `0.0`.

</code_context>

<specifics>
## Specific Behaviors

- **Non-critical alerting:** Telegram failures must NEVER affect bot operation. Always wrapped in try/except, logged, and swallowed.
- **arb_pairs is analytics-only:** It is never read during execution — only written after both legs confirm. Dashboard reads it for display.
- **Dashboard runs alongside bot:** FastAPI server starts in the same async event loop as the scan loop. Not a separate process in Phase 4.
- **Fee accuracy matters:** The `0.0` placeholder in `insert_trade()` was an explicit Phase 3 deferral. Phase 4 must replace it with real computation.
- **Daily summary fires at midnight UTC:** One alert per day regardless of trade count (even if 0 trades — useful for confirming bot is alive).

</specifics>

<deferred>
## Deferred Ideas

- Real-time WebSocket push to dashboard — Phase 5 or V2
- Telegram retry logic — not needed given non-critical nature
- Discord support — removed, backlog if ever needed
- Grafana + Prometheus metrics export — V2
- Historical backtesting queries on SQLite data — V2

</deferred>

---

*Phase: 04-observability-monitoring*
*Context gathered: 2026-04-14*
