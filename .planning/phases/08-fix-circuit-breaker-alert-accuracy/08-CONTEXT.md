# Phase 8: Fix Circuit Breaker & Alert Accuracy — Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Two surgical bug fixes across three files. No new features, no refactoring beyond what's required:

**Bug 1 (RISK-03):** `engine.py` never calls `risk_gate.record_order_error()` after the NO-leg retry loop exhausts. The hedge SELL runs but the circuit breaker is never notified. CB cannot trip from NO-leg failures.

**Bug 2 (OBS-02):** `live_run.py` passes `risk_gate.circuit_breaker_errors` (the static configured threshold, e.g. 5) to `alerter.send_circuit_breaker_trip(error_count=...)`. The alert message always reads "Errors: 5/60s" regardless of how many errors actually triggered the trip, because `gate.py` clears `_error_timestamps` before returning from `record_order_error()`.

Phase ends when: both call sites are wired, live count flows to the alert, unit tests confirm both fixes and regression.

**Out of scope:** All other engine.py behavior, alert formatting changes, gate.py logic changes beyond the new property, performance tuning.

</domain>

<decisions>
## Implementation Decisions

### D-01: engine.py — record_order_error() placement in NO exhaustion path
Call `risk_gate.record_order_error()` at the **top of the `if not no_filled:` block**, BEFORE the hedge SELL attempt.

Semantics: NO retries exhausted = order error. The hedge is a mitigation, not a second chance — the error is already established by the time we reach `if not no_filled:`.

Mirror the existing `hasattr` guard pattern used for YES verification failure at line 327:
```python
if not no_filled:
    if hasattr(risk_gate, "record_order_error"):
        risk_gate.record_order_error()
    # ... then proceed to hedge SELL
```

### D-02: gate.py — capture live count before clearing
Add instance attribute `self._last_trip_count: int = 0` (initialized in `__init__`).

In `record_order_error()`, capture the count BEFORE clearing `_error_timestamps`:
```python
if len(self._error_timestamps) >= self.circuit_breaker_errors:
    cooldown = self.circuit_breaker_cooldown_seconds * self._cb_cooldown_multiplier
    self._cb_cooldown_until = now + cooldown
    self._cb_cooldown_multiplier = min(self._cb_cooldown_multiplier * 2, 4)
    self._last_trip_count = len(self._error_timestamps)  # capture before clear
    self._error_timestamps.clear()
    logger.warning(...)
```

Expose via property:
```python
@property
def last_trip_error_count(self) -> int:
    """Error count that triggered the most recent CB trip. 0 if never tripped."""
    return self._last_trip_count
```

### D-03: live_run.py — pass live count to alert
Change the CB trip alert call site (approx line 398):
```python
# Before (passes static threshold):
error_count=risk_gate.circuit_breaker_errors,

# After (passes live triggering count):
error_count=risk_gate.last_trip_error_count,
```

### D-04: Test scope — two new fixes + one regression
Tests cover:
1. **NO exhaustion trips CB** — engine.py with mocked risk_gate verifies `record_order_error()` is called when `not no_filled` (all NO retries fail)
2. **CB alert shows live count** — live_run.py test verifies `send_circuit_breaker_trip` is called with `error_count=5` (live triggering count) NOT `circuit_breaker_errors` (static threshold) when they differ
3. **Regression: YES verify failure still trips CB** — `record_order_error()` still called when YES verify returns False (existing path unchanged)

