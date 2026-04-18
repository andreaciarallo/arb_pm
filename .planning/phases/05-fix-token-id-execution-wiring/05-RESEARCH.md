# Phase 5: Fix Token ID Execution Wiring — Research

**Researched:** 2026-04-18
**Domain:** Python dataclass extension, cross-module wiring, async CLOB API integration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Cross-market `no_token_id` handling**
Cross-market opportunities (`opportunity_type="cross_market"`) involve buying YES tokens across multiple mutually exclusive markets — there is no NO token. `no_token_id` will be set to `""` (empty string) on all cross-market `ArbitrageOpportunity` instances. Gate 0 in `engine.py` keeps its existing "both token IDs required" rule — cross-market opps will still be skipped at Gate 0.

**D-02: Engine.py signature — remove explicit params, read from opp**
Remove `yes_token_id: str = ""` and `no_token_id: str = ""` from `execute_opportunity()` function signature. Gate 0 reads `opp.yes_token_id` and `opp.no_token_id` directly from the opportunity dataclass.
Impact: All tests that pass `yes_token_id`/`no_token_id` as kwargs to `execute_opportunity()` must be updated to instead set those fields on the `ArbitrageOpportunity` object passed as `opp`.

**D-03: VWAP — fetch fresh order book at execution time**
Gate 1 (VWAP validation) is upgraded from the best_ask proxy to real multi-level VWAP simulation:
- `execute_opportunity()` calls `client.get_order_book(yes_token_id)` and `client.get_order_book(no_token_id)` right before Gate 1
- Order book asks/bids levels are extracted and passed to the existing `simulate_vwap()` function
- `simulate_vwap()` already accepts price levels — just needs real data wired in
- One extra API call per execution (acceptable — executions are rare relative to rate limits)
- The WR-07 deferral comment in `engine.py` is resolved and removed

### Claude's Discretion
- How to extract price levels from `OrderBookSummary` object (`.asks` is list of objects with `.price`, `.size`)
- Order of Gate 0 vs order book fetch (fetch after Gate 0 passes, before Gate 1)
- Error handling if order book fetch fails (log + skip opportunity)
- Test mock strategy for the fresh order book fetch
- Whether to update the WR-07 comment or remove it

### Deferred Ideas (OUT OF SCOPE)
- Cross-market execution — N-way YES arb needs its own execution engine (Phase 5 only fixes yes_no path)
- Real VWAP for cross-market — cross-market opps don't reach Gate 1 (blocked at Gate 0), so no VWAP needed there
- Phase 6 — Telegram kill switch + circuit breaker alerts (separate phase)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | Execute arbitrage trades automatically via CLOB API when opportunities found | Adding token ID fields to dataclass and reading them in Gate 0 removes the blocker — FAK order code already exists and is correct |
| EXEC-02 | Use FAK orders via create_order() + post_order(OrderType.FAK) | Already implemented in `order_client.py`; unreachable only because Gate 0 fires first. No changes needed to FAK code |
| EXEC-03 | Handle partial fills and one-leg execution risk mitigation | retry-then-hedge code already correct; becomes reachable after Gate 0 fix |
| EXEC-04 | Verify every order via REST API after WebSocket fill confirmation | `verify_fill_rest()` already correct; becomes reachable after Gate 0 fix |
| RISK-01 | Enforce maximum capital limit per trade (0.5-1.5% of total capital) | `kelly_size()` already correct; becomes reachable after Gate 0 fix |
</phase_requirements>

---

## Summary

The root cause of this phase is a two-hop wiring gap: token IDs are resolved in the detection engines but never stored on `ArbitrageOpportunity`, so `engine.py` Gate 0 receives empty strings on every call and returns `status='skipped'`. All five EXEC and RISK-01 requirements are architecturally satisfied by existing code that is simply unreachable.

The fix is surgical: add two string fields to the `ArbitrageOpportunity` dataclass with default `""`, populate them in `yes_no_arb.py` (both IDs) and `cross_market.py` (yes only, no remains `""`), and update `engine.py` Gate 0 to read from `opp` instead of function params. The same phase also upgrades Gate 1 VWAP from a best_ask proxy to real multi-level simulation using a fresh `client.get_order_book()` call — this resolves the WR-07 deferral documented inline in `engine.py`.

