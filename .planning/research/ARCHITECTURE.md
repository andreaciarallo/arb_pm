# Architecture Patterns

**Domain:** Polymarket Arbitrage Bot -- v2.0 Basket Arbitrage Engine
**Researched:** 2026-04-26
**Mode:** Integration architecture for V2 basket pricing pipeline into existing codebase

## Current Architecture Snapshot (v1.2)

```
src/bot/
  config.py              BotConfig (frozen dataclass, env-loaded, 30+ fields)
  client.py              ClobClient builder
  main.py                CLI entrypoint (--live vs dry-run)
  dry_run.py             Scan loop: detect + paper-trade simulate, no execution
  live_run.py            Scan loop + execution + risk gate + dashboard

  scanner/
    market_filter.py     Paginated CLOB fetch, active market filtering
    ws_client.py         WebSocket subscription (2000 token cap)
    http_poller.py       HTTP fallback for stale markets (50/cycle rotation)
    normalizer.py        Raw -> MarketPrice conversion
    price_cache.py       In-memory {token_id: MarketPrice} cache

  detection/
    yes_no_arb.py        YES+NO structural arb (sum < 1.0)  [REMOVE in v2.0]
    cross_market.py      Event-level grouping + pairwise dependency + detection
    dependency.py        5-signal weighted scorer (Jaccard/impl/num/temp/event)
    filters.py           Threshold filters (ask floor, sum cap, dead leg, dedup)
    fee_model.py         Category-aware taker fees + thresholds
    opportunity.py       ArbitrageOpportunity dataclass

  execution/
    engine.py            VWAP gate -> Kelly -> FAK orders -> retry/hedge
    kelly.py             Modified Kelly position sizing
    order_client.py      place_fak_order(), verify_fill_rest()

  risk/
    gate.py              RiskGate: stop-loss, circuit breaker, kill switch

  paper/
    simulator.py         VWAP+Kelly paper trade simulation
    writer.py            PaperTradeWriter for paper_trades table

  storage/
    schema.py            SQLite DDL: opportunities, trades, arb_pairs, paper_trades
    writer.py            AsyncWriter queue for opportunity inserts
    paper_summary.py     Summary queries for paper trades

  notifications/
    telegram.py          Telegram alerter (arb complete, CB trip, daily)

  dashboard/
    app.py               FastAPI + HTML dashboard (port 8080)
```

## V2 Pipeline: What Changes and Why

The V2 pipeline replaces the current cross-market detection and execution flow with a basket-level approach. The core insight: the current system detects opportunities at best-ask prices and only discovers the real executable cost (VWAP) at execution time. This causes a high rejection rate at the VWAP gate. V2 moves VWAP computation upstream into detection, computes a common trade size across all legs, and makes profitability decisions on executable costs.

### V1.2 Cross-Market Flow (current)

```
Event groups (Gamma)
    |
    v
Pairwise dependency check (O(n^2) pairs per group)
    |
    v
Dead leg + total_yes filters
    |
    v
Best-ask sum check (total_yes < 1.0?)
    |
    v
Gross/net spread at best-ask prices
    |
    v
ArbitrageOpportunity created with best-ask legs
    |
    v [execution engine only]
Fetch fresh order books per leg
    |
    v
VWAP simulation on fresh books
    |
    v
Kelly sizing on VWAP-adjusted spread
    |
    v
Sequential leg execution with retry-then-hedge
```

**Problems with V1.2:**
1. Detection uses best-ask, execution uses VWAP -- spread at detection != spread at execution
2. Pairwise dependency check is O(n^2) and uses text heuristics instead of structural validation
3. No common size across legs -- each leg sized independently
4. Sequential execution with fire-sale hedge on any failure
5. PriceCache stores single-level depth only (best ask + size at that level)

### V2 Basket Flow (target)

```
Stage 1: Event grouping (Gamma)                     [KEEP as-is]
    |
    v
Stage 2: Partition validation                        [NEW: replaces dependency]
    |       Is this group a valid 1-of-N partition?
    |       Structural check, not pairwise text heuristics
    v
Stage 3: Liquidity filtering                         [NEW: replaces price heuristics]
    |       Per-leg: depth >= threshold, spread < max, price not stale
    |       Group-level: all legs pass, min depth across group
    v
Stage 4: Basket construction                         [NEW]
    |       VWAP per leg at common target size
    |       total_vwap_cost = sum(vwap_i)
    v
Stage 5: Profitability gate                          [NEW]
    |       net_edge = 1.0 - total_vwap_cost - fees - slippage_buffer
    |       net_edge >= min_threshold?
    v
Stage 6: Size optimization                          [NEW]
    |       Common size = min(kelly_size, min_depth across legs)
    |       Pre-computed before any leg fires
    v
Stage 7: Execution                                   [MODIFIED]
        Parallel leg dispatch via batch /orders endpoint
        Abort-early: cancel unfilled legs, don't fire-sale
```

---

## Component Boundaries

