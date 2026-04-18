---
phase: 08-fix-circuit-breaker-alert-accuracy
plan: 02
subsystem: execution-engine
tags: [circuit-breaker, risk-management, tdd, bug-fix]
requirements: [RISK-03]
dependency_graph:
  requires: []
  provides: [RISK-03-no-leg-cb-wiring]
  affects: [src/bot/execution/engine.py, tests/test_execution_engine.py]
tech_stack:
  added: []
  patterns: [hasattr-guard, tdd-red-green]
key_files:
  created: []
  modified:
    - src/bot/execution/engine.py
    - tests/test_execution_engine.py
decisions:
  - "Use hasattr guard pattern (matching line 327) for backward-compatible CB notification on NO exhaustion"
  - "Insert record_order_error() call before logger.warning (error established at retry exhaustion, before hedge runs — D-01)"
metrics:
  duration: "~8 minutes"
  completed: "2026-04-18T18:23:19Z"
  tasks_completed: 2
  files_modified: 2
---

# Phase 8 Plan 02: Fix NO-Leg Circuit Breaker Wiring (RISK-03) Summary

**One-liner:** 2-line `hasattr` guard inserted before hedge SELL in `if not no_filled:` block so NO-leg retry exhaustion now notifies the circuit breaker sliding window.

## What Was Built

Added `record_order_error()` call to the NO-leg exhaustion path in `engine.py`. When all 3 NO-leg retries fail, the circuit breaker is now notified before the hedge SELL executes. This mirrors the identical `hasattr` guard pattern already present at line 327 for the YES verify failure path.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (TDD RED) | Add RISK-03 tests to test_execution_engine.py | 8f49f4c | tests/test_execution_engine.py |
| 2 (TDD GREEN) | Wire record_order_error() to NO exhaustion path | 7bbf690 | src/bot/execution/engine.py |

## Decisions Made

1. **hasattr guard pattern** — Used `if hasattr(risk_gate, "record_order_error"):` matching the existing guard at line 327. This keeps backward compatibility if a caller passes a risk_gate without this method.
2. **Placement before logger.warning** — record_order_error() is called at the top of the `if not no_filled:` block, before the hedge SELL and its logger.warning. Error is recorded at retry exhaustion, not after hedge outcome (D-01: error established when NO retries are truly exhausted).

## Verification Results

```
pytest tests/test_execution_engine.py tests/test_risk_gate.py -x -v
28 passed in 2.38s
```

Static grep confirmations:
- `grep -c "hasattr(risk_gate" src/bot/execution/engine.py` → **2** (YES verify + NO exhaustion)
- `grep -c "record_order_error" src/bot/execution/engine.py` → **4** (2 hasattr checks + 2 calls)
- hasattr guard at line 421 precedes `NO leg exhausted` at line 424

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all wiring is live. The hasattr guard is intentional backward-compat pattern, not a stub.

## Self-Check: PASSED

- [x] `src/bot/execution/engine.py` modified — verified with grep (hasattr at lines 327, 421)
- [x] `tests/test_execution_engine.py` modified — test names found at lines 304, 344
- [x] Commit 8f49f4c exists — TDD RED phase (test file)
- [x] Commit 7bbf690 exists — TDD GREEN phase (engine.py fix)
- [x] All 28 tests pass (10 engine + 18 risk gate)
- [x] RISK-03 gap closed: NO-leg retry exhaustion now notifies circuit breaker
