---
phase: project-review
reviewed: 2026-04-17T00:00:00Z
depth: standard
files_reviewed: 55
files_reviewed_list:
  - .gitignore
  - conftest.py
  - docker-compose.yml
  - Dockerfile
  - pytest.ini
  - requirements.txt
  - scripts/benchmark_latency.py
  - scripts/create_api_key.py
  - scripts/get_wallet_address.py
  - scripts/setup_vps.sh
  - src/bot/__init__.py
  - src/bot/client.py
  - src/bot/config.py
  - src/bot/dashboard/__init__.py
  - src/bot/dashboard/app.py
  - src/bot/detection/__init__.py
  - src/bot/detection/cross_market.py
  - src/bot/detection/fee_model.py
  - src/bot/detection/opportunity.py
  - src/bot/detection/yes_no_arb.py
  - src/bot/dry_run.py
  - src/bot/execution/__init__.py
  - src/bot/execution/engine.py
  - src/bot/execution/kelly.py
  - src/bot/execution/order_client.py
  - src/bot/health.py
  - src/bot/live_run.py
  - src/bot/main.py
  - src/bot/notifications/__init__.py
  - src/bot/notifications/telegram.py
  - src/bot/risk/__init__.py
  - src/bot/risk/gate.py
  - src/bot/scanner/__init__.py
  - src/bot/scanner/http_poller.py
  - src/bot/scanner/market_filter.py
  - src/bot/scanner/normalizer.py
  - src/bot/scanner/price_cache.py
  - src/bot/scanner/ws_client.py
  - src/bot/storage/__init__.py
  - src/bot/storage/schema.py
  - src/bot/storage/writer.py
  - tests/conftest.py
  - tests/test_config.py
  - tests/test_connectivity.py
  - tests/test_cross_market.py
  - tests/test_dashboard.py
  - tests/test_dry_run.py
  - tests/test_execution_engine.py
  - tests/test_fee_model.py
  - tests/test_http_poller.py
  - tests/test_kelly.py
  - tests/test_live_run.py
  - tests/test_market_filter.py
  - tests/test_normalizer.py
  - tests/test_order_client.py
  - tests/test_price_cache.py
  - tests/test_risk_gate.py
  - tests/test_storage.py
  - tests/test_telegram.py
  - tests/test_ws_client.py
  - tests/test_yes_no_arb.py
findings:
  critical: 6
  warning: 8
  info: 5
  total: 19
status: issues_found
---

# Project-Wide Code Review Report

**Reviewed:** 2026-04-17
**Depth:** standard
**Files Reviewed:** 55
**Status:** issues_found

## Summary

This is a thorough review of all four completed phases of the Polymarket arbitrage trading bot. The codebase is well-structured with clear module boundaries, consistent patterns, and good test coverage. The documented Polymarket API quirks (descending ask sort order, WebSocket field names) are handled correctly throughout.

The critical findings are concentrated in two areas: (1) financial correctness bugs in the P&L calculation and the fee model applied during detection, and (2) a security/operational risk from a module-level mutable global that persists dead token state across all tests and bot restarts without clearing. There are also several warning-level issues around error handling gaps, a race window in the kill switch sequence, and an integer division edge case in the P95 latency benchmark.

---

## Critical Issues

### CR-01: Gross P&L formula uses wrong contract count — assumes 1:1 USD-to-contracts

**File:** `src/bot/live_run.py:317-318`

**Issue:** The arb pair P&L is computed as:

```python
n_contracts = yes_result.size_filled / yes_result.price  # USD / price = contracts
gross_pnl = (1.0 - yes_result.price - no_result.price) * n_contracts
```

`size_filled` is a USD amount (e.g. `$10`). On Polymarket, 1 contract = $1 at resolution. To buy $10 worth of YES at $0.48/contract you receive `10 / 0.48 = 20.83` contracts, not `10 / 0.48` USD-denominated "contracts" paired against a `$10` NO position. However the NO leg is also sized in USD at `kelly_usd`, not in matching contracts. If YES and NO are placed at different prices, the contract counts will not match, and the gross P&L formula is only correct when `yes_price == no_price`. In the general case (yes_price ≠ no_price), the formula overstates or understates gross P&L.

The correct formula for a YES+NO arb where both legs are sized equally in USD is:

