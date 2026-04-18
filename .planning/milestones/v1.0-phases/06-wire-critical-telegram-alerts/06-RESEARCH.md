# Phase 6: Wire Critical Telegram Alerts — Research

**Researched:** 2026-04-18
**Domain:** Python asyncio, fire-and-forget alert wiring, unit test mocking
**Confidence:** HIGH

## Summary

Phase 6 is a surgical wiring phase with zero new functionality to build. Both `TelegramAlerter.send_kill_switch(trigger)` and `TelegramAlerter.send_circuit_breaker_trip(error_count, cooldown_seconds)` are fully implemented and tested in `notifications/telegram.py`. The only work is inserting two `asyncio.create_task()` call sites in `live_run.py` and adding unit tests for the new wiring.

The implementation touches exactly four locations in `live_run.py`: `_handle_signal()` (add `_kill_trigger_ref[0] = "SIGTERM"`), the KILL file check block (add `_kill_trigger_ref[0] = "KILL file"`), the kill switch check block (add `asyncio.create_task(alerter.send_kill_switch(...))`), and the scan loop execution section (add CB snapshot before + check after the `for opp in all_opps` block).

**Primary recommendation:** Follow D-01 through D-04 verbatim. No deviation from the locked decisions is warranted — the codebase already has all scaffolding in place.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Kill switch alert — call site approach (not function param)**
Do NOT add `alerter` as a parameter to `_execute_kill_switch(client, conn, writer)`. Its signature stays unchanged.

Instead, fire the alert at each call site in `live_run.py` BEFORE calling `_execute_kill_switch()`:
```python
asyncio.create_task(alerter.send_kill_switch(trigger=_kill_trigger))
await _execute_kill_switch(client, conn, writer)
```

There is exactly one call site: inside the scan loop's kill switch check block (line ~269 in live_run.py). The alert fires before position closure begins, honoring Phase 4 D-05 item 4.

**D-02: Kill switch trigger identification — track via mutable container**
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

**D-03: Circuit breaker detection — snapshot before/after execution block**
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

**D-04: Test coverage — add wiring tests**
Add unit tests verifying:
1. Kill switch alert fires with correct trigger string ("KILL file" and "SIGTERM" paths separately)
2. Circuit breaker alert fires when CB transitions closed -> open
3. Alert does NOT fire when CB was already open at cycle start (no duplicate)

Tests go in existing test suite (likely `tests/test_live_run.py` or a new `tests/test_alert_wiring.py`). Use `unittest.mock.AsyncMock` for alerter methods.

### Claude's Discretion

- Exact test file name and location
- Whether to add the snapshot CB check inside or outside the `if not risk_gate.is_blocked():` block
  (Recommendation: outside and after, since CB detection should happen even if we skipped execution)
- Exact ordering of `_kill_trigger_ref[0] = "KILL file"` relative to `risk_gate.activate_kill_switch()`
  (Recommendation: set trigger before activating, so trigger string is ready before the check fires)

### Deferred Ideas (OUT OF SCOPE)