| Component | Responsibility | Communicates With | Status |
|-----------|---------------|-------------------|--------|
| `cross_market.py` | Event grouping (Stage 1) + orchestrate detection pipeline | Gamma API (startup), PriceCache, basket modules | MODIFIED (stripped down) |
| `partition.py` | Validate that a market group is a true 1-of-N partition (Stage 2) | cross_market (called by) | NEW |
| `liquidity.py` | Per-leg and group-level liquidity checks (Stage 3) | PriceCache, BotConfig | NEW |
| `basket.py` | VWAP basket construction + profitability + sizing (Stages 4-6) | PriceCache, kelly.py, fee_model.py, order books | NEW |
| `opportunity.py` | BasketOpportunity dataclass (replaces ArbitrageOpportunity for cross-market) | All detection + execution modules | MODIFIED |
| `engine.py` | Basket execution with parallel legs and abort-early (Stage 7) | basket.py output, order_client.py, risk gate | MODIFIED |
| `order_client.py` | Add batch order placement via /orders endpoint | engine.py | MODIFIED |
| `simulator.py` | Paper-trade simulation updated for basket opportunities | basket.py, kelly.py | MODIFIED |
| `dry_run.py` | Updated to use basket pipeline, remove YES/NO path | basket pipeline, paper simulator | MODIFIED |
| `live_run.py` | Updated to use basket pipeline, remove YES/NO path | basket pipeline, execution engine | MODIFIED |

---

## Detailed Component Designs

### Component 1: Partition Validator (`detection/partition.py`)

**Purpose:** Replace pairwise dependency rejection with a structural one-of-N validation. Instead of checking O(n^2) question pairs for text overlap, validate that the group structurally represents a partition (exactly one outcome must resolve YES).

**Why replace dependency.py:** The current 5-signal scorer (Jaccard, implication, numeric, temporal, event bonus) has fundamental limitations. It uses text heuristics to detect whether markets are "related" or "subset," but what we actually need is confirmation that the group IS a valid exhaustive partition. Text similarity is a proxy for the wrong question. Markets in the same Polymarket event are already structurally related -- the question is whether they form a complete, mutually exclusive set.

**Approach:** A group is a valid partition if:
1. All markets share the same event_id (already guaranteed by Stage 1 grouping)
2. The group contains ALL markets in that event (no missing outcomes)
3. No market in the group has resolved or been delisted

```python
"""
Partition validation for cross-market basket arbitrage.

Validates that a group of markets forms a complete 1-of-N partition:
exactly one market will resolve YES, all others will resolve NO.

This is a STRUCTURAL check, not a text heuristic. It verifies completeness
(all event markets present) rather than pairwise independence.
"""

@dataclass(frozen=True)
class PartitionResult:
    valid: bool
    reason: str            # "valid" | "incomplete" | "too_small" | "too_large"
    group_size: int
    event_market_count: int  # total markets in event (from Gamma cache)


def validate_partition(
    group: list[dict],
    event_id: str,
    event_market_counts: dict[str, int],  # event_id -> total market count
    min_size: int = 2,
    max_size: int = 20,
) -> PartitionResult:
    """
    Validate that group contains ALL markets for the given event.

    A group is valid iff len(group) == event_market_counts[event_id].
    Incomplete groups (missing outcomes) are NOT valid partitions -- buying
    all present YES tokens doesn't guarantee profit if a missing outcome wins.
    """
```

**Key design decision:** The `event_market_counts` dict is populated alongside `_event_groups` at startup from the Gamma API. When we fetch events, we also count how many markets each event has. This count is the ground truth for completeness validation.

**Integration:** Called from the detection pipeline after grouping, before liquidity checks. Groups that fail partition validation are dropped entirely (no audit mode -- this is a structural invariant, not a tunable threshold).

**What happens to dependency.py:** It remains in the codebase but is no longer called from the detection hot path. It can be retained as a utility for diagnostics/logging if desired, or removed entirely. The `classify_pair()` function and its 5 signals are not needed for partition validation.

---

### Component 2: Liquidity Filter (`detection/liquidity.py`)

**Purpose:** Replace the current price-based heuristics (dead leg floor, total_yes floor, depth gate) with liquidity-oriented checks that operate on order book depth, spread quality, and freshness.

**Why separate from filters.py:** The current `filters.py` contains stateless threshold checks (is_ask_floor_reject, has_dead_leg, etc.) that are point-price checks. The V2 liquidity filter operates on multi-level order book data and includes time-based staleness checks. It is a different abstraction level.

```python
"""
Liquidity filtering for basket arbitrage legs.

Checks per-leg and group-level liquidity quality before basket construction.
Operates on PriceCache data (single-level in v2.0, multi-level when available).
"""

@dataclass(frozen=True)
class LegLiquidity:
    token_id: str
    best_ask: float
    best_bid: float
    depth_usd: float          # USD available at best ask
    spread_pct: float         # (ask - bid) / ask
    age_seconds: float        # time since last price update
    passes: bool
    reject_reason: str | None  # "insufficient_depth" | "wide_spread" | "stale" | None


@dataclass(frozen=True)
class GroupLiquidity:
    legs: list[LegLiquidity]
    min_depth_usd: float       # weakest leg's depth
    max_spread_pct: float      # widest leg's spread
    max_age_seconds: float     # oldest leg's timestamp
    all_pass: bool


def check_leg_liquidity(
    token_id: str,
    cache: PriceCache,
    config: BotConfig,
) -> LegLiquidity:
    """
    Check a single leg's liquidity quality.

    Reject conditions (all configurable via BotConfig):
    - depth < min_leg_depth_usd (default: $50)
    - spread > max_leg_spread_pct (default: 15%)
    - age > max_leg_age_seconds (default: 30s)
    - price <= min_ask_floor (default: $0.005)
    """


def check_group_liquidity(
    legs: list[dict],   # [{"token_id": str, ...}]
    cache: PriceCache,
    config: BotConfig,
) -> GroupLiquidity:
    """
    Check all legs in a group. Group passes only if ALL legs pass individually.
    Also computes group-level aggregates (min depth, max spread, max age).
    """
```