```python
# Payout = 1.0 per contract pair (one side resolves to $1, other to $0)
# Each leg buys size_usd / price contracts.
# YES contracts: size_usd / yes_price
# NO contracts: size_usd / no_price
# Gross P&L = size_usd * (1/yes_price + 1/no_price - 2) ... only if same USD size both sides
# OR simply: gross_pnl = size_usd - (yes_price + no_price) * (size_usd / ((yes_price + no_price)/2))
```

The simpler correct form for equal-USD sizing: `gross_pnl = size_usd * (1 - yes_price - no_price) / ((yes_price + no_price) / 2)` — but the actual correct approach depends on whether the bot matches by contract count or by USD size. The current formula is internally inconsistent.

**Fix:** Clarify the sizing convention. If the bot sends `kelly_usd` on both legs (equal USD), the gross P&L is:

```python
# Both legs are $kelly_usd. At resolution, the winning leg pays out
# kelly_usd / win_price dollars per contract * 1 contract = kelly_usd / win_price total.
# But per-contract cost is win_price, so payout is kelly_usd / win_price * $1 = kelly_usd / win_price.
# Cost = 2 * kelly_usd (both legs cost money).
# Gross P&L = (kelly_usd / yes_price + kelly_usd / no_price) / 2 - kelly_usd * (1/yes_price + 1/no_price) / 2
# Simplest correct form: gross_pnl = kelly_usd * (1 - yes_price - no_price) / yes_price
# (assuming YES resolves to 1; by symmetry works for NO too since total == 1)
gross_pnl = yes_result.size_filled * (1.0 - yes_result.price - no_result.price) / yes_result.price
```

---

### CR-02: Fee calculation applied only once in the detection, but is per-side — detection threshold may pass trades that are net losers

**File:** `src/bot/detection/yes_no_arb.py:103-105`

**Issue:** The estimated fee is computed as:

```python
estimated_fees = (yes_ask + no_ask) * taker_fee
```

`taker_fee` is a per-side rate (e.g. 1.0% per side for politics). The formula multiplies the sum of both prices by the per-side rate, which gives `(yes_ask + no_ask) * fee_rate`. This is mathematically equivalent to applying the fee rate to the total cost, which is correct only if `taker_fee` is the total round-trip rate. But per the configuration and docstrings, `fee_pct_politics = 0.010` is explicitly labeled "1.0% per side". Two sides means the total fee should be `yes_ask * fee_rate + no_ask * fee_rate = (yes_ask + no_ask) * fee_rate`. This is actually the same formula, so the arithmetic is incidentally correct.

However in `cross_market.py` the same pattern is used but only the YES side buys are accounted for:

```python
estimated_fees = total_yes * taker_fee  # line 154
```

For cross-market arb the trade is buying YES tokens on N markets. Each is a separate taker order, so total fees should be `sum(yes_asks) * taker_fee` per side — but there is no exit side modelled in the cross-market fee estimate. The detection engine thus systematically understates fees for cross-market opportunities by a factor of roughly 2x (no exit cost). Cross-market arb requires selling the winning contract at resolution (or a separate exit), which incurs another taker fee.

**Fix:** In `cross_market.py` line 154, account for both entry and exit taker costs if exit will be via a taker order:

```python
# Entry: buy all N YES tokens. Exit: sell winning token at resolution (taker).
# Conservative: assume exit fee equals entry fee on the winning token.
entry_fees = total_yes * taker_fee
exit_fee = (total_yes / len(group)) * taker_fee  # approximate: one exit on the winner
estimated_fees = entry_fees + exit_fee
```

Or at minimum document that exit fees are excluded and tighten the net_spread threshold accordingly.

---

### CR-03: Module-level mutable global `_dead_tokens` and `_poll_offset` persist across tests and bot restarts within a process

**File:** `src/bot/scanner/http_poller.py:18-19`

**Issue:**

```python
_dead_tokens: set[str] = set()  # tokens that returned 404 — never retry
_poll_offset: int = 0           # rotating offset so we cycle through all markets over time
```

These are module-level globals with no reset mechanism. Two problems:

1. **Test pollution:** The `_dead_tokens` set is shared across all tests in a process. If one test inserts a dead token (by triggering a 404 path), subsequent tests will skip that token silently. This is an existing source of test flakiness and ordering-sensitivity.