Five tests in `test_execution_engine.py` pass `yes_token_id`/`no_token_id` as explicit kwargs to `execute_opportunity()`. Per D-02, those kwargs are removed from the function signature. Each of the five call sites must be updated to instead set the fields on the `_opp()` helper and the constructed `ArbitrageOpportunity` object. This is mechanical but must not be missed.

**Primary recommendation:** Treat this as three sequential sub-tasks — (1) dataclass + detection wiring, (2) engine Gate 0 + Gate 1 upgrade, (3) test updates — in that order, verifying tests pass after each sub-task.

---

## Standard Stack

### Core (all already installed — no new dependencies)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| py-clob-client | 0.34.6 | `client.get_order_book(token_id)` returns `OrderBookSummary` | Installed |
| Python dataclasses | stdlib | `ArbitrageOpportunity` dataclass extension | N/A |
| loguru | 0.7+ | Logging throughout engine | Installed |
| pytest + pytest-asyncio | 8.3.4 | Unit tests, `asyncio_mode = auto` in pytest.ini | Installed |

**No new packages required.** This is a pure wiring fix.

---

## Architecture Patterns

### File Change Map (complete — all files that need editing)

```
src/bot/detection/
├── opportunity.py          # ADD yes_token_id: str = "" and no_token_id: str = ""
├── yes_no_arb.py           # POPULATE yes_token_id and no_token_id on ArbitrageOpportunity
└── cross_market.py         # POPULATE yes_token_id (group[0]'s yes tok) and no_token_id=""

src/bot/execution/
└── engine.py               # REMOVE params, read from opp, add order book fetch for Gate 1

tests/
└── test_execution_engine.py  # UPDATE 5 call sites from kwargs to opp fields
```

No other files need changes. `live_run.py` line 297 already calls `execute_opportunity(client, opp, config, risk_gate)` with no token ID args — it will continue working correctly once the params are removed from the signature.

### Pattern 1: ArbitrageOpportunity Dataclass Extension

**Current state** (`opportunity.py`): 13 fields, no `yes_token_id` / `no_token_id`.

**Required change:** Add two fields with `""` defaults at the end of the dataclass so positional construction in existing tests (the `_opp()` helper in `test_execution_engine.py`) does not break.

```python
# Source: direct code inspection of src/bot/detection/opportunity.py
@dataclass
class ArbitrageOpportunity:
    market_id: str
    market_question: str
    opportunity_type: str
    category: str
    yes_ask: float
    no_ask: float
    gross_spread: float
    estimated_fees: float
    net_spread: float
    depth: float
    vwap_yes: float
    vwap_no: float
    confidence_score: float
    detected_at: datetime
    # NEW — add at end with defaults to preserve positional construction compatibility
    yes_token_id: str = ""
    no_token_id: str = ""
```

**Why at the end with defaults:** The `_opp()` helper in `test_execution_engine.py` constructs `ArbitrageOpportunity` with keyword arguments only — not positional — so placement does not matter for that file. However, `test_dry_run.py` and `test_storage.py` may use `ArbitrageOpportunity` with positional args (verified: they do not — all use kwargs or `_opp()` helpers). Placing at end with defaults is the safe convention regardless.

**Dataclass field ordering constraint (confirmed HIGH):** Python dataclasses require fields with defaults to come after fields without defaults. All 13 existing fields have no defaults, so appending two fields with `""` defaults is valid and will not raise a `TypeError` at import time.

### Pattern 2: yes_no_arb.py Token ID Population

**Current state** (lines 60-67): `yes_token_id` and `no_token_id` are already resolved as local variables and used for cache lookups. They are not passed to the `ArbitrageOpportunity` constructor (lines 115-130).

**Required change:** Pass them to the constructor.