**Config additions to BotConfig:**

```python
# V2 Liquidity filter thresholds
min_leg_depth_usd: float = 50.0       # per-leg minimum depth
max_leg_spread_pct: float = 0.15      # per-leg maximum bid-ask spread
max_leg_age_seconds: float = 30.0     # per-leg maximum price staleness
```

---

### Component 3: Basket Constructor (`detection/basket.py`)

**Purpose:** Build a fully priced basket quote from a validated, liquid market group. This is the core of V2 -- it computes the VWAP cost per leg at a common target size, determines the net edge after fees, and pre-computes the optimal trade size.

**This is the single most important new module.** It replaces the split between detection (best-ask math) and execution (VWAP math) with a unified computation.

```python
"""
Basket construction and pricing for cross-market arbitrage.

Given a validated partition of N mutually exclusive markets, constructs a
basket quote: VWAP cost per leg at a common size, total cost, net edge
after fees and slippage buffer, and recommended trade size.

The basket is the unit of decision: if BasketQuote.is_profitable is True,
execute all legs. If False, skip the entire group.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LegQuote:
    token_id: str
    market_id: str         # condition_id
    question: str
    best_ask: float
    vwap_price: float      # VWAP at target_shares
    depth_usd: float       # total depth available
    max_shares: float      # maximum fillable shares at this leg
    category: str


@dataclass(frozen=True)
class BasketQuote:
    event_id: str
    legs: list[LegQuote]
    n_legs: int

    # Pricing
    total_best_ask: float       # sum of best asks (for comparison)
    total_vwap_cost: float      # sum of VWAP prices (executable cost)
    gross_edge: float           # 1.0 - total_vwap_cost
    estimated_fees: float       # taker fees on all legs
    slippage_buffer: float      # safety margin (configurable, e.g. 0.5%)
    net_edge: float             # gross_edge - fees - slippage

    # Sizing
    common_shares: float        # shares per leg (equal across all legs)
    total_cost_usd: float       # common_shares * total_vwap_cost
    expected_profit_usd: float  # common_shares * net_edge

    # Decision
    is_profitable: bool         # net_edge >= min_threshold
    reject_reason: str | None   # None if profitable, else why rejected


def build_basket(
    group: list[dict],           # market dicts from event grouping
    cache: PriceCache,
    config: BotConfig,
    order_books: dict[str, list] | None = None,  # token_id -> ask levels (optional)
) -> BasketQuote | None:
    """
    Build a fully-priced basket quote for an event group.

    Steps:
    1. Extract YES token IDs and current prices from cache
    2. Compute initial target_shares from Kelly sizing on best-ask spread
    3. For each leg, compute VWAP at target_shares
    4. Compute common_shares = min(max_shares across all legs)
    5. Re-compute VWAP at common_shares (may improve pricing)
    6. Compute fees, slippage buffer, net edge
    7. Return BasketQuote with profitability decision

    Returns None if any leg has no cached price data.
    """


def _compute_leg_vwap(
    asks: list[dict],    # [{"price": float, "size": float}]
    target_shares: float,
) -> tuple[float, float]:
    """
    Compute VWAP and max fillable shares from an ask book.

    Returns (vwap_price, max_shares).
    Uses existing simulate_vwap() logic but returns both values.
    """
```

**Key design decisions:**

1. **VWAP from cache vs fresh order books:** In the detection hot path, use cached single-level price data for VWAP approximation. The cache stores best_ask + depth_at_best_ask, which gives a single-level VWAP. For the final execution decision, optionally fetch fresh multi-level order books via the batch `/books` endpoint (one POST with all leg token IDs). This is configurable: `basket_use_fresh_books: bool = False` in BotConfig.

2. **Common shares, not common dollars:** All legs get the same number of shares (not the same dollar amount). `common_shares = min(kelly_shares, min(max_shares_per_leg))`. This guarantees payout = common_shares * $1.00 regardless of which leg wins.

3. **Slippage buffer:** A configurable safety margin (default 0.5%) subtracted from gross edge before the profitability decision. This accounts for price movement between detection and execution.

4. **BasketQuote is frozen:** It is a snapshot of pricing at a point in time. Once constructed, it is passed to the execution engine as-is. The execution engine does NOT recompute pricing -- it trusts the quote and executes. If the market has moved by execution time, the FAK orders will simply not fill (which is fine -- FAK cancels unfilled remainder).

**Integration with existing code:**

- `simulate_vwap()` from `engine.py` is reused (or its logic is extracted to a shared utility)
- `kelly_size()` from `kelly.py` is reused for sizing
- `get_taker_fee()` from `fee_model.py` is reused for fee computation
- `get_market_category()` from `fee_model.py` is reused for category detection

---

### Component 4: Updated Opportunity Dataclass

