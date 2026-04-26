# Feature Research: v2.0 Basket Arbitrage Engine

**Domain:** Prediction market cross-market basket arbitrage
**Researched:** 2026-04-26
**Confidence:** HIGH (codebase-verified, API docs confirmed)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that the basket arbitrage engine **must** have. Without these, the rewrite is incomplete and the bot cannot trade cross-market arb profitably.

| Feature | Why Expected | Complexity | Dependencies on Existing |
|---------|--------------|------------|--------------------------|
| **Group structure validation (one-of-N partition check)** | Current pairwise dependency detection (O(n^2) `classify_pair` calls per group) is fundamentally wrong for group-level validation. A 5-market election group runs 10 pair comparisons, any of which can falsely flag "related" and reject the entire group. Basket arb requires validating that a group forms a proper one-of-N partition: exactly one outcome resolves YES, the rest resolve NO. This is the group-level structure check, not a pairwise similarity heuristic. | MEDIUM | Replaces `detection/dependency.py` pairwise flow in `cross_market.py` (lines 218-257). Consumes `_event_groups` cache (Gamma API). Reads `negRisk` boolean from Gamma event data (already fetched in `load_event_groups()`). |
| **VWAP-based basket cost computation** | Current detection uses quoted `best_ask` per leg for `total_yes = sum(yes_asks)`. But best_ask is the price for 1 share -- at any meaningful size, you walk the book and pay more. The basket cost must be the aggregate VWAP cost of buying N shares across all legs simultaneously. Without this, every detected opportunity overstates profitability. | MEDIUM | Reuses `engine.simulate_vwap()` (pure function). Requires order book depth data per leg -- currently only `yes_ask` and `yes_depth` (single level) are cached in `PriceCache`. Needs either multi-level cache or fresh `get_order_books()` batch fetch. |
| **Common-size trade sizing** | Current cross-market execution uses `target_shares = kelly_usd / total_yes` uniformly. But VWAP fill price differs per leg, and some legs have less depth. The common size must be the maximum number of shares fillable across ALL legs at VWAP prices without exceeding any leg's available depth. The weakest leg determines the basket size. | MEDIUM | Depends on VWAP basket cost (needs per-leg VWAP first). Replaces the sizing logic in `_execute_cross_market()` (engine.py lines 138-140). Also replaces sizing in `simulate_cross_market()` (paper/simulator.py lines 214-215). |
| **Profitability gate with fees + slippage buffer** | Current detection computes `net_spread = gross_spread - estimated_fees` using quoted asks. After VWAP-based basket cost, the profitability gate must use VWAP-adjusted basket cost, real fee rates, AND a configurable slippage buffer (additional safety margin beyond VWAP). Without this buffer, VWAP inaccuracy from stale cache data will cause unprofitable trades. | LOW | Modifies `cross_market.py` detection logic (lines 265-280). Adds one config field (`slippage_buffer_pct`). Pure arithmetic on top of VWAP basket output. |
| **Liquidity-driven filtering (replace dead-leg heuristics)** | Current `DETECT-03` (`has_dead_leg`) checks if any leg's ask price is below a floor ($0.005). This is a price heuristic. True liquidity filtering checks: (a) depth >= minimum fill size at each leg, (b) bid-ask spread per leg is below a max threshold, (c) last update timestamp is fresh. Dead-leg price floors conflate "cheap" with "illiquid." | MEDIUM | Replaces `has_dead_leg()` in `filters.py` and its call in `cross_market.py` (lines 200-206). Needs bid data from cache or order book (currently only asks cached). Adds config fields for `min_leg_depth_usd`, `max_leg_spread`, `max_leg_stale_seconds`. |
| **Remove YES/NO arb path from detection loop** | PROJECT.md states "YES/NO arb removed -- cross-market basket arb only." v1.0-v1.2 ran both `detect_yes_no_opportunities()` and `detect_cross_market_opportunities()` every cycle. Market is efficient for YES/NO (0 detected in 15+ days of dry-run). Removing it simplifies the hot path and eliminates dead code. | LOW | Delete call to `detect_yes_no_opportunities()` in `dry_run.py` (line 118) and `live_run.py`. Keep module for reference but remove from scan loop. Remove `simulate_yes_no()` call in dry_run.py (line 128). |
| **Batch order book fetching (pre-execution)** | Current execution fetches order books one at a time via `client.get_order_book(token_id)`. For a 5-leg basket, that is 5 sequential HTTP calls. The SDK provides `client.get_order_books(params: list[BookParams])` which fetches multiple books in a single POST request. This reduces pre-execution latency from 5*RTT to 1*RTT. | LOW | `py_clob_client.client.get_order_books()` already exists (verified in SDK v0.34.6). Takes `list[BookParams]` where `BookParams(token_id=str)`. Returns `list[OrderBookSummary]`. Replace sequential `get_order_book()` calls in engine.py. CLOB rate limit for `/books`: 500 req/10s (verified from docs). |