2. **Operational risk:** In rare crash-recovery scenarios where the bot process is restarted without a full module reload (e.g. via `importlib.reload`), a valid token that returned a transient 404 remains permanently banned for the session. No mechanism exists to flush false-positives short of a full restart.

**Fix:** Move `_dead_tokens` and `_poll_offset` to instance state on a class (or pass them as arguments) so they can be reset per-test and are not process-global singletons. Alternatively add a `reset_state()` function callable from tests:

```python
# At module level:
def reset_poller_state() -> None:
    """Reset module-level state for testing or bot reinit."""
    global _dead_tokens, _poll_offset
    _dead_tokens = set()
    _poll_offset = 0
```

---

### CR-04: Kill switch executes position close AFTER verifying KILL file, but BEFORE checking kill switch state — race window where orders fire during close

**File:** `src/bot/live_run.py:249-256`

**Issue:** The kill switch sequence is:

```python
if os.path.exists(_KILL_FILE):          # line 249
    risk_gate.activate_kill_switch()    # line 251

if risk_gate.is_kill_switch_active():   # line 254
    await _execute_kill_switch(client, conn, writer)  # line 255
    break
```

This is correct. However `_execute_kill_switch` calls `client.cancel_all()` and then queries the trades table and places FAK SELL orders for open positions. If the scan loop is on a cycle boundary and a concurrent Telegram task or the daily summary task fires `conn.execute()` at the same moment that `_execute_kill_switch` is reading the trades table, SQLite with `check_same_thread=False` will not raise but the concurrent read during a write commit may return a stale result or cause unexpected behavior.

More concretely: after `cancel_all()` succeeds, the sell loop at `live_run.py:73-77` iterates rows from the trades table and places SELL orders. But this is the SAME `conn` used by the async writer task (`AsyncWriter._worker`) which may still be draining queued inserts concurrently. The `conn.commit()` in `insert_opportunity` can interleave with the `cursor.fetchall()` in `_execute_kill_switch`.

**Fix:** Before executing the kill switch position close, stop (flush and cancel) the async writer:

```python
async def _execute_kill_switch(client, conn, writer: AsyncWriter) -> None:
    # Drain writer queue first so all trades are committed before we read them
    await writer.flush()
    # ... then cancel_all() and sell open positions
```

The current signature already takes `writer` — the flush call just needs to precede the `conn.execute` reads.

---

### CR-05: `verify_fill_rest` accepts `order_id: str` but `yes_order_id = yes_resp.get("orderID")` may be `None` — no guard before passing to verifier

**File:** `src/bot/execution/engine.py:261-270`

**Issue:**

```python
yes_order_id = yes_resp.get("orderID")   # line 261 — may be None

yes_verified = False
try:
    yes_verified = await verify_fill_rest(client, yes_order_id)  # line 270
```

If the CLOB response does not include `"orderID"` (e.g. a malformed or unexpected response body), `yes_order_id` is `None`. `verify_fill_rest` then calls `client.get_order(None)`, which will either raise or return an unexpected result. The exception is caught by the outer try/except, but `verify_fill_rest` will be called with `None` and burn through 10 polling attempts, introducing a 5-second delay before returning False and aborting the NO leg.

More critically, if `client.get_order(None)` actually succeeds (returns some default) with `size_matched > 0`, the NO leg would fire against an unconfirmed YES fill.

**Fix:** Add an explicit guard before calling `verify_fill_rest`:

```python
yes_order_id = yes_resp.get("orderID")
if not yes_order_id:
    logger.error(f"YES response missing orderID for market={opp.market_id}: {yes_resp}")
    results.append(ExecutionResult(..., status="failed", error_msg="missing orderID"))
    return arb_id, results
```

---

### CR-06: Dashboard `/api/status` endpoint executes multiple synchronous SQLite queries on every HTTP request with no timeout — blocks the asyncio event loop

**File:** `src/bot/dashboard/app.py:622-648`

**Issue:** The `status()` endpoint handler is async but calls several synchronous SQLite functions directly (not via `run_in_executor`):

