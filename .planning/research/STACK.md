# Technology Stack: v2.0 Basket Arbitrage Engine

**Project:** Polymarket Arbitrage Bot
**Milestone:** v2.0 -- Basket Arbitrage Engine
**Researched:** 2026-04-26
**Scope:** Stack additions/changes for (1) basket VWAP construction, (2) common-size optimization, (3) group structure validation, (4) parallel/batched order execution
**Confidence:** HIGH

## Executive Assessment

**No new pip dependencies required.** All four features can be built with the existing stack (Python 3.12, py-clob-client 0.34.6, httpx, asyncio, SQLite, loguru) plus stdlib modules already in use. This is the same outcome as v1.2 -- zero dependency risk, zero version conflicts, zero Docker image bloat.

The critical discovery is that **py-clob-client 0.34.6 already ships batch methods** that the codebase has never used:

- `client.post_orders(args: list[PostOrdersArgs])` -- submit up to 15 FAK orders in a single HTTP call
- `client.get_order_books(params: list[BookParams])` -- fetch order books for all basket legs in one call

These existing SDK methods eliminate the need for custom HTTP batching or third-party libraries. The v2.0 engine should replace serial `get_order_book()` and `place_fak_order()` calls with batch equivalents.

Python 3.12's `asyncio.gather()` (with `return_exceptions=True`) provides parallel leg signing before batch submission. No new concurrency library needed.

## Recommended Stack (Unchanged from v1.2 -- additions are SDK method usage, not new packages)

### Core -- No Changes

| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| Python | 3.12 | Runtime | KEEP -- `asyncio.gather()` for parallel signing, `itertools.combinations()` for subset detection |
| py-clob-client | 0.34.6 | Polymarket CLOB API | KEEP -- **use existing `post_orders()` and `get_order_books()` batch methods** |
| httpx | 0.28.1 | HTTP requests | KEEP -- `load_event_groups()` for Gamma API |
| websockets | 16.0 | Real-time market data | KEEP -- no changes |
| loguru | 0.7.3 | Logging | KEEP -- no changes |
| SQLite | 3.40+ (bundled) | Persistence | KEEP -- no schema changes needed for basket detection |
| FastAPI | 0.135.3 | Dashboard | KEEP -- no changes |
| python-telegram-bot | 22.7 | Alerts | KEEP -- no changes |
| pytest | 8.3.4 | Tests | KEEP -- no changes |
| pytest-asyncio | 0.25.0 | Async tests | KEEP -- no changes |
| python-dotenv | 1.2.2 | Env vars | KEEP -- no changes |

### SDK Methods to Start Using (already installed, never called)

| Method | Location | Purpose | Current Usage |
|--------|----------|---------|---------------|
| `client.post_orders()` | `py_clob_client.client` | Batch-submit up to 15 signed orders in one HTTP call | **NEVER USED** -- current code calls `client.post_order()` serially per leg |
| `client.get_order_books()` | `py_clob_client.client` | Batch-fetch order books for all legs in one HTTP call | **NEVER USED** -- current code calls `client.get_order_book()` serially per leg |
| `PostOrdersArgs` | `py_clob_client.clob_types` | Dataclass wrapping signed order + order type for batch submission | **NEVER IMPORTED** |
| `BookParams` | `py_clob_client.clob_types` | Dataclass wrapping token_id for batch book fetch | **NEVER IMPORTED** |

### Stdlib Modules Used (No pip install)

| Module | Purpose | Feature |
|--------|---------|---------|
| `asyncio.gather` | Parallel order signing (CPU-bound EIP-712 signing in executor threads) | Parallel execution |
| `itertools.combinations` | Pairwise subset/duplicate detection in group validation | Group structure validation (already imported in cross_market.py) |
| `math` | VWAP arithmetic, sum comparisons | Basket VWAP construction (already imported) |
| `dataclasses` | Basket opportunity dataclass, leg result dataclass | All features (already imported) |
| `collections.defaultdict` | Group-by-event mapping | Already imported in cross_market.py |

## Feature-by-Feature Stack Analysis

### Feature 1: Basket VWAP Construction

**Stack impact: ZERO new dependencies.** Uses existing `simulate_vwap()` + new batch book fetch.