### Differentiators (Competitive Advantage)

Features that go beyond table stakes and meaningfully improve execution quality or profitability.

| Feature | Value Proposition | Complexity | Dependencies on Existing |
|---------|-------------------|------------|--------------------------|
| **Batch order submission (parallel legs)** | Polymarket's `POST /orders` endpoint (verified in docs) accepts up to 15 orders per request, processed in parallel. Instead of placing N legs sequentially (each waiting for the previous to fill), submit all leg orders in a single batch. Reduces total execution time from N*RTT to 1*RTT, dramatically shrinking the window where partial fills create exposure. SDK method: `client.post_orders(args: list[PostOrdersArgs])`. | MEDIUM | Requires creating N `SignedOrder` objects via `client.create_order()` (still sequential, local signing only), then posting all via `client.post_orders()`. Response includes per-order success/failure for partial failure handling. Replaces sequential loop in `_execute_cross_market()`. |
| **Abort-early instead of fire-sale hedge** | Current hedge strategy: if leg N fails, sell ALL filled legs at $0.01 (fire-sale). This guarantees massive loss on partial execution. Better strategy: if a non-critical leg fails, evaluate whether the remaining filled legs + unfilled legs still form a profitable partial basket, OR cancel unfilled GTC legs before they match. With FAK orders this is moot (they auto-cancel), but with batch submission, some orders may not have matched yet. Abort-early = don't sell filled legs unless net exposure exceeds a loss threshold. | HIGH | Depends on batch order submission (needs per-order status from batch response). Requires computing partial basket P&L: "if only legs {1,2,4} of {1,2,3,4,5} filled, what is worst-case loss?" This is the partial basket coverage calculation. |
| **Multi-level order book caching** | Current `PriceCache` stores only `yes_ask` + `yes_depth` (single best level). With multi-level caching (top 5-10 levels of asks per token), VWAP basket cost can be computed from cache without fetching fresh order books. Reduces detection-to-execution latency and API call volume. | MEDIUM | Modifies `PriceCache` data structure (new `MarketPrice` fields for ask levels array). Modifies `normalizer.py` and `ws_client.py` to populate multiple levels. WebSocket `market` channel already delivers full book updates (sells array), just currently only using first level. |
| **Event metadata cache for structure validation** | Gamma API returns `negRisk` boolean and market count per event. Caching this at startup (alongside `_event_groups`) enables structure validation without additional API calls: if `negRisk=True`, the exchange guarantees one-of-N structure. If `negRisk=False`, apply heuristic validation. | LOW | Extends `load_event_groups()` in `cross_market.py` to also store `{event_id: {neg_risk: bool, market_count: int, title: str}}`. Pure extension of existing startup fetch. |
| **Execution timing optimization (parallel create + batch post)** | Order creation (`create_order`) involves local EIP-712 signing -- no network call. All N orders can be created concurrently using `asyncio.gather()` with `run_in_executor()`, then batch-posted. This parallelizes the CPU-bound signing step. | LOW | Depends on batch order submission. Pure optimization of the create step. `create_order` is thread-safe (no shared mutable state in py-clob-client builder). |
| **Configurable basket size limits** | Cap the maximum number of legs in a basket (e.g., max 8). Large baskets (15+ legs) have higher execution risk (more legs = more chance of partial fill) and lower profit per leg. Small baskets (2-4 legs) are easier to fill and more profitable per leg. | LOW | Replaces `_MAX_GROUP_SIZE = 20` constant in `cross_market.py` with `config.max_basket_legs`. Add to `BotConfig`. |
| **Basket opportunity ranking** | When multiple basket opportunities are detected in the same cycle, rank them by expected net profit (VWAP-adjusted) and execute highest-profit first. Current code processes groups in arbitrary iteration order. With limited capital, executing the best opportunity first maximizes returns. | LOW | Runs after detection, before execution. Sort `opportunities` list by `net_spread * common_size` descending. No new modules needed. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem valuable but create more problems than they solve at this stage.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Atomic multi-leg execution (all-or-nothing)** | Eliminates partial fill risk entirely. "Just make all legs fill or none fill." | Polymarket CLOB has NO atomic multi-order guarantee. `POST /orders` processes orders in parallel but each matches independently. Even the on-chain CTF contracts settle per-order, not per-basket. Attempting atomicity would require a custom smart contract (out of scope, massive complexity). | Use batch `POST /orders` for speed + abort-early evaluation for partial fills. Accept that partial fills are inherent to multi-leg CLOB execution. |
| **GTC orders for basket legs** | "Use limit orders so legs fill over time, capturing better prices." | GTC basket legs create naked directional exposure. If leg 1 fills at $0.30 and leg 2 sits unfilled for 10 minutes, you hold unhedged YES tokens that could resolve to $0 at any time. The arb opportunity is time-sensitive -- if it exists, FAK captures it now or not at all. | Keep FAK-only for all basket legs. The arb spread is the edge; waiting for better prices on individual legs means the spread has already closed. |
| **LLM/AI mutual exclusivity validation** | "Use GPT to check if market questions are truly mutually exclusive." | Adds 200-500ms latency per group (API call), cost per inference, and a new external dependency. Polymarket NegRisk events are already exchange-verified as one-of-N. Non-NegRisk events need heuristic validation, not AI. LLM errors (hallucination) create false confidence. | Use NegRisk boolean as primary signal (exchange guarantees structure). For non-NegRisk events, use probability sum validation (sum of midprices near 1.0) + event metadata. |
| **Dynamic Kelly recalculation per leg** | "Recalculate Kelly after each leg fills to account for updated capital." | In a basket arb, all legs must fill for the arb to be complete. Adjusting position size mid-execution means legs have different share counts, which breaks the equal-shares invariant (payout depends on which leg wins). The basket is sized once, then executed. | Size the basket once using common-size (weakest leg determines size). Execute all legs at that size. |
| **Real-time mark-to-market for open baskets** | "Show P&L of partially-filled baskets using current market prices." | Partially-filled baskets are failure states, not positions to monitor. The bot should unwind them immediately, not track their P&L. Adding mark-to-market infrastructure for a state that should last <1 second adds complexity for no benefit. | Log the partial fill event, execute the unwind strategy (abort-early or hedge), and move on. Post-mortem analysis uses trade logs, not real-time monitoring. |
| **Cross-exchange arbitrage (Polymarket vs Kalshi/Metaculus)** | "Bigger opportunity set by comparing prices across platforms." | Different settlement mechanics, different collateral (USDC.e vs USD), different fee structures, regulatory differences (Kalshi is CFTC-regulated). Implementation complexity is 10x a single-exchange bot. | Stay Polymarket-only. The opportunity set is large enough (44k+ markets). Cross-exchange is a separate product. |
| **Stochastic fill simulation in paper trading** | "Add random fill rejection to make paper trading more realistic." | Makes paper trade results non-deterministic, harder to compare across runs, and harder to debug. The purpose of paper trading is to establish an upper bound on strategy profitability. | Keep deterministic depth-gated fills. Document that real fills will be worse. Use the gap between paper P&L and live P&L (once live) as the real-world slippage measure. |