- Retry logic on Telegram failure — explicitly deferred per Phase 4 D-03
- Alert on stop-loss trigger — not in Phase 6 scope, not in ROADMAP success criteria
- CB alert via `record_order_error()` return value — considered but rejected (requires engine.py changes)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-02 | Send instant alerts via Telegram/Discord for trade executions and errors | Both alert methods (`send_kill_switch`, `send_circuit_breaker_trip`) are fully implemented in `telegram.py`. Wiring two `asyncio.create_task()` call sites in `live_run.py` closes the TELEGRAM-PARTIAL gap and satisfies "errors" coverage in OBS-02. |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `python-telegram-bot` | 21+ (already installed) | Telegram Bot API wrapper | Project-mandated in CLAUDE.md; already used in `telegram.py` |
| `asyncio` (stdlib) | Python 3.10+ | Fire-and-forget task scheduling | `asyncio.create_task()` is the established pattern in this codebase (D-03 of Phase 4) |
| `unittest.mock` | stdlib | AsyncMock for coroutine mocking | Already used throughout the test suite (see `test_live_run.py`, `test_telegram.py`) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-asyncio` | installed (asyncio_mode=auto) | Run async test functions | All new alert wiring tests are async |
| `loguru` | 0.7+ (already installed) | Log alert scheduling events | Existing pattern in `live_run.py` |

**No new dependencies required.** All libraries are already installed and in use.

---

## Architecture Patterns

### Fire-and-Forget Alert Pattern (Established in Phase 4)
**What:** `asyncio.create_task(alerter.send_X(...))` schedules a coroutine without awaiting it. The scan loop continues immediately regardless of Telegram latency or failure.

**When to use:** Every alert call in `live_run.py`. `TelegramAlerter.send()` already swallows all exceptions, so failure is silent and safe.

**Existing example (line 361 of live_run.py):**
```python
asyncio.create_task(alerter.send_arb_complete(
    market_question=opp.market_question,
    ...
))
```

This is the exact same pattern required for Phase 6.

### Mutable Container for Nested-Function State (D-02)
**What:** A single-element list `_kill_trigger_ref = ["unknown"]` allows a nested `def _handle_signal()` to mutate outer scope without `nonlocal`.

**Why:** Python closures can read outer variables freely but cannot rebind them without `nonlocal`. A list is mutable in-place, sidestepping the constraint. This is a well-known Python idiom for pre-3.x-style closures.

**Example:**
```python
_kill_trigger_ref = ["unknown"]

def _handle_signal():
    _kill_trigger_ref[0] = "SIGTERM"   # mutation, not rebinding — works without nonlocal
    risk_gate.activate_kill_switch()
    _stop_event.set()
```

### CB State Snapshot Pattern (D-03)
**What:** Capture `was_cb_open` before the execution block; compare after. Detects first-trip transition without modifying `gate.py`.

**Placement:** The snapshot (`was_cb_open = risk_gate.is_circuit_breaker_open()`) must occur BEFORE `if not risk_gate.is_blocked():`. The post-execution check fires AFTER the entire `for opp in all_opps` block completes — and also AFTER the `elif risk_gate.is_stop_loss_triggered()` / `elif risk_gate.is_circuit_breaker_open()` branches. Per Claude's Discretion, the check should be OUTSIDE (after) the `if not risk_gate.is_blocked():` block, so it fires even in cycles where execution was skipped (the CB could have tripped from a previous cycle's error that carried over).

**Example:**
```python
was_cb_open = risk_gate.is_circuit_breaker_open()  # snapshot

if not risk_gate.is_blocked():
    for opp in all_opps:
        ...
elif risk_gate.is_stop_loss_triggered():
    ...
elif risk_gate.is_circuit_breaker_open():
    ...

# After execution block — check for CB trip transition
if not was_cb_open and risk_gate.is_circuit_breaker_open():
    asyncio.create_task(alerter.send_circuit_breaker_trip(
        error_count=risk_gate.circuit_breaker_errors,
        cooldown_seconds=risk_gate.cb_cooldown_remaining(),
    ))
```

### Anti-Patterns to Avoid
- **Awaiting alert calls:** `await alerter.send_kill_switch(...)` blocks the scan loop until Telegram responds. Use `asyncio.create_task()` exclusively.
- **Modifying `_execute_kill_switch` signature:** D-01 locks this. Adding `alerter` as a parameter would require changing all callers and test mocks.
- **Calling `risk_gate.record_order_error()` to detect CB trip:** Would require `engine.py` changes (deferred in CONTEXT.md).
- **Checking CB inside `if not risk_gate.is_blocked():`:** If CB tripped this cycle, `is_blocked()` is already True — the execution block is skipped entirely and the post-block CB check would never fire. The snapshot must be taken before `is_blocked()` is evaluated.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Telegram message formatting | Custom serializer | `TelegramAlerter.send_kill_switch()` / `send_circuit_breaker_trip()` | Both methods already format and send messages; Phase 6 only wires call sites |
| Nested function state mutation | `nonlocal` keyword or class attribute | `_kill_trigger_ref = ["unknown"]` mutable list | Simpler, idiomatic Python for this pattern |
| CB trip detection | Hook into `record_order_error()` | Snapshot-before/check-after pattern | Zero changes to `gate.py` or `engine.py` required |

---

## Code Examples

### Method signatures to wire (from telegram.py — verified by direct file read)

```python
# send_kill_switch — takes trigger string, no return value
async def send_kill_switch(self, trigger: str) -> None:
    text = f"Kill switch triggered via {trigger}. Closing positions now."
    await self.send(text, parse_mode=None)