**What exists and changes:**
- `simulate_vwap()` in `execution/engine.py` -- already accepts ask lists and target_size_usd. Reusable as-is per leg.
- `client.get_order_book()` -- currently called once per leg serially. Replace with `client.get_order_books()` to fetch all N legs in one HTTP round-trip.
- `PriceCache` -- currently stores single-level depth. For VWAP accuracy, the basket engine needs multi-level order book snapshots (top 5-10 levels from `get_order_books()` response).

**Key change: VWAP moves from execution to detection.** Currently, `detect_cross_market_opportunities()` uses cached `price.yes_ask` (single best ask) for spread calculation. The v2.0 basket engine should call `client.get_order_books()` to get full depth before computing VWAP-adjusted spread. This is the "multi-level VWAP in detection" improvement listed in STRATEGY.md.

**Integration:**
```python
from py_clob_client.clob_types import BookParams

# Fetch all leg order books in one batch call
params = [BookParams(token_id=leg["token_id"]) for leg in legs]
books = await loop.run_in_executor(None, client.get_order_books, params)

# Compute per-leg VWAP against full depth
for book in books:
    asks = sorted(book.asks, key=lambda a: float(a.price))  # ascending
    vwap = simulate_vwap(asks, target_size_per_leg)
```

**Why no library needed:** `simulate_vwap()` is a 25-line pure function that walks ask levels. The order book data comes from py-clob-client. No numerical library (numpy, scipy) is needed for weighted average arithmetic.

**Rate limit safety:** Batch book fetch via `POST /books` has a 500 req/10s limit. Each batch call fetches N books (one per leg). A 5-leg basket = 1 request instead of 5. At 30s scan intervals, this is well within limits.

### Feature 2: Common-Size Trade Optimization

**Stack impact: ZERO new dependencies.** Pure arithmetic on VWAP results.

**What changes:**
- After computing per-leg VWAP, determine the maximum shares fillable across ALL legs simultaneously at their VWAP costs.
- Current code: `target_shares = kelly_usd / total_yes` where `total_yes` = sum of best asks. This uses quoted ask prices, not VWAP costs.
- New code: `target_shares = kelly_usd / sum(vwap_per_leg)` where each `vwap_per_leg` is the VWAP cost for `target_shares` tokens from that leg's order book.

**The circular dependency problem:** VWAP depends on target size, but target size depends on VWAP. Resolution: iterate.

```python
# Iterative common-size solver (stdlib only)
target = kelly_usd / sum(best_asks)  # initial estimate
for _ in range(3):  # converges in 2-3 iterations
    vwaps = [simulate_vwap(asks[i], target * asks[i][0].price) for i in range(n)]
    total_cost = sum(v * target for v in vwaps)
    if total_cost <= 0:
        break
    target = kelly_usd / sum(vwaps)
```

**Why not scipy.optimize:** The VWAP function is piecewise-linear (stepping through discrete order book levels). A 3-iteration fixed-point loop converges for any realistic order book. scipy.optimize.minimize would be heavier, import a 30MB library, and solve the same problem less transparently.

**Why not numpy:** The arithmetic is `sum()`, `min()`, and `*` over lists of 2-20 floats. Python builtins handle this without measurable performance difference.

### Feature 3: Group Structure Validation (Duplicate/Subset Detection)

**Stack impact: ZERO new dependencies.** Uses `itertools.combinations` (already imported in cross_market.py) and existing `_preprocess()` from dependency.py.

**What changes:**
- Current: pairwise `classify_pair()` with 5-signal scorer to detect dependent pairs within an event group. This is O(n^2) in group size and designed for rejecting non-independent pairs.
- New: group-level partition check. Verify that the group's markets form a valid one-of-N partition (exactly one must resolve YES). This replaces pairwise dependency rejection with a structural validation.

**Duplicate detection (markets covering the same outcome):**
- Two markets in the same event asking "Will Trump win?" with different condition IDs = duplicates
- Detection: high Jaccard similarity (>0.9) on preprocessed question tokens using existing `_preprocess()` from `dependency.py`
- Implementation: `itertools.combinations(group, 2)` to check all pairs (already used in cross_market.py)

**Subset detection (market A implies market B):**
- "Will Bitcoin reach $100k by June?" is a subset of "Will Bitcoin reach $100k by December?"
- Detection: reuse existing `_keyword_implication()` and `_time_relation()` from `dependency.py`

**Why not NLP/ML:** Polymarket questions are short, structured strings. `difflib.SequenceMatcher` and token set comparison (already in the codebase) handle 95%+ of cases. The dependency.py module already has all 5 signals needed.