---

## Feature Dependencies

### Basket Detection Pipeline (order matters)

```
Event Grouping (existing: load_event_groups at startup)
    |
    v
Group Structure Validation (NEW: replaces pairwise dependency)
    |  NegRisk events: pass-through (exchange guarantees one-of-N)
    |  Non-NegRisk events: probability sum check + event metadata
    |  WHERE: detection/basket_validator.py (new module)
    v
Batch Order Book Fetch (NEW: get_order_books for all legs)
    |  Single POST for N books vs N sequential GETs
    |  WHERE: detection/basket_pricer.py or execution layer
    v
VWAP Basket Cost Computation (NEW: aggregate VWAP across all legs)
    |  basket_cost = sum(vwap_i * common_shares) for all legs
    |  WHERE: detection/basket_pricer.py (new module)
    v
Common-Size Computation (NEW: weakest leg determines size)
    |  common_shares = min(max_fillable_shares_i for all legs)
    |  WHERE: detection/basket_pricer.py
    v
Profitability Gate (MODIFIED: uses VWAP basket cost + slippage buffer)
    |  net_profit = $1.00 * common_shares - basket_cost - fees - slippage
    |  WHERE: cross_market.py (replaces current gross_spread logic)
    v
Liquidity Filter (NEW: replaces has_dead_leg price heuristic)
    |  Reject if any leg fails depth/spread/staleness checks
    |  WHERE: filters.py (new function, replaces has_dead_leg)
    v
Basket Opportunity (output: replaces current ArbitrageOpportunity)
```