**Problem:** The current `ArbitrageOpportunity` dataclass was designed for both YES/NO and cross-market, with fields like `yes_ask`, `no_ask`, `vwap_yes`, `vwap_no` that only make sense for YES/NO arb. Cross-market uses `legs` as a bolt-on list. V2 needs a basket-native representation.

**Approach:** Add a new `BasketOpportunity` dataclass that wraps `BasketQuote` with execution metadata. Keep `ArbitrageOpportunity` for backward compatibility with paper_trades table schema, but new code uses `BasketOpportunity`.

```python
@dataclass
class BasketOpportunity:
    """V2 basket arbitrage opportunity ready for execution."""
    basket_id: str              # UUID
    event_id: str
    basket: BasketQuote         # full pricing snapshot
    detected_at: datetime

    # Convenience accessors
    @property
    def market_id(self) -> str:
        return self.basket.legs[0].market_id

    @property
    def net_edge(self) -> float:
        return self.basket.net_edge

    @property
    def n_legs(self) -> int:
        return self.basket.n_legs

    @property
    def total_cost_usd(self) -> float:
        return self.basket.total_cost_usd
```

**Migration note:** The SQLite `opportunities` table currently stores ArbitrageOpportunity fields. V2 can either: (a) add new columns for basket fields, or (b) store BasketOpportunity in a new `basket_opportunities` table. Option (b) is cleaner -- no schema migration, and the old table retains historical v1.x data.

---

### Component 5: Updated Execution Engine (`execution/engine.py`)

**Changes to the execution engine for V2:**

1. **Remove `_execute_cross_market()`** -- replaced by basket execution
2. **Remove YES/NO execution path** (YES/NO arb removed per PROJECT.md)
3. **Add `execute_basket()`** -- new entry point for basket opportunities
4. **Add batch order book fetch** via `/books` endpoint
5. **Add parallel leg dispatch** via `/orders` endpoint (max 15 legs)
6. **Replace fire-sale hedge with abort-early** -- cancel unfilled legs instead of selling at $0.01

```python
async def execute_basket(
    client,
    opp: BasketOpportunity,
    config: BotConfig,
    risk_gate: RiskGate,
) -> tuple[str, list[ExecutionResult]]:
    """
    Execute a basket arbitrage opportunity.

    V2 execution flow:
    1. Pre-flight: risk gate check, freshness re-check
    2. Optional: fetch fresh order books via batch /books endpoint
    3. Optional: re-validate basket profitability at fresh prices
    4. Place all legs via batch /orders endpoint (max 15 per request)
    5. Verify fills via REST polling
    6. On partial fill: cancel unfilled legs (NOT fire-sale)
    7. Return execution results
    """
```

**Batch order placement via `/orders` endpoint:**

The Polymarket CLOB API supports posting up to 15 orders in a single request via `POST /orders`. This is ideal for basket execution:
- Rate limit: 1,000 req/10s burst, 15,000 req/10min sustained
- All orders are FAK (fill-and-kill)
- Response includes per-order success/failure and fill information

**Confidence: HIGH** -- verified from official API docs at docs.polymarket.com/api-reference/trade/post-multiple-orders.md. The endpoint processes orders and returns individual results. The docs state "Maximum 15 orders per request."

**Important constraint on batch FAK:** The official docs note that post-only orders work exclusively with GTC/GTD and cannot be combined with FAK. However, regular (non-post-only) FAK orders in batch are supported -- the restriction only applies to the `postOnly` flag. Each order in the batch can independently specify its `orderType`.

**py-clob-client support:** The SDK should expose a method for batch order posting. If it does not, the batch endpoint can be called directly via httpx with the appropriate auth headers.

**Abort-early vs fire-sale hedge:**

The V1 hedge strategy (sell all filled legs at $0.01) is extremely costly. A $0.50 position sold at $0.01 loses $0.49 per share. V2 uses abort-early:
- If any leg fails to fill, cancel all other pending legs
- Filled legs remain as open positions (they will resolve to $0 or $1)
- The expected value of holding a filled leg is its current price (e.g., $0.40)
- Selling at $0.01 crystallizes a loss of $0.39 -- worse than holding

**When to hedge instead of hold:**
- If >50% of legs are filled (partial basket), the held positions have correlated risk
- If the market is about to resolve, holding may be fine
- V2 default: hold filled legs, do not fire-sale. Monitor via dashboard.

---

### Component 6: Batch Order Book Fetch

**New capability:** The `/books` endpoint (`POST /books`) accepts an array of token IDs and returns order book summaries for all of them in one request. This eliminates the need for N sequential `GET /book?token_id=X` calls.

**Rate limits:**
- `/book` (single): 1,500 req/10s
- `/books` (batch): 500 req/10s

**Integration:** Add `fetch_order_books_batch()` to `order_client.py`:

```python
async def fetch_order_books_batch(
    client,
    token_ids: list[str],
) -> dict[str, OrderBookSummary]:
    """
    Fetch order books for multiple tokens in a single request.

    Uses POST /books endpoint. Returns {token_id: OrderBookSummary}.
    Falls back to sequential GET /book calls if batch fails.
    """
```

**Usage in basket pipeline:** When `basket_use_fresh_books=True`, the basket constructor calls this once per group to get multi-level order books for all legs simultaneously. This replaces N sequential calls with 1 batch call.

---

### Component 7: Updated Paper Trade Simulator