```python
# Source: direct inspection of yes_no_arb.py lines 115-130
opportunity = ArbitrageOpportunity(
    market_id=market.get("condition_id", ""),
    market_question=market.get("question", ""),
    opportunity_type="yes_no",
    category=category,
    yes_ask=yes_ask,
    no_ask=no_ask,
    gross_spread=round(gross_spread, 6),
    estimated_fees=round(estimated_fees, 6),
    net_spread=round(net_spread, 6),
    depth=round(depth, 2),
    vwap_yes=yes_ask,
    vwap_no=no_ask,
    confidence_score=round(confidence, 4),
    detected_at=datetime.utcnow(),
    yes_token_id=yes_token_id,   # ADD THIS
    no_token_id=no_token_id,     # ADD THIS
)
```

### Pattern 3: cross_market.py Token ID Population (D-01)

**Current state** (line 117): `yes_token_id` resolved in the inner loop per market but not accumulated. The constructor at line 171 omits both token ID fields.

**Required change per D-01:** Set `yes_token_id` to the first group market's YES token ID (already computed at `group[0]`'s loop iteration) and `no_token_id=""`. Gate 0 will skip cross-market opps because `no_token_id=""`.

The loop structure makes this slightly tricky: `yes_token_id` is a local inside the inner `for market in group:` loop and is last assigned to `group[-1]`'s token. The planner must decide whether to capture `group[0]`'s YES token ID before the loop or after. The correct approach is to capture it from `group[0]`'s tokens before the loop.

```python
# Pattern for cross_market.py: extract before loop
first_market_tokens = group[0].get("tokens", [])
group0_yes_token_id = next(
    (t["token_id"] for t in first_market_tokens if t.get("outcome", "").lower() == "yes"),
    ""
)

# Then in the ArbitrageOpportunity constructor:
opp = ArbitrageOpportunity(
    ...
    yes_token_id=group0_yes_token_id,  # ADD
    no_token_id="",                    # ADD (D-01: cross-market has no NO token)
)
```

### Pattern 4: Engine Gate 0 — Read From opp (D-02)

**Current state** (`engine.py` lines 115-162):
```python
async def execute_opportunity(
    client,
    opp: ArbitrageOpportunity,
    config,
    risk_gate,
    yes_token_id: str = "",    # REMOVE
    no_token_id: str = "",     # REMOVE
) -> tuple[str, list[ExecutionResult]]:
```
Gate 0 at line 144: `if not yes_token_id or not no_token_id:`

**Required changes:**
1. Remove the two kwargs from the function signature
2. Add local variables at the top of the function body that read from `opp`:
   ```python
   yes_token_id = opp.yes_token_id
   no_token_id = opp.no_token_id
   ```
3. No change to Gate 0 logic itself — `if not yes_token_id or not no_token_id:` remains correct

The rest of `engine.py` uses `yes_token_id` and `no_token_id` as local variables throughout (YES leg, NO leg, hedge leg) — they will continue to work unchanged once bound to the new local vars.

### Pattern 5: Engine Gate 1 — Real VWAP Upgrade (D-03)

**Current state** (lines 163-197): Gate 1 uses `opp.vwap_yes` and `opp.vwap_no` (which are set to `yes_ask`/`no_ask` by detection engines — a best_ask proxy). `simulate_vwap()` is called only if `opp.vwap_yes >= 1.0` (resolved market sentinel), never for real opportunities.

**Required change:** After Gate 0 passes (and after the local `yes_token_id`/`no_token_id` vars are bound), fetch fresh order books and pass their asks to `simulate_vwap()`:

```python
# After Gate 0 — fetch fresh order books for VWAP simulation (D-03)
# run_in_executor keeps the event loop unblocked (consistent with order_client.py pattern)
loop = asyncio.get_running_loop()
yes_book = None
no_book = None
try:
    yes_book = await loop.run_in_executor(None, client.get_order_book, yes_token_id)
    no_book = await loop.run_in_executor(None, client.get_order_book, no_token_id)
except Exception as exc:
    logger.warning(
        f"Order book fetch failed for VWAP gate | market={opp.market_id}: {exc} — skipping"
    )
    results.append(ExecutionResult(
        market_id=opp.market_id, leg="skip", side="", token_id="",
        price=0.0, size=0.0, order_id=None, status="skipped",
        size_filled=0.0, kelly_size_usd=0.0, vwap_price=0.0,
        error_msg="order book fetch failed for VWAP",
    ))
    return arb_id, results

# Extract asks — sorted ascending (best ask first) — same as normalizer.py pattern
yes_asks = sorted(
    _get(yes_book, "asks", []),
    key=lambda a: float(getattr(a, "price", 1.0) if not isinstance(a, dict) else a.get("price", 1.0))
)
no_asks = sorted(
    _get(no_book, "asks", []),
    key=lambda a: float(getattr(a, "price", 1.0) if not isinstance(a, dict) else a.get("price", 1.0))
)

target_size = config.total_capital_usd * config.kelly_max_capital_pct
vwap_yes = simulate_vwap(yes_asks, target_size)
vwap_no = simulate_vwap(no_asks, target_size)
vwap_spread = 1.0 - vwap_yes - vwap_no
```