### Basket Execution Pipeline (order matters)

```
Basket Opportunity detected
    |
    v
Common-Size verified against fresh order books (re-check)
    |  get_order_books() batch fetch for all legs
    |  Recompute VWAP at execution time (prices may have moved)
    v
Parallel Order Creation (asyncio.gather on create_order per leg)
    |  EIP-712 signing is CPU-bound, no network call
    v
Batch Order Submission (client.post_orders with all signed orders)
    |  Single POST to /orders endpoint, max 15 per request
    |  FAK order type -- each leg fills immediately or is killed
    v
Batch Response Parsing
    |  Per-order success/failure from response array
    v
Partial Fill Evaluation (abort-early logic)
    |  If all legs filled: basket complete, log profit
    |  If some legs failed: evaluate exposure, decide unwind strategy
    v
Unwind (if needed)
    |  Sell filled legs at market price (not $0.01 fire-sale)
    |  OR hold if partial basket is still profitable
```

### Module-Level Dependencies

```
config.py (new fields)
    |
    +-- detection/basket_validator.py (NEW)
    |     |  Consumes: _event_groups, event metadata cache
    |     |  Produces: validated group list with structure label
    |     v
    +-- detection/basket_pricer.py (NEW)
    |     |  Consumes: validated groups, order book data
    |     |  Produces: BasketOpportunity with VWAP cost, common size, net profit
    |     |  Imports: engine.simulate_vwap (pure function)
    |     v
    +-- detection/cross_market.py (MODIFIED)
    |     |  Orchestrates: validator -> pricer -> opportunity output
    |     |  Removes: pairwise dependency calls, quoted-price spread calc
    |     v
    +-- execution/engine.py (MODIFIED)
    |     |  Replaces: sequential _execute_cross_market with batch execution
    |     |  New: parallel create_order + batch post_orders
    |     |  New: abort-early partial fill evaluation
    |     v
    +-- execution/order_client.py (EXTENDED)
    |     |  New: place_fak_orders_batch() using client.post_orders()
    |     |  New: fetch_order_books_batch() using client.get_order_books()
    |     v
    +-- paper/simulator.py (MODIFIED)
    |     |  Replaces: simulate_cross_market with basket-aware simulation
    |     |  Uses: basket_pricer for VWAP cost, common-size logic
    |     v
    +-- detection/filters.py (MODIFIED)
          |  Replaces: has_dead_leg with check_leg_liquidity
          |  New: depth, spread, staleness checks per leg
```

### Dependency Notes