**Changes to `paper/simulator.py`:**

1. Remove `simulate_yes_no()` (YES/NO arb removed)
2. Replace `simulate_cross_market()` with `simulate_basket()`
3. The new simulator takes a `BasketQuote` and produces `PaperTrade` rows
4. P&L computation uses basket-level metrics (common_shares * net_edge)

```python
def simulate_basket(
    opp: BasketOpportunity,
    cache: PriceCache,
    config: BotConfig,
) -> list[PaperTrade]:
    """
    Simulate a basket arbitrage paper trade.

    Uses the pre-computed BasketQuote for pricing (no redundant VWAP).
    Produces one PaperTrade row per leg.
    P&L = common_shares * net_edge, distributed equally across legs.
    """
```

---

## V2 Architecture Diagram

```
                    Polymarket APIs (CLOB + Gamma)
                              |
                              v
               +----------------------------+
               |   DATA INGESTION LAYER     |
               |  ws_client, http_poller    |
               |  market_filter             |
               +-------------+--------------+
                              |
                              v
               +----------------------------+
               |    NORMALIZATION LAYER     |
               |  normalizer, price_cache   |
               +-------------+--------------+
                              |
                              v
    +--------------------------------------------------+
    |          BASKET DETECTION PIPELINE (V2)           |
    |                                                  |
    |  Stage 1: Event Grouping (cross_market.py)       |
    |      |  load_event_groups() at startup            |
    |      |  _group_by_event() in detection loop       |
    |      v                                            |
    |  Stage 2: Partition Validation (partition.py)     |
    |      |  validate_partition() per group             |
    |      v                                            |
    |  Stage 3: Liquidity Filtering (liquidity.py)     |
    |      |  check_group_liquidity() per group          |
    |      v                                            |
    |  Stage 4-6: Basket Construction (basket.py)      |
    |      |  build_basket() -> BasketQuote              |
    |      |  VWAP per leg, fees, slippage, sizing      |
    |      v                                            |
    |  BasketOpportunity                                |
    +------------------------+-------------------------+
                              |
                  +-----------+-----------+
                  |                       |
          +-------+--------+     +-------+--------+
          |   LIVE PATH    |     |  PAPER PATH    |
          |  risk gate     |     |  simulate_     |
          |  execute_      |     |  basket()      |
          |  basket()      |     |  paper writer  |
          |  batch /orders |     +-------+--------+
          +-------+--------+             |
                  |                       |
                  v                       v
          +----------------------------------+
          |     STORAGE & MONITORING         |
          |  schema.py, writer.py            |
          |  dashboard/app.py                |
          |  telegram.py                     |
          +----------------------------------+
```

---

## Data Flow: Event Groups to Execution

### Detection Path (runs every scan cycle)

```
1. priced_markets = [m for m in markets if has_cached_price(m)]

2. groups = _group_by_event(priced_markets)
   # Returns list of market groups, each sharing an event_id
   # Filters: 2 <= len(group) <= 20

3. for group in groups:
       # Stage 2: Partition check
       event_id = get_event_id(group[0])
       result = validate_partition(group, event_id, event_market_counts)
       if not result.valid:
           diag.partition_rejects += 1
           continue

       # Stage 3: Liquidity check
       liq = check_group_liquidity(group_legs, cache, config)
       if not liq.all_pass:
           diag.liquidity_rejects += 1
           continue

       # Stages 4-6: Basket construction
       basket = build_basket(group, cache, config)
       if basket is None:
           diag.basket_build_failures += 1
           continue
       if not basket.is_profitable:
           diag.profitability_rejects += 1
           continue

       # Emit opportunity
       opp = BasketOpportunity(
           basket_id=uuid4(),
           event_id=event_id,
           basket=basket,
           detected_at=utcnow(),
       )
       opportunities.append(opp)
```

### Execution Path (live mode only)

```
4. for opp in opportunities:
       if risk_gate.is_blocked():
           continue

       # Optional: re-fetch fresh order books
       if config.basket_use_fresh_books:
           token_ids = [leg.token_id for leg in opp.basket.legs]
           books = await fetch_order_books_batch(client, token_ids)
           # Re-build basket with fresh books
           basket = build_basket(group, cache, config, order_books=books)
           if not basket.is_profitable:
               continue  # market moved, skip

       # Execute
       arb_id, results = await execute_basket(client, opp, config, risk_gate)

       # Log results
       for result in results:
           insert_trade(conn, result, ...)
```

### Paper Trade Path (dry-run mode)

```
4. for opp in opportunities:
       trades = simulate_basket(opp, cache, config)
       for trade in trades:
           paper_writer.enqueue(trade)
```

---

## Module Dependency Graph (V2)

```
config.py
  |
  +-- detection/fee_model.py
  |
  +-- detection/partition.py     [NEW: no deps beyond config]
  |
  +-- detection/liquidity.py     [NEW: depends on price_cache, config]
  |
  +-- detection/basket.py        [NEW: depends on price_cache, config,
  |     |                                kelly.py, fee_model.py,
  |     |                                engine.simulate_vwap()]
  |     +-- execution/kelly.py
  |     +-- detection/fee_model.py
  |
  +-- detection/cross_market.py  [MODIFIED: stripped to grouping + pipeline orchestration]
  |     |
  |     +-- detection/partition.py
  |     +-- detection/liquidity.py
  |     +-- detection/basket.py
  |
  +-- execution/engine.py        [MODIFIED: execute_basket(), remove YES/NO path]
  |     +-- execution/order_client.py  [MODIFIED: batch order book fetch, batch order post]
  |     +-- risk/gate.py
  |
  +-- paper/simulator.py         [MODIFIED: simulate_basket()]
  |     +-- detection/basket.py
  |     +-- execution/kelly.py
  |
  +-- dry_run.py                 [MODIFIED: basket pipeline, remove YES/NO]
  +-- live_run.py                [MODIFIED: basket pipeline, remove YES/NO, execute_basket]
```

