---
phase: 05-fix-token-id-execution-wiring
plan: "01"
subsystem: detection
tags: [token-id, arbitrage-opportunity, dataclass, yes-no-arb, cross-market]
dependency_graph:
  requires: []
  provides:
    - ArbitrageOpportunity.yes_token_id field (non-empty for yes_no opps)
    - ArbitrageOpportunity.no_token_id field (non-empty for yes_no opps)
    - yes_token_id wired from detection engine to dataclass
  affects:
    - src/bot/execution/engine.py (Gate 0 now receives non-empty token IDs — unblocks live execution)
tech_stack:
  added: []
  patterns:
    - Dataclass field ordering — fields with defaults must come after fields without; appended after detected_at
    - D-01 decision applied — cross_market sets no_token_id="" intentionally (no NO leg)
key_files:
  created: []
  modified:
    - src/bot/detection/opportunity.py
    - src/bot/detection/yes_no_arb.py
    - src/bot/detection/cross_market.py
    - tests/test_yes_no_arb.py
decisions:
  - "yes_token_id / no_token_id use str default \"\" (not None) — consistent with Gate 0 empty-string check in engine.py"
  - "cross_market captures group0_yes_token_id BEFORE inner for-market-in-group loop to avoid local var overwrite"
  - "no_token_id=\"\" for cross_market opps per D-01 — Gate 0 in engine.py will skip these (expected, not a bug)"
metrics:
  duration_minutes: 8
  completed_date: "2026-04-18"
  tasks_completed: 2
  files_modified: 4
---

# Phase 05 Plan 01: Extend ArbitrageOpportunity with Token ID Fields Summary

**One-liner:** Added `yes_token_id` and `no_token_id` str fields to `ArbitrageOpportunity` and wired them through both detection engines so Gate 0 in `engine.py` receives non-empty token IDs on yes_no opportunities.

## What Was Built

Two new string fields (`yes_token_id: str = ""` and `no_token_id: str = ""`) were appended to the `ArbitrageOpportunity` dataclass after `detected_at`, maintaining dataclass field ordering rules (fields with defaults after fields without).

`yes_no_arb.py` already resolved both token IDs in a local loop — the fix was simply passing them as constructor kwargs (`yes_token_id=yes_token_id, no_token_id=no_token_id`).

`cross_market.py` required extracting `group0_yes_token_id` from `group[0]`'s tokens *before* the inner `for market in group:` loop (which re-uses the local name `yes_token_id` and would overwrite it). The constructor now receives `yes_token_id=group0_yes_token_id, no_token_id=""` per D-01 (cross-market arb has no NO leg).

A new test `test_token_ids_populated` was added to `test_yes_no_arb.py`, asserting that both fields equal the specific token IDs from the market dict and are non-empty.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend ArbitrageOpportunity dataclass and wire detection engines | 42b6ebd | opportunity.py, yes_no_arb.py, cross_market.py |
| 2 | Add token_id population test to test_yes_no_arb.py | e47e1f1 | tests/test_yes_no_arb.py |

## Verification Results

```
12 passed in 0.03s
  tests/test_yes_no_arb.py::test_clear_arbitrage_detected PASSED
  tests/test_yes_no_arb.py::test_marginal_below_threshold_not_returned PASSED
  tests/test_yes_no_arb.py::test_resolved_market_skipped PASSED
  tests/test_yes_no_arb.py::test_insufficient_depth_skipped PASSED
  tests/test_yes_no_arb.py::test_missing_price_in_cache_skipped PASSED
  tests/test_yes_no_arb.py::test_geopolitics_lower_threshold PASSED
  tests/test_yes_no_arb.py::test_token_ids_populated PASSED
  tests/test_cross_market.py::test_exclusivity_constraint_detected PASSED
  tests/test_cross_market.py::test_unrelated_markets_not_grouped PASSED
  tests/test_cross_market.py::test_insufficient_depth_skips_group PASSED
  tests/test_cross_market.py::test_no_arb_when_sum_at_or_above_one PASSED
  tests/test_cross_market.py::test_single_market_group_not_returned PASSED
```

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `str = ""` default (not `Optional[str]`) | Matches Gate 0's existing empty-string check `if not yes_token_id` in engine.py |
| Capture `group0_yes_token_id` before inner loop | Inner loop reuses `yes_token_id` local var — capturing before the loop prevents overwrite |
| `no_token_id=""` for cross_market | D-01: cross-market opportunities buy YES-only across N markets; no NO leg exists |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all token ID fields are now populated from real Polymarket API data for yes_no opportunities. Cross-market `no_token_id=""` is intentional per D-01, documented in the constructor comment.

## Self-Check: PASSED

- [x] `src/bot/detection/opportunity.py` contains `yes_token_id: str = ""`
- [x] `src/bot/detection/opportunity.py` contains `no_token_id: str = ""`
- [x] `src/bot/detection/yes_no_arb.py` contains `yes_token_id=yes_token_id`
- [x] `src/bot/detection/cross_market.py` contains `group0_yes_token_id`
- [x] Commit 42b6ebd exists (Task 1)
- [x] Commit e47e1f1 exists (Task 2)
- [x] 12 tests pass (7 yes_no_arb + 5 cross_market)
