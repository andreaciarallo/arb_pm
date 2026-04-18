# Phase 8: Fix Circuit Breaker & Alert Accuracy — Research

**Researched:** 2026-04-18
**Domain:** Python asyncio bug fix — circuit breaker wiring + alert data accuracy
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: engine.py — record_order_error() placement in NO exhaustion path**
Call `risk_gate.record_order_error()` at the top of the `if not no_filled:` block, BEFORE the hedge SELL attempt. Mirror the existing `hasattr` guard pattern used for YES verification failure at line 327:
```python
if not no_filled:
    if hasattr(risk_gate, "record_order_error"):
        risk_gate.record_order_error()
    # ... then proceed to hedge SELL
```

**D-02: gate.py — capture live count before clearing**
Add instance attribute `self._last_trip_count: int = 0` (initialized in `__init__`). In `record_order_error()`, capture the count BEFORE clearing `_error_timestamps`:
```python
self._last_trip_count = len(self._error_timestamps)  # capture before clear
self._error_timestamps.clear()
```
Expose via property:
```python
@property
def last_trip_error_count(self) -> int:
    """Error count that triggered the most recent CB trip. 0 if never tripped."""
    return self._last_trip_count
```

**D-03: live_run.py — pass live count to alert**
Change the CB trip alert call site (approx line 399):
```python
# Before (passes static threshold):
error_count=risk_gate.circuit_breaker_errors,

# After (passes live triggering count):
error_count=risk_gate.last_trip_error_count,
```

**D-04: Test scope — two new fixes + one regression**
Tests cover:
1. NO exhaustion trips CB — engine.py with mocked risk_gate verifies `record_order_error()` is called when `not no_filled` (all NO retries fail)
2. CB alert shows live count — live_run.py test verifies `send_circuit_breaker_trip` is called with `error_count=5` (live triggering count) NOT `circuit_breaker_errors` (static threshold) when they differ
3. Regression: YES verify failure still trips CB — `record_order_error()` still called when YES verify returns False (existing path unchanged)

