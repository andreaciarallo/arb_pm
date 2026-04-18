---
phase: 05-fix-token-id-execution-wiring
plan: "02"
subsystem: execution
tags: [token-id, execution-engine, vwap, gate-0, gate-1, order-book, fak, kelly]
dependency_graph:
  requires:
    - 05-01 (ArbitrageOpportunity.yes_token_id and no_token_id populated by detection engines)
  provides:
    - execute_opportunity() reads token IDs from opp (D-02 — Gate 0 no longer permanently skips)
    - Gate 1 VWAP uses fresh order book data via client.get_order_book (D-03 — WR-07 resolved)
    - Full execution path (FAK orders, retry-then-hedge, verify_fill_rest) now reachable
  affects:
    - src/bot/execution/engine.py (signature changed, Gate 1 upgraded)
    - tests/test_execution_engine.py (all 8 tests updated to match new signature and Gate 1)
tech_stack:
  added: []
  patterns:
    - run_in_executor(None, client.get_order_book, token_id) — wraps sync CLOB call in async context (consistent with order_client.py)
    - sorted(asks, key=lambda a: float(...)) ascending — CLOB returns asks descending (MEMORY.md critical finding)
    - Gate 0 reads opp fields into local vars — downstream legs (YES, NO, hedge) use same locals unchanged
key_files:
  created: []
  modified:
    - src/bot/execution/engine.py
    - tests/test_execution_engine.py
decisions:
  - "Token IDs bound as local vars (yes_token_id = opp.yes_token_id) immediately after arb_id setup — Gate 0 and all downstream legs use same locals, no changes needed to YES/NO/hedge leg code"
  - "target_size computed in Gate 1 for VWAP; Gate 2 (Kelly) recomputes it — harmless duplicate, keeps Gate 2 unchanged per plan constraint"
  - "_opp() defaults yes_token_id='yes_tok', no_token_id='no_tok' so Gate 0 passes in all tests; each test then controls skip behavior via order book mock prices"
  - "Test 1 VWAP skip uses level.price='0.50' (not opp.vwap_yes) — VWAP now comes from fresh book, not opp fields"
metrics:
  duration_minutes: 12
  completed_date: "2026-04-18"
  tasks_completed: 2
  files_modified: 2
---

# Phase 05 Plan 02: Engine Signature Fix and Gate 1 VWAP Upgrade Summary

**One-liner:** Removed `yes_token_id`/`no_token_id` params from `execute_opportunity()` and replaced Gate 1's best-ask proxy with real multi-level VWAP using a fresh `client.get_order_book()` call, making all five EXEC and RISK-01 requirements reachable for the first time.

## What Was Built

**Change 1 — Function signature (D-02):** Removed `yes_token_id: str = ""` and `no_token_id: str = ""` from `execute_opportunity()`. Two local variable bindings (`yes_token_id = opp.yes_token_id`, `no_token_id = opp.no_token_id`) are assigned immediately after `results: list[ExecutionResult] = []`. Gate 0's check (`if not yes_token_id or not no_token_id:`) and all downstream legs (YES BUY, NO BUY retry loop, hedge SELL) continue to use these same local variables without any other changes.

