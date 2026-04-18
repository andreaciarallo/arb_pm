---
phase: 06-wire-critical-telegram-alerts
plan: 01
subsystem: notifications
tags: [telegram, asyncio, alerts, kill-switch, circuit-breaker, live-run]

# Dependency graph
requires:
  - phase: 04-observability-monitoring
    provides: TelegramAlerter.send_kill_switch() and send_circuit_breaker_trip() already implemented; D-03 fire-and-forget rule; D-05 alert events list
  - phase: 03-execution-risk-controls
    provides: RiskGate.circuit_breaker_errors, cb_cooldown_remaining(), is_circuit_breaker_open(), kill switch design (D-07, D-08)
provides:
  - Kill switch Telegram alert wired in live_run.py: fires before _execute_kill_switch() with correct trigger string
  - Circuit breaker trip Telegram alert wired in live_run.py: fires on closed->open CB transition per cycle
  - Kill trigger tracking via _kill_trigger_ref mutable list distinguishing "KILL file" from "SIGTERM"
  - CB snapshot-before/check-after pattern preventing duplicate alerts across consecutive cycles
  - Four unit tests covering all four alert wiring behaviors
affects: [future phases modifying live_run.py, any phase touching RiskGate or TelegramAlerter]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fire-and-forget alert via asyncio.create_task(): established in Phase 4, now used for kill switch and CB trip"
    - "Mutable list _kill_trigger_ref = ['unknown'] for nested-function mutation without nonlocal"
    - "CB snapshot before/check after: was_cb_open = is_circuit_breaker_open() before execution gate, check after all branches"

key-files:
  created: []
  modified:
    - src/bot/live_run.py
    - tests/test_live_run.py

key-decisions:
  - "D-01: Kill switch alert fired at call site (not added as _execute_kill_switch param) — signature stays (client, conn, writer)"
  - "D-02: _kill_trigger_ref = ['unknown'] mutable list tracks trigger reason across nested _handle_signal() closure"
  - "D-03: CB snapshot taken before if not risk_gate.is_blocked(): so check fires even when execution block is skipped"
  - "Tests use await asyncio.sleep(0) after triggering to yield control before asserting AsyncMock was awaited"

patterns-established:
  - "kill switch alert: asyncio.create_task(alerter.send_kill_switch(trigger=_kill_trigger_ref[0])) immediately before await _execute_kill_switch()"
  - "CB trip alert: was_cb_open snapshot before execution gate; if not was_cb_open and risk_gate.is_circuit_breaker_open(): after gate"

requirements-completed: [OBS-02]

# Metrics
duration: 10min
completed: 2026-04-18
---

# Phase 6 Plan 01: Wire Critical Telegram Alerts Summary

**Two missing Telegram alert call sites wired in live_run.py: kill switch fires with SIGTERM/KILL-file trigger string, circuit breaker fires on closed-to-open transition only — OBS-02 gap closed**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-18T16:35:00Z
- **Completed:** 2026-04-18T16:45:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Wired `asyncio.create_task(alerter.send_kill_switch(trigger=_kill_trigger_ref[0]))` before `_execute_kill_switch()` in the kill switch check block
- Added `_kill_trigger_ref = ["unknown"]` mutable list so nested `_handle_signal()` can set `"SIGTERM"` and the KILL file block sets `"KILL file"` without `nonlocal`
- Wired CB trip alert: `was_cb_open` snapshot before execution gate; `asyncio.create_task(alerter.send_circuit_breaker_trip(...))` fires only on closed-to-open transition
- Added four unit tests (TDD RED -> GREEN) covering kill-file path, SIGTERM path, CB trip, and no-duplicate behavior — all pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Write alert wiring unit tests (TDD RED)** - `1e4dd70` (test)
2. **Task 2: Wire kill switch and circuit breaker alert call sites** - `8901804` (feat)

## Files Created/Modified

- `src/bot/live_run.py` — Added `_kill_trigger_ref` mutable list, SIGTERM/KILL-file trigger mutations, kill switch alert call site, CB snapshot and trip alert call site
- `tests/test_live_run.py` — Appended four new unit tests: `test_kill_switch_alert_fires_kill_file`, `test_kill_switch_alert_fires_sigterm`, `test_cb_alert_fires_on_trip`, `test_cb_alert_no_duplicate`

## Decisions Made

- Used `await asyncio.sleep(0)` in tests after triggering to yield control and allow scheduled `asyncio.create_task()` coroutines to execute before asserting `assert_awaited_once_with` — matches pitfall 1 documented in RESEARCH.md
- CB snapshot placed outside (before) the `if not risk_gate.is_blocked():` block so it captures state even when execution is skipped — prevents undefined `was_cb_open` if CB trips between cycles
- `_kill_trigger_ref[0] = "KILL file"` placed before `risk_gate.activate_kill_switch()` so trigger string is ready when the kill switch check fires immediately below

## Deviations from Plan

None — plan executed exactly as written. All locked decisions (D-01 through D-04) followed verbatim.

## Issues Encountered

None. All existing tests continued to pass after Task 1 (171-line addition to test file). All 103 unit tests green after Task 2.

## User Setup Required

None — no external service configuration required. Telegram credentials already configured from Phase 4.

## Next Phase Readiness

- Phase 6 complete. OBS-02 requirement satisfied.
- Both `send_kill_switch` and `send_circuit_breaker_trip` now have verified call sites in `live_run.py`.
- Bot will send Telegram notifications on kill switch activation (with correct trigger source) and first circuit breaker trip per cycle.

---
*Phase: 06-wire-critical-telegram-alerts*
*Completed: 2026-04-18*
