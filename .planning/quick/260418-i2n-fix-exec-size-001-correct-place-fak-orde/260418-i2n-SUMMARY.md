---
phase: quick
plan: 260418-i2n
subsystem: execution
tags: [bug-fix, order-client, tdd, exec-size-001]
dependency_graph:
  requires: []
  provides: [correct-fak-order-sizing]
  affects: [src/bot/execution/order_client.py, tests/test_order_client.py]
tech_stack:
  added: []
  patterns: [size_tokens = size_usd / price conversion before OrderArgs construction]
key_files:
  modified:
    - src/bot/execution/order_client.py
    - tests/test_order_client.py
decisions:
  - "size_tokens = size_usd / price computed in place_fak_order; callers continue to pass kelly_usd as size_usd (no engine.py changes needed)"
  - "ExecutionResult.size stores kelly_usd (USD exposure for P&L logging), not token count — this is correct and unchanged"
metrics:
  duration: ~6 minutes
  completed_date: "2026-04-18T11:06:12Z"
  tasks_completed: 1
  files_changed: 2
---

# Quick Task 260418-i2n: Fix EXEC-SIZE-001 — Correct place_fak_order Token Sizing

**One-liner:** Added `size_tokens = size_usd / price` conversion in `place_fak_order` so `OrderArgs.size` receives outcome token count instead of USD, fixing systematic under-sizing at sub-$1 prices.

---

## Objective

Fix EXEC-SIZE-001: `place_fak_order` was passing `size_usd` directly to `OrderArgs.size`, but the Polymarket CLOB interprets `size` as number of outcome tokens. At price 0.50, a $10 intent sent size=10 tokens ($5 actual spend) — half the intended capital per trade.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix size conversion + regression tests (TDD) | 7bfbd9f | src/bot/execution/order_client.py, tests/test_order_client.py |

---

## What Changed

### src/bot/execution/order_client.py

- Added `size_tokens = size_usd / price` immediately before `OrderArgs(...)` construction
- `OrderArgs` now receives `size=size_tokens` (token count) instead of `size=size_usd` (USD)
- Debug log updated to emit both `size_usd` and `size_tokens` for observability
- Docstring updated to document the internal conversion

### tests/test_order_client.py

Three new regression tests added (total: 12 tests, all passing):
- `test_place_fak_order_converts_usd_to_tokens` — size_usd=10.0, price=0.50 → size=20.0
- `test_place_fak_order_converts_usd_to_tokens_partial_price` — size_usd=5.0, price=0.40 → size=12.5
- `test_place_fak_order_converts_usd_to_tokens_price_one` — size_usd=5.0, price=1.0 → size=5.0 (identity)

---

## Verification

```
tests/test_order_client.py — 12 passed
Full suite — 130 passed, 5 skipped
```

All callers in `engine.py` correctly pass `kelly_usd` as `size_usd` — no engine changes needed.

---

## Deviations from Plan

None — plan executed exactly as written. `current-infrastructure.md` was gitignored so the EXEC-SIZE-001 status update there was applied locally but not committed (file is in `.gitignore`).

---

## Known Stubs

None.

---

## Self-Check: PASSED

- `src/bot/execution/order_client.py` — FOUND, contains `size_tokens = size_usd / price`
- `tests/test_order_client.py` — FOUND, contains all 3 new regression tests
- Commit `7bfbd9f` — FOUND in git log
- 12/12 tests pass, 130/130 full suite pass