- **Group structure validation requires event metadata cache:** The validator needs the `negRisk` boolean per event to decide validation strategy. This must be cached during `load_event_groups()` at startup.
- **VWAP basket cost requires order book depth:** Single-level cache data produces inaccurate VWAP. Either multi-level caching (differentiator) or fresh batch fetch (table stakes) is needed.
- **Common-size requires VWAP per leg:** You cannot compute the weakest leg without knowing the VWAP fill curve for each leg at a candidate size.
- **Batch execution requires batch order creation:** All signed orders must be created before the single `post_orders()` call.
- **Abort-early conflicts with current fire-sale hedge:** These are mutually exclusive unwind strategies. Abort-early replaces fire-sale, not augments it.

---

## MVP Definition

### Must Ship (v2.0 Core)

In build-dependency order:

1. **Remove YES/NO arb from scan loop** -- Simplifies hot path, eliminates dead code. Zero risk (0 opportunities detected in 15+ days).

2. **Event metadata cache extension** -- Extend `load_event_groups()` to store `negRisk` boolean and market count per event. Foundation for structure validation. ~20 lines added to existing function.

3. **Group structure validation** -- Replace pairwise dependency detection with group-level one-of-N partition check. NegRisk events auto-pass; non-NegRisk events use probability sum validation. Eliminates the entire `classify_pair` O(n^2) loop from cross-market detection.

4. **Batch order book fetching** -- Use `client.get_order_books()` for multi-book fetch in a single call. Required by VWAP basket pricer and execution. Verified available in py-clob-client v0.34.6.

5. **VWAP basket cost computation** -- Compute aggregate VWAP cost across all legs for a given share count. This is the core of accurate basket pricing.

6. **Common-size trade sizing** -- Compute the maximum shares fillable across all legs. The weakest leg determines the basket size.

7. **Profitability gate with slippage buffer** -- Updated gate using VWAP basket cost + configurable slippage margin.

8. **Liquidity-driven filtering** -- Replace dead-leg price heuristics with depth/spread/staleness checks per leg.

### Should Ship (v2.0 Enhanced)

9. **Batch order submission** -- Use `client.post_orders()` for parallel leg execution. Reduces execution latency from N*RTT to 1*RTT. Verified available in SDK and API docs (max 15 orders/request, FAK supported).

10. **Basket opportunity ranking** -- Execute highest-profit basket first when multiple detected in same cycle.

11. **Configurable basket size limits** -- Replace magic constant with config field.

### Add After Validation (v2.x)

12. **Multi-level order book caching** -- Enables cache-only VWAP computation, eliminates pre-execution order book fetch. Meaningful latency improvement but requires PriceCache refactor.

13. **Abort-early partial fill evaluation** -- Smarter unwind than fire-sale hedge. Requires computing partial basket P&L, which is complex. Wait until batch execution is proven in production.

14. **Execution timing optimization (parallel create)** -- Parallelize EIP-712 signing via `asyncio.gather`. Minor latency improvement (signing is ~10ms per order). Low risk but low impact.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Group structure validation | HIGH | MEDIUM | P1 |
| VWAP basket cost computation | HIGH | MEDIUM | P1 |
| Common-size trade sizing | HIGH | MEDIUM | P1 |
| Profitability gate with slippage | HIGH | LOW | P1 |
| Batch order book fetching | HIGH | LOW | P1 |
| Remove YES/NO arb path | MEDIUM | LOW | P1 |
| Liquidity-driven filtering | MEDIUM | MEDIUM | P1 |
| Event metadata cache | MEDIUM | LOW | P1 |
| Batch order submission | HIGH | MEDIUM | P2 |
| Basket opportunity ranking | MEDIUM | LOW | P2 |
| Configurable basket size limits | LOW | LOW | P2 |
| Multi-level order book caching | MEDIUM | MEDIUM | P3 |
| Abort-early unwind | MEDIUM | HIGH | P3 |
| Parallel order creation | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for v2.0 launch -- without these, basket arb is not functional
- P2: Should have -- improves execution quality meaningfully
- P3: Nice to have -- defer until P1/P2 validated in production