Test files: add to `tests/test_execution_engine.py` (D-04 #1, #3) and `tests/test_live_run.py` (D-04 #2).

### Claude's Discretion
- Whether to add type annotation `_last_trip_count: int` in the class body before `__init__` (consistent with some codebases)
- Exact ordering of `self._last_trip_count = len(self._error_timestamps)` relative to other statements in the trip block (before or after setting `_cb_cooldown_until` — both work, before-clear is required)
- Whether to also cover `not no_filled` after kill switch break (kill switch abort mid-retry: skip `record_order_error()` there since kill switch is a deliberate stop, not an order error)

### Deferred Ideas (OUT OF SCOPE)
- WebSocket fill channel for YES verification — deferred since Phase 3
- `record_order_error()` return value API — not added; instance attribute approach is less invasive
- Retry logic on Telegram failure — deferred per Phase 4
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RISK-03 | Implement circuit breaker that pauses trading on high error rates | Bug: NO-leg retry exhaustion never calls `record_order_error()`. Fix in engine.py `if not no_filled:` block. |
| OBS-02 | Send instant alerts via Telegram/Discord for trade executions and errors | Bug: CB alert passes static threshold (`circuit_breaker_errors=5`) not live count. Fix requires new `last_trip_error_count` property on RiskGate and one-word change in live_run.py. |
</phase_requirements>

---

## Summary

Phase 8 closes two integration gaps — both are surgical one-to-three-line fixes with no refactoring. The research confirms all decisions in CONTEXT.md are correct by reading the actual source code.

**Bug 1 (RISK-03):** `engine.py` lines 420–456 show the `if not no_filled:` block starts at line 420 with only a `logger.warning()` call before the hedge SELL. There is no call to `risk_gate.record_order_error()` in this path. The existing `hasattr(risk_gate, "record_order_error")` guard pattern at line 327 (YES verify failure) is the exact model to mirror.

**Bug 2 (OBS-02):** `live_run.py` line 399 passes `risk_gate.circuit_breaker_errors` (the static configured int, e.g. `5`) to `alerter.send_circuit_breaker_trip(error_count=...)`. After `record_order_error()` trips the CB it clears `_error_timestamps`, so there is no way to read the live count post-trip. The fix is to capture `len(self._error_timestamps)` into `self._last_trip_count` immediately before `self._error_timestamps.clear()` in `gate.py`, then expose it as a property, then reference `risk_gate.last_trip_error_count` at the live_run.py call site.

**The test gap is real:** `test_live_run.py::test_cb_alert_fires_on_trip` (line 283–286) currently asserts `error_count=5` matching `mock_rg.circuit_breaker_errors = 5` — which passes today because the static threshold equals the expected count. The new test must use a mock where `last_trip_error_count` differs from `circuit_breaker_errors` to prove the fix.

**Primary recommendation:** Three file edits (engine.py, gate.py, live_run.py) + two test file additions (engine + live_run tests). All changes are non-breaking and additive except the one-word live_run.py substitution.

---

## Standard Stack

No new libraries. All fixes use Python stdlib and existing project dependencies.

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| Python | 3.12 (Docker base) | Runtime | Already installed |
| pytest + pytest-asyncio | installed (asyncio_mode=auto) | Test runner | Already configured |
| unittest.mock (AsyncMock, MagicMock, patch) | stdlib | Mocking in tests | Already used in existing tests |
| loguru | 0.7+ | Logging | Already used in gate.py and engine.py |

**Installation:** No new packages required.

---

## Architecture Patterns

### Files to Modify (from CONTEXT.md canonical refs)

```
src/bot/
├── execution/engine.py        # Add record_order_error() call at line ~420
├── risk/gate.py               # Add _last_trip_count attribute + property
└── live_run.py                # Change error_count= argument at line ~399

tests/
├── test_execution_engine.py   # Add 2 new tests (D-04 #1, #3)
└── test_live_run.py           # Add 1 new test (D-04 #2), update existing test
```

### Pattern 1: record_order_error() hasattr guard (existing — mirror this)

The YES verify failure path at engine.py line 327 uses this pattern. Mirror exactly for NO exhaustion:

```python
# Source: src/bot/execution/engine.py lines 327-328 (existing — already in production)
if hasattr(risk_gate, "record_order_error"):
    risk_gate.record_order_error()
```

Application for Bug 1 fix (insert at line 420, top of `if not no_filled:` block):
```python
if not no_filled:
    if hasattr(risk_gate, "record_order_error"):
        risk_gate.record_order_error()
    logger.warning(
        f"NO leg exhausted all retries — triggering hedge SELL | "
        f"market={opp.market_id} price={_HEDGE_PRICE}"
    )
    # ... hedge SELL continues unchanged
```

### Pattern 2: Instance attribute + property (gate.py)

RiskGate uses mutable instance attributes for state (already established pattern: `_error_timestamps`, `_cb_cooldown_until`, `_cb_cooldown_multiplier`, `_kill_switch_active`). Adding `_last_trip_count` follows the identical pattern.

Current `record_order_error()` trip block (gate.py lines 118-126):
```python
if len(self._error_timestamps) >= self.circuit_breaker_errors:
    cooldown = self.circuit_breaker_cooldown_seconds * self._cb_cooldown_multiplier
    self._cb_cooldown_until = now + cooldown
    self._cb_cooldown_multiplier = min(self._cb_cooldown_multiplier * 2, 4)
    self._error_timestamps.clear()          # <-- count lost here
    logger.warning(...)
```

Fixed trip block (insert capture before clear):
```python
if len(self._error_timestamps) >= self.circuit_breaker_errors:
    cooldown = self.circuit_breaker_cooldown_seconds * self._cb_cooldown_multiplier
    self._cb_cooldown_until = now + cooldown
    self._cb_cooldown_multiplier = min(self._cb_cooldown_multiplier * 2, 4)
    self._last_trip_count = len(self._error_timestamps)  # capture before clear
    self._error_timestamps.clear()
    logger.warning(...)
```

Property to add after `cb_cooldown_remaining()`:
```python
@property
def last_trip_error_count(self) -> int:
    """Error count that triggered the most recent CB trip. 0 if never tripped."""
    return self._last_trip_count
```

### Pattern 3: CB alert call site in live_run.py (lines 397-401)

Current (passing static threshold — the bug):
```python
# live_run.py line 397-401 (current — BUG)
if not was_cb_open and risk_gate.is_circuit_breaker_open():
    asyncio.create_task(alerter.send_circuit_breaker_trip(
        error_count=risk_gate.circuit_breaker_errors,
        cooldown_seconds=risk_gate.cb_cooldown_remaining(),
    ))
```

Fixed (passing live triggering count):
```python
# live_run.py line 397-401 (fixed)
if not was_cb_open and risk_gate.is_circuit_breaker_open():
    asyncio.create_task(alerter.send_circuit_breaker_trip(
        error_count=risk_gate.last_trip_error_count,
        cooldown_seconds=risk_gate.cb_cooldown_remaining(),
    ))
```

### Pattern 4: Test structure — engine.py tests

All engine tests follow the same structure:
- `@patch("bot.execution.engine.kelly_size", return_value=10.0)` — prevents Kelly from returning 0
- `@patch("bot.execution.engine.verify_fill_rest", new_callable=AsyncMock, return_value=True)` — or False
- `client = MagicMock()` with `client.get_order_book.return_value = mock_book`
- `risk_gate = MagicMock()` with `risk_gate.is_kill_switch_active.return_value = False`
- Assert on `risk_gate.record_order_error.call_count`

New test for D-04 #1 (NO exhaustion trips CB):
```python
@patch("bot.execution.engine.kelly_size", return_value=10.0)
@patch("bot.execution.engine.verify_fill_rest", new_callable=AsyncMock, return_value=True)
async def test_no_exhaustion_calls_record_order_error(mock_verify, mock_kelly):
    """YES fills; all 3 NO retries fail → record_order_error() called once."""
    call_counter = {"n": 0}

    async def side_effect(*args, **kwargs):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            return {"orderID": "yes1", "status": "matched"}
        side_arg = kwargs.get("side") or (args[4] if len(args) > 4 else None)
        if side_arg == "SELL":
            return {"orderID": "hedge1", "status": "matched"}
        return None  # NO BUY attempts fail

    with patch("bot.execution.engine.place_fak_order", new_callable=AsyncMock,
               side_effect=side_effect):
        client = MagicMock()
        mock_book = MagicMock()
        level = MagicMock()
        level.price = "0.48"
        level.size = "500"
        mock_book.asks = [level]
        client.get_order_book.return_value = mock_book
        risk_gate = MagicMock()
        risk_gate.is_kill_switch_active.return_value = False
        _, results = await execute_opportunity(client, _opp(), _config(), risk_gate)
        risk_gate.record_order_error.assert_called_once()
```

New test for D-04 #3 (regression — YES verify failure still trips CB):
```python
@patch("bot.execution.engine.kelly_size", return_value=10.0)
@patch("bot.execution.engine.place_fak_order", new_callable=AsyncMock,
       return_value={"orderID": "yes1", "status": "matched"})
@patch("bot.execution.engine.verify_fill_rest", new_callable=AsyncMock, return_value=False)
async def test_yes_verify_failure_calls_record_order_error(mock_verify, mock_place, mock_kelly):
    """YES verify returns False → record_order_error() still called (regression guard)."""
    client = MagicMock()
    mock_book = MagicMock()
    level = MagicMock()
    level.price = "0.48"
    level.size = "500"
    mock_book.asks = [level]
    client.get_order_book.return_value = mock_book
    risk_gate = MagicMock()
    _, _ = await execute_opportunity(client, _opp(), _config(), risk_gate)
    risk_gate.record_order_error.assert_called_once()
```

### Pattern 5: Test structure — live_run.py CB alert test

The existing `test_cb_alert_fires_on_trip` (line 241-286) uses `mock_rg.circuit_breaker_errors = 5`. The new test must use a mock where `last_trip_error_count` returns a value different from `circuit_breaker_errors` to prove the fix.

New test for D-04 #2 (CB alert shows live count):
```python
@pytest.mark.asyncio
async def test_cb_alert_shows_live_count_not_static_threshold():
    """CB alert fires with last_trip_error_count (live), not circuit_breaker_errors (static)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = _test_config()
        client = MagicMock()

        alerter_mock = MagicMock()
        alerter_mock.send_circuit_breaker_trip = AsyncMock(return_value=None)

        # CB starts closed (False), then trips (True) on second call
        cb_open_calls = [False, True]
        call_count = [0]

        def cb_open_side_effect():
            idx = min(call_count[0], len(cb_open_calls) - 1)
            result = cb_open_calls[idx]
            call_count[0] += 1
            return result

        with patch("bot.live_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
             patch("bot.live_run.WebSocketClient") as mock_ws, \
             patch("bot.live_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.live_run.detect_yes_no_opportunities", return_value=[]), \
             patch("bot.live_run.detect_cross_market_opportunities", return_value=[]), \
             patch("bot.live_run._start_dashboard", new_callable=AsyncMock), \
             patch("bot.live_run._daily_summary_task", new_callable=AsyncMock), \
             patch("bot.live_run.TelegramAlerter", return_value=alerter_mock), \
             patch("bot.live_run.RiskGate") as mock_rg_cls:
            mock_ws.return_value.run = AsyncMock()
            mock_rg = MagicMock()
            mock_rg.is_kill_switch_active.return_value = False
            mock_rg.is_blocked.return_value = False
            mock_rg.is_stop_loss_triggered.return_value = False
            mock_rg.is_circuit_breaker_open.side_effect = cb_open_side_effect
            mock_rg.circuit_breaker_errors = 5      # static configured threshold
            mock_rg.last_trip_error_count = 7       # live count differs — e.g. 7 errors burst
            mock_rg.cb_cooldown_remaining.return_value = 300.0
            mock_rg_cls.return_value = mock_rg
            from bot import live_run
            await live_run.run(config, client, duration_hours=0.00001, db_path=db_path)

        await asyncio.sleep(0)
        # Must pass live count (7), NOT static threshold (5)
        alerter_mock.send_circuit_breaker_trip.assert_awaited_once_with(
            error_count=7,
            cooldown_seconds=300.0,
        )
```

### Anti-Patterns to Avoid

- **Placing `record_order_error()` AFTER the hedge SELL attempt**: The CONTEXT.md decision D-01 locks the position — BEFORE the hedge, not after. Error already established at retry exhaustion.
- **Returning the count from `record_order_error()`**: D-02 locks the approach to instance attribute + property, not return value. Changing the return signature would be a more invasive API change.
- **Asserting `error_count=5` in the new CB live-count test**: This would replicate the bug in the test. Use `error_count=7` (a value that differs from `circuit_breaker_errors=5`) so the test fails if the fix is not applied.
- **Adding a kill switch guard to the `if not no_filled:` block**: CONTEXT.md `<specifics>` section confirms that when the kill switch breaks the retry loop early, `no_filled` is still False — so `record_order_error()` WILL fire. CONTEXT.md says this is "acceptable." Adding an extra `is_kill_switch_active()` guard is at Claude's discretion but is not required.
- **Modifying `_error_timestamps` clear timing**: The count MUST be captured before `.clear()`. Any other ordering loses the data.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Live error count tracking | Custom counter, separate list, return value | `_last_trip_count` instance attribute set before `.clear()` | Non-invasive, no API change, zero race conditions in single-threaded asyncio loop |
| Test CB transition in live_run | Integration test with real RiskGate | Mock `is_circuit_breaker_open` with `side_effect` list | Existing pattern (test_cb_alert_fires_on_trip) already proves this works; no need to wire real RiskGate through live_run |

---

## Common Pitfalls

### Pitfall 1: Count captured AFTER clear — loses the data

**What goes wrong:** Placing `self._last_trip_count = len(self._error_timestamps)` after `self._error_timestamps.clear()` always stores `0`.

**Why it happens:** `.clear()` is destructive. After it, `len()` returns 0.

**How to avoid:** The line `self._last_trip_count = len(self._error_timestamps)` must appear BEFORE `self._error_timestamps.clear()`. CONTEXT.md D-02 is explicit about this.

**Warning signs:** `last_trip_error_count` always returns 0; the new test for D-04 #2 fails.

### Pitfall 2: `record_order_error()` placed after hedge SELL — wrong semantics

**What goes wrong:** Placing `risk_gate.record_order_error()` after the hedge SELL block means the CB counts the hedge attempt, not the NO retry exhaustion.

**Why it happens:** The hedge block follows `if not no_filled:`. Inserting the call at the bottom of the block instead of the top.

**How to avoid:** Insert at the top of `if not no_filled:` as specified in D-01 and confirmed by the YES-verify-failure pattern at line 327.

**Warning signs:** The CB fires on hedge SELL failures rather than NO retry failures; semantically wrong per D-07 docstring ("Only call from execution path — order rejection, timeout, auth failure").

### Pitfall 3: Existing CB alert test breaks

**What goes wrong:** `test_cb_alert_fires_on_trip` currently asserts `error_count=5` and `mock_rg.circuit_breaker_errors = 5`. After the live_run.py fix, it reads `risk_gate.last_trip_error_count` instead of `risk_gate.circuit_breaker_errors`. The `MagicMock` will auto-create `last_trip_error_count` as a `MagicMock` object, not `5`, so the assertion `error_count=5` will fail.

**How to avoid:** Update the existing `test_cb_alert_fires_on_trip` to also set `mock_rg.last_trip_error_count = 5` so the assertion continues to pass. This is a one-line addition to the existing test.

**Warning signs:** `test_cb_alert_fires_on_trip` fails with `AssertionError: Expected call: send_circuit_breaker_trip(error_count=5, ...)` after the live_run.py fix.

### Pitfall 4: `hasattr` guard omitted for NO exhaustion path

**What goes wrong:** Calling `risk_gate.record_order_error()` directly (without `hasattr` guard) means tests that pass a `MagicMock()` with no explicit method spec will call the auto-mock silently — but other code paths (like Gate 0 skips) that don't provide a real RiskGate might raise `AttributeError`.

**Why it happens:** The `hasattr` guard was added deliberately to the YES verify path. Omitting it for the NO path creates an inconsistency.

**How to avoid:** Mirror exactly: `if hasattr(risk_gate, "record_order_error"): risk_gate.record_order_error()`.

**Note:** `MagicMock()` will auto-generate the attribute, so the `hasattr` guard doesn't affect test behavior — it only guards against unexpected callers passing objects without the method.

### Pitfall 5: `asyncio.create_task` wrapper means alert test needs `await asyncio.sleep(0)`

**What goes wrong:** `asyncio.create_task(alerter.send_circuit_breaker_trip(...))` schedules the coroutine as a task. Without yielding the event loop, the task may not run before the assertion.

**How to avoid:** All existing alert tests in test_live_run.py already include `await asyncio.sleep(0)` after the `live_run.run()` call. Follow this pattern for the new test.

**Warning signs:** `assert_awaited_once_with` fails intermittently or always fails even with correct fix.

---

## Code Examples

### engine.py — exact insertion point

Current code at lines 417-425 (the `if not no_filled:` block opening):
```python
# Source: src/bot/execution/engine.py lines 417-425 (read 2026-04-18)
    # ------------------------------------------------------------------
    # Hedge: if NO never filled, SELL YES at market-aggressive price=0.01
    # ------------------------------------------------------------------
    if not no_filled:
        logger.warning(
            f"NO leg exhausted all retries — triggering hedge SELL | "
            f"market={opp.market_id} price={_HEDGE_PRICE}"
        )
```

After fix — insert 2 lines before `logger.warning`:
```python
    if not no_filled:
        if hasattr(risk_gate, "record_order_error"):
            risk_gate.record_order_error()
        logger.warning(
            f"NO leg exhausted all retries — triggering hedge SELL | "
            f"market={opp.market_id} price={_HEDGE_PRICE}"
        )
```

### gate.py — __init__ addition

Current `__init__` ends at line 79 with `self._kill_switch_active: bool = False`. Add one line:
```python
# Source: src/bot/risk/gate.py lines 73-79 (read 2026-04-18)
        # Mutable state
        self._daily_loss_usd: float = 0.0
        self._day_reset_timestamp: float = time.time()
        self._error_timestamps: list[float] = []
        self._cb_cooldown_until: float = 0.0
        self._cb_cooldown_multiplier: int = 1
        self._kill_switch_active: bool = False
        self._last_trip_count: int = 0  # ADD THIS LINE
```

### gate.py — record_order_error() trip block insertion

Current block (lines 118-126):
```python
# Source: src/bot/risk/gate.py lines 118-126 (read 2026-04-18)
        if len(self._error_timestamps) >= self.circuit_breaker_errors:
            cooldown = self.circuit_breaker_cooldown_seconds * self._cb_cooldown_multiplier
            self._cb_cooldown_until = now + cooldown
            self._cb_cooldown_multiplier = min(self._cb_cooldown_multiplier * 2, 4)
            self._error_timestamps.clear()
            logger.warning(
                f"Circuit breaker tripped — cooldown {cooldown}s "
                f"(next multiplier={self._cb_cooldown_multiplier}x)"
            )
```

After fix (insert capture before clear):
```python
        if len(self._error_timestamps) >= self.circuit_breaker_errors:
            cooldown = self.circuit_breaker_cooldown_seconds * self._cb_cooldown_multiplier
            self._cb_cooldown_until = now + cooldown
            self._cb_cooldown_multiplier = min(self._cb_cooldown_multiplier * 2, 4)
            self._last_trip_count = len(self._error_timestamps)  # ADD BEFORE clear
            self._error_timestamps.clear()
            logger.warning(
                f"Circuit breaker tripped — cooldown {cooldown}s "
                f"(next multiplier={self._cb_cooldown_multiplier}x)"
            )
```

### live_run.py — one-word substitution at line 399

```python
# Source: src/bot/live_run.py lines 397-401 (read 2026-04-18)
# Before (bug):
        if not was_cb_open and risk_gate.is_circuit_breaker_open():
            asyncio.create_task(alerter.send_circuit_breaker_trip(
                error_count=risk_gate.circuit_breaker_errors,
                cooldown_seconds=risk_gate.cb_cooldown_remaining(),
            ))

# After (fix):
        if not was_cb_open and risk_gate.is_circuit_breaker_open():
            asyncio.create_task(alerter.send_circuit_breaker_trip(
                error_count=risk_gate.last_trip_error_count,
                cooldown_seconds=risk_gate.cb_cooldown_remaining(),
            ))
```

---

## Runtime State Inventory

Step 2.5: SKIPPED — This is not a rename/refactor/migration phase. No string replacement, no data migration required. The changes are additive code edits and a one-word substitution.

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — all changes are internal code edits using already-installed project dependencies).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pytest.ini` (root of project) |
| asyncio_mode | `auto` (all async tests run without `@pytest.mark.asyncio` decorator — but existing tests use it anyway) |
| Quick run command | `pytest tests/test_execution_engine.py tests/test_live_run.py tests/test_risk_gate.py -x` |
| Full suite command | `pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RISK-03 | NO-leg retry exhaustion calls `record_order_error()` | unit | `pytest tests/test_execution_engine.py::test_no_exhaustion_calls_record_order_error -x` | ❌ Wave 0 |
| RISK-03 | YES verify failure still calls `record_order_error()` (regression) | unit | `pytest tests/test_execution_engine.py::test_yes_verify_failure_calls_record_order_error -x` | ❌ Wave 0 |
| OBS-02 | CB alert passes live count (`last_trip_error_count`), not static threshold | unit | `pytest tests/test_live_run.py::test_cb_alert_shows_live_count_not_static_threshold -x` | ❌ Wave 0 |
| OBS-02 | Existing CB alert test still passes after live_run.py fix | regression | `pytest tests/test_live_run.py::test_cb_alert_fires_on_trip -x` | ✅ exists |

