# Phase 4 Code Review — Observability & Monitoring

**Reviewer:** Claude (gsd-verifier)
**Date:** 2026-04-15
**Scope:** Phase 4 changes to the Polymarket Arbitrage Bot
**Verdict:** CONDITIONAL SHIP — 2 BLOCKs must be resolved before deploying to live capital

---

## Verdict Summary

| Severity | Count |
|----------|-------|
| BLOCK    | 2     |
| FLAG     | 8     |
| PASS     | 12    |

The two BLOCKs are logic errors that will silently corrupt financial data in production:
(1) fees are computed twice and added together for the `arb_pairs` row, and
(2) the `_query_open_positions_count` JOIN silently under-counts open positions for YES legs
that have a corresponding NO-leg row in `trades` but no `arb_pairs` row yet.

---

## BLOCKs — Must Fix Before Shipping

### BLOCK-1: Fee double-counting in `arb_pairs` P&L calculation

**File:** `src/bot/live_run.py`, lines 293–315

**Description:**
For each leg result in `results`, `fees_usd` is computed and passed to `insert_trade()`.
Then, when both legs are confirmed and the `arb_pairs` row is assembled, `yes_fees` and
`no_fees` are recomputed from scratch using `get_taker_fee()` again — on the same
`size_filled` values. This is correct for the `arb_pairs.fees_usd` column itself.

However the P&L formula on line 316–317 is:

```python
gross_pnl = (1.0 - yes_result.price - no_result.price) * yes_result.size_filled
net_pnl = gross_pnl - total_fees
```

`size_filled` here equals `kelly_usd` (the requested size in USD). On the YES leg this is
the USD amount spent, not the number of contracts. For a YES token at $0.40, spending $10
buys 25 contracts. The gross P&L of a YES/NO arb resolves to
`(1 - entry_yes - entry_no) * contracts`, not `(1 - entry_yes - entry_no) * usd_spent`.

When `price < 1.0`, `size_filled` in USD and `size_in_contracts` diverge:
- USD spent on YES = `kelly_usd`
- Contracts received = `kelly_usd / price`

The formula should be `(1.0 - yes_price - no_price) * (kelly_usd / yes_price)` or
equivalently expressed in contract units consistently. Using `yes_result.size_filled`
(which is set to `kelly_usd` on the confirmed fill path in `engine.py` line 307) produces
a P&L figure that is systematically wrong for any price other than $0.50.

**Example:** YES at 0.40, NO at 0.55, kelly_usd = 10
- Gross P&L (current code): `(1 - 0.40 - 0.55) * 10 = $0.50`
- Correct (contract-based): `(1 - 0.40 - 0.55) * (10/0.40) = $1.25`

The dashboard and Telegram alert will both display the wrong P&L figure. The `trades` rows
are unaffected because `net_pnl` is not computed there.

**Fix required:** Decide whether sizes are tracked in USD or contracts throughout the
execution path, then apply the consistent formula. The `arb_pairs.size_usd` column stores
`yes_result.size_filled` and labels it "size_usd", which suggests USD is the intended unit.
If so the gross P&L formula must account for the price-to-contract conversion.

---

### BLOCK-2: `_query_open_positions_count` silently misses YES legs with failed NO fills

**File:** `src/bot/dashboard/app.py`, lines 76–87

```python
cursor = conn.execute(
    "SELECT COUNT(*) FROM trades t "
    "LEFT JOIN arb_pairs ap ON ap.yes_trade_id = t.trade_id "
    "WHERE t.leg = 'yes' AND t.status = 'filled' AND ap.arb_id IS NULL"
)
```

**Description:**
The JOIN condition `ap.yes_trade_id = t.trade_id` matches only if the `arb_pairs` row
records this specific `yes_trade_id`. But `arb_pairs` rows are written using a freshly
generated `trade_id = str(uuid.uuid4())` local to each loop iteration. That ID is
correctly stored in `yes_trade_id` in `live_run.py` line 300.

The real problem is a different scenario: when the NO leg fails and a hedge SELL fires,
the YES leg remains in `trades` with `status = 'filled'` and no corresponding `arb_pairs`
row (by design per D-12 and D-19). The query is intended to count these.

