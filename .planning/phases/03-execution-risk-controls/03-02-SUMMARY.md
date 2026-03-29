---
phase: 03-execution-risk-controls
plan: "02"
subsystem: execution/order-client
tags: [tdd, fak-orders, fill-verification, asyncio, rest-polling]
dependency_graph:
  requires: [03-01]
  provides: [place_fak_order, verify_fill_rest]
  affects: [03-03, 03-04, 03-05]
tech_stack:
  added: []
  patterns: [run_in_executor, FAK-two-step, REST-poll-verification]
key_files:
  created:
    - src/bot/execution/order_client.py
    - tests/test_order_client.py
  modified: []
decisions:
  - "PolyApiException(error_msg=...) — status_code kwarg not supported in SDK 0.34.6; plan documented wrong constructor signature"
  - "create_and_post_order in docstring comments only — executable code is FAK-only; runtime test confirms it is never called"
metrics:
  duration_seconds: 169
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
requirements_addressed: [EXEC-01, EXEC-02, EXEC-04]
---

# Phase 03 Plan 02: FAK Order Client and REST Fill Verification Summary

**One-liner:** FAK order placement via create_order+post_order(FAK) and REST poll verification with 500ms intervals and 5s timeout, all wrapped in run_in_executor.

## What Was Built

Two async functions in `src/bot/execution/order_client.py`:

- `place_fak_order(client, token_id, price, size_usd, side)` — two-step FAK pattern: create_order() for local EIP-712 signing, then post_order(FAK) for REST submission. Returns response dict on success, None on any exception.
- `verify_fill_rest(client, order_id, timeout_seconds=5.0)` — polls get_order() every 500ms for up to 10 iterations. Returns True when size_matched > 0, False on timeout.

All three py-clob-client calls (create_order, post_order, get_order) are wrapped in `asyncio.run_in_executor()` to avoid blocking the event loop.

## TDD Execution

**RED (Task 1):** Created 9 failing tests in `tests/test_order_client.py`. All tests failed with `ModuleNotFoundError: No module named 'bot.execution.order_client'`.

**GREEN (Task 2):** Implemented `order_client.py` per plan spec. 9/9 tests pass.

## Test Results

| Test | Status |
|------|--------|
| test_place_fak_order_success | PASS |
| test_place_fak_order_uses_fak_not_gtc | PASS |
| test_place_fak_order_poly_exception_returns_none | PASS |
| test_place_fak_order_generic_exception_returns_none | PASS |
| test_verify_fill_rest_success_first_poll | PASS |
| test_verify_fill_rest_timeout_all_unmatched | PASS |
| test_verify_fill_rest_false_on_zero_size_matched | PASS |
| test_place_fak_order_is_async | PASS |
| test_place_fak_order_never_calls_create_and_post_order | PASS |

Full suite: 70 passed, 5 skipped, 4 pre-existing failures in test_market_filter.py (not caused by this plan).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 (RED) | fa9cee1 | test(03-02): add failing tests for order_client |
| Task 2 (GREEN) | 89ce4ab | feat(03-02): implement order_client with place_fak_order and verify_fill_rest |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed PolyApiException constructor call in test**
- **Found during:** Task 2 (GREEN phase, first test run)
- **Issue:** Plan documented `PolyApiException(status_code=400, error_msg="rejected")` but actual SDK 0.34.6 signature is `PolyApiException(resp=Optional[httpx.Response], error_msg=None)` — `status_code` is not a constructor kwarg
- **Fix:** Changed to `PolyApiException(error_msg="rejected")` in test_order_client.py
- **Files modified:** tests/test_order_client.py (line 58)
- **Commit:** 89ce4ab (included in GREEN commit)

## Known Stubs

None — `place_fak_order` and `verify_fill_rest` are fully implemented with no placeholder logic.

## Self-Check

- FOUND: src/bot/execution/order_client.py
- FOUND: tests/test_order_client.py
- FOUND: commit fa9cee1 (RED)
- FOUND: commit 89ce4ab (GREEN)

## Self-Check: PASSED