```python
@app.get("/api/status")
async def status(request: Request) -> dict:
    ...
    return {
        "open_positions_count": _query_open_positions_count(state.conn),   # sync SQLite
        "efficiency_7d_pct": _query_capital_efficiency(state.conn, 7, ...),  # sync SQLite
        "efficiency_30d_pct": _query_capital_efficiency(state.conn, 30, ...), # sync SQLite
        "total_fees_paid_usd": _query_total_fees(state.conn),               # sync SQLite
        "avg_fee_rate_pct": _query_avg_fee_rate(state.conn),                # sync SQLite
        "recent_trades": _query_recent_trades(state.conn, limit=20),        # sync SQLite
        "arb_pairs": _query_arb_pairs(state.conn, limit=20),                # sync SQLite
    }
```

All seven of these are blocking SQLite calls on the main event loop thread. While the app comment says "CPython asyncio is single-threaded — reads/writes from the same event loop are safe without locks," blocking the event loop for the duration of 7 synchronous database queries directly delays the scan loop's next cycle.

The `_query_open_positions_count` query at line 79-90 performs a multi-table LEFT JOIN with two join conditions which can be slow on a growing trades table with no composite index covering `(token_id, leg, status, market_id)`.

**Fix:** Wrap the blocking queries in `asyncio.get_running_loop().run_in_executor(None, ...)` or, for this scale, at minimum add a composite index on the trades table for the open-positions query:

```sql
CREATE INDEX IF NOT EXISTS idx_trades_leg_status ON trades(leg, status, token_id, market_id);
```

And for the dashboard endpoint, consider caching the result for 5 seconds to avoid recomputing on every 10-second browser refresh.

---

## Warnings

### WR-01: P95 index computation is off-by-one for sample sizes not divisible by 20

**File:** `scripts/benchmark_latency.py:52`

**Issue:**

```python
p95_index = int(SAMPLES * 0.95) - 1  # 0-indexed, so index 18 for 20 samples
```

For `SAMPLES = 20`: `int(20 * 0.95) - 1 = int(19) - 1 = 18`. The comment is correct for this specific case. However if `SAMPLES` is changed to a value like `10`: `int(10 * 0.95) - 1 = int(9) - 1 = 8`, which is the last element — giving P95 = P100. For `SAMPLES = 19`: `int(18.05) - 1 = 17`, which is the 18th element out of 19 = 94.7th percentile, not 95th. The formula is fragile for non-default `SAMPLES`.

**Fix:** Use `statistics.quantiles` or a correct percentile formula:

```python
p95_index = max(0, int(math.ceil(SAMPLES * 0.95)) - 1)
```

---

### WR-02: `market_filter.py` calls `time.sleep()` (blocking) inside an async function during 429 retry

**File:** `src/bot/scanner/market_filter.py:41`

**Issue:**

```python
def _get_markets_page(client: ClobClient, **kwargs) -> dict:
    ...
    time.sleep(backoff)  # blocks event loop when called from async context
```

`_get_markets_page` is a synchronous helper called directly from the async `fetch_liquid_markets` coroutine (line 68). When a 429 rate limit is hit, `time.sleep(backoff)` blocks the entire asyncio event loop for up to 60 seconds. During this block, the WebSocket client cannot process messages, the scan loop is frozen, and the kill switch check does not fire.

**Fix:** Either make `_get_markets_page` a true async function using `await asyncio.sleep(backoff)`, or wrap the blocking `time.sleep` call inside `await loop.run_in_executor(None, time.sleep, backoff)`:

```python
async def _get_markets_page(client: ClobClient, **kwargs) -> dict:
    backoff = _RETRY_BACKOFF_START
    for attempt in range(_MAX_RETRIES):
        try:
            return client.get_markets(**kwargs)
        except Exception as e:
            if "429" in str(e) and attempt < _MAX_RETRIES - 1:
                logger.warning(...)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            else:
                raise
```

---

### WR-03: `_execute_kill_switch` closes positions based on ALL `filled/partial` trades, not just open (unhedged) ones

**File:** `src/bot/live_run.py:68-77`

**Issue:**

```python
cursor = conn.execute(
    "SELECT token_id, size FROM trades WHERE status IN ('filled', 'partial')"
)
rows = cursor.fetchall()
for token_id, size in rows:
    sell_resp = await place_fak_order(client, token_id, 0.01, size, "SELL")
```

This query returns ALL filled/partial trades, including both YES and NO legs of completed arb pairs (where both sides are already held and offset each other), as well as YES legs that were successfully hedged. For a completed arb where YES was bought and NO was also bought, selling both would create a net short position, not close it.