However the query also matches YES fills where the `arb_pairs` row has been written but
the `yes_trade_id` column in `arb_pairs` uses a different UUID than what appears in
`trades.trade_id`. Since `trade_id` is generated with `uuid.uuid4()` inside the for-loop
(line 290), and this same value is used as `yes_trade_id` in the `arb_pair` dict (line
300), the JOIN will work correctly when the row is written. So the direct JOIN logic is
sound.

The actual gap is more subtle: the query only counts `leg = 'yes'`. In a YES/NO arb, an
"open position" after a failed NO fill is the YES holding — that is counted. But if the
YES fill verification fails (engine returns early with `status = 'failed'` before the NO
leg even runs), `status` is `'failed'`, not `'filled'`, so these are not counted — that
is also correct.

Re-examining: the genuine bug is that `leg = 'yes' AND status = 'filled'` also matches
YES legs for arbs that completed successfully (both legs filled) because the `arb_pairs`
JOIN will exclude them only if the `yes_trade_id` matches. Since `insert_arb_pair` uses
the same UUID, successful arbs will have a matching `arb_pairs` row and will be excluded.
This logic is actually correct.

**Revised finding:** The query logic is correct as written. Reclassifying to FLAG-1 below.

---

**Revised BLOCK-2:** Replacing with the actual BLOCK-2 finding.

### BLOCK-2: XSS via `market_question` rendered as raw HTML in dashboard JS

**File:** `src/bot/dashboard/app.py`, lines 487 and 511 (inside `_DASHBOARD_HTML`)

```javascript
'<td class="market-cell" title="' + (t.market_question || '') + '">' +
    (t.market_question || '').substring(0,48) + '</td>'
```

and in `renderArbs`:

```javascript
'<td class="market-cell">' + (a.market_question || '').substring(0,48) + '</td>'
```

**Description:**
`market_question` is a string read directly from SQLite (which in turn came from the
Polymarket API). These strings are interpolated directly into innerHTML via string
concatenation without HTML-escaping. If a market question contains `<script>` tags, angle
brackets, or quote characters, those characters will be interpreted as HTML by the browser.

Polymarket questions could in theory contain characters like `<`, `>`, `"`, or `&` — for
example: `Will the S&P 500 > 5000 by year end?`. An ampersand or a `>` in a market title
will break the table layout. A crafted or malicious market question could execute arbitrary
JavaScript in the operator's browser.

The `title` attribute interpolation on the same line is additionally dangerous because a
`"` character in `market_question` will break out of the attribute value.

The dashboard is described as VPS-only with no auth (D-18), but the operator's browser
executing attacker-controlled JS is still a meaningful risk when wallet private keys are
in the environment.

**Fix required:** Add an `escapeHtml()` function in the dashboard JS that replaces
`&`, `<`, `>`, `"`, `'` with their HTML entity equivalents. Apply it to all dynamic text
inserted into `innerHTML`. The `title` attribute value must also be escaped.

---

## FLAGs — Worth Fixing

### FLAG-1: `_derive_bot_status` accesses private attribute `_cb_cooldown_until` directly

**File:** `src/bot/dashboard/app.py`, lines 139 and 621

```python
cooldown_remaining = max(0.0, risk_gate._cb_cooldown_until - time.time())
```

This is duplicated in two places (inside `_derive_bot_status` and in the `status` endpoint
function). `RiskGate` exposes `is_circuit_breaker_open()` as a public API but does not
expose the remaining cooldown duration. The dashboard reaches into the private attribute
to show the countdown timer. If `RiskGate` is ever refactored, this silently breaks.

The test suite mocks `_cb_cooldown_until` directly (`risk_gate._cb_cooldown_until = 0.0`),
which means the coupling is baked into the test contract as well.

**Recommendation:** Add a `circuit_breaker_cooldown_remaining_seconds() -> float` method
to `RiskGate`. Low priority since the bot is single-author, but the coupling is fragile.

---

### FLAG-2: `send_arb_complete` uses HTML parse mode but `market_question` is not escaped

**File:** `src/bot/notifications/telegram.py`, lines 93–99