# send_circuit_breaker_trip — takes int error_count + float cooldown_seconds
async def send_circuit_breaker_trip(
    self,
    error_count: int,
    cooldown_seconds: float,
) -> None:
    cooldown_minutes = int(cooldown_seconds // 60)
    cooldown_secs = int(cooldown_seconds % 60)
    text = (
        f"Circuit breaker tripped. "
        f"Errors: {error_count}/60s. "
        f"Cooldown: {cooldown_minutes}m {cooldown_secs}s."
    )
    await self.send(text, parse_mode=None)
```

### RiskGate attributes needed (from gate.py — verified by direct file read)

```python
# circuit_breaker_errors: int (constructor param, immutable after init — equals the threshold)
risk_gate.circuit_breaker_errors  # e.g. 5

# cb_cooldown_remaining(): float — seconds remaining on cooldown, 0.0 if not active
risk_gate.cb_cooldown_remaining()

# is_circuit_breaker_open(): bool — True if cooldown is currently active
risk_gate.is_circuit_breaker_open()
```

### Existing create_task pattern in live_run.py (line 361 — established model)

```python
asyncio.create_task(alerter.send_arb_complete(
    market_question=opp.market_question,
    yes_entry_price=yes_result.price,
    ...
))
```

### AsyncMock test pattern (from test_telegram.py and test_live_run.py — verified)

```python
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

@pytest.mark.asyncio
async def test_kill_switch_alert_fires_on_kill_file():
    alerter = MagicMock()
    alerter.send_kill_switch = AsyncMock()
    # ... patch live_run internals, run one cycle with KILL file present
    alerter.send_kill_switch.assert_awaited_once_with(trigger="KILL file")
```

Note: `asyncio.create_task()` schedules a coroutine but does not await it immediately. Tests must either `await asyncio.sleep(0)` after the triggering action to allow the scheduled task to run, or patch `asyncio.create_task` itself and assert it was called with the correct coroutine.

---

## Common Pitfalls

### Pitfall 1: Testing create_task calls — awaiting vs. patching
**What goes wrong:** Test asserts `alerter.send_kill_switch.assert_awaited_once()` but the mock is never awaited because `asyncio.create_task()` schedules it without running it in the same tick.

**Why it happens:** `asyncio.create_task()` queues the coroutine on the event loop; it runs when control returns to the loop (after the current coroutine yields). If the test assertion runs before yielding, the mock hasn't been called yet.

**How to avoid:** Two valid approaches:
1. After triggering the kill switch, `await asyncio.sleep(0)` to yield control and let the task execute, then assert.
2. Patch `asyncio.create_task` with a `MagicMock` and assert `create_task.call_args` contains the expected coroutine type — this is synchronous and faster.

The existing `test_live_run.py` uses approach 2 implicitly (patching entire `_start_dashboard` etc). For wiring tests, approach 1 is simpler and more realistic.

### Pitfall 2: CB snapshot placement — must precede is_blocked() check
**What goes wrong:** Snapshot taken inside the `if not risk_gate.is_blocked():` block. If CB tripped in the same cycle, `is_blocked()` returns True and the block is skipped entirely — snapshot never taken, check never fires.

**Why it happens:** The CB trips during `execute_opportunity()` via `record_order_error()` inside `engine.py`. After the execution loop, `is_circuit_breaker_open()` is True. But if the snapshot was inside the skipped block, `was_cb_open` is undefined.

**How to avoid:** Place `was_cb_open = risk_gate.is_circuit_breaker_open()` BEFORE the `if not risk_gate.is_blocked():` check. The CB check fires independently after all execution branches.

### Pitfall 3: Duplicate CB alerts on consecutive cycles
**What goes wrong:** CB is already open at start of cycle N+1. `was_cb_open = True`, post-check evaluates `not True and True` = False. Alert does not re-fire. This is correct behavior — but the test must verify the "no duplicate" case explicitly.

**Why it happens:** The snapshot pattern correctly handles this. The pitfall is in test design: failing to write the "no duplicate" test case (required by D-04 item 3).

**How to avoid:** Include a test where `was_cb_open=True` from cycle start and confirm `send_circuit_breaker_trip` is NOT called.

### Pitfall 4: Kill trigger "unknown" on SIGTERM path if mutation order is wrong
**What goes wrong:** `_kill_trigger_ref[0] = "SIGTERM"` executes in `_handle_signal()`, but the kill switch check fires before the mutation propagates (timing issue in tests).

**Why it happens:** `_handle_signal()` is synchronous and runs in the signal handler context. In production, the mutation is immediate. In tests using `MagicMock`, signal handlers are typically replaced entirely.

**How to avoid:** Test the SIGTERM path by directly calling `_handle_signal()` in the test (not via signal dispatch), then checking the trigger ref value after.

### Pitfall 5: `_kill_trigger_ref` vs `_kill_trigger` naming confusion
**What goes wrong:** CONTEXT.md D-01 shows `trigger=_kill_trigger` (bare string), while D-02 defines `_kill_trigger_ref = ["unknown"]` (list). The actual call should be `trigger=_kill_trigger_ref[0]`.

**Why it happens:** D-01 uses a shorthand `_kill_trigger` to represent the string value; D-02 clarifies the implementation mechanism is the mutable list. The call site reads index 0.

**How to avoid:** At the kill switch check call site: `asyncio.create_task(alerter.send_kill_switch(trigger=_kill_trigger_ref[0]))`.

---

## Exact Change Locations in live_run.py

Verified by direct file read (line numbers approximate, content confirmed):

| Location | Line Range | Change |
|----------|------------|--------|
| `run()` function start, after `_stop_event = asyncio.Event()` | ~230 | Add `_kill_trigger_ref = ["unknown"]` |
| `_handle_signal()` body | ~232-235 | Add `_kill_trigger_ref[0] = "SIGTERM"` as first line |
| KILL file check block | ~263-265 | Add `_kill_trigger_ref[0] = "KILL file"` before `risk_gate.activate_kill_switch()` |
| Before `if not risk_gate.is_blocked():` | ~295 | Add `was_cb_open = risk_gate.is_circuit_breaker_open()` |
| Kill switch check block | ~268-270 | Add `asyncio.create_task(alerter.send_kill_switch(trigger=_kill_trigger_ref[0]))` before `await _execute_kill_switch(...)` |
| After `elif risk_gate.is_circuit_breaker_open():` block | ~388 | Add CB trip check: `if not was_cb_open and risk_gate.is_circuit_breaker_open():` + `asyncio.create_task(...)` |

Current kill switch block (lines 267-270):
```python
# Kill switch takes absolute priority — execute active close and exit loop
if risk_gate.is_kill_switch_active():
    await _execute_kill_switch(client, conn, writer)
    break
```

After Phase 6:
```python
# Kill switch takes absolute priority — execute active close and exit loop
if risk_gate.is_kill_switch_active():
    asyncio.create_task(alerter.send_kill_switch(trigger=_kill_trigger_ref[0]))
    await _execute_kill_switch(client, conn, writer)
    break
```

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest with pytest-asyncio |
| Config file | `pytest.ini` (asyncio_mode=auto) |
| Quick run command | `pytest tests/test_live_run.py -x -q` or `pytest tests/test_alert_wiring.py -x -q` |
| Full suite command | `pytest tests/ -m unit -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OBS-02 | Kill switch alert fires with trigger="KILL file" | unit | `pytest tests/test_live_run.py -k "kill_switch_alert" -x` | Wave 0 — new test |
| OBS-02 | Kill switch alert fires with trigger="SIGTERM" | unit | `pytest tests/test_live_run.py -k "sigterm_alert" -x` | Wave 0 — new test |
| OBS-02 | CB alert fires on closed→open transition | unit | `pytest tests/test_live_run.py -k "circuit_breaker_trip_alert" -x` | Wave 0 — new test |
| OBS-02 | CB alert NOT fired when CB already open | unit | `pytest tests/test_live_run.py -k "no_duplicate_cb_alert" -x` | Wave 0 — new test |
| OBS-02 | send_kill_switch has ≥1 call site (grep) | manual | `grep -n "send_kill_switch" src/bot/live_run.py` | Verify post-implementation |
| OBS-02 | send_circuit_breaker_trip has ≥1 call site (grep) | manual | `grep -n "send_circuit_breaker_trip" src/bot/live_run.py` | Verify post-implementation |

### Sampling Rate
- **Per task commit:** `pytest tests/ -m unit -q`
- **Per wave merge:** `pytest tests/ -m unit -q`
- **Phase gate:** Full unit suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] New alert wiring tests (4 tests) — covers OBS-02 wiring verification
  - File: `tests/test_live_run.py` (extend existing) or `tests/test_alert_wiring.py` (new file)
  - Test names: `test_kill_switch_alert_fires_kill_file`, `test_kill_switch_alert_fires_sigterm`, `test_cb_alert_fires_on_trip`, `test_cb_alert_no_duplicate`

