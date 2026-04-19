---
phase: 01-research-polymarket-market-mechanics-and-arb-math-to-fix-cro
plan: 03
subsystem: execution
tags: [cross-market, execution-engine, equal-shares, partial-hedge, tdd]
dependency_graph:
  requires: [01-01, 01-02]
  provides: [cross-market-execution-path]
  affects: [engine.py, opportunity.py, cross_market.py]
tech_stack:
  added: []
  patterns:
    - Equal-shares cross-market sizing (target_shares = kelly_usd / total_yes)
    - Partial fill hedge via FAK SELL at price=0.01 for previously filled legs
    - Gate 0 dual-routing: cross_market with legs → _execute_cross_market(); YES+NO unchanged
key_files:
  created: []
  modified:
    - src/bot/detection/opportunity.py
    - src/bot/detection/cross_market.py
    - src/bot/execution/engine.py
    - tests/test_execution_engine.py
decisions:
  - id: D-CM-01
    summary: Equal shares not equal dollars — target_shares = kelly_usd / total_yes; size_usd_i = ask_i * target_shares
  - id: D-CM-02
    summary: Partial hedge sells ALL previously filled legs at price=0.01 (market-aggressive FAK SELL) if any leg fails
  - id: D-CM-03
    summary: Gate 0 routing is explicit on opportunity_type to prevent YES+NO bypass — both conditions required (type==cross_market AND legs populated)
metrics:
  duration: 918s
  completed: 2026-04-19
  tasks_completed: 2
  tasks_total: 2
  files_modified: 4
---

# Phase 01 Plan 03: Cross-Market Execution Wiring Summary

**One-liner:** Equal-shares cross-market execution via `_execute_cross_market()` with per-leg FAK BUY orders and partial-fill hedge SELL at price=0.01, gated by Gate 0 routing on `opportunity_type == "cross_market" and opp.legs`.

## What Was Built

### Task 1: legs field on ArbitrageOpportunity + cross_market.py population

Added `legs: list = field(default_factory=list)` to `ArbitrageOpportunity` as the last field, with `field` imported from `dataclasses`. In `cross_market.py`, added `legs_data: list[dict] = []` alongside `yes_asks`/`depths`/`categories` and populated it per market iteration with `{"token_id": yes_token_id, "ask": price.yes_ask, "depth": price.yes_depth}`. Passed `legs=legs_data` to the `ArbitrageOpportunity` constructor. Cross-market opportunities now carry all YES token IDs, ask prices, and depths needed for execution.

### Task 2: Gate 0 routing + _execute_cross_market() implementation

**Gate 0 change (before → after):**

Before:
```python
if not yes_token_id or not no_token_id:
    # skip with "missing token IDs"
```

After:
```python
# Cross-market routing (bypasses token ID check when legs populated)
if opp.opportunity_type == "cross_market" and opp.legs:
    return await _execute_cross_market(client, opp, config, risk_gate, arb_id, results)

if not yes_token_id or not no_token_id:
    # skip with "missing token IDs" — YES+NO path unchanged
```

**Sizing formula used:**
```python
total_yes = sum(leg["ask"] for leg in opp.legs)
kelly_usd = config.total_capital_usd * config.kelly_max_capital_pct
target_shares = kelly_usd / total_yes   # equal shares per leg
size_usd_i = leg["ask"] * target_shares  # proportional dollar amount
```

Example (from test): legs=[0.40, 0.25], kelly_usd=50, total_yes=0.65
- target_shares = 50/0.65 = 76.92
- Leg A: size_usd = 0.40 * 76.92 = $30.77 → 76.92 YES-A tokens
- Leg B: size_usd = 0.25 * 76.92 = $19.23 → 76.92 YES-B tokens
- Regardless of winner: payout = 76.92 * $1.00 = $76.92. Profit = $76.92 - $50.00 = $26.92.

**Partial hedge:** `test_cross_market_partial_hedge` confirms that when leg 2 fails after leg 1 fills, a SELL FAK order is placed for leg 1 at price=0.01. Verified: mock_fak called 3 times (leg1 BUY → leg2 BUY → leg1 SELL hedge). Result statuses: "filled", "failed", "hedged".

## Test Results

- **Tests added:** 3 (`test_cross_market_equal_shares`, `test_cross_market_partial_hedge`, `test_yes_no_missing_token_still_skips`)
- **Tests passing:** 13/13 in `test_execution_engine.py`
- **Full suite:** 106/106 unit tests passing
- **TDD cycle:** RED confirmed (2 new tests failed before implementation), GREEN after implementation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_cross_market_partial_hedge side_effect returned None for hedge SELL**

- **Found during:** Task 2 GREEN phase — test failed with `AssertionError: 'hedged' not in ['filled', 'failed', 'failed']`
- **Issue:** The plan's test code used `return None` for all calls after call 1, including the hedge SELL. Since `engine.py` sets `status = "hedged" if hedge_resp else "failed"`, a `None` hedge response produced `"failed"` not `"hedged"`. The test assertion `assert "hedged" in statuses` then failed.
- **Fix:** Added `if side == "SELL": return {"orderID": "hedge_order", "status": "matched"}` to the side_effect, matching the pattern used in `test_no_leg_retry_then_hedge`.
- **Files modified:** `tests/test_execution_engine.py`
- **Commit:** `581f150`

## Known Stubs

None. All execution paths are wired to `place_fak_order()`. The `legs` field is populated by `cross_market.py` from real price cache data. No hardcoded empty values flow to UI or decision logic.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. `_execute_cross_market()` uses the same `place_fak_order()` function as the YES+NO path — no new external interfaces.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/bot/detection/opportunity.py | FOUND |
| src/bot/detection/cross_market.py | FOUND |
| src/bot/execution/engine.py | FOUND |
| tests/test_execution_engine.py | FOUND |
| 01-03-SUMMARY.md | FOUND |
| commit 688fc9e (Task 1) | FOUND |
| commit 581f150 (Task 2) | FOUND |