The correct query should sell only positions that are not offset by a corresponding paired position. In the current schema that means selling YES legs that have no corresponding arb_pairs row and no hedge row. The open positions count query in `dashboard/app.py` at line 79-91 already has the right join logic — the kill switch should use similar logic.

**Fix:** Use the same open-positions logic as the dashboard query, or track position state more explicitly:

```python
cursor = conn.execute(
    "SELECT t.token_id, t.size FROM trades t "
    "LEFT JOIN arb_pairs ap ON ap.yes_trade_id = t.trade_id "
    "LEFT JOIN trades hedge ON hedge.token_id = t.token_id "
    "  AND hedge.leg = 'hedge' AND hedge.status = 'hedged' "
    "  AND hedge.market_id = t.market_id "
    "WHERE t.leg = 'yes' AND t.status IN ('filled', 'partial') "
    "  AND ap.arb_id IS NULL AND hedge.trade_id IS NULL"
)
```

---

### WR-04: `execute_opportunity` returns `(arb_id, results)` but all callers in `test_execution_engine.py` unpack as just `results`

**File:** `tests/test_execution_engine.py:76-77`, `88-89`, etc.

**Issue:** The function signature is:

```python
async def execute_opportunity(...) -> tuple[str, list[ExecutionResult]]:
    ...
    return arb_id, results
```

But every test unpacks the return as a single value:

```python
results = await execute_opportunity(client, opp, _config(), MagicMock())
assert any(r.status == "skipped" for r in results)
```

When `execute_opportunity` returns a `(str, list)` tuple, iterating over `results` (which is actually the tuple) with `any(r.status == "skipped" for r in results)` will try to access `.status` on a `str` (the `arb_id`) and on a `list` — this will raise `AttributeError` at runtime.

If the tests actually pass, it means either (a) the test isolation is masking the error, or (b) the function is being monkey-patched somewhere that changes the return value. This is a real bug in the tests that could produce false-positive passing tests.

**Fix:** Update all test call sites to unpack correctly:

```python
arb_id, results = await execute_opportunity(client, opp, _config(), MagicMock())
assert any(r.status == "skipped" for r in results)
```

---

### WR-05: `record_loss()` in `RiskGate` is never called from the execution path — stop-loss will never trigger

**File:** `src/bot/live_run.py` (entire scan loop), `src/bot/risk/gate.py:85-102`

**Issue:** `RiskGate.record_loss(loss_usd)` exists and is thoroughly tested, but there is no call to `risk_gate.record_loss()` anywhere in `live_run.py`'s scan loop. The daily P&L is tracked via `app_state.daily_pnl_usd += net_pnl` (line 337) but only for *profitable* arbs. The `record_loss` API is documented as "call after a confirmed fill that results in a loss." There are several loss scenarios:

- A hedge SELL at `price=0.01` results in a near-total loss of the YES position size.
- A partial fill with net negative spread.

Without `record_loss()` being called, `is_stop_loss_triggered()` will never return `True` and the 5% daily stop-loss protection (D-06) is completely non-functional.

**Fix:** In the results loop at `live_run.py:290-306`, after computing `net_pnl`, call `risk_gate.record_loss` when the outcome is negative:

```python
if net_pnl < 0:
    risk_gate.record_loss(abs(net_pnl))
```

Also record a loss for hedge events in the same loop.

---

### WR-06: `_daily_summary_task` queries `submitted_at >= today_str` but `submitted_at` is stored as a full ISO datetime — date prefix comparison may miss records

**File:** `src/bot/live_run.py:126-140`

**Issue:**

```python
today_str = datetime.utcnow().strftime("%Y-%m-%d")
cursor = conn.execute(
    "SELECT COUNT(*) FROM trades WHERE submitted_at >= ?",
    (today_str,)
)
```

`submitted_at` is stored as a full ISO 8601 string (e.g. `"2026-04-17T10:23:44.123456"`). Comparing `submitted_at >= "2026-04-17"` with SQLite's text comparison works because ISO 8601 strings are lexicographically sortable, and `"2026-04-17T..."` is greater than `"2026-04-17"`. However if a `submitted_at` value is stored with a UTC offset like `"2026-04-17T00:00:00+00:00"`, the comparison still works. But if stored as `"2026-04-17 10:23:44"` (space separator, not T), the comparison also works. This is technically correct but fragile and depends on the ISO format invariant being maintained.

