---
phase: 01-research-polymarket-market-mechanics-and-arb-math-to-fix-cro
plan: 04
subsystem: scanner-startup
tags: [cross-market, event-grouping, gamma-api, dry-run, live-run, tdd]
one_liner: "Wire load_event_groups() into both scanner runners so _event_groups is populated before the first detection cycle"

dependency_graph:
  requires:
    - 01-03-PLAN.md  # defined load_event_groups() in cross_market.py
  provides:
    - load_event_groups() called at startup in dry_run.run() and live_run.run()
    - UAT Test 4 gap closed: _event_groups non-empty at runtime
  affects:
    - src/bot/dry_run.py
    - src/bot/live_run.py
    - tests/test_dry_run.py
    - tests/test_live_run.py

tech_stack:
  added: []
  patterns:
    - "Belt-and-suspenders startup guard: outer try/except wraps load_event_groups() which already catches internally"
    - "TDD: RED commit (failing tests) then GREEN commit (implementation) then full suite verification"

key_files:
  created: []
  modified:
    - src/bot/dry_run.py
    - src/bot/live_run.py
    - tests/test_dry_run.py
    - tests/test_live_run.py

decisions:
  - "Call load_event_groups() after fetch_liquid_markets and before WebSocketClient in both runners — ensures mapping is ready before any detection cycle and before WS subscription begins"
  - "Outer try/except marked # pragma: no cover because load_event_groups() already swallows all exceptions internally; outer guard is belt-and-suspenders only"

metrics:
  duration: "11 minutes"
  completed_date: "2026-04-19T18:53:52Z"
  tasks_completed: 2
  files_modified: 4
  commits: 2
---

# Phase 01 Plan 04: Wire load_event_groups() at Scanner Startup — Summary

**One-liner:** Wire load_event_groups() into both scanner runners so _event_groups is populated before the first detection cycle.

## What Was Built

This plan closes the sole remaining UAT failure (Test 4): `_event_groups` was always `{}` at runtime because `load_event_groups()` — though defined in `cross_market.py` — was never called from the runner entrypoints.

### Files Modified

| File | Change |
|------|--------|
| `src/bot/dry_run.py` | Added `load_event_groups` to import; added startup call after `fetch_liquid_markets`, before `WebSocketClient` |
| `src/bot/live_run.py` | Added `load_event_groups` to import; added startup call after `fetch_liquid_markets`, before `WebSocketClient` |
| `tests/test_dry_run.py` | Added `test_load_event_groups_called_at_startup` |
| `tests/test_live_run.py` | Added `test_load_event_groups_called_at_startup` |

### Implementation Detail

**Import change (both files):**
```python
# Before
from bot.detection.cross_market import detect_cross_market_opportunities

# After
from bot.detection.cross_market import detect_cross_market_opportunities, load_event_groups
```

**Startup call (both files, after `fetch_liquid_markets`, before `WebSocketClient`):**
```python
# Load Gamma API event->market mappings once at startup.
# Failure is non-fatal: logs a warning and detection falls back to neg_risk_market_id.
try:
    load_event_groups()
except Exception as exc:  # pragma: no cover
    logger.warning(f"load_event_groups startup call failed: {exc}")
```

**Call site positioning:**
- `dry_run.py` line 68: after `logger.info(f"Loaded {len(markets)} liquid markets")`, before `ws_client = WebSocketClient(...)`
- `live_run.py` line 250: same positioning relative to equivalent lines

### Test Coverage

Two new tests (TDD, RED then GREEN):

| Test | File | Assertion |
|------|------|-----------|
| `test_load_event_groups_called_at_startup` | `test_dry_run.py` | `mock_leg.assert_called_once()` after dry_run.run() completes |
| `test_load_event_groups_called_at_startup` | `test_live_run.py` | `mock_leg.assert_called_once()` — uses KILL file to exit after first cycle |

Both patch `bot.dry_run.load_event_groups` / `bot.live_run.load_event_groups` (patching at use site, not definition site).

### Gap Closed

**UAT Test 4** — "_event_groups not populated: `load_event_groups()` is defined but never called from runner startup."

With this change: at scanner startup, `load_event_groups()` fetches all active events from `https://gamma-api.polymarket.com/events` and populates `_event_groups` with `condition_id -> event_id` mappings. All subsequent `detect_cross_market_opportunities()` calls use the populated mapping, enabling detection of non-NegRisk mutually exclusive events (elections, sports with N candidates) that the old keyword heuristic missed.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 82e4da4 | test | Add failing tests for load_event_groups startup wiring (RED) |
| f5bd0fb | feat | Wire load_event_groups() into scanner startup (GREEN) |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All wiring is live: `load_event_groups()` makes a real HTTP call to the Gamma API at startup.

## Threat Flags

No new threat surface introduced. The Gamma API call was already present in `cross_market.py`; this plan only moves the call site to the runner startup. The threat register in this plan (T-01-04-01, T-01-04-02, T-01-04-03) covers the existing surface — no new entries required.

## Self-Check: PASSED

- `src/bot/dry_run.py` — FOUND, contains `load_event_groups`
- `src/bot/live_run.py` — FOUND, contains `load_event_groups`
- `tests/test_dry_run.py` — FOUND, contains `test_load_event_groups_called_at_startup`
- `tests/test_live_run.py` — FOUND, contains `test_load_event_groups_called_at_startup`
- Commit 82e4da4 — FOUND (RED phase)
- Commit f5bd0fb — FOUND (GREEN phase)
- All 109 unit tests pass (0 failures, 0 errors)