---

## API Surface Verified for This Milestone

Critical API capabilities confirmed via Polymarket docs (2026-04-26):

| Capability | Endpoint | Verified | Notes |
|------------|----------|----------|-------|
| Batch order books | `POST /books` | YES (SDK: `client.get_order_books()`) | Takes `list[BookParams]`, returns `list[OrderBookSummary]`. No documented max batch size. Rate limit: 500 req/10s. |
| Batch order placement | `POST /orders` | YES (SDK: `client.post_orders()`) | Max 15 orders per request. Processed in parallel. FAK supported. Per-order success/failure in response. Rate limit: 1,000 req/10s burst. |
| NegRisk identification | Gamma API `negRisk` field | YES | Boolean on event object. True = exchange-guaranteed one-of-N structure. |
| Full order book depth | `GET /book?token_id=X` | YES | Returns all bids and asks (no documented depth limit). Asks sorted ascending by price. |
| Order type FAK | `POST /order` or `POST /orders` | YES (SDK: `OrderType.FAK`) | Fill-And-Kill. Matches what it can immediately, cancels remainder. |

---

## Competitor / Prior Art Analysis

| Approach | How Used in Practice | Applicability to Our Bot |
|----------|---------------------|--------------------------|
| **Portfolio-level Dutch auction** | Used in traditional equities for basket rebalancing. Submit the entire basket as a unit, let market makers fill. | Not applicable -- Polymarket has no portfolio-level order type. Must use per-leg orders. |
| **Statistical arb basket (pairs trading)** | Quant funds trade correlated asset baskets when co-integration deviates. Mean-reversion expectation. | Not applicable -- we trade deterministic arb (guaranteed profit if all legs fill), not statistical relationships. |
| **Sports betting arb (surebets)** | Bettors buy all outcomes across bookmakers when total odds < 1.0. Sequential execution, fastest finger wins. | Directly applicable -- same math (sum < 1.0 = guaranteed profit). Key lesson: execution speed is everything. Opportunities last seconds. Batch execution is the equivalent of "fastest finger." |
| **DeFi MEV basket arb** | Flashbots/MEV bots atomically execute multi-swap arb within a single block. Smart contract ensures all-or-nothing. | Partially applicable -- same idea (multi-leg deterministic arb), but we lack atomic execution on Polymarket CLOB. Takeaway: accept partial fill risk, focus on minimizing execution window. |
| **Options market multi-leg (spreads, straddles)** | Options exchanges offer native multi-leg order types (e.g., spread orders). | Not applicable -- Polymarket has no native multi-leg order type. But the risk decomposition is relevant: identify which partial fills create bounded vs unbounded loss. |

---

## Sources

### PRIMARY (HIGH confidence -- direct verification)
- py-clob-client v0.34.6 source code: `client.post_orders()`, `client.get_order_books()`, `PostOrdersArgs`, `BookParams` types inspected in installed package
- Polymarket docs: `POST /orders` endpoint -- max 15 orders, parallel processing, FAK supported, per-order success/failure response
- Polymarket docs: `POST /books` endpoint -- batch order book fetch
- Polymarket docs: Rate limits -- `/orders`: 1,000 req/10s burst / 15,000 req/10min sustained; `/books`: 500 req/10s
- Polymarket docs: NegRisk -- `negRisk` boolean on Gamma events, exchange-guaranteed one-of-N structure
- Existing codebase: `cross_market.py`, `dependency.py`, `engine.py`, `order_client.py`, `simulator.py`, `filters.py`, `config.py`, `dry_run.py` -- all read and analyzed

### SECONDARY (MEDIUM confidence -- domain knowledge from training data)
- Sports betting arbitrage execution patterns (surebets): sequential vs parallel execution tradeoffs
- DeFi MEV arbitrage: atomic execution guarantees via smart contracts (not available on Polymarket CLOB)
- Options multi-leg order types: partial fill risk decomposition framework

---
*Feature research for: v2.0 Basket Arbitrage Engine*
*Researched: 2026-04-26*