```python
text = (
    f"<b>Arb complete — {market_question[:60]}</b>\n\n"
    ...
)
await self.send(text, parse_mode="HTML")
```

The comment on line 80 says "avoids HTML entity escaping issues on dynamic content", but
then `market_question` is embedded directly inside `<b>` tags with `parse_mode="HTML"`.
A market question containing `</b>` or `<` will break the Telegram message formatting or
cause a `BadRequest` from the Telegram API (which `TelegramError` will catch and swallow).
The comment is wrong and the implementation is inconsistent with its stated rationale.

**Recommendation:** Either switch this alert to `parse_mode=None` (plain text) and remove
the `<b>` tags, or apply `html.escape()` to `market_question` before embedding.

---

### FLAG-3: `_daily_summary_task` queries `submitted_at` with a date prefix, not a full ISO timestamp

**File:** `src/bot/live_run.py`, lines 126–128

```python
today_str = datetime.utcnow().strftime("%Y-%m-%d")
cursor = conn.execute(
    "SELECT COUNT(*) FROM trades WHERE submitted_at >= ?",
    (today_str,)
)
```

`submitted_at` is stored as a full ISO 8601 string like `2026-04-15T10:00:00.123456`
(from `datetime.utcnow().isoformat()` in `schema.py`). SQLite string comparison with
`>= "2026-04-15"` works because ISO strings sort lexicographically — `"2026-04-15T..."
>= "2026-04-15"` is true. This is technically correct but fragile: it relies on the ISO
format being stable and no subsecond precision changing the sort order.

More importantly, the same `today_str` is used for `arb_pairs WHERE entry_time >= ?`.
The `entry_time` field stores `datetime.utcnow().isoformat()` (line 287), so the same
implicit comparison applies. This works but should be documented explicitly.

**Recommendation:** Use `today_str + "T00:00:00"` as the cutoff to make the range query
explicit and unambiguous. Not a correctness bug under current behavior, but worth noting.

---

### FLAG-4: `_query_open_positions_count` does not filter out `hedge` leg fills

**File:** `src/bot/dashboard/app.py`, lines 79–82

The query counts `leg = 'yes' AND status = 'filled'` with no corresponding `arb_pairs`
row. However, a successful hedge SELL (`leg = 'hedge'`, `status = 'hedged'`) closes the
YES position. After a hedge fires, the YES leg `status` in `trades` remains `'filled'`
(it was set at YES fill time). The hedge is a separate row with `leg = 'hedge'`. The
query will continue counting this YES trade as an "open position" even after the hedge
has closed it, because the hedge leg has a different `trade_id` and there is no foreign
key linking them.

This means "OPEN POSITIONS" on the dashboard will over-count by 1 for every completed
hedge. With active trading this could show e.g. 3 open positions when all positions are
closed via hedges.

**Recommendation:** Track which YES `trade_id` was hedged. One approach: store the YES
`trade_id` in the hedge result's `error_msg` or add a `parent_trade_id` column to
`trades`. Alternatively, query for YES fills that have no associated hedge row:
`AND NOT EXISTS (SELECT 1 FROM trades h WHERE h.leg = 'hedge' AND h.market_id = t.market_id AND h.status = 'hedged')`.
This is imperfect (market_id is not unique per arb) but closer to correct. The real fix
needs an explicit link column.

---

### FLAG-5: Dashboard `/api/status` executes 6 SQL queries synchronously on every request

**File:** `src/bot/dashboard/app.py`, lines 630–641

```python
return {
    ...
    "open_positions_count": _query_open_positions_count(state.conn),
    "efficiency_7d_pct": _query_capital_efficiency(state.conn, 7, ...),
    "efficiency_30d_pct": _query_capital_efficiency(state.conn, 30, ...),
    "total_fees_paid_usd": _query_total_fees(state.conn),
    "avg_fee_rate_pct": _query_avg_fee_rate(state.conn),
    "recent_trades": _query_recent_trades(state.conn, limit=20),
    "arb_pairs": _query_arb_pairs(state.conn, limit=20),
}
```