---

## Files Changed Summary

### New Files (3 source + 3 test)

| File | LOC Est | Purpose |
|------|---------|---------|
| `detection/partition.py` | ~60 | Partition validation (1-of-N completeness check) |
| `detection/liquidity.py` | ~80 | Per-leg and group-level liquidity filtering |
| `detection/basket.py` | ~200 | VWAP basket construction, pricing, sizing |
| `tests/test_partition.py` | ~80 | Partition validation tests |
| `tests/test_liquidity.py` | ~80 | Liquidity filter tests |
| `tests/test_basket.py` | ~150 | Basket construction + pricing tests |

### Modified Files (8)

| File | Change Scope | Impact |
|------|-------------|--------|
| `detection/cross_market.py` | **Major rewrite**: strip detection logic, keep grouping, add pipeline orchestration | High |
| `detection/opportunity.py` | Add `BasketOpportunity` dataclass | Medium |
| `execution/engine.py` | Replace `_execute_cross_market()` with `execute_basket()`, remove YES/NO path | High |
| `execution/order_client.py` | Add `fetch_order_books_batch()`, add `place_fak_orders_batch()` | Medium |
| `paper/simulator.py` | Replace `simulate_cross_market()` with `simulate_basket()`, remove YES/NO | Medium |
| `config.py` | Add ~8 new basket/liquidity config fields | Low |
| `dry_run.py` | Use basket pipeline, remove YES/NO detection path | Medium |
| `live_run.py` | Use basket pipeline, remove YES/NO, use `execute_basket()` | Medium |

### Removed/Deprecated Files

| File | Action | Reason |
|------|--------|--------|
| `detection/yes_no_arb.py` | Remove (or keep as dead code) | YES/NO arb removed per PROJECT.md |
| `detection/dependency.py` | Deprecate (retain for diagnostics if desired) | Replaced by partition.py |
| `detection/filters.py` | Deprecate most functions | Replaced by liquidity.py; DedupTracker may be retained |
| `tests/test_yes_no_arb.py` | Remove | Corresponds to removed feature |
| `tests/test_dependency.py` | Remove or update | Corresponds to deprecated module |

### Unchanged Files

| Module | Reason |
|--------|--------|
| `scanner/*` (ws_client, http_poller, normalizer, price_cache, market_filter) | Data ingestion layer is untouched |
| `risk/gate.py` | Risk controls unchanged |
| `storage/schema.py`, `storage/writer.py` | May need minor additions for basket tables |
| `notifications/telegram.py` | Notification format may need minor updates |
| `dashboard/app.py` | Dashboard reads from DB -- minor query updates |
| `execution/kelly.py` | Pure function, reused as-is |
| `detection/fee_model.py` | Pure functions, reused as-is |

---

## Config Changes

New fields for `BotConfig`:

```python
# V2: Partition validation
# (No config needed -- partition is structural, not threshold-based)

# V2: Liquidity filtering
min_leg_depth_usd: float = 50.0          # per-leg minimum depth at best ask
max_leg_spread_pct: float = 0.15         # per-leg maximum bid-ask spread (15%)
max_leg_age_seconds: float = 30.0        # per-leg maximum price staleness

# V2: Basket construction
basket_slippage_buffer: float = 0.005    # 0.5% safety margin on net edge
basket_use_fresh_books: bool = False     # fetch fresh /books before execution
basket_min_net_edge: float = 0.01        # 1% minimum net edge after fees+slippage

# V2: Execution
basket_parallel_legs: bool = True        # use batch /orders endpoint
basket_abort_on_partial: bool = True     # cancel unfilled legs instead of hedge
```

Fields to remove (or leave as deprecated defaults):
```python
# No longer used in V2 (YES/NO arb removed):
# min_ask_floor, max_ask_sum remain in config for backward compat
# min_cross_leg_ask, min_cross_total_yes replaced by liquidity.py
# dep_weight_*, dep_threshold_*, dependency_audit_mode replaced by partition.py
```

---

## Suggested Build Order

```
Phase 1: Basket Core (detection side)
    1a. detection/partition.py + tests
    1b. detection/liquidity.py + tests
    1c. detection/basket.py + tests
    1d. detection/opportunity.py (BasketOpportunity)

Phase 2: Pipeline Integration
    2a. Refactor cross_market.py to use partition -> liquidity -> basket pipeline
    2b. Update dry_run.py to use basket pipeline (remove YES/NO)
    2c. Update paper/simulator.py for basket paper trades
    2d. Config.py additions

Phase 3: Execution Engine
    3a. order_client.py: fetch_order_books_batch()
    3b. order_client.py: place_fak_orders_batch()
    3c. engine.py: execute_basket() with batch orders + abort-early
    3d. Update live_run.py to use execute_basket()

Phase 4: Polish & Cleanup
    4a. Remove YES/NO arb code and tests
    4b. Update storage schema for basket_opportunities table
    4c. Update dashboard queries
    4d. Update Telegram notification format
```