**`_get` helper already exists in `normalizer.py`** — the planner should either import it or inline the pattern. Inlining is simpler since `engine.py` has no existing normalizer import.

**`simulate_vwap()` already accepts both dict and object-style levels** (lines 86-92 of `engine.py`): the function handles `isinstance(level, dict)` vs attribute access. The `OrderBookSummary.asks` items are objects with `.price` and `.size` attributes (confirmed from `normalizer.py` `_price_size()` function which handles both styles).

**`run_in_executor` pattern:** Consistent with `order_client.py` where all CLOB sync calls are wrapped. The existing `place_fak_order` and `verify_fill_rest` use this pattern. Gate 1 adds two more `run_in_executor` calls.

**Remove WR-07 deferral comment** (lines 166-173) — replace with the new implementation. The comment documents the deferral to Phase 5; Phase 5 is now delivering it.

### Pattern 6: Test Updates for D-02

**Exact call sites using removed kwargs (from inspection):**

| Test | Line(s) | Current | Required Fix |
|------|---------|---------|-------------|
| `test_full_success_returns_two_filled_results` | 111-113 | `yes_token_id="yes_tok", no_token_id="no_tok"` as kwargs | Remove kwargs; set on `_opp()` result or construct opp with fields set |
| `test_yes_leg_fails_no_exposure` | 128-130 | same | same |
| `test_no_leg_retry_then_hedge` | 164-166 | same | same |
| `test_kill_switch_stops_no_retries` | 194-196 | same | same |
| `test_yes_verify_false_aborts_no_leg` | 214-216 | same | same |

**Two approaches to fix each test:**

Option A (update `_opp()` helper to accept token ID params):
```python
def _opp(
    net_spread=0.03, yes_ask=0.48, no_ask=0.48,
    depth=200.0, vwap_yes=0.48, vwap_no=0.48,
    yes_token_id="", no_token_id="",     # ADD
):
    return ArbitrageOpportunity(
        ...
        yes_token_id=yes_token_id,       # ADD
        no_token_id=no_token_id,         # ADD
    )
```
Then each test that needs token IDs calls `_opp(yes_token_id="yes_tok", no_token_id="no_tok")` instead of passing them to `execute_opportunity()`.

Option B (set fields on the result): Call `_opp()` as before, then do `opp.yes_token_id = "yes_tok"; opp.no_token_id = "no_tok"` (works because `ArbitrageOpportunity` is not a frozen dataclass).