All 6 calls are synchronous SQLite queries executed in the FastAPI request handler — which
runs in the asyncio event loop. SQLite `conn.execute()` is blocking I/O. Under CPython,
short SQLite queries against a small DB (Phase 4 scale: <1000 rows) block the event loop
for microseconds — tolerable. However `_query_capital_efficiency` does a full table scan
of `arb_pairs` for 7-day and 30-day windows. As the table grows these block longer.

Given the documented constraint (under $1k capital, low trade volume), this is not an
immediate problem. It becomes one if Phase 5 extends the bot's life span.

**Recommendation:** Cache the 7d/30d efficiency values in `AppState` and recompute them
once per scan cycle rather than on every dashboard request. Not urgent for Phase 4.

---

### FLAG-6: `test_live_run_exits_on_kill_file` does not assert the kill switch was triggered

**File:** `tests/test_live_run.py`, lines 30–54

The test creates a KILL file, runs `live_run.run()`, and asserts only that the coroutine
returns (i.e., the loop exited). It does not assert that `risk_gate.activate_kill_switch()`
was called or that `_execute_kill_switch()` ran. The test passes even if the loop exits
for an unrelated reason (e.g., `duration_hours=0.001` elapsed before the KILL file was
checked). This is not a false positive today because the test is clearly time-bound, but
it provides weaker guarantees than claimed by the docstring.

**Recommendation:** Capture a mock `RiskGate` instance in the test and assert
`mock_rg.activate_kill_switch.assert_called_once()`.

---

### FLAG-7: `test_alerter_calls_send_message_with_html_parse_mode` tests `send()` directly, not `send_arb_complete()`

**File:** `tests/test_telegram.py`, lines 50–62

The test verifies that `parse_mode="HTML"` is set when calling `alerter.send(...)` with
a string. But `send_arb_complete()` calls `self.send(text, parse_mode="HTML")` — there
is no test that verifies the full `send_arb_complete()` message format, the hold-time
formatting logic (the `if hold_seconds < 60` branch), or that the pnl sign prefix
(`pnl_sign`) is correct for negative values. The edge-case `hold_seconds = 60` (exactly
60) formats as "1m 0s" — untested.

**Recommendation:** Add a test for `send_arb_complete()` that checks the formatted string
passed to `send()`, including the `hold_seconds < 60` and `>= 60` branches.

---

### FLAG-8: Dashboard `countdown` timer drifts from actual refresh timing

**File:** `src/bot/dashboard/app.py` (inline JS), lines 586–591

```javascript
setInterval(refresh, 10000);
setInterval(function() {
  countdown = Math.max(0, countdown - 1);
  setEl('countdown', countdown);
}, 1000);
refresh();
```

The two `setInterval` calls are not synchronized. `countdown` is set to 10 at the end of
`refresh()`, but `refresh()` is called immediately on page load, then every 10000ms. The
1-second countdown interval starts at page load too, so they race. If `refresh()` takes
>0ms (it always does), the countdown will show "0" momentarily and then immediately jump
back to 10. On slow connections where the fetch takes several seconds, the countdown can
show negative-looking stale values before being reset.

This is a cosmetic issue only and does not affect data correctness.

**Recommendation:** Reset `countdown = 10` at the top of `refresh()` rather than the
bottom, or use a single `setInterval` to drive both the countdown and the fetch. Low
priority.

---

## PASSes — No Issues Found

1. **`schema.py` — `INSERT OR IGNORE`** on both `trades` and `arb_pairs` is correct
   duplicate protection. The `trade_id` uniqueness constraint is enforced at the DB level.

2. **`schema.py` — `fees_usd` parameter in `insert_trade()`** — The Phase 4 fix
   (previously hardcoded 0.0) is correct. The parameter flows through cleanly and the
   test `test_insert_trade_fees_usd_not_zero` validates it.

3. **`schema.py` — `check_same_thread=False`** in `init_db()` — Correct for a single
   asyncio event loop where the connection is shared. The dashboard's comment about
   CPython single-threaded asyncio is accurate.

4. **`telegram.py` — Fire-and-forget semantics** — The dual `except` blocks (one for
   `TelegramError`, one for `Exception`) with no re-raise correctly implement D-03.
   `asyncio.create_task()` usage in `live_run.py` is correct; the task's exceptions
   are silently swallowed inside `send()`.