**Key architectural change:** Instead of pairwise rejection (O(n^2) classify_pair calls per group), the new validator should:
1. Check for duplicates (Jaccard > 0.9) -- reject group or deduplicate
2. Check for subsets (implication + temporal signals) -- reject group
3. If clean, proceed to basket pricing

This is a simplification, not an addition. The 5-signal weighted scorer remains, but its usage shifts from "reject non-independent pairs" to "validate partition structure."

### Feature 4: Parallel/Batched Order Execution

**Stack impact: ZERO new dependencies.** Uses `asyncio.gather()` (stdlib) + `client.post_orders()` (already in py-clob-client).

**Current execution flow (serial, O(n) round-trips):**
```
for leg in legs:
    signed = await run_in_executor(client.create_order, args)  # EIP-712 sign
    result = await run_in_executor(client.post_order, signed)  # HTTP POST
    # verify fill...
```

**New execution flow (parallel sign, batch submit, 2 round-trips total):**
```
# Step 1: Sign all orders in parallel (CPU-bound, use executor pool)
sign_tasks = [
    loop.run_in_executor(None, client.create_order, leg_args)
    for leg_args in all_leg_args
]
signed_orders = await asyncio.gather(*sign_tasks, return_exceptions=True)

# Step 2: Batch submit all signed orders in one HTTP call
batch_args = [
    PostOrdersArgs(order=signed, orderType=OrderType.FAK)
    for signed in signed_orders
    if not isinstance(signed, Exception)
]
results = await loop.run_in_executor(None, client.post_orders, batch_args)
```

**Why `asyncio.gather()` not `asyncio.TaskGroup`:**
- `TaskGroup` (Python 3.11+) cancels all tasks on first exception. For order signing, we want partial results -- if 1 of 5 signatures fails, we should still submit the other 4 (or abort cleanly).
- `gather(return_exceptions=True)` returns exceptions as values in the result list, allowing the caller to decide what to do (submit partial basket or abort entirely).
- `TaskGroup` would cancel healthy signing operations when one fails, which is more aggressive than desired.

**Batch API constraints (verified from docs.polymarket.com):**
- `POST /orders` accepts up to **15 orders per request** (sufficient for any Polymarket event group, max 20 legs)
- Orders are processed **in parallel** server-side
- Response is an array of per-order results with `success: bool` and `errorMsg`
- Partial failures are possible (some orders fill, others rejected)
- Rate limit: 1,000 req/10s burst, 15,000 req/10min sustained for batch endpoint

**Abort-early vs fire-sale hedge:**
- Current: if leg N fails, sell all filled legs at $0.01 (fire-sale hedge)
- New: if any leg in batch results has `success: false`, check if the failing legs make the basket unprofitable, and decide to abort (sell filled legs at market) or accept partial basket
- This is a logic change, not a stack change

**Why not aiohttp or httpx async:** py-clob-client uses synchronous httpx internally. The batch `post_orders()` method is one HTTP call, so async HTTP adds zero benefit. The parallelism comes from signing (CPU-bound, uses executor threads) and server-side parallel processing of the batch.

## What NOT to Add

| Library | Why Not | Use Instead |
|---------|---------|-------------|
| numpy | VWAP is `sum(price * size) / sum(size)` over 2-20 floats. Python builtins are sufficient and add zero import overhead. | `sum()`, list comprehensions |
| scipy | No optimization problem to solve. VWAP iteration converges in 3 loops. | 3-iteration fixed-point loop |
| pandas | No dataframe operations needed. Basket pricing is per-opportunity, not bulk analysis. | Direct arithmetic on leg lists |
| redis | No cross-process caching needed. Single bot process with in-memory event groups dict. | Module-level dict (existing pattern) |
| celery / dramatiq | No task queue needed. Batch order submission is a single HTTP call, not a distributed job. | `asyncio.gather()` + `post_orders()` |
| aiohttp | py-clob-client is sync internally. Wrapping sync calls in executor is cleaner than replacing the HTTP layer. | `asyncio.run_in_executor()` (existing pattern) |
| rapidfuzz / thefuzz | Duplicate detection needs Jaccard on tokenized sets, not fuzzy string matching. `_preprocess()` + set operations are more correct. | `_preprocess()` + `frozenset` ops (existing in dependency.py) |

## Config Additions

New fields for `BotConfig` dataclass (all with sensible defaults):

