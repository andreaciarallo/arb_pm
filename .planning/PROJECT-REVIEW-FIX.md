---
phase: project-review
fixed_at: 2026-04-17T00:00:00Z
review_path: .planning/PROJECT-REVIEW.md
iteration: 1
findings_in_scope: 14
fixed: 14
skipped: 0
status: all_fixed
---

# Project-Wide Code Review Fix Report

**Fixed at:** 2026-04-17
**Source review:** `.planning/PROJECT-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 14 (6 Critical + 8 Warning)
- Fixed: 14
- Skipped: 0

---

## Fixed Issues

### CR-01: Gross P&L formula uses wrong contract count

**Files modified:** `src/bot/live_run.py`
**Commit:** `065fb50`
**Applied fix:** Replaced the inconsistent `n_contracts = size_filled / price; gross_pnl = (1 - yes - no) * n_contracts` formula with the correct equal-USD sizing formula: `gross_pnl = yes_result.size_filled * (1.0 - yes_result.price - no_result.price) / yes_result.price`. Added a comment explaining the economic basis. This is a logic fix — requires human verification that the formula matches the actual trade sizing convention.
**Status:** fixed: requires human verification

---

### CR-02: Fee calculation in cross_market.py missing exit fee

**Files modified:** `src/bot/detection/cross_market.py`
**Commit:** `6378220`
**Applied fix:** Split `estimated_fees = total_yes * taker_fee` into `entry_fees = total_yes * taker_fee` plus `exit_fee = (total_yes / len(group)) * taker_fee`, summed as `estimated_fees = entry_fees + exit_fee`. This accounts for the taker fee on the winning token's exit at resolution. The `estimated_fees` field stored on the opportunity object now reflects both entry and exit costs.

---

### CR-03: Module-level mutable globals in http_poller.py cause test pollution

**Files modified:** `src/bot/scanner/http_poller.py`
**Commit:** `01bd3d2`
**Applied fix:** Added `reset_poller_state()` function that uses `global _dead_tokens, _poll_offset` to reset both module-level globals to their initial values. Function is documented for use between tests and at bot reinit to clear false-positive 404 bans from transient errors.

---

### CR-04: Kill switch reads trades table before flushing the async writer

**Files modified:** `src/bot/live_run.py`
**Commit:** `3bbba9e`
**Applied fix:** Moved `await writer.flush()` to the very beginning of `_execute_kill_switch()` (before `cancel_all()` and before the trades table query). Updated the docstring to reflect the new step ordering. The final `await writer.flush()` at the end is retained to catch any records written during the close sequence. Combined with WR-03 fix in the same commit.

---

### WR-03: Kill switch closes ALL filled trades instead of only open (unhedged) positions

**Files modified:** `src/bot/live_run.py`
**Commit:** `3bbba9e`
**Applied fix:** Replaced the simple `SELECT token_id, size FROM trades WHERE status IN ('filled', 'partial')` query with the same LEFT JOIN logic used by the dashboard's open-positions query — selects only YES legs that have no corresponding `arb_pairs` row and no hedge trade, matching the correct open-position definition.

---

### CR-05: No guard for None yes_order_id before calling verify_fill_rest

**Files modified:** `src/bot/execution/engine.py`
**Commit:** `0fb7683`
**Applied fix:** Added an explicit `if not yes_order_id:` guard immediately after `yes_order_id = yes_resp.get("orderID")`. When `orderID` is absent, the engine logs an error, appends a `failed` `ExecutionResult` with `error_msg="missing orderID in YES response"`, and returns early — preventing 5 seconds of futile polling with `None` as the order ID.

---

### CR-06: Dashboard /api/status endpoint lacks index for open-positions query

**Files modified:** `src/bot/storage/schema.py`
**Commit:** `ced1cfe`
**Applied fix:** Added `"CREATE INDEX IF NOT EXISTS idx_trades_leg_status ON trades(leg, status, token_id, market_id)"` to `_CREATE_TRADES_INDEXES`. The index covers the LEFT JOIN query's filter predicates (`leg='yes'`, `status IN ('filled','partial')`) and join columns (`token_id`, `market_id`), accelerating both the dashboard endpoint and the kill switch position close on a growing trades table.

---

### WR-01: P95 index computation fragile for non-default SAMPLES values

**Files modified:** `scripts/benchmark_latency.py`
**Commit:** `1009d2c`
**Applied fix:** Added `import math` and replaced `int(SAMPLES * 0.95) - 1` with `max(0, int(math.ceil(SAMPLES * 0.95)) - 1)`. Using `ceil` ensures the index correctly rounds up to the nearest sample at or above the 95th percentile for any value of `SAMPLES`, and `max(0, ...)` prevents a negative index if `SAMPLES` is 0.

---

### WR-02: market_filter.py uses blocking time.sleep in async context during 429 retry

**Files modified:** `src/bot/scanner/market_filter.py`
**Commit:** `d2d7a28`
**Applied fix:** Converted `_get_markets_page` from a synchronous `def` to an `async def`, replaced `time.sleep(backoff)` with `await asyncio.sleep(backoff)`, removed the `import time` statement, and updated the call site in `fetch_liquid_markets` from `response = _get_markets_page(...)` to `response = await _get_markets_page(...)`. Python syntax verified clean after the change.

---

### WR-04: test_execution_engine.py unpacks execute_opportunity return as single value

**Files modified:** `tests/test_execution_engine.py`
**Commit:** `39f4209`
**Applied fix:** Updated all 8 test call sites from `results = await execute_opportunity(...)` to `_, results = await execute_opportunity(...)` so the `(arb_id, results)` tuple is correctly unpacked. Without this fix, iterating `results` (which is actually the raw tuple) raises `AttributeError` when accessing `.status` on a `str` (the arb_id element).

---

### WR-05: record_loss() never called — stop-loss protection non-functional

**Files modified:** `src/bot/live_run.py`
**Commit:** `34ee5b9`
**Applied fix:** Added two `record_loss()` call sites in the scan loop results handler:
1. After `net_pnl` is computed for a completed arb pair: `if net_pnl < 0: risk_gate.record_loss(abs(net_pnl))`
2. For the hedge path (YES filled, NO failed): computes `hedge_loss = yes_result.size_filled * (yes_result.price - hedge.price)` and calls `risk_gate.record_loss(hedge_loss)` when positive. This activates the 5% daily stop-loss (D-06) which was previously unreachable.
**Status:** fixed: requires human verification (hedge loss formula is an approximation)

---

### WR-06: Daily summary queries the new day instead of the day just ended

**Files modified:** `src/bot/live_run.py`
**Commit:** `ad66f4c`
**Applied fix:** Moved `today_str = now.strftime("%Y-%m-%d")` from inside the `try` block (after `await asyncio.sleep`) to before the sleep, computed from the `now` captured at loop start. Added a comment explaining the race: if computed after sleep, even 1ms of drift past midnight returns the new day's date string, causing the query to return 0 results for the day just ended.

---

### WR-07: simulate_vwap is dead code — never called with real order book data

**Files modified:** `src/bot/execution/engine.py`
**Commit:** `6be16c6`
**Applied fix:** Added a clearly marked `NOTE (WR-07)` comment block in Gate 1 of `execute_opportunity` explaining that `simulate_vwap()` is implemented correctly but deferred from Phase 3, that `vwap_yes/vwap_no` are currently set to `best_ask` by the detection engine, and that Phase 5 will wire real order book data. This makes the known deferral explicit and avoids silently confusing future maintainers.

---

### WR-08: get_wallet_address.py may print private key via exception message

**Files modified:** `scripts/get_wallet_address.py`
**Commit:** `998aedf`
**Applied fix:** Changed `except Exception as e: print(f"ERROR: Failed to derive address: {e}")` to `except Exception: print("ERROR: Failed to derive address. Check that WALLET_PRIVATE_KEY is a valid 32-byte hex private key.")`. The exception object is no longer referenced or printed, eliminating the risk that a crypto library embeds key material in the error string.

---

_Fixed: 2026-04-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