### Sampling Rate
- **Per task commit:** `pytest tests/test_execution_engine.py tests/test_live_run.py tests/test_risk_gate.py -x`
- **Per wave merge:** `pytest -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_execution_engine.py` — add `test_no_exhaustion_calls_record_order_error` and `test_yes_verify_failure_calls_record_order_error` — covers RISK-03
- [ ] `tests/test_live_run.py` — add `test_cb_alert_shows_live_count_not_static_threshold`; update `test_cb_alert_fires_on_trip` to set `mock_rg.last_trip_error_count = 5` — covers OBS-02

*(No framework installation needed — pytest + pytest-asyncio already configured)*

---

## Project Constraints (from CLAUDE.md)

| Directive | Applies to Phase 8? |
|-----------|-------------------|
| Must integrate with Polymarket's official API | No change to API integration |
| Ultra-low latency execution required | No change to execution path latency (record_order_error() is O(n) over a tiny list, negligible) |
| Under $1k total capital at risk | No change |
| Must run continuously on cloud VPS | No change |
| GSD Workflow Enforcement: use GSD commands before file edits | Yes — phase is executing through GSD |
| Tech stack: Python 3.10+ | No new packages |

---

## Open Questions

1. **Kill switch mid-retry: should record_order_error() fire or be skipped?**
   - What we know: CONTEXT.md `<specifics>` says it's "acceptable" for the call to fire when kill switch breaks the retry loop, since NO leg still failed.
   - What's unclear: Whether adding `if not risk_gate.is_kill_switch_active():` guard before `record_order_error()` is preferred for semantic purity.
   - Recommendation: Leave as-is (let it fire). The `is_kill_switch_active()` guard is at Claude's discretion per CONTEXT.md. Adding it would require an additional state check that slightly complicates the code with marginal benefit — the CB cooldown becomes irrelevant the moment kill switch is active anyway.