### Rationale for This Order

1. **Basket core FIRST** because partition, liquidity, and basket are pure functions with no side effects and no integration dependencies. They can be built and tested in complete isolation. This is the most important new code and benefits from being developed and tested before integration pressure.

2. **Pipeline integration SECOND** because it wires the new modules into the existing scan loop. The detection side (dry_run, cross_market) changes before the execution side because detection is lower-risk (no real orders). Paper trading validates the pipeline produces sensible results before any live execution.

3. **Execution engine THIRD** because it depends on the basket pipeline producing valid BasketOpportunity objects. Batch order placement (/orders endpoint) and abort-early logic are the highest-risk changes and should be built last, after the detection pipeline is stable and producing verified output.

4. **Cleanup LAST** because removing old code and updating peripheral systems (dashboard, Telegram, storage) is low-risk and can be done after the core pipeline is working.

---

## Patterns to Follow

### Pattern 1: Basket as Unit of Decision

**What:** All profitability decisions happen at the basket level, not per-leg. A basket is profitable or not -- never "leg 1 is good but leg 3 is bad."

**Why:** In cross-market arb, individual legs are not independently profitable. A YES token at $0.40 is only profitable in the context of a group summing to less than $1.00. Evaluating individual legs in isolation is meaningless.

```python
# Good: basket-level decision
basket = build_basket(group, cache, config)
if basket.is_profitable:
    execute_all_legs(basket)

# Bad: per-leg evaluation
for leg in group:
    if leg_is_profitable(leg):  # meaningless for cross-market
        execute_leg(leg)
```

### Pattern 2: Frozen Quotes, Fresh Execution

**What:** BasketQuote is frozen at detection time. Execution does not recompute pricing. If the market has moved, FAK orders naturally fail (unfilled remainder is cancelled).

**Why:** Re-checking prices between detection and execution introduces a TOCTOU race. If we re-check and find the price has moved 0.1%, do we still execute? At what threshold do we abort? These decisions add complexity without value because FAK orders are inherently safe -- they fill at the specified price or not at all.

```python
# Good: trust the quote, let FAK handle staleness
basket = build_basket(group, cache, config)
if basket.is_profitable:
    results = await execute_basket(client, opp, config, risk_gate)
    # FAK fills what it can, cancels the rest

# Bad: re-check everything before execution
basket = build_basket(group, cache, config)
if basket.is_profitable:
    fresh_books = await fetch_books(...)
    fresh_basket = rebuild_basket(fresh_books)
    if fresh_basket.is_profitable:  # TOCTOU: might change again by execution time
        results = await execute_basket(...)
```

**Exception:** The `basket_use_fresh_books` config option allows re-validation with fresh order books before execution. This is opt-in, not default, and is useful for high-value baskets where the extra latency is worth the precision.

### Pattern 3: Structural Validation Over Heuristic Scoring

**What:** V2 validates structural properties (partition completeness, liquidity thresholds) rather than scoring text similarity.

