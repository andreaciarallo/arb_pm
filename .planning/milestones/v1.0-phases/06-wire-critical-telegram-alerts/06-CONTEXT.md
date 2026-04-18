# Phase 6: Wire Critical Telegram Alerts — Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire two missing Telegram alert call sites to close the TELEGRAM-PARTIAL integration gap:

1. Kill switch activation alert — fires at each call site in `live_run.py` before `_execute_kill_switch()` runs
2. Circuit breaker trip alert — fires in the scan loop when the CB transitions from closed to open

Both `TelegramAlerter.send_kill_switch()` and `TelegramAlerter.send_circuit_breaker_trip()` are already fully implemented in `notifications/telegram.py`. This phase only wires call sites.

Phase ends when: both methods have ≥1 verified call site (grep-confirmed), unit tests pass.

**Out of scope:** Any changes to TelegramAlerter methods, gate.py logic, engine.py logic, detection, dashboard.

</domain>

<decisions>
## Implementation Decisions

### D-01: Kill switch alert — call site approach (not function param)
Do NOT add `alerter` as a parameter to `_execute_kill_switch(client, conn, writer)`. Its signature stays unchanged.

Instead, fire the alert at each call site in `live_run.py` BEFORE calling `_execute_kill_switch()`:
```python
asyncio.create_task(alerter.send_kill_switch(trigger=_kill_trigger))
await _execute_kill_switch(client, conn, writer)
```

There is exactly one call site: inside the scan loop's kill switch check block (line ~269 in live_run.py). The alert fires before position closure begins, honoring Phase 4 D-05 item 4.

### D-02: Kill switch trigger identification — track via mutable container
Phase 4 decision D-05 item 4 requires "trigger reason (SIGTERM or KILL file)".

Implement via a single-element list `_kill_trigger_ref = ["unknown"]` in `run()` scope. This allows the nested `_handle_signal()` function to mutate it without `nonlocal`:

```python
_kill_trigger_ref = ["unknown"]  # mutable container for nested-function mutation

def _handle_signal():
    _kill_trigger_ref[0] = "SIGTERM"
    risk_gate.activate_kill_switch()
    _stop_event.set()
```

At the KILL file check in the scan loop, set:
```python
if os.path.exists(_KILL_FILE):
    _kill_trigger_ref[0] = "KILL file"
    risk_gate.activate_kill_switch()
```

At the kill switch alert call site, read: `trigger=_kill_trigger_ref[0]`

### D-03: Circuit breaker detection — snapshot before/after execution block
No changes to `gate.py` or `engine.py`.

In the scan loop, snapshot CB state BEFORE the execution block:
```python
was_cb_open = risk_gate.is_circuit_breaker_open()
```

After the execution block completes (after the `for opp in all_opps` loop), check if CB just opened:
```python
if not was_cb_open and risk_gate.is_circuit_breaker_open():
    asyncio.create_task(alerter.send_circuit_breaker_trip(
        error_count=risk_gate.circuit_breaker_errors,
        cooldown_seconds=risk_gate.cb_cooldown_remaining(),
    ))
```

`risk_gate.circuit_breaker_errors` — already public, equals the configured threshold (5 by default)
`risk_gate.cb_cooldown_remaining()` — already public method, returns remaining cooldown in seconds

This snapshot approach detects the first trip in each cycle. If the CB was already open coming into a cycle, no duplicate alert fires.

### D-04: Test coverage — add wiring tests
Add unit tests verifying:
1. Kill switch alert fires with correct trigger string ("KILL file" and "SIGTERM" paths separately)
2. Circuit breaker alert fires when CB transitions closed → open
3. Alert does NOT fire when CB was already open at cycle start (no duplicate)

Tests go in existing test suite (likely `tests/test_live_run.py` or a new `tests/test_alert_wiring.py`). Use `unittest.mock.AsyncMock` for alerter methods.

### Claude's Discretion
- Exact test file name and location
- Whether to add the snapshot CB check inside or outside the `if not risk_gate.is_blocked():` block
  (Recommendation: outside and after, since CB detection should happen even if we skipped execution)
- Exact ordering of `_kill_trigger_ref[0] = "KILL file"` relative to `risk_gate.activate_kill_switch()`
  (Recommendation: set trigger before activating, so trigger string is ready before the check fires)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Files to modify
- `src/bot/live_run.py` — primary change target: `_handle_signal()`, KILL file check block, kill switch check block, scan loop execution section
- `tests/` — add alert wiring tests

### Files to read but NOT modify
- `src/bot/notifications/telegram.py` — `send_kill_switch(trigger)` and `send_circuit_breaker_trip(error_count, cooldown_seconds)` signatures (already implemented)
- `src/bot/risk/gate.py` — `circuit_breaker_errors` attribute, `cb_cooldown_remaining()` method, `is_circuit_breaker_open()`
- `src/bot/execution/engine.py` — confirms `record_order_error()` is called inside engine on YES verify failure; no changes needed

### Prior phase decisions
- `.planning/phases/04-observability-monitoring/04-CONTEXT.md` — D-05 alert events list, D-03 fire-and-forget rule
- `.planning/phases/03-execution-risk-controls/03-CONTEXT.md` — D-07 circuit breaker behavior, D-08 kill switch design

</canonical_refs>

<specifics>
## Specific Behaviors

- **Alert ordering for kill switch**: `asyncio.create_task(alerter.send_kill_switch(...))` fires BEFORE `await _execute_kill_switch(...)`. Task is scheduled (not awaited), so position closure proceeds immediately without waiting for Telegram.
- **CB snapshot placement**: `was_cb_open` snapshot taken ONCE per cycle, before the execution block. The check fires after the execution block completes (whether or not opportunities were executed).
- **`circuit_breaker_errors` as error_count**: On trip, the threshold (e.g., 5) equals the actual count that triggered it. Accurate enough for the alert.
- **`cb_cooldown_remaining()` as cooldown_seconds**: Called immediately after detecting the trip — will be approximately the full configured cooldown.
- **Mutable list for signal handler**: `_kill_trigger_ref = ["unknown"]` is the simplest approach for mutating from a nested function without `nonlocal`. Alternative `nonlocal` declaration is equally valid.

</specifics>

<deferred>
## Deferred

- Retry logic on Telegram failure — explicitly deferred per Phase 4 D-03
- Alert on stop-loss trigger — not in Phase 6 scope, not in ROADMAP success criteria
- CB alert via `record_order_error()` return value — considered but rejected (requires engine.py changes)

</deferred>

---

*Phase: 06-wire-critical-telegram-alerts*
*Context gathered: 2026-04-18*