```python
# Basket VWAP construction
basket_vwap_iterations: int = 3           # Fixed-point VWAP/size convergence iterations
basket_min_leg_depth_usd: float = 20.0    # Skip basket if any leg has < $20 ask depth

# Common-size optimization
basket_max_depth_fraction: float = 0.5    # Never take > 50% of any leg's depth

# Group structure validation
basket_duplicate_jaccard_threshold: float = 0.90  # Flag as duplicate if Jaccard > 0.90
basket_max_group_size: int = 20           # Existing _MAX_GROUP_SIZE, now configurable
basket_min_group_size: int = 2            # Existing _MIN_GROUP_SIZE, now configurable

# Parallel execution
basket_batch_enabled: bool = True         # Use post_orders() batch endpoint
basket_abort_on_partial: bool = True      # Abort basket if any leg fails in batch
```

## Installation

**No changes to requirements.txt.** The existing pinned dependencies are sufficient:

```
py-clob-client==0.34.6
httpx[http2]==0.28.1
websockets==16.0
loguru==0.7.3
python-dotenv==1.2.2
pytest==8.3.4
pytest-asyncio==0.25.0
fastapi==0.135.3
uvicorn==0.44.0
python-telegram-bot==22.7
```

No Docker image rebuild needed for dependency changes. Only code changes trigger rebuild.

## New py-clob-client Imports (add to relevant modules)

```python
# In basket execution module (new or modified engine.py):
from py_clob_client.clob_types import BookParams, PostOrdersArgs, OrderType

# Usage:
# Batch book fetch
params = [BookParams(token_id=tid) for tid in token_ids]
books = client.get_order_books(params)

# Batch order submission
batch = [PostOrdersArgs(order=signed, orderType=OrderType.FAK) for signed in signed_orders]
results = client.post_orders(batch)
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Parallel signing | `asyncio.gather(return_exceptions=True)` | `asyncio.TaskGroup` | TaskGroup cancels all tasks on first exception; we want partial results for abort decisions |
| Batch orders | `client.post_orders()` (SDK built-in) | Custom HTTP to `POST /orders` | SDK already handles auth headers, serialization, signing; reimplementing adds zero value |
| Batch books | `client.get_order_books()` (SDK built-in) | Serial `get_order_book()` per leg | Serial = N round-trips; batch = 1 round-trip. Latency matters for arb. |
| VWAP iteration | 3-iteration fixed-point loop | scipy.optimize.minimize | Piecewise-linear VWAP function converges trivially; scipy adds 30MB dependency |
| Duplicate detection | Jaccard on preprocessed tokens | sentence-transformers / LLM | Polymarket questions are short templates; NLP embeddings are overkill. OUT OF SCOPE per PROJECT.md. |

## Architecture Integration Map

```
Basket Detection (Feature 1 + 2 + 3):

  event_groups --> [group_by_event] --> [validate_partition]  --> [batch_fetch_books] --> [basket_vwap] --> [common_size] --> basket_opps
                   EXISTING              NEW (stdlib)            NEW (SDK batch)          REUSE+extend     NEW (arithmetic)

Basket Execution (Feature 4):

  basket_opp --> [parallel_sign] --> [batch_submit] --> [verify_results] --> [abort_or_accept]
                 asyncio.gather      post_orders()      per-result check     NEW logic
                 + run_in_executor   SDK built-in       (existing pattern)
```

## Key py-clob-client API Details (verified from source code inspection)

### `post_orders()` Signature
```python
def post_orders(self, args: list[PostOrdersArgs]) -> list[dict]:
    """
    Posts multiple orders. Max 15 per request.
    Each PostOrdersArgs has: order (SignedOrder), orderType (OrderType), postOnly (bool).
    Returns list of dicts with: success, orderID, status, errorMsg.
    """
```

### `get_order_books()` Signature
```python
def get_order_books(self, params: list[BookParams]) -> list[OrderBookSummary]:
    """
    Fetches order books for multiple tokens in one POST /books call.
    Each BookParams has: token_id (str), side (str, optional).
    Returns list of OrderBookSummary with: asks, bids, tick_size, neg_risk, etc.
    """
```

### `PostOrdersArgs` Dataclass
```python
@dataclass
class PostOrdersArgs:
    order: SignedOrder       # from client.create_order()
    orderType: OrderType     # FAK for arb
    postOnly: bool = False   # never True for FAK
```

### `BookParams` Dataclass
```python
@dataclass
class BookParams:
    token_id: str
    side: str = ""           # empty = both sides returned
