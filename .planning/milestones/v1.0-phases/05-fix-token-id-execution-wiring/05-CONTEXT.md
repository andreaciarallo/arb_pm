# Phase 5: Fix Token ID Execution Wiring — Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Patch the TOKEN-ID-GAP integration gap so live trade execution actually fires. `ArbitrageOpportunity` must carry `yes_token_id` and `no_token_id` through to `engine.py` Gate 0, which currently returns `status='skipped'` on every opportunity because token IDs are always empty strings.

Also includes: upgrade VWAP Gate 1 from best_ask proxy to real multi-level simulation using a fresh order book snapshot.

Phase ends when at least one simulated FAK order call is reached in a live-mode dry run, verified via logs.

**Out of scope:** Cross-market execution engine (N-way YES arb), Telegram alerts (Phase 6), full Bregman optimization.

</domain>

<decisions>
## Implementation Decisions

### D-01: Cross-market `no_token_id` handling
Cross-market opportunities (`opportunity_type="cross_market"`) involve buying YES tokens across multiple mutually exclusive markets — there is no NO token. `no_token_id` will be set to `""` (empty string) on all cross-market `ArbitrageOpportunity` instances. Gate 0 in `engine.py` keeps its existing "both token IDs required" rule — cross-market opps will still be skipped at Gate 0.

**Rationale:** Cross-market execution requires a different engine (multi-leg YES purchases). Phase 5 success is driven entirely through the yes_no arb path. Cross-market execution is deferred.

### D-02: Engine.py signature — remove explicit params, read from opp
Remove `yes_token_id: str = ""` and `no_token_id: str = ""` from `execute_opportunity()` function signature. Gate 0 reads `opp.yes_token_id` and `opp.no_token_id` directly from the opportunity dataclass.

**Impact:** All tests that pass `yes_token_id`/`no_token_id` as kwargs to `execute_opportunity()` must be updated to instead set those fields on the `ArbitrageOpportunity` object passed as `opp`.

**Rationale:** Cleaner API — caller never passes token IDs separately since they're now on the dataclass. Eliminates the redundancy of having both a param and an opp field.

### D-03: VWAP — fetch fresh order book at execution time
Gate 1 (VWAP validation) is upgraded from the best_ask proxy to real multi-level VWAP simulation:

- `execute_opportunity()` calls `client.get_order_book(yes_token_id)` and `client.get_order_book(no_token_id)` right before Gate 1
- Order book asks/bids levels are extracted and passed to the existing `simulate_vwap()` function
- `simulate_vwap()` already accepts price levels — just needs real data wired in
- One extra API call per execution (acceptable — executions are rare relative to rate limits)
- The WR-07 deferral comment in `engine.py` is resolved and removed

**Rationale:** Fresh snapshot eliminates staleness from the detection→execution lag. `simulate_vwap()` already handles the computation; only the data source changes.

### Claude's Discretion
- How to extract price levels from `OrderBookSummary` object (`.asks` is list of objects with `.price`, `.size`)
- Order of Gate 0 vs order book fetch (fetch after Gate 0 passes, before Gate 1)
- Error handling if order book fetch fails (log + skip opportunity)
- Test mock strategy for the fresh order book fetch
- Whether to update the WR-07 comment or remove it

</decisions>

<open_topics>
## Open Topics

None. All decisions locked above.

</open_topics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit
- `.planning/v1.0-MILESTONE-AUDIT.md` — Full gap analysis with exact file+line evidence for TOKEN-ID-GAP (critical section: lines 55-64 of gaps.integration)

### Code files with the bug
- `src/bot/detection/opportunity.py` — ArbitrageOpportunity dataclass (add yes_token_id, no_token_id fields)
- `src/bot/detection/yes_no_arb.py` lines 60-67 — token IDs as local vars, not stored in returned opp
- `src/bot/detection/cross_market.py` line 117 — same pattern (no_token_id="" acceptable here)
- `src/bot/live_run.py` line 297 — execute_opportunity() call site (no token ID args needed once on opp)
- `src/bot/execution/engine.py` lines 115-162 — function signature + Gate 0 + Gate 1 (WR-07 VWAP)

### Prior phase decisions
- `.planning/phases/03-execution-risk-controls/03-CONTEXT.md` — D-02 (FAK pattern), D-03 (retry-then-hedge), D-05 (VWAP gate intent)
- `.planning/phases/02-market-data-detection/02-CONTEXT.md` — MarketPrice structure, OrderBookSummary access patterns

### Tech stack
- `CLAUDE.md` — py-clob-client, loguru, SQLite

</canonical_refs>

<specifics>
## Specific Behaviors

- **yes_no_arb.py**: `yes_token_id` and `no_token_id` are already resolved as local variables — they just need to be passed to the `ArbitrageOpportunity` constructor
- **cross_market.py**: Set `yes_token_id=group[0]'s YES token ID` (or leave `""`) and `no_token_id=""` — cross-market opps stay skipped at Gate 0, which is intentional
- **opportunity.py**: Fields should have `str` type with `""` default so existing code constructing opps without token IDs continues to work (or explicit defaults to avoid breaking callers)
- **engine.py**: Order of operations after D-03 — Gate 0 (token ID check) → fresh order book fetch → Gate 1 (VWAP with real data) → Kelly → order submission
- **Test updates**: Any test using `execute_opportunity(..., yes_token_id="...", no_token_id="...")` must instead build the opp with those fields set

</specifics>

<deferred>
## Deferred

- **Cross-market execution** — N-way YES arb needs its own execution engine (Phase 5 only fixes yes_no path)
- **Real VWAP for cross-market** — cross-market opps don't reach Gate 1 (blocked at Gate 0), so no VWAP needed there
- **Phase 6** — Telegram kill switch + circuit breaker alerts (separate phase)

</deferred>

---

*Phase: 05-fix-token-id-execution-wiring*
*Context gathered: 2026-04-18*