**Recommendation (Claude's discretion):** Option A is cleaner. Update `_opp()` to accept and pass through the token ID params. The 5 affected tests each just need their `yes_token_id=`/`no_token_id=` kwargs moved from `execute_opportunity()` to `_opp()`.

**Tests that pass without any changes (confirmed):**
- `test_vwap_gate_low_spread_skips` — Gate 1 fires before Gate 0 is even bypassed... actually: Gate 0 now reads `opp.yes_token_id=""`, so it will fire and return `skipped` before reaching the VWAP gate. This test must also set token IDs on the opp so Gate 0 passes and Gate 1 triggers correctly.
- `test_kelly_zero_returns_skipped` — same issue as above.
- `test_vwap_gate_insufficient_depth_skips` — same issue.

**Critical finding:** Tests 1, 2, and 8 currently pass because `_opp()` does NOT set token IDs and Gate 0 returns `skipped` — which happens to satisfy `assert any(r.status == "skipped" for r in results)`. After the fix, Gate 0 will also skip (because `opp.yes_token_id=""`), but for the wrong reason. These tests should set non-empty token IDs on `opp` and verify the skip is due to VWAP/Kelly, not Gate 0. However, if the test assertion is only `status == "skipped"`, the tests will still pass. The planner must decide whether to strengthen these tests.

**For the D-03 VWAP upgrade:** The 5 tests that test Gates 1+ must now mock `client.get_order_book` to return a valid order book. The mock should return a simple object with `.asks` = a list with `.price`/`.size` attributes, or a dict. The simplest approach is a `MagicMock` with `asks` set appropriately, then patching `execute_opportunity`'s call via `run_in_executor` — or patching `loop.run_in_executor` to return the mock book directly.

**Simpler test mock strategy for D-03:** Add `get_order_book` to the `client` mock:
```python
mock_book = MagicMock()
mock_book.asks = [MagicMock(price="0.48", size="100")]  # enough depth, real VWAP near 0.48
mock_book.bids = []
client.get_order_book.return_value = mock_book
```
Since `run_in_executor` runs the sync function in a thread pool and returns its result, and the client is a `MagicMock`, `client.get_order_book("yes_tok")` returns `mock_book`. The `run_in_executor(None, client.get_order_book, yes_token_id)` call should work transparently because `MagicMock` is callable from any thread.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-level VWAP computation | New function | `simulate_vwap()` in `engine.py` lines 65-108 | Already handles dict/object duality, returns 1.0 on empty book, tested |
| Order book ask extraction | Custom sort | Inline sort + `simulate_vwap()` | Same pattern as `normalizer.py` `_price_size()` which is proven correct |
| Order book fetch | New HTTP call | `client.get_order_book(token_id)` | Official CLOB client method, already used in `http_poller.py` line 75 |
| Thread executor pattern | `asyncio.create_task` | `loop.run_in_executor(None, ...)` | Pattern established in `order_client.py` for all sync CLOB calls |

---

## Common Pitfalls

### Pitfall 1: Fields With Defaults Must Follow Fields Without Defaults
**What goes wrong:** Adding `yes_token_id: str` and `no_token_id: str` (no defaults) before `detected_at: datetime` raises `TypeError: non-default argument follows default argument` at import time.
**Why it happens:** Python dataclasses enforce the same rule as function parameters.
**How to avoid:** Add both fields at the END of the dataclass with `= ""` defaults.
**Warning signs:** `ImportError` or `TypeError` on any `from bot.detection.opportunity import ArbitrageOpportunity`.

### Pitfall 2: Ask Sort Order — Descending From CLOB
**What goes wrong:** Using `book.asks[0]` as the best ask returns the WORST ask (~$0.99) because CLOB returns asks sorted descending (confirmed in MEMORY.md and normalizer.py).
**Why it happens:** Polymarket CLOB API sorts asks descending (highest price first).
**How to avoid:** Always sort ascending before passing to `simulate_vwap()`. Use `sorted(asks, key=lambda a: float(a.price))` or equivalent.
**Warning signs:** VWAP values near 0.99 for liquid markets — a sign that the worst ask is being used.

### Pitfall 3: Gate 0 Must Use Local Vars, Not opp Fields Directly
**What goes wrong:** `if not opp.yes_token_id or not opp.no_token_id:` works for Gate 0, but the rest of the function (`place_fak_order(client, yes_token_id, ...)`) uses `yes_token_id` local var. If the local var assignment is missed, those calls get `NameError`.
**How to avoid:** Assign local vars `yes_token_id = opp.yes_token_id` and `no_token_id = opp.no_token_id` immediately after `arb_id = str(uuid.uuid4())`, before any gate. Gate 0 then uses the same local vars as the rest of the function.

### Pitfall 4: Tests 1, 2, 8 Will "Pass" for the Wrong Reason After the Fix
**What goes wrong:** After removing token ID params from `execute_opportunity()`, tests 1, 2, and 8 use `_opp()` which defaults to `yes_token_id=""`. Gate 0 fires and returns `status='skipped'`. The existing assertions (`assert any(r.status == "skipped")`) still pass, but the skip reason is "missing token IDs" not "VWAP below threshold" or "kelly=0.0".
**How to avoid:** Update `_opp()` to default to non-empty token IDs (`yes_token_id="yes_tok"`, `no_token_id="no_tok"`), and add `client.get_order_book` mock returning adequate depth. This ensures the tests verify what they claim to verify.

### Pitfall 5: `run_in_executor` for CLOB Calls in Gate 1
**What goes wrong:** Calling `client.get_order_book(token_id)` directly (sync, blocking) in an async function blocks the event loop for the HTTP round-trip latency (~35ms on HEL1).
**Why it happens:** `py-clob-client` is a synchronous client.
**How to avoid:** Wrap in `loop = asyncio.get_running_loop(); await loop.run_in_executor(None, client.get_order_book, token_id)` — same pattern as `place_fak_order` in `order_client.py`.

### Pitfall 6: cross_market.py `yes_token_id` Variable Scope
**What goes wrong:** The inner `for market in group:` loop overwrites `yes_token_id` on each iteration. At loop end, `yes_token_id` is `group[-1]`'s token, not `group[0]`'s. Using the final loop value gives the wrong market's token ID for the ArbitrageOpportunity.
**How to avoid:** Capture `group[0]`'s YES token ID before the loop, in a separate variable like `group0_yes_token_id`.

---

## Code Examples

### OrderBookSummary Object Structure (confirmed from normalizer.py + http_poller.py usage)

```python
# client.get_order_book(token_id) returns an OrderBookSummary object.
# Access pattern (from normalizer.py _get() and _price_size() helpers):

book = client.get_order_book(token_id)
# book.asset_id: str
# book.asks: list of OrderSummary objects — each has .price (str) and .size (str)
# book.bids: list of OrderSummary objects — same structure
# CLOB returns asks DESCENDING (worst first) — must sort ascending before VWAP

# Extraction for simulate_vwap() — sort ascending first:
asks_sorted = sorted(book.asks, key=lambda a: float(a.price))
# simulate_vwap already handles objects with .price and .size attributes
vwap = simulate_vwap(asks_sorted, target_size_usd)
```

### Test Mock for Order Book (D-03 test pattern)

```python
# MagicMock order book — readable by simulate_vwap() object-path:
mock_book = MagicMock()
level = MagicMock()
level.price = "0.48"
level.size = "500"
mock_book.asks = [level]
mock_book.bids = []
client.get_order_book.return_value = mock_book
# run_in_executor(None, client.get_order_book, token_id) returns mock_book automatically
```

### Updated `_opp()` Helper (test_execution_engine.py)

```python
def _opp(
    net_spread=0.03, yes_ask=0.48, no_ask=0.48,
    depth=200.0, vwap_yes=0.48, vwap_no=0.48,
    yes_token_id="yes_tok", no_token_id="no_tok",  # default to valid IDs
):
    return ArbitrageOpportunity(
        market_id="cond_abc",
        market_question="Will X happen?",
        opportunity_type="yes_no",
        category="politics",
        yes_ask=yes_ask,
        no_ask=no_ask,
        gross_spread=1.0 - yes_ask - no_ask,
        estimated_fees=0.01,
        net_spread=net_spread,
        depth=depth,
        vwap_yes=vwap_yes,
        vwap_no=vwap_no,
        confidence_score=0.8,
        detected_at=datetime.utcnow(),
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
    )
```

---

## Runtime State Inventory

Not applicable — this is a pure code wiring fix. No database schema changes, no data migration, no renamed keys or service registrations.

---

## Environment Availability

Step 2.6: SKIPPED — phase is pure Python code changes. All dependencies (py-clob-client, loguru, pytest) are already installed. No new external tools required.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 + pytest-asyncio |
| Config file | `pytest.ini` (project root) |
| Quick run command | `python -m pytest tests/test_execution_engine.py tests/test_yes_no_arb.py tests/test_cross_market.py -v` |
| Full suite command | `python -m pytest tests/ -v -m "not smoke"` |

Current baseline (all 19 tests pass before any changes):
```
tests/test_execution_engine.py  8 passed
tests/test_yes_no_arb.py        6 passed
tests/test_cross_market.py      5 passed
```

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | `yes_token_id`/`no_token_id` on dataclass → Gate 0 passes → FAK order called | unit | `python -m pytest tests/test_execution_engine.py::test_full_success_returns_two_filled_results -xvs` | ✅ |
| EXEC-01 | yes_no_arb.py populates token IDs on returned opp | unit | `python -m pytest tests/test_yes_no_arb.py -xvs -k "token_id"` | ❌ Wave 0 |
| EXEC-02 | FAK order is called when Gate 0 passes | unit | existing `test_full_success_returns_two_filled_results` (after fix) | ✅ |
| EXEC-03 | retry-then-hedge reachable after Gate 0 fix | unit | `python -m pytest tests/test_execution_engine.py::test_no_leg_retry_then_hedge -xvs` | ✅ |
| EXEC-04 | verify_fill_rest reachable after Gate 0 fix | unit | `python -m pytest tests/test_execution_engine.py::test_yes_verify_false_aborts_no_leg -xvs` | ✅ |
| RISK-01 | kelly_size evaluated after Gate 0 passes | unit | `python -m pytest tests/test_execution_engine.py::test_kelly_zero_returns_skipped -xvs` | ✅ |

### Wave 0 Gaps

- [ ] `tests/test_yes_no_arb.py` — add test asserting `opp.yes_token_id` and `opp.no_token_id` are populated on returned opportunity (confirms the wiring fix in `yes_no_arb.py`)
- [ ] `tests/test_execution_engine.py` — update `_opp()` helper and 5 call sites (mechanical, but required to keep tests valid after D-02)
- [ ] `tests/test_execution_engine.py` — add `client.get_order_book` mock to Gate 1+ tests (required after D-03 adds order book fetch)

---

## Project Constraints (from CLAUDE.md)

| Constraint | Applies To This Phase |
|------------|----------------------|
| py-clob-client is the official Polymarket SDK — use it | Yes — `client.get_order_book()` is the correct method |
| FAK orders via `create_order() + post_order(FAK)` — `create_and_post_order()` FORBIDDEN | Not changed in this phase (already correct) |
| loguru for all logging | Already used in engine.py — no change needed |
| SQLite for trade logs | Not changed in this phase |
| Docker deployment — must run in container | No new dependencies added — no Dockerfile changes |
| GSD workflow enforcement — use GSD commands before edits | Followed |

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection of all 5 bug files — confirmed exact line numbers and current behavior
- `tests/test_execution_engine.py` — confirmed 5 exact call sites that use `yes_token_id`/`no_token_id` as kwargs
- `pytest.ini` + `conftest.py` — confirmed `asyncio_mode = auto`, test infrastructure, no new setup needed
- `normalizer.py` — confirmed `OrderBookSummary.asks` is list of objects with `.price`/`.size`, sort order is descending from CLOB
- `http_poller.py` line 75 — confirmed `client.get_order_book(token_id)` is the correct call pattern
- `engine.py` `simulate_vwap()` — confirmed it handles both dict and object-style levels
- Live test run — confirmed all 19 tests pass before changes (baseline)

### Secondary (MEDIUM confidence)
- MEMORY.md — confirms ask sort order (CLOB descending), `run_in_executor` pattern for sync CLOB calls
- `order_client.py` (not read directly, referenced in STATE.md and engine.py docstring) — `run_in_executor` is the established pattern for async-wrapping sync CLOB calls

---

## Metadata

**Confidence breakdown:**
- Bug root cause: HIGH — confirmed by direct code inspection, audit evidence, and live test run
- Fix approach (dataclass + detection): HIGH — straightforward field addition
- Fix approach (engine Gate 0): HIGH — local var assignment pattern is unambiguous
- Fix approach (engine Gate 1 VWAP): HIGH — `simulate_vwap()` already handles object-style asks; ask sort order is confirmed descending
- Test update strategy: HIGH — exact call sites identified, two valid approaches documented
- `run_in_executor` for Gate 1: HIGH — identical pattern to existing CLOB calls in order_client.py

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (stable codebase, no external API changes expected)