```

## Rate Limit Budget (verified from docs.polymarket.com)

| Operation | Endpoint | Limit | v2.0 Usage per Cycle |
|-----------|----------|-------|---------------------|
| Batch book fetch | `POST /books` | 500 req/10s | 1-5 calls (one per candidate basket group) |
| Batch order submit | `POST /orders` | 1,000 req/10s burst | 0-1 calls (only when executing) |
| Single order verify | `GET /order/:id` | 3,500 req/10s | N polls per leg (existing verify_fill_rest) |
| Gamma events | `GET /events` | 500 req/10s | 1 call at startup (existing) |

At 30s scan intervals with 5-10 candidate basket groups per cycle: ~10 batch book fetches = ~10 requests per 30s. Well within 500 req/10s limit.

## Confidence Assessment

| Component | Confidence | Reason |
|-----------|------------|--------|
| No new dependencies needed | HIGH | Thorough audit of all 4 features against existing codebase + SDK source code |
| `post_orders()` batch method | HIGH | Verified in py-clob-client 0.34.6 source code at line 592; uses `PostOrdersArgs` dataclass |
| `get_order_books()` batch method | HIGH | Verified in py-clob-client 0.34.6 source code at line 780; uses `BookParams` dataclass |
| `asyncio.gather(return_exceptions=True)` | HIGH | Python 3.12 stdlib; well-documented, battle-tested for parallel I/O |
| VWAP iteration convergence | MEDIUM | 3 iterations is sufficient for typical order books with 5-10 price levels; may need 4-5 for very sparse books |
| Batch order partial failure handling | MEDIUM | API returns per-order success/failure, but real-world behavior (atomicity, timing) needs live testing |
| Rate limit headroom | HIGH | Verified limits from docs.polymarket.com; batch calls reduce total request count vs serial |

## Risk: Batch Order Atomicity

The `POST /orders` batch endpoint processes orders "in parallel" but does NOT guarantee atomicity. In a 5-leg basket:
- Leg 1, 2, 3 may fill
- Leg 4 may be rejected ("insufficient liquidity")
- Leg 5 may fill

This leaves a partial basket (4 of 5 legs filled) which is NOT arbitrage -- it is directional exposure. The execution engine MUST handle partial batch results by unwinding filled legs if the basket is incomplete.

**Mitigation:** Check all result entries for `success: true` before considering the basket filled. If any leg fails, immediately submit hedge orders for all filled legs. This is the same retry-then-hedge pattern from v1.0 but applied to batch results.

## Risk: Order Book Staleness Between Fetch and Submit

Batch order book fetch gives a snapshot. By the time orders are signed and submitted (100-500ms later), prices may have moved. For cross-market arb with thin spreads (1-3%), even 0.5% price movement can eliminate profitability.

**Mitigation:** Compute VWAP with a slippage buffer (e.g., 0.5%) subtracted from the expected spread. Only proceed if `basket_spread - slippage_buffer > fee_threshold`. This is a config parameter, not a library.

## Sources

- py-clob-client 0.34.6 source code: `/Users/aciarallo001/.pyenv/versions/3.10.10/lib/python3.10/site-packages/py_clob_client/client.py` (lines 592, 780)
- py-clob-client types: `/Users/aciarallo001/.pyenv/versions/3.10.10/lib/python3.10/site-packages/py_clob_client/clob_types.py` (PostOrdersArgs line 254, BookParams line 40)
- Polymarket API docs: [Post Multiple Orders](https://docs.polymarket.com/api-reference/trade/post-multiple-orders) -- max 15 orders, parallel processing
- Polymarket API docs: [Get Order Books](https://docs.polymarket.com/api-reference/market-data/get-order-books-request-body) -- batch order book fetch
- Polymarket API docs: [Rate Limits](https://docs.polymarket.com/api-reference/rate-limits) -- CLOB batch endpoint limits
- Polymarket API docs: [Order Creation](https://docs.polymarket.com/trading/orders/create) -- `post_orders()` SDK usage
- Python 3.12 docs: [asyncio.gather](https://docs.python.org/3/library/asyncio-task.html) -- return_exceptions parameter
- Existing codebase: `src/bot/execution/engine.py`, `src/bot/execution/order_client.py`, `src/bot/detection/cross_market.py`, `src/bot/detection/dependency.py`

---
*Stack research for: v2.0 Basket Arbitrage Engine*
*Researched: 2026-04-26*