**Why:** The V1 dependency scorer (5-signal weighted) is fundamentally a heuristic that can be fooled by unusual question phrasing. Structural checks are binary (the group has all event markets or it doesn't) and cannot produce false positives from text ambiguity.

```python
# Good: structural check
if len(group) == event_market_counts[event_id]:
    # This is a complete partition -- all outcomes are present
    pass

# Bad: heuristic scoring
score = jaccard(q_a, q_b) * 0.2 + temporal(q_a, q_b) * 0.3 + ...
if score < 0.3:
    # "Independent" -- but what if the questions are phrased unusually?
    pass
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Per-Leg Profitability Checks

**What:** Evaluating whether individual legs are "good" or "bad" before building the basket.

**Why bad:** A leg with ask=$0.95 looks expensive, but if it's the only leg in a 10-way group, the total is $0.95 + 9*$0.01 = $1.04 (not profitable). Conversely, a $0.50 leg looks neutral, but in a 2-way group totaling $0.96, it is highly profitable. Per-leg evaluation is misleading.

### Anti-Pattern 2: Recomputing VWAP in Execution

**What:** The execution engine fetching order books and running VWAP again after the basket pipeline already computed it.

**Why bad:** Double work, introduces inconsistency (detection says profitable, execution disagrees), and adds latency. The basket quote already contains the VWAP cost. Execution should trust it and let FAK orders handle price movement.

### Anti-Pattern 3: Sequential Leg Execution with Hedge

**What:** Executing legs one at a time and selling all filled legs at $0.01 if any leg fails.

**Why bad:** Fire-sale at $0.01 crystallizes a near-total loss. With batch order placement, all legs can be submitted simultaneously. Unfilled legs are simply not filled (FAK cancels). Filled legs retain their expected value -- holding is almost always better than selling at $0.01.

### Anti-Pattern 4: Using dependency.py Scores as a Gate

**What:** Running the 5-signal dependency scorer on V2 groups to "double-check" the partition validation.

**Why bad:** Partition validation is strictly more correct. If a group passes partition validation (all event markets present, correct count), the dependency scorer adds nothing except false-positive risk from text heuristics. Running both wastes CPU and creates confusion about which result to trust when they disagree.

---

## Scalability Considerations

| Concern | V1.2 (current) | V2 (target) | Mitigation |
|---------|----------------|-------------|------------|
| Detection false positives | ~10% (after v1.2 filters) | ~1% (partition + liquidity) | Structural validation eliminates text-heuristic false positives |
| VWAP accuracy in detection | None (best-ask only) | VWAP at target size | Single-level cache VWAP in v2.0; multi-level when price cache is enhanced |
| Order book fetches in hot path | 0 (detection), N (execution) | 0-1 per group (optional batch) | `/books` batch endpoint reduces N calls to 1 |
| Execution latency | Sequential (N legs * 2 calls each) | Parallel (1 batch POST) | `/orders` endpoint, max 15 legs per request |
| Hedge losses | $0.01 fire-sale = ~99% loss on filled legs | Hold positions (expected value = current price) | Abort-early, no fire-sale |
| Config complexity | 30+ fields | 38+ fields (+8 basket config) | All new fields have sensible defaults |

---

## PriceCache Limitation and Future Enhancement

**Current:** PriceCache stores single-level price data (best_ask, best_bid, depth_at_best). VWAP at any size > depth_at_best degrades to the fallback price of 1.0.

**V2 impact:** Single-level VWAP is a reasonable approximation for small trade sizes (under $50, which is the default kelly_max_capital_pct * total_capital_usd = 0.05 * $1000 = $50). For most legs with depth > $50, single-level VWAP equals best_ask.

**Future enhancement (not V2 scope):** Store top-5 or top-10 ask levels per token in PriceCache. The WebSocket `book` event already sends the full ask array -- currently only the best ask is extracted. Storing all levels enables true multi-level VWAP without additional API calls. This is a scanner-layer change (ws_client.py, normalizer.py, price_cache.py) and is independent of the basket pipeline.

---

## Critical Integration Points

### 1. Gamma API Startup: Event Market Counts

`load_event_groups()` in `cross_market.py` currently builds `_event_groups: dict[str, str]` (condition_id -> event_id). V2 also needs `_event_market_counts: dict[str, int]` (event_id -> number of markets in that event). This is computed from the same Gamma API response -- no additional API call needed.

```python
# In load_event_groups(), add:
_event_market_counts: dict[str, int] = {}

for event in events:
    event_id = str(event.get("id", ""))
    markets = event.get("markets", [])
    _event_market_counts[event_id] = len(markets)
```

### 2. simulate_vwap() Location

Currently lives in `execution/engine.py`. V2's `basket.py` needs it. Options:
- **(A) Import from engine.py** -- current approach, works but couples detection to execution
- **(B) Extract to shared utility** -- e.g., `detection/vwap.py` or `shared/math.py`
- **(C) Duplicate in basket.py** -- no coupling but violates DRY

**Recommendation: (B)** Extract `simulate_vwap()` to a new `detection/vwap.py` (or keep in engine.py and import). The function is pure (list + float -> float) with zero side effects. Extracting it eliminates the detection -> execution import that currently exists in `paper/simulator.py`.

### 3. DedupTracker Retention

`DedupTracker` from `filters.py` is still useful in V2 to prevent re-detecting the same basket opportunity within a time window. Keep it, but key on event_id instead of market_id + opportunity_type.

### 4. FilterDiagnostics Evolution

The current `FilterDiagnostics` tracks per-cycle rejection counts (ask_floor_rejects, dep_rejects, etc.). V2 needs updated counters:

```python
@dataclass
class BasketDiagnostics:
    groups_found: int = 0           # Stage 1 output
    partition_rejects: int = 0      # Stage 2 rejects
    liquidity_rejects: int = 0     # Stage 3 rejects
    basket_build_failures: int = 0  # Stage 4 failures
    profitability_rejects: int = 0  # Stage 5 rejects
    opportunities_emitted: int = 0  # passed all stages
    dedup_suppressed: int = 0       # suppressed by DedupTracker
```

---

## Sources

- Existing codebase: all `src/bot/` modules read directly (full source reviewed)
- Polymarket CLOB API order book endpoint: [docs.polymarket.com](https://docs.polymarket.com) -- single-level summary, no depth parameter (HIGH confidence)
- Batch order books (`POST /books`): [docs.polymarket.com](https://docs.polymarket.com/api-reference/market-data/get-order-books-request-body.md) -- returns array of OrderBookSummary (HIGH confidence)
- Batch order placement (`POST /orders`): [docs.polymarket.com](https://docs.polymarket.com/api-reference/trade/post-multiple-orders.md) -- max 15 orders/request (HIGH confidence)
- Rate limits: [docs.polymarket.com](https://docs.polymarket.com/api-reference/rate-limits.md) -- /orders: 1,000 req/10s burst (HIGH confidence)
- Order types: [docs.polymarket.com](https://docs.polymarket.com/trading/orders/overview.md) -- FAK supported in batch, post-only restricted to GTC/GTD (HIGH confidence)
- Gamma API event structure: confirmed in v1.1 (MEMORY.md, production-validated)
- VWAP simulation: existing `engine.simulate_vwap()` (v1.0, production-validated)
- Kelly sizing: existing `kelly.kelly_size()` (v1.0, production-validated)