5. **`telegram.py` — `send_daily_summary()` plain text mode** — Correct to avoid HTML
   escaping issues when `market_question` is embedded. Consistent with its own rationale
   (unlike `send_arb_complete()` in FLAG-2).

6. **`live_run.py` — `_stop_event` / `asyncio.wait_for` pattern** — Correct approach
   for interruptible sleep. `TimeoutError` is caught and treated as a normal cycle end.
   `_stop_event.set()` in the signal handler wakes the sleep immediately.

7. **`live_run.py` — Task cleanup in `finally` block** — `dashboard_task.cancel()`,
   `summary_task.cancel()`, and `ws_task.cancel()` are all awaited with `CancelledError`
   suppressed. `writer.stop()` and `conn.close()` are called last. Order is correct.

8. **`live_run.py` — arb_pairs write guard** — `if yes_result and no_result and
   yes_trade_id and no_trade_id:` correctly prevents writing `arb_pairs` on the hedge
   path per D-12/D-19.

9. **`engine.py` — tuple return `(arb_id, results)`** — Clean. `arb_id` is a stable UUID
   generated at the top of `execute_opportunity()`, before any leg is attempted. This
   ensures the ID is available whether the trade completes, fails, or is skipped.

10. **`dashboard/app.py` — `AppState` thread-safety comment** — Accurate. Single-threaded
    asyncio + `workers=1` means no locking is needed for the shared mutable fields.

11. **`docker-compose.yml` — Port 8080 exposure** — Correctly documents that VPS firewall
    must restrict access. No auth added per D-18. The `restart: unless-stopped` policy
    is appropriate.

12. **`config.py` — Telegram fields** — `telegram_bot_token` and `telegram_chat_id` are
    optional (`None` default), not in `REQUIRED_SECRETS`. This matches D-04.

---

## Test Coverage Gaps (not BLOCKs but notable)

- No test covers the full `arb_pairs` write path in `live_run.py` (both legs filled →
  `insert_arb_pair()` called → Telegram alert fired). The integration test
  `test_trade_inserted_on_execution` only tests `insert_trade()` directly, bypassing
  `live_run.run()` for the arb_pairs path.

- No test covers `_derive_bot_status()` or the `_daily_summary_task()` coroutine. The
  daily summary query logic (FLAG-3) is exercised nowhere.

- `test_dashboard.py` does not seed any rows into `trades` or `arb_pairs` before calling
  `/api/status`, so `recent_trades` and `arb_pairs` always return empty lists in the
  tests. The JSON structure is validated but the data-return path is untested.

- `send_circuit_breaker_trip()` and `send_kill_switch()` in `telegram.py` have no
  dedicated tests. They delegate to `send()` (which is tested), but the formatting
  logic is not verified.

---

## Summary

| # | Item | File | Severity |
|---|------|------|----------|
| BLOCK-1 | Gross P&L formula uses USD size instead of contract units | `live_run.py:316` | BLOCK |
| BLOCK-2 | XSS: `market_question` injected raw into innerHTML | `dashboard/app.py:487,511` | BLOCK |
| FLAG-1 | `_cb_cooldown_until` accessed as private attribute from outside `RiskGate` | `dashboard/app.py:139,621` | FLAG |
| FLAG-2 | `send_arb_complete` uses HTML mode but does not escape `market_question` | `telegram.py:93` | FLAG |
| FLAG-3 | Daily summary queries use date string comparison instead of ISO timestamp | `live_run.py:123` | FLAG |
| FLAG-4 | Open positions counter does not account for hedged-and-closed YES legs | `dashboard/app.py:79` | FLAG |
| FLAG-5 | 6 synchronous SQLite queries per dashboard request in async handler | `dashboard/app.py:630` | FLAG |
| FLAG-6 | Kill-file test does not assert `activate_kill_switch()` was called | `test_live_run.py:30` | FLAG |
| FLAG-7 | `send_arb_complete()` message format and hold-time branches are untested | `test_telegram.py` | FLAG |
| FLAG-8 | Countdown timer drifts from actual refresh interval | `dashboard/app.py` (JS) | FLAG |
