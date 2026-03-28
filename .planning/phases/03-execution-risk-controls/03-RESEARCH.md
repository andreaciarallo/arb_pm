# Phase 3: Execution & Risk Controls - Research

**Researched:** 2026-03-28
**Domain:** Polymarket CLOB order execution, position sizing, asyncio risk controls
**Confidence:** HIGH (primary sources: installed py-clob-client 0.34.6 source, existing codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Modified Kelly formula for position sizing: `f = (b × p - q) / b × √p`
  - `b` = net spread, `p` = execution probability (`min(1.0, depth / target_size)`), `q = 1 - p`
  - Hard cap: 50% of order book depth
  - Floor: $5 minimum order
  - Ceiling: 5% of total capital
- **D-02:** All orders use IOC (Immediate-or-Cancel) type. In Polymarket SDK: `OrderType.FAK` ("Fill-And-Kill"). GTC excluded. FOK excluded.
- **D-03:** Retry-then-hedge for one-leg failure: YES fills → attempt NO up to 3 retries × 500ms → sell YES at market if still unfilled.
- **D-04:** Dual verification: WebSocket fill (primary) + REST `get_order(order_id)` (secondary). Disagreement = treat as unfilled.
- **D-05:** Pre-execution VWAP simulation before every order. Skip if VWAP-adjusted spread < `min_net_profit_pct`.
- **D-06:** Daily stop-loss = 5% of total capital. Cumulative realized losses since midnight UTC. Midnight UTC reset.
- **D-07:** Circuit breaker: 5 consecutive order errors in 60s → 5min cooldown. Exponential backoff: 5m → 10m → 20m (cap).
- **D-08:** Kill switch: active close all positions → cancel pending orders → sell all holdings → stop loop → flush SQLite → exit. Triggered by SIGTERM or `/app/data/KILL` file (checked every scan cycle).
- **D-09:** Bregman/Frank-Wolfe deferred (needs Gurobi, not justified at <$1k capital).
- **D-10:** LLM-based market dependency detection deferred.
- **D-11:** Telegram/Discord alerts deferred to Phase 4.
- **D-12:** Dashboard deferred to Phase 4.

### Claude's Discretion

- SQLite `trades` table schema (columns beyond the obvious)
- Retry logic implementation details (asyncio task, timeout handling)
- Kelly formula edge cases (b ≤ 0, p = 0, result < floor → skip)
- Circuit breaker state persistence across scan cycles (in-memory counter, reset on clean cycle)
- SIGTERM handler registration (Python `signal` module, asyncio-safe)

### Deferred Ideas (OUT OF SCOPE)

- Full Bregman projection + Frank-Wolfe + Gurobi optimization
- LLM-based market dependency detection
- Telegram/Discord alerts (Phase 4)
- Dashboard (Phase 4)
- Per-arb analytics (Phase 4)
- Multi-wallet, cross-platform arbitrage (V2+)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | Execute arbitrage trades automatically via CLOB API when opportunities found | `create_order()` + `post_order(ord, orderType=OrderType.FAK)` pattern verified in py-clob-client 0.34.6 source |
| EXEC-02 | Use `create_and_post_order()` for dual-verified order placement | CRITICAL FINDING: `create_and_post_order()` does not accept `orderType` — always uses GTC. Must use `create_order()` then `post_order(ord, orderType=OrderType.FAK)` for IOC/FAK semantics |
| EXEC-03 | Handle partial fills and one-leg execution risk mitigation | FAK semantics handle partial fills natively; retry-then-hedge logic implemented with asyncio.sleep and cancel_all fallback |
| EXEC-04 | Verify every order via REST API after WebSocket fill confirmation | `get_order(order_id)` → Level 2 auth → returns dict with order status fields |
| RISK-01 | Enforce maximum capital limit per trade (0.5-1.5% of total capital) | Modified Kelly formula with 5% ceiling and $5 floor; BotConfig gets `total_capital_usd` and risk params |
| RISK-02 | Implement daily stop-loss (5-8% daily loss limit) | In-memory cumulative loss counter, midnight UTC reset via asyncio task |
| RISK-03 | Implement circuit breaker that pauses trading on high error rates | In-memory consecutive error counter with time window check |
| RISK-04 | Implement emergency kill switch for immediate position closure | `loop.add_signal_handler(signal.SIGTERM, ...)` + KILL file check per cycle |
</phase_requirements>

---

## Summary

Phase 3 transitions the bot from dry-run detection to live order execution on Polymarket's CLOB. The execution engine must integrate directly with the existing Phase 2 modules: `ArbitrageOpportunity` objects from the detection engine become inputs to the execution pipeline, which chains Kelly sizing → VWAP validation → FAK order submission → dual verification → retry-hedge if needed.

The most critical finding from code inspection is that **`create_and_post_order()` cannot submit FAK orders** — it calls `post_order(ord)` with no `orderType` argument, which defaults to `OrderType.GTC`. IOC/FAK semantics require splitting into `create_order()` + `post_order(ord, orderType=OrderType.FAK)`. This is the correct pattern for all limit orders in this phase.

Risk controls are implemented as an independent state layer (not embedded in the execution path): a `RiskGate` class holds the stop-loss accumulator, circuit breaker counter, and kill switch flag. The scan loop (new `live_run.py`) checks `RiskGate.is_blocked()` before entering execution for each opportunity. The kill switch must override all other blocked states and is the only path that actively closes positions — stop-loss and circuit breaker only pause new order submission.

The existing test infrastructure (pytest + asyncio_mode=auto, 56 passing unit tests) is fully capable of testing Phase 3 modules via `unittest.mock` — no live API calls needed in unit tests.

**Primary recommendation:** Use `create_order()` + `post_order(ord, orderType=OrderType.FAK)` for all orders, never `create_and_post_order()`. Register SIGTERM via `loop.add_signal_handler()`, not `signal.signal()`, for asyncio-safe shutdown.

---

## Standard Stack

### Core (verified from installed packages and codebase)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| py-clob-client | 0.34.6 (installed) | Order placement, REST verification, balance queries | Official Polymarket SDK; only way to place orders |
| websockets | 16.0 (installed) | User WebSocket channel for fill events | Already in use for market channel; same library for user channel |
| httpx | 0.28.1 (installed) | Underlying HTTP for py-clob-client (sync); used in http_helpers | Already in use |
| loguru | 0.7.3 (installed) | All execution + risk logging | Project standard |
| sqlite3 | stdlib | Trade logging | Project standard (schema.py already exists) |
| asyncio | stdlib | Async execution loop, signal handling, sleep for retry delays | Runtime standard |
| signal | stdlib | SIGTERM registration via `loop.add_signal_handler()` | Only asyncio-safe signal handler method |

### No New Packages Needed

The entire Phase 3 execution engine can be built on already-installed packages. No additions to `requirements.txt` are required.

**Version verification:**
```bash
pip show py-clob-client websockets httpx loguru
# py-clob-client: 0.34.6 | websockets: 16.0 | httpx: 0.28.1 | loguru: 0.7.3
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/bot/
├── execution/
│   ├── __init__.py
│   ├── engine.py          # execute_opportunity() — main execution coroutine
│   ├── kelly.py           # kelly_size() — modified Kelly formula
│   ├── vwap.py            # simulate_vwap() — pre-execution order book simulation
│   └── order_client.py    # place_fak_order(), verify_order() — wraps py-clob-client
├── risk/
│   ├── __init__.py
│   └── gate.py            # RiskGate — stop-loss, circuit breaker, kill switch state
├── storage/
│   ├── schema.py          # EXTEND: add trades table
│   └── writer.py          # REUSE: AsyncWriter pattern for trade logging
├── live_run.py            # New: mirrors dry_run.py for live execution
├── dry_run.py             # UNCHANGED: dry-run mode stays functional
└── config.py              # EXTEND: add Phase 3 risk params
```

### Pattern 1: FAK Order Placement (CRITICAL — NOT `create_and_post_order()`)

**What:** Submit an IOC/FAK limit order on Polymarket CLOB.

**Why `create_and_post_order()` is wrong:** Inspecting py-clob-client 0.34.6 source:
```python
# client.py line 654–661
def create_and_post_order(self, order_args: OrderArgs, options: PartialCreateOrderOptions = None):
    ord = self.create_order(order_args, options)
    return self.post_order(ord)   # <-- NO orderType arg — defaults to OrderType.GTC
```

`post_order()` signature: `post_order(self, order, orderType: OrderType = OrderType.GTC, ...)`

**Correct pattern:**
```python
# Source: py_clob_client/client.py (0.34.6) — verified by code inspection
from py_clob_client.clob_types import OrderArgs, OrderType

order_args = OrderArgs(
    token_id=token_id,     # YES or NO token ID from market data
    price=price,           # CLOB price (e.g., 0.41 for 41 cents)
    size=size_usdc,        # Size in USDC
    side="BUY",            # "BUY" to go long, "SELL" to close
    fee_rate_bps=0,        # auto-resolved from market by create_order()
    nonce=0,               # 0 unless using onchain cancellation
    expiration=0,          # 0 = no expiration (FAK cancels at submit anyway)
)

# Step 1: create + sign the order (Level 1 auth — triggers chain lookup for tick_size, neg_risk)
signed_order = client.create_order(order_args)

# Step 2: submit as FAK (Level 2 auth required — has API creds)
response = client.post_order(signed_order, orderType=OrderType.FAK)
# response is a dict: {"orderID": "...", "status": "matched"/"unmatched"/...}
```

**OrderArgs fields verified from py_clob_client/clob_types.py:**
- `token_id: str` — YES or NO conditional token asset ID
- `price: float` — must be valid for market tick_size (validated by `price_valid()` in create_order)
- `size: float` — size in conditional token units
- `side: str` — `"BUY"` or `"SELL"`
- `fee_rate_bps: int = 0` — auto-resolved from market; leave at 0
- `nonce: int = 0` — for onchain cancellation; leave at 0
- `expiration: int = 0` — timestamp; 0 = no expiration
- `taker: str = ZERO_ADDRESS` — for public orders; leave as default

**OrderType values verified from py_clob_client/clob_types.py:**
```python
class OrderType(enumerate):
    GTC = "GTC"   # Good-Till-Cancelled (dangerous for arb — DO NOT USE for execution)
    FOK = "FOK"   # Fill-Or-Kill (too conservative)
    GTD = "GTD"   # Good-Till-Date
    FAK = "FAK"   # Fill-And-Kill = IOC (CORRECT for arb)
```

### Pattern 2: REST Order Verification

**What:** Confirm a WebSocket-reported fill via REST.

```python
# Source: py_clob_client/client.py line 797–806 + endpoints.py
# get_order requires Level 2 auth — already set up in build_client()

order_data = client.get_order(order_id)
# Returns a dict (raw JSON from /data/order/{order_id})
# Key fields to check:
#   order_data.get("status")          — e.g. "matched", "unmatched", "canceled"
#   order_data.get("size_matched")    — amount actually filled
#   order_data.get("maker_amount")    — original maker amount submitted
#   order_data.get("taker_amount")    — original taker amount submitted
#   order_data.get("id")              — order ID
```

**MEDIUM confidence** on exact field names — py-clob-client 0.34.6 source does not define a typed response dataclass for `get_order()`; it returns the raw JSON dict from `/data/order/{order_id}`. Field names follow Polymarket REST API conventions. Key fields `status`, `size_matched`, `id` are confirmed by standard Polymarket REST API patterns.

**Dual verification logic:**
```python
async def verify_fill(client, order_id: str, ws_fill_size: float) -> bool:
    """Return True only if REST confirms the fill matches the WS report."""
    try:
        data = await asyncio.get_event_loop().run_in_executor(
            None, client.get_order, order_id
        )
        rest_size = float(data.get("size_matched", 0))
        return rest_size > 0 and abs(rest_size - ws_fill_size) < 0.01  # 1-cent tolerance
    except Exception as e:
        logger.error(f"REST verification failed for {order_id}: {e}")
        return False
```

Note: `client.get_order()` uses httpx synchronously (py-clob-client's http_helpers uses `httpx.Client`, not `AsyncClient`). Wrap in `run_in_executor` to avoid blocking the asyncio event loop.

### Pattern 3: User WebSocket Channel (Fill Events)

**What:** Subscribe to the user channel to receive real-time fill notifications.

**URL confirmed from Phase 1 research and official Polymarket clob-client examples:**
```
wss://ws-subscriptions-clob.polymarket.com/ws/user
```

**Subscription format (MEDIUM confidence — confirmed URL from Phase 1 research, message format inferred from official TypeScript client patterns):**
```python
import json
from py_clob_client.signing.hmac import build_hmac_signature

# User channel requires authenticated subscription message
subscribe_msg = {
    "type": "user",
    "auth": {
        "apiKey": api_key,
        "passphrase": api_passphrase,
        "timestamp": str(int(time.time())),
        "signature": build_hmac_signature(
            api_secret,
            timestamp,
            "GET",
            "/ws/user",
            ""
        )
    },
    "markets": [],          # empty = subscribe to all user markets
    "assets_ids": [],       # empty = all assets
}
```

**Fill event message format (MEDIUM confidence — inferred from Polymarket WebSocket patterns):**
```python
# Expected message fields for a fill/trade event:
{
    "event_type": "trade",        # or "fill" — confirm on first live trade
    "order_id": "...",
    "status": "matched",
    "size_matched": "10.5",       # shares filled (string)
    "price": "0.41",              # fill price
    "asset_id": "...",            # token_id
    "side": "BUY",
}
```

**Alternative approach (HIGH confidence, simpler):** Poll `get_order(order_id)` with a timeout loop instead of implementing a separate user WebSocket. Given the 5-second verification timeout from D-04, polling every 500ms for 5 iterations avoids the complexity of user channel auth. Recommend this for Phase 3 simplicity — user WebSocket can be added in Phase 4 when observability is built.

**Recommendation:** For Phase 3, use REST polling for fill verification (3–5 polls × 500ms = 1.5–2.5s, within the 5s timeout). This eliminates user channel authentication complexity while meeting the dual-verification requirement.

### Pattern 4: asyncio-Safe SIGTERM Handler

**What:** Register a SIGTERM handler that triggers the kill switch without blocking the event loop.

```python
# Source: Python docs — asyncio.loop.add_signal_handler (Unix only, confirmed available)
import asyncio
import signal

async def live_run(config, client, ...):
    loop = asyncio.get_running_loop()
    risk_gate = RiskGate(config)

    def _handle_sigterm():
        logger.warning("SIGTERM received — activating kill switch")
        risk_gate.activate_kill_switch()
        # Kill switch check in scan loop will trigger active close

    loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)

    # Also check KILL file on each scan cycle (≤30s detection lag per D-08)
    kill_file = "/app/data/KILL"
```

**Why `loop.add_signal_handler()` not `signal.signal()`:** `signal.signal()` is not asyncio-safe — the handler runs in the main thread and can interrupt coroutines mid-execution. `loop.add_signal_handler()` schedules the callback safely within the event loop. Only available on Unix (confirmed: Docker container on Linux VPS).

**SIGINT handling:** Register both SIGTERM and SIGINT to the same handler to support `Ctrl+C` during local development.

### Pattern 5: Modified Kelly Formula

```python
# Source: "Unravelling the Probabilistic Forest" (arxiv 2508.03474) — D-01
import math

def kelly_size(
    net_spread: float,      # b: arbitrage profit % from detection (e.g., 0.03 for 3%)
    depth: float,           # order book depth in USD
    target_size: float,     # initial target size estimate
    total_capital: float,   # total bot capital in USD
    min_order_usd: float = 5.0,
    max_capital_pct: float = 0.05,  # 5% ceiling
) -> float:
    """
    Modified Kelly formula: f = (b × p - q) / (b × √p)

    Returns position size in USD, or 0.0 if trade should be skipped.
    """
    b = net_spread
    if b <= 0:
        return 0.0   # Kelly says no

    p = min(1.0, depth / target_size)  # execution probability from depth
    if p <= 0:
        return 0.0

    q = 1.0 - p

    numerator = b * p - q
    if numerator <= 0:
        return 0.0   # Kelly negative or zero — skip

    denominator = b * math.sqrt(p)
    if denominator <= 0:
        return 0.0

    kelly_fraction = numerator / denominator

    # Constraints from D-01
    max_by_depth = depth * 0.5                    # 50% of order book depth
    max_by_capital = total_capital * max_capital_pct  # 5% of total capital
    size = kelly_fraction * total_capital

    size = min(size, max_by_depth, max_by_capital)

    if size < min_order_usd:
        return 0.0  # Below Polymarket minimum — skip

    return round(size, 2)
```

**Edge cases (Claude's discretion, verified):**
- `b <= 0`: formula numerator always negative → return 0.0 (skip)
- `p = 0`: division by zero → return 0.0 (skip)
- `numerator <= 0` (b×p < q): Kelly says expected value negative → return 0.0 (skip)
- Result < $5 floor → return 0.0 (skip, do NOT round up to minimum)
- Never force a minimum allocation when Kelly says no

### Pattern 6: Pre-Execution VWAP Simulation

```python
# Source: D-05 + existing PriceCache.get() from Phase 2
# OrderBookSummary.asks is a list[OrderSummary(price=str, size=str)]

def simulate_vwap(asks: list, target_size_usd: float) -> float:
    """
    Calculate VWAP for buying target_size_usd worth against the current ask book.
    Returns the VWAP fill price. Returns 1.0 if insufficient depth (worst case).
    """
    remaining = target_size_usd
    total_cost = 0.0
    total_shares = 0.0

    for level in asks:  # asks are sorted best (lowest) first
        price = float(level.price)
        size_shares = float(level.size)
        level_cost = price * size_shares  # cost of this level in USD

        if remaining <= level_cost:
            shares_needed = remaining / price
            total_cost += remaining
            total_shares += shares_needed
            remaining = 0
            break
        else:
            total_cost += level_cost
            total_shares += size_shares
            remaining -= level_cost

    if total_shares == 0:
        return 1.0  # no depth at all

    return total_cost / total_shares  # VWAP
```

**Integration with `get_order_book()`:** `client.get_order_book(token_id)` returns `OrderBookSummary` with `.asks` (list[OrderSummary]) and `.bids` sorted by best price first. The `calculate_market_price()` method already exists in the client for similar calculations (lines 1062–1082 of client.py) — reference it when implementing.

### Pattern 7: RiskGate State Machine

```python
import time
from dataclasses import dataclass, field

@dataclass
class RiskGate:
    """
    Tracks stop-loss, circuit breaker, and kill switch state.
    In-memory only — does not persist across restarts.
    """
    total_capital_usd: float
    daily_loss_limit_pct: float = 0.05      # 5% = $50 at $1k
    circuit_breaker_errors: int = 5          # consecutive errors
    circuit_breaker_window_seconds: int = 60
    circuit_breaker_cooldown_seconds: int = 300  # 5 minutes

    # Mutable state (NOT frozen — must update in place)
    _daily_loss_usd: float = field(default=0.0, repr=False)
    _day_reset_timestamp: float = field(default_factory=time.time, repr=False)
    _error_timestamps: list = field(default_factory=list, repr=False)
    _cb_cooldown_until: float = field(default=0.0, repr=False)
    _cb_cooldown_multiplier: int = field(default=1, repr=False)
    _kill_switch_active: bool = field(default=False, repr=False)

    def record_loss(self, loss_usd: float) -> None:
        """Add to daily realized loss accumulator."""
        self._check_day_reset()
        self._daily_loss_usd += loss_usd

    def record_order_error(self) -> None:
        """Record a consecutive order-phase error."""
        now = time.time()
        self._error_timestamps.append(now)
        # Trim to window
        cutoff = now - self.circuit_breaker_window_seconds
        self._error_timestamps = [t for t in self._error_timestamps if t >= cutoff]
        # Check if breaker should trip
        if len(self._error_timestamps) >= self.circuit_breaker_errors:
            cooldown = self.circuit_breaker_cooldown_seconds * self._cb_cooldown_multiplier
            self._cb_cooldown_until = now + cooldown
            self._cb_cooldown_multiplier = min(self._cb_cooldown_multiplier * 2, 4)  # cap at 4x = 20m
            self._error_timestamps.clear()

    def record_clean_cycle(self) -> None:
        """Reset consecutive error count on a clean (no-error) order cycle."""
        # Error timestamps trim naturally by window; no explicit reset needed
        pass

    def activate_kill_switch(self) -> None:
        self._kill_switch_active = True

    def is_kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def is_stop_loss_triggered(self) -> bool:
        self._check_day_reset()
        limit = self.total_capital_usd * self.daily_loss_limit_pct
        return self._daily_loss_usd >= limit

    def is_circuit_breaker_open(self) -> bool:
        return time.time() < self._cb_cooldown_until

    def is_blocked(self) -> bool:
        """Return True if any risk control prevents new order submission."""
        # Kill switch overrides everything — but its action is taken by caller
        return self.is_kill_switch_active() or self.is_stop_loss_triggered() or self.is_circuit_breaker_open()

    def _check_day_reset(self) -> None:
        """Reset daily loss at midnight UTC."""
        import datetime
        now_utc = datetime.datetime.utcnow()
        midnight = datetime.datetime.combine(now_utc.date(), datetime.time.min)
        if self._day_reset_timestamp < midnight.timestamp():
            self._daily_loss_usd = 0.0
            self._day_reset_timestamp = time.time()
```

### Pattern 8: Kill Switch Active Close Sequence

```python
# Source: D-08 — kill switch active close sequence
async def execute_kill_switch(client, risk_gate: RiskGate, writer: AsyncWriter):
    """
    Active kill switch: cancel pending + sell all positions.
    Must complete even if partially successful.
    """
    logger.warning("Kill switch executing — cancelling all open orders")

    # Step 1: Cancel all pending orders
    try:
        client.cancel_all()  # DELETE /cancel-all — Level 2 auth
        logger.info("All pending orders cancelled")
    except Exception as e:
        logger.error(f"cancel_all failed: {e}")

    # Step 2: Sell all held positions
    # get_balance_allowance() retrieves conditional token balances
    try:
        positions = _get_open_positions(client)  # reads from SQLite trade log
        for token_id, size in positions.items():
            if size > 0:
                order_args = OrderArgs(
                    token_id=token_id, price=0.01,  # minimum price — will fill at market bid
                    size=size, side="SELL"
                )
                signed = client.create_order(order_args)
                client.post_order(signed, orderType=OrderType.FAK)
                logger.info(f"Kill switch: sold {size} of {token_id}")
    except Exception as e:
        logger.error(f"Kill switch position close failed: {e}")

    # Step 3: Flush SQLite writer
    await writer.flush()
    logger.warning("Kill switch complete — bot halted")
```

### Anti-Patterns to Avoid

- **Using `create_and_post_order()` for live orders:** Always defaults to GTC. All arb orders must use FAK.
- **Using `signal.signal(signal.SIGTERM, handler)` in asyncio:** Not thread-safe with the event loop. Use `loop.add_signal_handler()`.
- **Blocking the event loop with sync httpx calls:** `client.get_order()` and all py-clob-client REST calls are synchronous. Wrap in `run_in_executor` when called from async context.
- **Counting WebSocket disconnects during idle scanning as circuit breaker errors:** D-07 explicitly states only order-phase errors count (rejections, timeouts during order flow, auth failures).
- **Treating `daily_loss_usd` accumulator as unrealized losses:** Only realized losses (filled orders that closed at a loss) count. Open positions are excluded until filled.
- **Using `OrderType.FOK` for arb:** FOK ("Fill-Or-Kill") requires 100% fill or cancels entirely — kills fill rate on thin markets. FAK fills as much as possible and cancels the remainder.
- **Hardcoding `fee_rate_bps`:** `create_order()` auto-resolves from the market via `__resolve_fee_rate()` when `fee_rate_bps=0`. Do not override.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Order signing (EIP-712) | Custom EIP-712 signing | `client.create_order()` | py-clob-client handles Polygon chain ID, neg_risk flag, tick_size rounding, signature nonce — all subtleties that will cause order rejection if wrong |
| Auth headers for REST | Manual HMAC construction | `client.get_order()`, `client.cancel_all()` | Level 2 headers require HMAC-SHA256 of method + path + body + timestamp — py-clob-client handles this |
| Tick size validation | Custom price rounding | `create_order()` validates via `price_valid(price, tick_size)` | Polymarket rejects orders with invalid tick sizes (e.g., 0.415 on a 0.01 tick market) |
| Neg-risk detection | Manual neg_risk lookup | `create_order()` calls `get_neg_risk(token_id)` internally | Neg-risk markets use different contract address — wrong address → invalid order signature |
| Order book VWAP | Third-party library | `calculate_market_price()` on `client` (lines 1062–1082) or custom `simulate_vwap()` | Already exists in py-clob-client; build on top |
| Cancel-all on shutdown | Iterating and cancelling one-by-one | `client.cancel_all()` | Single DELETE /cancel-all endpoint cancels all open orders atomically |

**Key insight:** py-clob-client encapsulates all Polygon-specific signing complexity. Never bypass it for order creation — even a 1-bit error in the EIP-712 struct causes silent order rejection.

---

## Common Pitfalls

### Pitfall 1: `create_and_post_order()` Silently Uses GTC

**What goes wrong:** Orders submitted via `create_and_post_order()` use `OrderType.GTC` by default. An arb order placed as GTC stays in the book after the opportunity disappears, creating naked exposure that fills later at an unfavorable price.

**Why it happens:** The method signature shows no `orderType` parameter. It's a convenience wrapper that calls `post_order(ord)` without forwarding order type.

**How to avoid:** Always use `create_order()` followed by `post_order(signed_order, orderType=OrderType.FAK)`. Never use `create_and_post_order()` for live execution.

**Warning signs:** Orders appearing as "open" in the book after submission; unexpected fills minutes later.

### Pitfall 2: Blocking the Event Loop with Sync REST Calls

**What goes wrong:** `client.get_order()`, `client.post_order()`, `client.cancel_all()` all use `httpx.Client` (synchronous). Calling them directly in an `async def` blocks the entire asyncio event loop, including the WebSocket client, during the HTTP round-trip (50–200ms per call).

**Why it happens:** py-clob-client is not async-native — it uses a module-level `_http_client = httpx.Client(http2=True)` instance.

**How to avoid:** Wrap all py-clob-client REST calls in `await asyncio.get_event_loop().run_in_executor(None, client.method, args)`.

**Warning signs:** WebSocket disconnects during order placement; scan cycle timing spikes.

### Pitfall 3: Kelly Formula Returning Near-Zero Sizes

**What goes wrong:** When `p` (execution probability = `min(1.0, depth / target_size)`) is very low (thin market), the Kelly numerator `b×p - q` becomes negative even with a positive spread. The formula correctly returns 0 — but the implementation must handle this without special-casing every edge.

**How to avoid:** Check `if numerator <= 0: return 0.0` explicitly. Never assert `kelly_result > 0` without checking.

**Warning signs:** Bot skips every opportunity even on good spreads; check depth values in price cache.

### Pitfall 4: Circuit Breaker Counting Wrong Error Types

**What goes wrong:** WebSocket reconnections during idle scanning increment the consecutive error counter, tripping the circuit breaker during normal network fluctuations.

**Why it happens:** D-07 specifies "connection errors during idle scanning do NOT count" — but without careful separation, WebSocket events can reach the error counter.

**How to avoid:** Error counting must occur only within the execution pipeline (order submission, verification, retry phases), not in the scan loop background tasks. Pass the `RiskGate.record_order_error()` call only to the execution engine, not to WebSocket reconnect handlers.

### Pitfall 5: Stop-Loss Including Unrealized P&L

**What goes wrong:** Including open positions in the stop-loss calculation causes premature trading halt when positions are temporarily underwater.

**Why it happens:** D-06 specifies "unrealized positions not counted until filled or cancelled."

**How to avoid:** Only call `risk_gate.record_loss()` when a trade is closed (fill confirmed via dual verification). Track open positions separately in the `trades` SQLite table with `status='open'` vs `status='closed'`.

### Pitfall 6: KILL File Delay in Execution Phase

**What goes wrong:** If the bot is blocked inside a 3-retry × 500ms sequence (1.5s total), the KILL file check (once per 30s scan cycle) misses the kill signal for up to 31.5 seconds.

**How to avoid:** Check the KILL file inside the retry loop AND at the start of each cycle. The retry coroutine should `check_kill_file()` before each retry attempt.

### Pitfall 7: `price_valid()` Rejecting Limit Prices

**What goes wrong:** `create_order()` validates `price >= float(tick_size) and price <= 1 - float(tick_size)`. If the VWAP-computed price rounds to exactly 0.0 or 1.0, the order is rejected.

**How to avoid:** Clamp prices: `price = max(float(tick_size), min(price, 1 - float(tick_size)))`. Tick sizes are `"0.1"`, `"0.01"`, `"0.001"`, or `"0.0001"` (from `TickSize` type in clob_types.py).

---

## Code Examples

### EXEC-01/EXEC-02: Place FAK Order

```python
# Source: py_clob_client/client.py lines 492–535, 623–661 (0.34.6, verified by code inspection)

from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.exceptions import PolyApiException

async def place_fak_order(
    client, token_id: str, price: float, size_usd: float, side: str
) -> dict | None:
    """
    Place a FAK (Fill-And-Kill) order. Returns response dict or None on failure.
    All REST calls wrapped in run_in_executor to avoid blocking the event loop.
    """
    loop = asyncio.get_running_loop()

    order_args = OrderArgs(
        token_id=token_id,
        price=price,
        size=size_usd,
        side=side,  # "BUY" or "SELL"
    )

    try:
        # create_order is sync but fast (local signing, one async get_neg_risk call)
        signed = await loop.run_in_executor(None, client.create_order, order_args)
        response = await loop.run_in_executor(
            None,
            lambda: client.post_order(signed, orderType=OrderType.FAK)
        )
        return response   # dict with "orderID", "status", etc.
    except PolyApiException as e:
        logger.error(f"Order rejected: {e.status_code} {e.error_msg}")
        return None
    except Exception as e:
        logger.error(f"Order placement error: {e}")
        return None
```

### EXEC-03: Retry-Then-Hedge (One-Leg Risk)

```python
# Source: D-03 decision — 3 retries × 500ms, then sell YES at market

async def execute_arb_with_hedge(client, risk_gate, opp, yes_size, no_size):
    """
    Execute YES leg, then attempt NO leg with retry-then-hedge fallback.
    """
    # Step 1: Buy YES
    yes_resp = await place_fak_order(client, opp.yes_token_id, opp.yes_ask, yes_size, "BUY")
    if not yes_resp or yes_resp.get("status") == "unmatched":
        return  # YES leg failed — no exposure taken

    yes_order_id = yes_resp.get("orderID")

    # Step 2: Verify YES fill via REST (dual verification per D-04)
    yes_filled = await verify_fill_rest(client, yes_order_id, timeout_seconds=5)
    if not yes_filled:
        logger.warning(f"YES fill unconfirmed for {yes_order_id} — aborting NO leg")
        risk_gate.record_order_error()
        return

    # Step 3: Attempt NO leg with retries
    for attempt in range(3):
        if risk_gate.is_kill_switch_active():
            break  # Kill switch check inside retry loop
        no_resp = await place_fak_order(client, opp.no_token_id, opp.no_ask, no_size, "BUY")
        if no_resp and no_resp.get("status") != "unmatched":
            return  # NO leg succeeded — full arb captured
        await asyncio.sleep(0.5)

    # Step 4: Hedge — sell YES at market to close naked exposure
    logger.warning(f"NO leg failed after 3 retries — hedging YES position for {opp.market_id}")
    await place_fak_order(client, opp.yes_token_id, price=0.01, size_usd=yes_size, side="SELL")
```

### RISK-04: SIGTERM + KILL File Handler

```python
# Source: Python stdlib signal module + asyncio docs

import asyncio
import os
import signal

KILL_FILE = "/app/data/KILL"

async def live_run(config, client, ...):
    loop = asyncio.get_running_loop()
    risk_gate = RiskGate(config.total_capital_usd)

    def _sigterm_handler():
        logger.warning("SIGTERM received — kill switch activated")
        risk_gate.activate_kill_switch()

    loop.add_signal_handler(signal.SIGTERM, _sigterm_handler)
    loop.add_signal_handler(signal.SIGINT, _sigterm_handler)

    while True:
        # Kill file check at top of every scan cycle
        if os.path.exists(KILL_FILE):
            logger.warning(f"KILL file detected at {KILL_FILE} — activating kill switch")
            risk_gate.activate_kill_switch()

        if risk_gate.is_kill_switch_active():
            await execute_kill_switch(client, risk_gate, writer)
            break

        # ... rest of scan cycle
```

### Trades Table Schema (Claude's Discretion)

```sql
-- Source: schema.py pattern (Phase 2) extended for Phase 3
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE NOT NULL,           -- UUID generated at submission time
    market_id TEXT NOT NULL,                  -- condition_id
    market_question TEXT NOT NULL,
    leg TEXT NOT NULL,                        -- 'yes' | 'no'
    side TEXT NOT NULL,                       -- 'BUY' | 'SELL'
    token_id TEXT NOT NULL,                   -- CLOB token_id
    price REAL NOT NULL,                      -- limit price submitted
    size REAL NOT NULL,                       -- size submitted in USD
    size_filled REAL NOT NULL DEFAULT 0.0,    -- size actually filled (from REST verify)
    fees_usd REAL NOT NULL DEFAULT 0.0,       -- estimated fees paid
    net_pnl REAL,                             -- realized P&L (null until closed)
    order_id TEXT,                            -- Polymarket order ID (from post_order response)
    status TEXT NOT NULL DEFAULT 'pending',   -- 'pending'|'filled'|'partial'|'failed'|'hedged'
    kelly_size REAL,                          -- Kelly formula output for this trade
    vwap_price REAL,                          -- VWAP-simulated price at submission
    submitted_at TEXT NOT NULL,               -- ISO datetime
    filled_at TEXT,                           -- ISO datetime, null until confirmed
    error_msg TEXT                            -- error detail if status='failed'
);

CREATE INDEX IF NOT EXISTS idx_trades_market_id ON trades(market_id);
CREATE INDEX IF NOT EXISTS idx_trades_submitted_at ON trades(submitted_at);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
```

---

## Runtime State Inventory

> Phase 3 is NOT a rename/refactor phase. No runtime state migration required.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | bot.db has `opportunities` table (Phase 2); `trades` table does not exist yet | Add `trades` table via `init_db()` extension — schema additive, no migration |
| Live service config | None | — |
| OS-registered state | None | — |
| Secrets/env vars | New Phase 3 config fields (total_capital_usd, etc.) use BotConfig defaults — no new env vars required | None |
| Build artifacts | None | — |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| py-clob-client | Order placement (EXEC-01, EXEC-02) | Yes | 0.34.6 | — |
| websockets | User WS channel for fills | Yes | 16.0 | Use REST polling (recommended for Phase 3) |
| httpx | REST calls via py-clob-client | Yes | 0.28.1 | — |
| loguru | All logging | Yes | 0.7.3 | — |
| sqlite3 | Trade logging | Yes | stdlib | — |
| asyncio signal handlers | SIGTERM via `loop.add_signal_handler` | Yes | stdlib (Unix only) | — |
| pytest + pytest-asyncio | Unit tests | Yes | 8.3.4 + 0.25.0 | — |
| Python 3.12 (Docker) | Runtime | Yes (3.10 locally, 3.12 in Docker) | 3.10/3.12 | Run on 3.10 locally for dev, 3.12 in container |
| Polymarket CLOB API (live) | Smoke tests with real orders | Required on VPS | — | Unit tests mock all API calls |

**Missing dependencies with no fallback:** None — all required packages are already installed.

**Note on Python version:** Local dev uses Python 3.10; Docker uses 3.12-slim. Both are >= 3.10, which is sufficient for py-clob-client. Union type hints (`str | None`) require 3.10+ — already in use throughout the codebase.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 + pytest-asyncio 0.25.0 |
| Config file | `pytest.ini` (exists — `asyncio_mode = auto`, `markers = unit, smoke`) |
| Quick run command | `pytest tests/ -m "not smoke" -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | `execute_opportunity()` calls `create_order()` + `post_order(FAK)` when spread exceeds threshold | unit | `pytest tests/test_execution_engine.py::test_executes_on_valid_opportunity -x` | Wave 0 |
| EXEC-01 | `execute_opportunity()` does NOT call order placement when VWAP check fails | unit | `pytest tests/test_execution_engine.py::test_skips_on_vwap_fail -x` | Wave 0 |
| EXEC-02 | `place_fak_order()` passes `OrderType.FAK` to `post_order()` — never GTC | unit | `pytest tests/test_order_client.py::test_fak_order_type -x` | Wave 0 |
| EXEC-03 | Retry logic attempts NO leg up to 3 times with 500ms sleep | unit | `pytest tests/test_execution_engine.py::test_no_leg_retries -x` | Wave 0 |
| EXEC-03 | Hedge triggered after 3 failed NO retries — SELL YES called | unit | `pytest tests/test_execution_engine.py::test_hedge_on_no_leg_failure -x` | Wave 0 |
| EXEC-04 | Dual verification calls `get_order(order_id)` after WebSocket/REST fill | unit | `pytest tests/test_order_client.py::test_verify_fill_calls_rest -x` | Wave 0 |
| EXEC-04 | Discrepancy between WebSocket and REST → abort NO leg | unit | `pytest tests/test_execution_engine.py::test_abort_on_verify_discrepancy -x` | Wave 0 |
| RISK-01 | Kelly formula returns 0.0 for negative spread | unit | `pytest tests/test_kelly.py::test_kelly_negative_spread -x` | Wave 0 |
| RISK-01 | Kelly formula caps at 5% of total capital | unit | `pytest tests/test_kelly.py::test_kelly_capital_ceiling -x` | Wave 0 |
| RISK-01 | Kelly formula returns 0.0 when result < $5 floor | unit | `pytest tests/test_kelly.py::test_kelly_below_floor -x` | Wave 0 |
| RISK-01 | Kelly formula caps at 50% of order book depth | unit | `pytest tests/test_kelly.py::test_kelly_depth_cap -x` | Wave 0 |
| RISK-02 | Stop-loss triggers after cumulative realized loss >= 5% of capital | unit | `pytest tests/test_risk_gate.py::test_stop_loss_triggers -x` | Wave 0 |
| RISK-02 | Stop-loss resets at midnight UTC | unit | `pytest tests/test_risk_gate.py::test_stop_loss_midnight_reset -x` | Wave 0 |
| RISK-02 | Stop-loss does NOT count unrealized positions | unit | `pytest tests/test_risk_gate.py::test_stop_loss_unrealized_excluded -x` | Wave 0 |
| RISK-03 | Circuit breaker trips after 5 consecutive errors in 60s | unit | `pytest tests/test_risk_gate.py::test_circuit_breaker_trips -x` | Wave 0 |
| RISK-03 | Circuit breaker exponential backoff: 5m → 10m → 20m | unit | `pytest tests/test_risk_gate.py::test_circuit_breaker_backoff -x` | Wave 0 |
| RISK-03 | WebSocket idle disconnects do NOT increment error counter | unit | `pytest tests/test_risk_gate.py::test_idle_disconnects_excluded -x` | Wave 0 |
| RISK-04 | Kill switch blocks new order submission immediately | unit | `pytest tests/test_risk_gate.py::test_kill_switch_blocks_orders -x` | Wave 0 |
| RISK-04 | Kill switch triggers `cancel_all()` + SELL for all positions | unit | `pytest tests/test_execution_engine.py::test_kill_switch_active_close -x` | Wave 0 |
| RISK-04 | KILL file detected within scan cycle triggers kill switch | unit | `pytest tests/test_live_run.py::test_kill_file_detected -x` | Wave 0 |
| RISK-04 | Kill switch overrides stop-loss and circuit breaker state | unit | `pytest tests/test_risk_gate.py::test_kill_switch_overrides_all -x` | Wave 0 |

### Simulation Strategy for No-Capital Testing

All EXEC and RISK tests are fully mockable:

```python
# Pattern for all execution tests (no live API calls needed)
@pytest.mark.unit
async def test_executes_on_valid_opportunity(bot_config):
    from unittest.mock import MagicMock, AsyncMock, patch
    from bot.execution.engine import execute_opportunity

    mock_client = MagicMock()
    mock_client.create_order.return_value = MagicMock()  # fake SignedOrder
    mock_client.post_order.return_value = {"orderID": "abc123", "status": "matched"}
    mock_client.get_order.return_value = {"status": "matched", "size_matched": "10.0"}

    # Simulate partial fill: inject mock that returns "partial" then "matched"
    mock_client.post_order.side_effect = [
        {"orderID": "abc", "status": "unmatched"},  # first NO attempt fails
        {"orderID": "abc", "status": "matched"},     # second attempt succeeds
    ]
```

**Error injection for RISK-03:** Simulate 5 consecutive API exceptions → verify circuit breaker state.

**Simulated partial fill for EXEC-03:** Return `size_matched < size_submitted` from mocked `get_order()`.

**Kill switch test for RISK-04:** Set kill file path to a temp file, verify `execute_kill_switch()` called `cancel_all()` and issued SELL orders.

### Sampling Rate

- **Per task commit:** `pytest tests/ -m "not smoke" -x -q`
- **Per wave merge:** `pytest tests/ -m "not smoke" -x -q` (same — all Phase 3 tests are unit tests)
- **Phase gate:** Full unit suite green + manual VPS smoke test with live credentials before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_kelly.py` — covers RISK-01 (Kelly formula unit tests)
- [ ] `tests/test_risk_gate.py` — covers RISK-02, RISK-03, RISK-04 (RiskGate state machine)
- [ ] `tests/test_order_client.py` — covers EXEC-02, EXEC-04 (FAK order type, REST verification)
- [ ] `tests/test_execution_engine.py` — covers EXEC-01, EXEC-03 (full pipeline, retry-hedge, kill switch)
- [ ] `tests/test_live_run.py` — covers RISK-04 (KILL file detection, scan loop integration)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `create_and_post_order()` for all orders | `create_order()` + `post_order(FAK)` for arb orders | py-clob-client always had split API | `create_and_post_order()` is a GTC convenience wrapper — never use for arb |
| `signal.signal()` for process signals in async code | `loop.add_signal_handler()` | Python 3.4+ | asyncio-safe; `signal.signal()` can corrupt event loop state |
| Order book depth check only | VWAP simulation before execution | Adoption of execution-validation layer pattern | More accurate fill price prediction; prevents executing on stale detections |

**Deprecated/outdated in this domain:**
- `signal.signal()` in asyncio context: Use `loop.add_signal_handler()` instead.
- `create_and_post_order()` for arb: Always GTC. Use `create_order()` + `post_order(FAK)`.
- Polling `get_trades()` for fill confirmation: `get_order(order_id)` is faster and order-specific.

---

## Open Questions

1. **Exact fill event message format on user WebSocket channel**
   - What we know: URL is `wss://ws-subscriptions-clob.polymarket.com/ws/user` (confirmed from Phase 1 research and official TypeScript client). Subscription format requires API key + HMAC signature.
   - What's unclear: Exact `event_type` field value for a fill (is it `"trade"`, `"fill"`, or `"order_update"`?). Exact JSON fields in the fill event.
   - Recommendation: Phase 3 should use REST polling for fill verification (not user WebSocket) — simpler, no auth complexity, sufficient for 5-second verification window. Document as `# TODO: Phase 4 — migrate fill detection to user WebSocket for lower latency` in the code.

2. **`post_order()` response dict exact schema**
   - What we know: Returns `resp.json()` from the Polymarket REST API. Confirmed to be a dict. The `orderID` field is present (used in `get_order(order_id)`). `status` field is used for matching.
   - What's unclear: Exact status values ("matched" vs "MATCHED" vs 0 vs other). Whether `size_matched` is a field in the immediate `post_order` response or only in the subsequent `get_order` response.
   - Recommendation: Log the full response dict on the first live order (with a `[DEBUG]` log) to confirm field names. Design `verify_fill_rest()` to handle both cases defensively.

3. **Selling YES tokens to close a position**
   - What we know: `OrderArgs.side = "SELL"` submits a sell order. `MarketOrderArgs` also supports SELL with `amount` = shares to sell.
   - What's unclear: For the hedge/kill switch, should the SELL price be set to `0.01` (minimum) to ensure immediate fill, or use `calculate_market_price()` to find the current bid?
   - Recommendation: Use `client.calculate_market_price(token_id, "SELL", amount, OrderType.FAK)` to compute current bid price, then submit as FAK SELL. Fall back to `price=0.01` if the call fails.

---

## Project Constraints (from CLAUDE.md)

| Directive | Constraint |
|-----------|-----------|
| Tech stack | Python + py-clob-client only. No alternative SDKs. |
| Order placement | Must use py-clob-client `create_order()` + `post_order(FAK)` — never bypass for raw HTTP |
| Latency | Sub-100ms to Polymarket APIs (already verified in Phase 1) |
| Capital | Under $1k total — Kelly formula with 5% ceiling enforces this |
| Deployment | Docker on VPS; kill switch must work via `docker compose stop` (SIGTERM) |
| Logging | loguru only — no stdlib logging, no structlog |
| Database | SQLite — `init_db()` extended, not replaced |
| Architecture | `dry_run.py` stays intact; live execution in new `live_run.py` |
| GSD Workflow | All code changes go through GSD commands |

---

## Sources

### Primary (HIGH confidence)

- `py_clob_client/clob_types.py` (0.34.6, installed) — `OrderType.FAK`, `OrderArgs` fields, `MarketOrderArgs`, `OrderBookSummary`, `TickSize` values verified by direct code inspection
- `py_clob_client/client.py` (0.34.6, installed) — `create_order()`, `post_order()`, `create_and_post_order()`, `get_order()`, `cancel_all()`, `calculate_market_price()` signatures verified by direct code inspection
- `py_clob_client/order_builder/builder.py` (0.34.6, installed) — `calculate_buy_market_price()`, `calculate_sell_market_price()` logic for FOK/FAK price computation
- `py_clob_client/utilities.py` (0.34.6, installed) — `order_to_json()` confirms `orderType` is passed as-is to API body
- `py_clob_client/http_helpers/helpers.py` (0.34.6, installed) — sync `httpx.Client` confirmed; `run_in_executor` requirement verified
- `py_clob_client/endpoints.py` (0.34.6, installed) — `GET_ORDER = "/data/order/"`, `CANCEL_ALL = "/cancel-all"` confirmed
- `src/bot/config.py` — `BotConfig` dataclass verified; Phase 3 must add `total_capital_usd` and risk params as fields with defaults
- `src/bot/detection/opportunity.py` — `ArbitrageOpportunity` fields verified; `yes_ask`, `no_ask`, `depth`, `net_spread` are inputs to execution engine
- `src/bot/scanner/price_cache.py` — `MarketPrice.yes_depth`, `no_depth` are USD depth at best ask; used for Kelly `p` calculation
- `src/bot/dry_run.py` — scan loop structure confirmed; `live_run.py` is a direct extension
- Python stdlib `asyncio` + `signal` — `loop.add_signal_handler()` confirmed available on macOS/Linux
- `.planning/phases/01-infrastructure-foundation/01-RESEARCH.md` — `WSS_USER_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"` confirmed from Phase 1

### Secondary (MEDIUM confidence)

- Phase 1 research citing `github.com/Polymarket/clob-client examples/socketConnection.ts` — WebSocket URL format `{host}/ws/{type}` confirmed; user channel subscription auth format inferred from TypeScript client patterns
- Phase 1 research citing `github.com/J-Verwey/pm_access_example` — market channel subscription format confirmed; user channel format inferred
- Polymarket REST API conventions — `status`, `size_matched`, `orderID` field names inferred from standard patterns; confirmed via `get_order()` endpoint path `/data/order/{id}`

### Tertiary (LOW confidence)

- User WebSocket channel fill event `event_type` exact values — not confirmed from authoritative source; inferred from standard Polymarket patterns. Flag for validation on first live order.
- `post_order()` response dict exact field schema — function returns raw JSON; exact status value strings (e.g., "matched" vs "MATCHED") not confirmed from source code.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified from installed 0.34.6 source
- Architecture: HIGH — patterns verified from code inspection; critical `FAK` vs `GTC` finding is HIGH confidence
- Order placement API: HIGH — `create_order()` + `post_order(FAK)` pattern verified from source
- Fill verification (REST): MEDIUM — `get_order()` confirmed to exist; response field names inferred from patterns
- User WebSocket fill events: LOW — URL confirmed, message format inferred
- Risk gate patterns: HIGH — pure Python logic, no external API dependency
- Kelly formula: HIGH — direct implementation from arxiv 2508.03474 paper cited in CONTEXT.md

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (py-clob-client version pinned at 0.34.6; API changes possible but unlikely within 30 days)
