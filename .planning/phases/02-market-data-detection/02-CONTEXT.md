# Phase 2: Market Data & Detection - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement real-time market data ingestion and arbitrage opportunity detection without executing any trades. Bot scans liquid markets via WebSocket (HTTP polling fallback), detects YES+NO structural arbitrage and basic cross-market arbitrage, scores opportunities using CLOB ask prices and VWAP, and logs all findings to terminal + SQLite in dry-run mode.

Phase ends when bot runs 24h in dry-run with zero trades placed and a meaningful opportunity log in SQLite.

No trade execution, no position management, no Bregman optimization. Detection and logging only.

</domain>

<decisions>
## Implementation Decisions

### Arbitrage Strategy (confirmed via two reference articles)
- **D-01:** Focus exclusively on **structural arbitrage** — no directional strategies, no momentum, no CEX price comparison. Both reference bots confirm directional strategies lose money (layerx: -37.81% on crypto 15-min).
- **D-02:** **Primary:** Single-market YES+NO arb — detect when YES ask + NO ask < $1.00 after fees.
- **D-03:** **Secondary:** Basic cross-market arb — group markets by category + keyword similarity, check subset/exclusivity logical constraints. LLM-based dependency detection deferred to Phase 3.
- **D-04:** Full Bregman projection optimization deferred to Phase 3 (execution). Phase 2 uses simpler VWAP-based detection.

### Price Source (critical — layerx's most expensive lesson)
- **D-05:** Always use **CLOB ask prices** for opportunity detection and paper P&L calculation — never Gamma API bid prices. Using bid prices in paper trading shows phantom profits that disappear in live execution.

### Market Scanning
- **D-06:** Fetch market list via HTTP, filter to liquid markets by volume. Threshold: **$1,000 USD 24h volume** (user-confirmed). Stored as `min_market_volume` config field. Yields ~500 liquid markets — matches LayerX production scale (D-19).
- **D-07:** Filter parameters are config values, not hardcoded — adjustable later via admin panel (Phase 4).
- **D-08:** Scan cycle: **every 30 seconds**, ~500 markets per cycle (aligned with layerx production config).
- **D-09:** WebSocket subscription is primary data source (DATA-01). HTTP polling fallback when WebSocket data is >5s stale (DATA-02).

### Opportunity Scoring
- **D-10:** Use **VWAP-weighted pricing** against order book depth — not just best bid/ask. Realistic execution price matters even in dry-run.
- **D-11:** Minimum order book depth: **$50** — opportunities with less depth are not worth logging (profit too small to cover execution risk).
- **D-12:** **Min net profit threshold: 1.5% base (configurable, tiered by category).** Small capital bots (<$1k) cannot compete at 0.5–1% spreads — institutional bots with co-located servers capture those first. 1.5% requires ~3–3.5% gross spread, achievable during volatile moments. Stored as `min_net_profit_pct` config field. Tier overrides: crypto = 2.0% (`min_net_profit_pct_crypto`), geopolitics = 0.75% (`min_net_profit_pct_geopolitics`).
- **D-13:** Fee model is **category-aware** (D-18). Slippage estimated from VWAP deviation from best ask.
- **D-18:** **Category-aware fee rates (researched, 2026 Polymarket structure):**
  - Crypto: 1.8% taker per side (highest) — requires 2.0% min net profit
  - Politics/Finance/Tech: 1.0% taker per side
  - Sports: 0.75% taker per side
  - Geopolitics: 0% fee-free — requires only 0.75% min net profit (highest value targets)
  - Default/unknown: 1.0% taker per side (conservative)
  - Strategic priority: target geopolitics (fee-free) and focus on endgame arb (93%+ probability, <48hr resolution)
- **D-19:** **Market volume filter: $1,000 USD 24h volume** (user-confirmed, 2026-03-28). Stored as `min_market_volume` config field. Yields ~500 liquid markets at Polymarket's current scale.

### Dry-Run Output (DATA-06)
- **D-14:** Log all detected opportunities to **both loguru (terminal) and SQLite**.
- **D-15:** SQLite schema must support automation and debugging: structured fields (market_id, market_question, yes_ask, no_ask, gross_spread, net_spread, depth, vwap_yes, vwap_no, detected_at, opportunity_type). No freeform text blobs.
- **D-16:** Dry-run runs for **24h with zero trades placed** as verification gate.
- **D-17:** Opportunity log must be easy to query after the run — meaningful column names, indexed by detected_at.

### Claude's Discretion
- SQLite table schema specifics beyond required columns above
- WebSocket reconnection and backoff logic
- HTTP polling interval when WebSocket is degraded
- Data normalization format for unified price representation (DATA-03)
- Keyword similarity algorithm for cross-market grouping

</decisions>

<open_topics>
## Open Topics

All topics resolved as of 2026-03-28. See D-12, D-18, D-19.

</open_topics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Strategy references
- Binance article (cross-market arb math): Marginal polytope, integer programming, Bregman projection, VWAP, non-atomic execution risk, 2-cent minimum deviation threshold, Kelly-modified position sizing
- LayerX article: Lessons from 4 failed/active strategies. Key: CLOB ask prices always, 0.5% min profit, 30s scan cycle, ~500 markets, VWAP + orderbook verification

### Project files
- `CLAUDE.md` — Tech stack (py-clob-client, websockets 16.0, httpx, loguru, SQLite)
- `.planning/REQUIREMENTS.md` §DATA — DATA-01 through DATA-06
- `.planning/phases/01-infrastructure-foundation/01-CONTEXT.md` — Established patterns: BotConfig, build_client(), secrets injection

### Existing code to build on
- `src/bot/config.py` — BotConfig, load_config() — Phase 2 adds config fields for scan params
- `src/bot/client.py` — build_client() — Phase 2 uses this for CLOB API calls
- `src/bot/health.py` — check_health() — reuse for startup validation
- `src/bot/main.py` — replace idle loop with scanner loop

</canonical_refs>

<specifics>
## Specific Behaviors

- Bot must NOT place any orders in Phase 2 — dry-run is enforced at the scanner level, not just a flag
- Opportunity detection must handle market resolution gracefully (resolved markets return $1.00, not an arb)
- WebSocket reconnection must be automatic — a dropped connection should not stop the scanner
- SQLite writes must not block the main scan loop — use async or write queue

</specifics>

<deferred>
## Deferred to Later Phases

- **Phase 3:** Full Bregman projection optimization, Frank-Wolfe algorithm, actual trade execution
- **Phase 3:** LLM-based market dependency detection for cross-market arb
- **Phase 3:** Modified Kelly position sizing
- **Phase 4:** Admin panel for live filter tuning
- **Phase 4:** Dashboard (Vercel-style) for opportunity log visualization

</deferred>

---

*Phase: 02-market-data-detection*
*Context gathered: 2026-03-28*