**Change 2 — Gate 1 VWAP upgrade (D-03, resolves WR-07):** Replaced the entire WR-07 deferral block (which used `opp.vwap_yes`/`opp.vwap_no` as best-ask proxies) with a fresh order book fetch via `loop.run_in_executor(None, client.get_order_book, yes_token_id)` and the same for `no_token_id`. Asks are sorted ascending before being passed to the existing `simulate_vwap()` function (correcting for CLOB's descending sort order per MEMORY.md). Exception handling logs a warning and returns an early `skipped` result if the fetch fails.

**Change 3 — Test suite update:** Updated `_opp()` helper to accept `yes_token_id="yes_tok"` and `no_token_id="no_tok"` defaults and pass them to the `ArbitrageOpportunity` constructor. Removed `yes_token_id`/`no_token_id` kwargs from five `execute_opportunity()` call sites (Tests 3–7). Added `client.get_order_book.return_value = mock_book` to all 8 tests so Gate 1's fresh order book fetch succeeds. Test 1 uses `level.price = "0.50"` to produce `vwap_spread = 0.0` (below 1.5% threshold), reliably triggering the VWAP skip.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update engine.py — remove params, read from opp, upgrade Gate 1 VWAP | ba6aaa1 | src/bot/execution/engine.py |
| 2 | Update test_execution_engine.py — _opp() helper, 5 call sites, order book mocks | e93d1c0 | tests/test_execution_engine.py |

## Verification Results

```
20 passed in 1.37s

tests/test_execution_engine.py::test_vwap_gate_low_spread_skips PASSED
tests/test_execution_engine.py::test_kelly_zero_returns_skipped PASSED
tests/test_execution_engine.py::test_full_success_returns_two_filled_results PASSED
tests/test_execution_engine.py::test_yes_leg_fails_no_exposure PASSED
tests/test_execution_engine.py::test_no_leg_retry_then_hedge PASSED
tests/test_execution_engine.py::test_kill_switch_stops_no_retries PASSED
tests/test_execution_engine.py::test_yes_verify_false_aborts_no_leg PASSED
tests/test_execution_engine.py::test_vwap_gate_insufficient_depth_skips PASSED
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

Function signature verified:
```
['client', 'opp', 'config', 'risk_gate']
```

## Requirements Verified

| Req ID | Test | Result |
|--------|------|--------|
| EXEC-01 | test_full_success_returns_two_filled_results — FAK order called after Gate 0 passes | PASS |
| EXEC-02 | test_full_success_returns_two_filled_results — 2 filled results confirm FAK code reachable | PASS |
| EXEC-03 | test_no_leg_retry_then_hedge — hedge SELL triggered after 3 failed NO retries | PASS |
| EXEC-04 | test_yes_verify_false_aborts_no_leg — verify_fill_rest reachable and controls NO leg | PASS |
| RISK-01 | test_kelly_zero_returns_skipped — Kelly sizing evaluated after Gate 0+1 pass | PASS |

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Local var binding (not direct opp field access in downstream code) | Downstream legs already use `yes_token_id`/`no_token_id` locals — binding at top of function keeps all downstream code unchanged |
| `target_size` computed in both Gate 1 and Gate 2 | Gate 2 (Kelly) kept completely unchanged per plan constraint; harmless duplicate |
| `_opp()` defaults to `"yes_tok"`/`"no_tok"` (not `""`) | Ensures Gate 0 passes in all tests; skip behavior controlled by order book mock prices, not Gate 0 |
| Test 1 VWAP skip via `level.price = "0.50"` | VWAP now comes from fresh order book, not `opp.vwap_yes` — price controls the spread computation directly |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — token ID wiring is complete end-to-end for yes_no opportunities:
- Detection engine (`yes_no_arb.py`) populates `yes_token_id` and `no_token_id` from Polymarket API
- `ArbitrageOpportunity` dataclass stores both fields (Plan 01)
- `execute_opportunity()` reads both fields from `opp`, Gate 0 passes, FAK orders execute (this plan)

## Self-Check: PASSED

- [x] `src/bot/execution/engine.py` — `yes_token_id: str = ""` param NOT present in signature
- [x] `src/bot/execution/engine.py` — `yes_token_id = opp.yes_token_id` present at line 141
- [x] `src/bot/execution/engine.py` — `run_in_executor(None, client.get_order_book, yes_token_id)` present at line 176
- [x] `src/bot/execution/engine.py` — WR-07 deferral NOTE block removed (only "resolves WR-07" reference remains)
- [x] `tests/test_execution_engine.py` — `yes_token_id="yes_tok"` default in `_opp()` helper
- [x] `tests/test_execution_engine.py` — no `yes_token_id` kwargs on any `execute_opportunity()` call site
- [x] `tests/test_execution_engine.py` — `client.get_order_book.return_value` set in all 8 tests
- [x] Commit ba6aaa1 exists (Task 1)
- [x] Commit e93d1c0 exists (Task 2)
- [x] 20 tests pass (8 engine + 7 yes_no_arb + 5 cross_market)
- [x] Function signature: `['client', 'opp', 'config', 'risk_gate']`