More importantly, the daily summary fires at midnight UTC and queries from `today_str` (which is NOW midnight UTC), so it will correctly return today's trades. However, if the summary task wakes up slightly after midnight (e.g. due to sleep drift), `today_str` will be the NEW day and the query will return 0 results for the day just ended.

**Fix:** Compute `today_str` BEFORE the sleep, not after:

```python
today_str = now.strftime("%Y-%m-%d")  # use the `now` captured before sleep
tomorrow_midnight = ...
await asyncio.sleep(sleep_seconds)
# Use today_str (the day that just ended) for the summary query
```

---

### WR-07: `simulate_vwap` in `engine.py` uses `asks` sorted ascending (best ask first) per docstring, but `execute_opportunity` passes `opp.vwap_yes` directly as a scalar — VWAP simulation is bypassed entirely

**File:** `src/bot/execution/engine.py:167-168`

**Issue:**

```python
vwap_yes = simulate_vwap([], 0.0) if opp.vwap_yes >= 1.0 else opp.vwap_yes
vwap_no = simulate_vwap([], 0.0) if opp.vwap_no >= 1.0 else opp.vwap_no
```

`simulate_vwap` is only called with empty `asks` and `target_size=0` (which returns `1.0`) as the sentinel fallback for resolved markets. In all other cases, the detection engine's `vwap_yes` is used directly — which at this stage of the codebase is always `= yes_ask` (the best ask), not a real VWAP. The `simulate_vwap` function itself is correct and well-implemented, but it is never actually used to compute VWAP — it is dead code in the execution path.

The VWAP gate at line 171 thus reduces to `if yes_ask + no_ask >= 1.0 - threshold: skip`, which is approximately the same gate already applied in the detection engine. The VWAP gate provides no additional protection against order-book slippage.

This is documented as a known deferral ("VWAP = best ask for now, refined in Phase 3"), so this is a warning rather than a critical issue. But the `simulate_vwap` function is a code quality problem — it is never invoked with real order book data.

**Fix:** Either wire `simulate_vwap` to real order book data (requires passing the live order book to `execute_opportunity`) or remove the dead function and document the simplification clearly until Phase 5 adds real VWAP.

---

### WR-08: `get_wallet_address.py` prints the private key indirectly if `Account.from_key` raises an unexpected exception

**File:** `scripts/get_wallet_address.py:32-34`

**Issue:**

```python
try:
    from eth_account import Account
    account = Account.from_key(private_key)
    print(f"Wallet address: {account.address}")
except Exception as e:
    print(f"ERROR: Failed to derive address: {e}")
    sys.exit(1)
```

If `Account.from_key` raises with an exception message that embeds the key (which some lower-level crypto libraries do in debug/verbose modes), the private key is printed to stdout. While unlikely with eth-account's standard error messages, this is a latent risk for a secrets-handling script.

**Fix:** Use a generic error message that does not propagate the exception detail:

```python
except Exception:
    print("ERROR: Failed to derive address. Check that WALLET_PRIVATE_KEY is a valid 32-byte hex private key.")
    sys.exit(1)
```

---

## Info

### IN-01: `conftest.py` test private key (Hardhat account 0) is committed to source — expected but worth noting

**File:** `tests/conftest.py:12-14`

**Issue:**

```python
TEST_PRIVATE_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)
```