Test files: add to `tests/test_execution_engine.py` (D-04 #1, #3) and `tests/test_live_run.py` (D-04 #2).

### Claude's Discretion
- Whether to add type annotation `_last_trip_count: int` in the class body before `__init__` (consistent with some codebases)
- Exact ordering of `self._last_trip_count = len(self._error_timestamps)` relative to other statements in the trip block (before or after setting `_cb_cooldown_until` — both work, before-clear is required)
- Whether to also cover `not no_filled` after kill switch break (kill switch abort mid-retry: skip `record_order_error()` there since kill switch is a deliberate stop, not an order error)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Files to modify
- `src/bot/execution/engine.py` — add `record_order_error()` call at top of `if not no_filled:` block (approx lines 420–425)
- `src/bot/risk/gate.py` — add `_last_trip_count` attribute + `last_trip_error_count` property; set count before `_error_timestamps.clear()` in `record_order_error()`
- `src/bot/live_run.py` — change `error_count=risk_gate.circuit_breaker_errors` → `error_count=risk_gate.last_trip_error_count` in CB trip alert (approx line 399)
- `tests/test_execution_engine.py` — add NO exhaustion CB test, regression for YES verify failure
- `tests/test_live_run.py` — add CB alert live-count test

### Files to read but NOT modify
- `src/bot/notifications/telegram.py` — `send_circuit_breaker_trip(error_count, cooldown_seconds)` signature; `error_count` is `int`
- `src/bot/risk/gate.py` — full class before editing: `record_order_error()` internals, `circuit_breaker_errors` attribute, `_error_timestamps` list, `_last_trip_count` insertion point

### Prior phase decisions
- `.planning/phases/06-wire-critical-telegram-alerts/06-CONTEXT.md` — D-03: snapshot-based CB trip detection pattern already in place in live_run.py; no changes to detection logic needed
- `.planning/phases/03-execution-risk-controls/03-CONTEXT.md` — D-07: circuit breaker behavior; `record_order_error()` docstring says "Only call from execution path — order rejection, timeout, auth failure"

### ROADMAP success criteria (exact targets)
- `.planning/ROADMAP.md` Phase 8 section: four success criteria at line and file granularity

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `hasattr(risk_gate, "record_order_error")` guard pattern — already used at YES verify failure path (engine.py ~line 327); mirror exactly for NO exhaustion call
- `risk_gate.circuit_breaker_errors` — static configured threshold (int, e.g. 5); used in `__init__` and `record_order_error()` trip condition; NOT the live count
- `risk_gate.cb_cooldown_remaining()` — public method, already passed to alert in live_run.py; no changes needed there
- `self._error_timestamps.clear()` — line 122 in gate.py; insert `self._last_trip_count = len(self._error_timestamps)` immediately BEFORE this line

### Established Patterns
- `record_order_error()` is a void method with no return value — new count capture via instance attribute (not return value) is consistent
- All `send_*()` alert methods are fire-and-forget via `asyncio.create_task()` — no change to call pattern in live_run.py
- Tests use `unittest.mock.AsyncMock` for alerter, `MagicMock` for risk_gate — see test_live_run.py for patterns

### Integration Points
- engine.py's `execute_opportunity()` receives `risk_gate` as a parameter — call site for `record_order_error()` is internal to function body, no signature change
- live_run.py already reads `risk_gate.circuit_breaker_errors` (static) at line 399; swapping to `last_trip_error_count` is a one-word change

</code_context>

<specifics>
## Specific Behaviors

- **NO exhaustion + kill switch abort**: When the NO retry loop breaks early due to kill switch (`if risk_gate.is_kill_switch_active(): break`), `no_filled` remains False and execution falls into `if not no_filled:`. The `record_order_error()` call WILL fire in this case. This is acceptable — the abort was due to kill switch, but the NO leg still failed. Claude may choose to skip it with an additional guard if the `is_kill_switch_active()` state is detectable at that point.
- **`last_trip_error_count` initial value**: Returns 0 before any CB trip occurs. Live_run.py only reads it after detecting a closed→open transition, so 0 is never passed to the alert in practice.
- **Count accuracy**: After `record_order_error()` trips the CB, `len(_error_timestamps)` equals exactly the threshold count (e.g. 5) in normal cases. It may be slightly higher if multiple errors arrive in the same tick before the condition is checked (list accumulates all within the window). Capturing before `clear()` gives the precise triggering count.

</specifics>

<deferred>
## Deferred

- WebSocket fill channel for YES verification — deferred since Phase 3 (D-03 Phase 3-03 note), no change
- `record_order_error()` return value API — not added; instance attribute approach is less invasive
- Retry logic on Telegram failure — deferred per Phase 4 D-03, no change

</deferred>

---

*Phase: 08-fix-circuit-breaker-alert-accuracy*
*Context gathered: 2026-04-18*