2. **Type annotation in class body (`_last_trip_count: int`)?**
   - What we know: Other attributes (`_daily_loss_usd: float`, `_error_timestamps: list[float]`) are declared only in `__init__`, not as class-body annotations. The RiskGate class has no class-body attribute declarations.
   - Recommendation: Do NOT add class-body annotation. Follow the existing pattern — declare only in `__init__`. This is consistent with all other mutable state attributes in the class.

---

## Sources

### Primary (HIGH confidence)
- `src/bot/execution/engine.py` — read 2026-04-18, lines 420-456 confirm bug location and exact context
- `src/bot/risk/gate.py` — read 2026-04-18, lines 104-126 confirm `record_order_error()` internals and clear timing
- `src/bot/live_run.py` — read 2026-04-18, lines 397-401 confirm exact bug: `risk_gate.circuit_breaker_errors` passed to alert
- `src/bot/notifications/telegram.py` — read 2026-04-18, `send_circuit_breaker_trip(error_count: int, cooldown_seconds: float)` signature confirmed
- `tests/test_execution_engine.py` — read 2026-04-18, all 8 existing tests reviewed for mocking patterns
- `tests/test_live_run.py` — read 2026-04-18, `test_cb_alert_fires_on_trip` at lines 241-286 reviewed
- `tests/test_risk_gate.py` — read 2026-04-18, confirms RiskGate test patterns (sync, no AsyncMock)
- `pytest.ini` — read 2026-04-18, `asyncio_mode = auto` confirmed
- `.planning/phases/08-fix-circuit-breaker-alert-accuracy/08-CONTEXT.md` — all decisions locked

---

## Metadata

**Confidence breakdown:**
- Bug locations: HIGH — confirmed by direct source code read
- Fix approach: HIGH — locked in CONTEXT.md, validated against actual code structure
- Test patterns: HIGH — inferred from reading 8 existing engine tests + 8 live_run tests
- Regression risk: HIGH — only 3 existing tests touch the affected code paths; all identified

**Research date:** 2026-04-18
**Valid until:** No external dependencies — source code is the truth, valid indefinitely
