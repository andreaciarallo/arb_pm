---
phase: 03-execution-risk-controls
plan: 01
subsystem: execution
tags: [kelly, position-sizing, risk-controls, tdd, config]

# Dependency graph
requires:
  - phase: 02-detection-engine
    provides: "BotConfig dataclass with Phase 2 scanning fields (fee_pct_default etc.)"
provides:
  - "kelly_size() function: Modified Kelly position sizing with all edge-case guards"
  - "BotConfig Phase 3 fields: total_capital_usd, kelly_min_order_usd, kelly_max_capital_pct, daily_stop_loss_pct, circuit_breaker_error_count, circuit_breaker_window_seconds, circuit_breaker_cooldown_seconds"
  - "src/bot/execution/ package: new execution subsystem package"
affects:
  - 03-02-PLAN  # FAK order execution uses kelly_size() output
  - 03-03-PLAN  # Retry/hedge uses kelly_size() to size positions
  - 03-04-PLAN  # Stop-loss uses daily_stop_loss_pct from BotConfig
  - 03-05-PLAN  # Circuit breaker uses circuit_breaker_* fields from BotConfig

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Modified Kelly formula: f = (b*p - q) / (b*sqrt(p)) from arxiv 2508.03474"
    - "Return 0.0 on all edge cases — caller skips the trade, never force minimum"
    - "Hard constraints applied after formula: min(size, depth*0.5, capital*max_pct)"
    - "TDD pattern: RED commit then GREEN commit for position sizing primitives"

key-files:
  created:
    - src/bot/execution/__init__.py
    - src/bot/execution/kelly.py
    - tests/test_kelly.py
  modified:
    - src/bot/config.py

key-decisions:
  - "kelly_size() returns 0.0 (not $5 floor) when Kelly formula yields below-minimum — caller decides to skip"
  - "Modified Kelly uses sqrt(p) in denominator (arxiv 2508.03474) not standard Kelly denominator"
  - "p = min(1.0, depth/target_size) as execution probability proxy — simple, no order book walk needed"
  - "Hard constraints applied after formula: depth cap 50%, capital cap 5% (D-01)"

patterns-established:
  - "Pattern 1: All execution primitives in src/bot/execution/ package"
  - "Pattern 2: Edge cases return sentinel 0.0 — callers must check, never auto-promote"
  - "Pattern 3: BotConfig frozen dataclass extended with defaults — no new required env vars"

requirements-completed: [RISK-01]

# Metrics
duration: 7min
completed: 2026-03-29
---

# Phase 3 Plan 01: Kelly Position Sizing Summary

**Modified Kelly formula (arxiv 2508.03474) with 5 edge-case guards, depth/capital hard caps, and $5 floor — returns 0.0 to skip trades with negative expected value**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-03-29T16:46:40Z
- **Completed:** 2026-03-29T16:53:00Z
- **Tasks:** 2 (RED + GREEN TDD)
- **Files modified:** 4

## Accomplishments

- Implemented `kelly_size()` with Modified Kelly formula (D-01) using execution probability proxy `p = min(1.0, depth/target_size)`
- Extended `BotConfig` with 7 Phase 3 risk parameter fields (total_capital_usd, kelly_min_order_usd, kelly_max_capital_pct, daily_stop_loss_pct, circuit_breaker_error_count, circuit_breaker_window_seconds, circuit_breaker_cooldown_seconds)
- Created `src/bot/execution/` package as the execution subsystem home for Phase 3 plans
- All 9 TDD tests green; 60 existing tests pass with zero new regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — Write failing tests for kelly_size()** - `47ec4a7` (test)
2. **Task 2: GREEN — Extend BotConfig + implement kelly_size()** - `473e7d1` (feat)

_Note: TDD tasks use test then feat commit pattern_

## Files Created/Modified

- `src/bot/execution/__init__.py` — New execution package init
- `src/bot/execution/kelly.py` — Modified Kelly position sizer with all edge-case guards
- `src/bot/config.py` — Extended with 7 Phase 3 risk parameter fields (defaults only, no new env vars)
- `tests/test_kelly.py` — 9-test TDD suite covering normal case, all 5 edge cases, depth cap, capital cap, floor

## Decisions Made

- `kelly_size()` returns `0.0` (not `min_order_usd`) when Kelly formula or constraints yield below-floor — the caller must skip the trade entirely; never auto-promote to minimum (D-01)
- Formula uses `sqrt(p)` in denominator per arxiv 2508.03474 (Modified Kelly), not standard Kelly `b` denominator
- Execution probability `p = min(1.0, depth/target_size)` — simple proxy, no full order book walk needed at sizing stage

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

Pre-existing failure discovered (out of scope): `tests/test_market_filter.py::test_fetch_liquid_markets_filters_by_volume` fails because mock market data doesn't set `active`, `enable_order_book`, `accepting_orders=True`. Confirmed pre-existing via git stash verification. Logged to `deferred-items.md`. Not caused by this plan's changes.

## User Setup Required

None — no external service configuration required. All new BotConfig fields have defaults.

## Next Phase Readiness

- `kelly_size()` is ready for consumption by Plan 03-02 (FAK order execution)
- `BotConfig.daily_stop_loss_pct` available for Plan 03-04 (stop-loss)
- `BotConfig.circuit_breaker_*` fields available for Plan 03-05 (circuit breaker)
- No blockers for subsequent Phase 3 plans

## Self-Check: PASSED

- FOUND: src/bot/execution/__init__.py
- FOUND: src/bot/execution/kelly.py
- FOUND: tests/test_kelly.py
- FOUND: 03-01-SUMMARY.md
- FOUND: 47ec4a7 (RED commit)
- FOUND: 473e7d1 (GREEN commit)
- 6 `return 0.0` occurrences (5 edge-case guards + 1 floor check)
- `def kelly_size` present in kelly.py
- `total_capital_usd` present in config.py
- `round(size, 2)` present in kelly.py

---
*Phase: 03-execution-risk-controls*
*Completed: 2026-03-29*