*(Existing test infrastructure in `tests/test_live_run.py` and `tests/test_telegram.py` covers all other aspects. No new conftest fixtures needed — `_test_config()` and `MagicMock`/`AsyncMock` from stdlib are sufficient.)*

---

## Environment Availability

Step 2.6: SKIPPED — this phase is a code/config-only change with no external dependencies beyond the already-installed project libraries.

---

## Open Questions

1. **Test file location — test_live_run.py extension vs. new test_alert_wiring.py**
   - What we know: Both approaches are valid; existing `test_live_run.py` already tests scan loop behavior.
   - What's unclear: Whether adding 4 more tests to `test_live_run.py` makes it unwieldy.
   - Recommendation: Extend `test_live_run.py` to keep alert wiring tests co-located with the file they test. Four focused tests won't push the file to an unwieldy size.

2. **CB snapshot placement — inside or outside `if not risk_gate.is_blocked():`**
   - What we know: CONTEXT.md Claude's Discretion recommends outside/after.
   - What's unclear: Nothing. The recommendation is unambiguous and correct for the reason given.
   - Recommendation: Place snapshot before `if not risk_gate.is_blocked():`, check after all branches.

---

## Sources

### Primary (HIGH confidence)
- Direct file read: `src/bot/live_run.py` — complete scan loop structure, all call sites verified
- Direct file read: `src/bot/notifications/telegram.py` — exact method signatures for `send_kill_switch` and `send_circuit_breaker_trip`
- Direct file read: `src/bot/risk/gate.py` — `circuit_breaker_errors` attribute, `cb_cooldown_remaining()`, `is_circuit_breaker_open()` all verified
- Direct file read: `tests/test_live_run.py` — established mocking patterns (AsyncMock, patch)
- Direct file read: `tests/test_telegram.py` — Bot mock pattern with `__aenter__`/`__aexit__`
- Direct file read: `tests/conftest.py` — `_test_config()` helper, fixture availability
- Direct file read: `pytest.ini` — asyncio_mode=auto confirmed
- Direct file read: `.planning/phases/06-wire-critical-telegram-alerts/06-CONTEXT.md` — all decisions

### Secondary (MEDIUM confidence)
- Python docs (training knowledge, HIGH confidence for stdlib): `asyncio.create_task()` schedules coroutine without awaiting; task runs when event loop yields control

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all libraries already installed and in use
- Architecture patterns: HIGH — verified against actual source files; patterns directly observed in codebase
- Pitfalls: HIGH — derived from direct inspection of code and test patterns; not speculative
- Exact change locations: HIGH — verified by direct file read with line number cross-reference

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (stable phase — no external API changes relevant)