This is the well-known Hardhat/Anvil default account 0 private key used for testing. It corresponds to address `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`. It appears in the source in 6 test files. While this is intentional and safe (it's a public test vector), automated secrets scanners will flag it on every CI run. The same key is also duplicated across `tests/conftest.py`, `tests/test_config.py`, `tests/test_cross_market.py`, `tests/test_fee_model.py`, `tests/test_http_poller.py`, `tests/test_ws_client.py`, and `tests/test_yes_no_arb.py` rather than being imported from the shared conftest fixture.

**Fix:** Have all test files import `TEST_PRIVATE_KEY` from `tests/conftest.py` rather than duplicating the constant. Add a `.gitleaks.toml` or `.secrets.baseline` allowlist entry for this specific key value to suppress false-positive scanner alerts.

---

### IN-02: `market_filter.py` docstring mentions volume filter but the implementation does not filter by volume

**File:** `src/bot/scanner/market_filter.py:58`

**Issue:** The function docstring says:

```
Filters:
- volume >= config.min_market_volume (D-19)
- closed == False (active markets only)
```

But the implementation at lines 84-96 filters only on `active`, `enable_order_book`, and `accepting_orders` — there is no volume filter. The docstring references `config.min_market_volume` (which is loaded in `BotConfig` at `config.py:39`) and `D-19`, but the filter was removed because the CLOB API does not return volume data. The config field `min_market_volume` is therefore unused dead configuration.

**Fix:** Remove `min_market_volume` from `BotConfig` and its docstring reference, or update the filter docstring to accurately describe what is filtered. The `min_market_volume` config default (1000.0) is also tested in `test_market_filter.py` as a parameter, creating a misleading test that passes `min_volume=1000.0` to a filter that ignores it.

---

### IN-03: `fee_model.py` geopolitics keyword `"un "` (with trailing space) will fail to match "UN" in question text due to case

**File:** `src/bot/detection/fee_model.py:22`

**Issue:**

```python
_GEO_KEYWORDS = frozenset([
    "nato", "un ", "united nations", ...
])
```

The keyword `"un "` (with a trailing space) is designed to match "UN " in sentences like "Will the UN respond...". However:

1. The check at line 57 uses `any(kw in question for kw in _CRYPTO_KEYWORDS)` on a `.lower()` string. After `.lower()`, "UN" becomes "un" but "UN " with trailing space becomes "un ". This works correctly for "un " as a word boundary check (prevents matching "unilateral", "until", etc.).
2. But "un\n" (newline after UN), "un." (period after UN), or "un," will not match because the trailing space in the keyword requires a literal space after "un".

**Fix:** Use word-boundary regex or a word-split approach instead of substring matching:

```python
import re
_GEO_PATTERN = re.compile(r'\b(nato|un|united nations|war|treaty|...)\b', re.IGNORECASE)
```

---

### IN-04: `AsyncWriter._worker` may silently drop queue items if cancelled while draining

**File:** `src/bot/storage/writer.py:73-89`

**Issue:** The `stop()` method calls `flush()` (which joins the queue) then cancels the task. But `flush()` waits for `queue.join()` which completes when all `task_done()` calls are made. If the worker is cancelled between `queue.get()` and `queue.task_done()`, the item is consumed from the queue but `task_done()` is never called, causing `queue.join()` to hang forever. The `finally: self._queue.task_done()` pattern in the worker loop does prevent this in the normal exception path, but `asyncio.CancelledError` raised at the `await asyncio.wait_for(self._queue.get(), timeout=1.0)` line will be caught by the `except asyncio.CancelledError: break` clause — correctly stopping the loop. However if `CancelledError` is raised after `get()` succeeds but before the `try: insert_opportunity(...)` block, `task_done()` is still called in the `finally` block. This path appears safe.

The real risk is: if `stop()` is called and then the event loop is closed before `flush()` completes, the write is lost with no error. This is acceptable for an opportunity log but is problematic if this writer is ever reused for trade records.

**Fix:** This is more of a documentation issue. Add a warning comment that `stop()` must be awaited before the event loop closes to guarantee all items are written.

---

### IN-05: Dashboard port `8080` bound on `0.0.0.0` with no authentication — `docker-compose.yml` comment warns about firewall but no enforcement

**File:** `src/bot/live_run.py:100`, `docker-compose.yml:19-20`

**Issue:** The dashboard is intentionally unauthenticated per the design ("No auth in Phase 4 — VPS firewall provides access control"). The docker-compose file binds `"8080:8080"` which exposes the port on all host interfaces. The comment says "Restrict in VPS firewall: only allow trusted IPs to reach port 8080" — but this is advisory only. If the VPS firewall is misconfigured or the bot is run in development on a machine with a permissive firewall, the dashboard (which exposes trade history, P&L, wallet address behavior, and bot status) is accessible to anyone.

The dashboard does not expose API keys or private keys directly, but it does reveal:
- Market positions being traded
- P&L information
- Bot state (useful for front-running)

**Fix:** For a trading bot, add basic HTTP bearer token authentication to the dashboard endpoint or at minimum bind to `127.0.0.1` only and use an SSH tunnel for remote access. A single check is sufficient:

```python
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path != "/":
        token = request.headers.get("X-Dashboard-Token", "")
        if token != os.environ.get("DASHBOARD_TOKEN", ""):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)
```

---

_Reviewed: 2026-04-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
