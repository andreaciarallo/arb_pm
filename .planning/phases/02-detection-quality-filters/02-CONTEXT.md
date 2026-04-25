# Phase 2: Detection Quality Filters - Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase adds quality filters to the existing YES/NO and cross-market detection pipeline to eliminate ~93% of false-positive opportunities caused by dead markets ($0.001 asks), near-resolved markets, degenerate cross-market groups, and repeated logging of the same opportunity across scan cycles. No new detection types or execution logic — filters only.

</domain>

<decisions>
## Implementation Decisions

### Deduplication Strategy
- **D-01:** Dedup key is `(market_id, opportunity_type)` — YES/NO and cross-market detections on the same market are tracked independently
- **D-02:** Dedup state is an in-memory dict mapping `(market_id, type)` → `last_seen` timestamp. Resets on bot restart. Zero I/O overhead in hot detection path.
- **D-03:** Default dedup time window is 5 minutes (~10 scan cycles at 30s interval), configurable via `BotConfig.dedup_window_seconds`

### Threshold Configuration
- **D-04:** All filter thresholds are `BotConfig` fields with REQUIREMENTS values as defaults:
  - `min_ask_floor: float = 0.03` (DETECT-01: YES/NO ask floor)
  - `max_ask_sum: float = 0.99` (DETECT-02: YES/NO sum cap)
  - `min_cross_leg_ask: float = 0.005` (DETECT-03: cross-market leg floor)
  - `min_cross_total_yes: float = 0.10` (DETECT-04: cross-market group floor)
  - `dedup_window_seconds: int = 300` (DETECT-05: dedup window)
- **D-05:** Follows the established `BotConfig` frozen dataclass pattern — consistent with `min_order_book_depth`, `fee_pct_*`, etc.

### Rejection Telemetry
- **D-06:** Two-level reporting: summary counters at INFO level (always visible) plus per-rejection detail at DEBUG level (opt-in via log level)
- **D-07:** Each filter type has its own diagnostic counter: `ask_floor_rejects`, `sum_cap_rejects`, `leg_floor_rejects`, `total_yes_rejects`, `dedup_suppressed`
- **D-08:** Dedup suppression count is added to the cycle summary log line in `dry_run.py` — visible signal that dedup is working without checking DEBUG logs

### Filter Architecture
- **D-09:** New module `src/bot/detection/filters.py` containing all quality filters and dedup logic in one place
- **D-10:** Threshold filters are stateless functions; dedup is a stateful class/function (manages timestamp dict) — both colocated in `filters.py`
- **D-11:** Detectors (`yes_no_arb.py`, `cross_market.py`) import and call filter functions before appending to the opportunities list. Filtered opps never leave the detector.
- **D-12:** Filter diagnostic counters are returned alongside detection results for cycle-level reporting

### Claude's Discretion
- Internal organization of `filters.py` (function signatures, class vs module-level dict for dedup state)
- How counters are returned from detectors (separate return value, dataclass, or dict)
- Exact DEBUG log format for per-rejection messages

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — DETECT-01 through DETECT-05 define exact threshold values and behavior

### Existing Detection Code
- `src/bot/detection/yes_no_arb.py` — Current YES/NO detector with existing gate pattern (resolved guard, depth check, spread threshold, diagnostic counters)
- `src/bot/detection/cross_market.py` — Current cross-market detector with event grouping, depth gate, and exclusivity check
- `src/bot/detection/opportunity.py` — ArbitrageOpportunity dataclass (filter target)
- `src/bot/detection/fee_model.py` — Category-aware fee model used by both detectors

### Configuration
- `src/bot/config.py` — BotConfig frozen dataclass pattern; new threshold fields go here

### Scan Loop
- `src/bot/dry_run.py` — Orchestrator that calls detectors and logs results; cycle summary log line needs dedup count

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BotConfig` frozen dataclass in `config.py` — established pattern for all configurable params
- Diagnostic counter pattern in `yes_no_arb.py` (`both_cached`, `depth_fails`, `spread_fails`) — extend to new filter counters
- `PriceCache.get()` returns price objects with `.yes_ask`, `.yes_depth` — filter functions receive these

### Established Patterns
- Gate-style filtering: each check is a sequential `if ... continue` block inside the detection loop
- Loguru for all logging (`logger.info`, `logger.debug`)
- Module-level caches populated at startup (`_event_groups` dict in `cross_market.py`)

### Integration Points
- `detect_yes_no_opportunities()` — add filter calls before appending to `opportunities` list
- `detect_cross_market_opportunities()` — add filter calls before appending to `opportunities` list
- `dry_run.py` cycle summary log line — add `dedup_suppressed=N`
- `BotConfig` dataclass — add 5 new fields with defaults

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-detection-quality-filters*
*Context gathered: 2026-04-25*
