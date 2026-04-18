---
plan: 08-01
phase: 08-fix-circuit-breaker-alert-accuracy
status: complete
completed_at: 2026-04-18
requirements_closed:
  - OBS-02
---

# Plan 08-01 Summary — CB Alert Live Count Fix

## What Was Built

Fixed the circuit breaker Telegram alert to report the **live triggering error count** instead of the static configured threshold.

### Bug Fixed (OBS-02)

Before: `alerter.send_circuit_breaker_trip(error_count=risk_gate.circuit_breaker_errors)` — always sent the configured integer (e.g. 5), regardless of how many errors actually triggered the trip.

After: `alerter.send_circuit_breaker_trip(error_count=risk_gate.last_trip_error_count)` — sends the actual count captured at the moment of tripping (e.g. 7 if 7 errors burst through the window).

## Files Changed

| File | Change |
|------|--------|
| `src/bot/risk/gate.py` | Added `_last_trip_count: int = 0` in `__init__`; captured `len(_error_timestamps)` before `.clear()` in `record_order_error()`; exposed via `last_trip_error_count` property |
| `src/bot/live_run.py` | CB alert call site: `circuit_breaker_errors` → `last_trip_error_count` |
| `tests/test_live_run.py` | Added `mock_rg.last_trip_error_count = 5` to `test_cb_alert_fires_on_trip`; added new `test_cb_alert_shows_live_count_not_static_threshold` |

## Commits

- `6dc8b47` — feat(08-01): add last_trip_error_count property to RiskGate
- `71c783c` — fix(08-01): wire CB alert to last_trip_error_count, add OBS-02 test

## Test Results

All 29 tests pass (`tests/test_live_run.py` + `tests/test_risk_gate.py`):
- `test_cb_alert_fires_on_trip` — updated, still green
- `test_cb_alert_shows_live_count_not_static_threshold` — new, proves live count (7) not static threshold (5) is sent
- `test_last_trip_error_count_zero_before_any_trip` — new gate test, green
- `test_last_trip_error_count_reflects_triggering_count` — new gate test, green
- `test_last_trip_error_count_with_excess_errors` — new gate test, green

## Key Decision

D-02: `_last_trip_count = len(self._error_timestamps)` must appear **before** `self._error_timestamps.clear()` — after clear, len() returns 0. Order is critical.
