# Pitfalls Research

**Domain:** Basket VWAP Pricing, Multi-Leg Parallel Execution, and Group Structure Validation for Polymarket Cross-Market Arbitrage (v2.0 Rewrite)
**Researched:** 2026-04-26
**Confidence:** HIGH (primary sources: existing codebase inspection, Polymarket API docs, v1.0-v1.2 operational findings in MEMORY.md)

---

## Critical Pitfalls

### Pitfall 1: VWAP Basket Cost Uses Stale Single-Level Cache Instead of Multi-Level Order Book

**What goes wrong:** The v1.2 paper trading simulator (`simulator.py` line 87-91) builds VWAP from a single cache level: `[{"price": cached.yes_ask, "size": cached.yes_depth}]`. Basket pricing in v2.0 replaces ask-sum with VWAP-based executable cost, but if the VWAP computation still uses this single-level cache, the basket cost estimate is just `sum(best_ask_i)` with extra steps. Multi-level depth is the entire point of VWAP -- without it, the v2.0 basket pricing is mathematically identical to the v1.2 ask-sum it replaces, just wrapped in more code.

**Why it happens:**
- The `PriceCache` (`price_cache.py`) stores only `yes_ask`, `yes_depth` (a single float each) per token. There is no multi-level order book data in the cache.
- The live execution engine (`engine.py` lines 316-343) fetches fresh order books via `client.get_order_book()` to get multi-level data, but this is a synchronous call wrapped in `run_in_executor`. Fetching N order books for N legs hits API rate limits.
- Developers will naturally reuse the existing `simulate_vwap()` function, which correctly handles multi-level asks, but pass it single-level data from the cache -- producing correct-looking code that returns the same number as `best_ask`.

**How to avoid:**
- Extend `PriceCache` / `MarketPrice` to store top-K ask levels (at least 3-5 levels), not just the best ask. The WebSocket `market` channel already provides multi-level data in each update -- the cache currently discards everything except level 0.
- Alternatively, store the raw ask array from each WebSocket update in a separate `OrderBookCache` keyed by token_id. The detection hot path reads from this cache; no API calls needed.
- If multi-level cache is deferred, document explicitly that v2.0 VWAP basket pricing is single-level and therefore NOT a true VWAP improvement -- just a rename. Do not claim "VWAP-based executable cost" in detection if the data source is single-level.

**Warning signs:**
- `simulate_vwap()` always returns exactly `best_ask` for every leg (because there is only one level in the input list).
- Basket cost from VWAP equals `sum(best_ask_i)` to 6+ decimal places. If these numbers diverge by < 0.001 consistently, the VWAP is not doing real multi-level work.

**Phase to address:** Basket Pricing phase. Cache extension must be designed BEFORE VWAP basket construction, because basket pricing depends on multi-level data.

---

### Pitfall 2: Parallel Leg Execution Causes Nonce/Signing Collision in py-clob-client

**What goes wrong:** The v1.2 engine executes legs sequentially (one `place_fak_order` at a time, `engine.py` lines 149-241). The v2.0 plan replaces this with parallel/batched execution via `asyncio.gather()` or similar. However, `py-clob-client`'s `create_order()` is a synchronous function that internally generates an EIP-712 signed order with a nonce and timestamp. If two `create_order()` calls run concurrently in separate `run_in_executor` threads, they may generate orders with identical or conflicting timestamps/nonces, causing one or both to be rejected by the CLOB operator.

**Why it happens:**
- `place_fak_order()` (`order_client.py` lines 59-65) wraps `client.create_order(order_args)` and `client.post_order(signed, orderType=OrderType.FAK)` in sequential `run_in_executor()` calls. Each call runs in the default thread pool.
- The py-clob-client `create_order()` internally calls `build_order()` which generates a salt/nonce from `int(time.time())`. If two threads call this within the same second, they get the same salt, and the CLOB operator may reject the duplicate as a replay attack.
- From the v1.0 research (`03-RESEARCH.md` line 156): `nonce=0` is the default for `OrderArgs`. The nonce in EIP-712 signing is separate from this field -- it comes from the internal `build_order()` code path. The interaction between `OrderArgs.nonce` and the EIP-712 salt is opaque.

**How to avoid:**
- Do NOT use `asyncio.gather()` with multiple `place_fak_order()` calls. Instead, use Polymarket's batch order endpoint: `POST /orders` accepts up to 15 orders per request, processed in parallel server-side. This avoids client-side nonce collision entirely.
- Verify that `py-clob-client` exposes a batch order method (likely `client.post_orders()` -- plural). If it does, pre-sign all orders sequentially (each `create_order()` call in series to avoid salt collision), then submit the batch in one HTTP call.
- If no batch method exists in the SDK, implement a sequential-sign + parallel-submit pattern: sign all N orders one at a time (ensuring unique salts), then submit all N `post_order()` calls concurrently.
- Add a minimum 1ms delay between `create_order()` calls if they must be parallelized, to ensure timestamp-based salts differ.

**Warning signs:**
- Orders intermittently rejected with "duplicate order" or "invalid signature" errors when submitting 2+ legs simultaneously.
- Rejection rate increases with leg count (N legs = higher collision probability).
- First leg always succeeds, subsequent legs fail -- classic nonce collision pattern.

**Phase to address:** Execution Improvements phase. Must be resolved BEFORE enabling parallel leg submission. Test with 2-leg, 5-leg, and 10-leg baskets to verify no collision.

---

### Pitfall 3: Common-Size Calculation Uses Best Ask Instead of VWAP Price Per Leg

**What goes wrong:** The v2.0 plan introduces pre-computed common-size: "max fillable depth across all legs before trade decision." The existing equal-shares formula (`engine.py` line 140: `target_shares = kelly_usd / total_yes`) uses `sum(leg["ask"])` for `total_yes`. If common-size uses best-ask prices but execution hits multi-level depth, the actual cost per leg exceeds the budget. The bot attempts to buy `target_shares` of each leg, but the real USD cost (at VWAP price, not best ask) is higher than allocated, causing the last leg(s) to be under-funded.

**Why it happens:**
- `total_yes` is computed from `leg["ask"]` values (best ask), but the actual fill walks up the book. If best ask is $0.30 with 100 shares, but you need 200 shares, the VWAP might be $0.35. The cost per leg is $70 instead of $60.
- With N legs, the cumulative error compounds. A 5-leg basket where each leg's VWAP is 15% above best ask costs 15% more total than the ask-sum estimate. Kelly sizing based on ask-sum over-allocates.
- The v1.2 code does not have this problem because it uses ask prices for both sizing and execution (consistently wrong, but consistently). The v2.0 change to VWAP pricing in detection but ask-based sizing creates an inconsistency.

**How to avoid:**
- Common-size must be computed from VWAP prices, not best asks. The flow is: (1) for a target size S, compute VWAP_i for each leg at size S, (2) compute `total_vwap = sum(VWAP_i)`, (3) compute `basket_cost = S * total_vwap`, (4) if `basket_cost > kelly_usd`, reduce S proportionally and recompute. This is an iterative convergence, not a single-pass calculation.
- Implement `compute_common_size(legs_order_books, kelly_usd)` that binary-searches for the maximum S where `sum(VWAP_i(S)) * S <= kelly_usd`. Typically converges in 5-10 iterations.
- Never mix ask-based sizing with VWAP-based cost estimation. Use VWAP everywhere or ask everywhere.

**Warning signs:**
- `sum(actual_fill_cost_i) > kelly_usd` after execution. The bot spent more than Kelly authorized.
- Last leg has insufficient balance to fill. Capital exhausted before all legs are placed.
- Paper trading P&L is systematically more optimistic than live execution.

**Phase to address:** Basket Pricing phase. Common-size is a core computation that everything else depends on.

---

### Pitfall 4: Group Partition Validation Incorrectly Assumes All Gamma Events Are Partitions

**What goes wrong:** The v2.0 plan replaces pairwise dependency rejection with "group-level partition validation" -- checking if a group of markets forms a one-of-N partition (exactly one must resolve YES). The current `_group_by_event()` function (`cross_market.py` lines 95-122) groups ALL markets sharing a Gamma API event_id, regardless of whether the event is actually a partition. Polymarket events can contain markets that are NOT mutually exclusive (e.g., "US Economic Indicators" with independent sub-markets). The v1.2 pairwise dependency filter (`classify_pair`) catches some of these, but removing it and relying solely on event_id grouping makes the problem worse, not better.

**Why it happens:**
- Gamma API events are an organizational grouping, not a logical exclusivity guarantee (confirmed in v1.2 PITFALLS.md Pitfall 5).
- NegRisk-enabled events (`negRisk=True` on market objects) ARE contractually mutually exclusive -- the smart contract enforces it. Standard events are NOT.
- The v2.0 plan removes pairwise dependency detection, which was the safety net catching non-exclusive groups. Without a replacement validation, the partition assumption is unguarded.
- The Gamma API `negRisk` field is available on market objects within events but is currently NOT checked by `_group_by_event()` or `detect_cross_market_opportunities()`.

**How to avoid:**
- Partition validation MUST check `negRisk` as the primary signal. Groups where ALL markets have `negRisk=True` and share a `neg_risk_market_id` are confirmed partitions. No further validation needed.
- For non-NegRisk events (standard markets), implement a multi-signal partition check: (a) `sum(YES_ask_i)` should be in range [0.5, 1.5] for a plausible partition (NOT exactly 1.0 -- deviations ARE the arb), (b) event title should contain partition-indicating language ("Who will", "Which", "Winner of"), (c) market question text should share a common subject with only the outcome varying.
- Do NOT remove the dependency detection module entirely. Demote it to a secondary signal for non-NegRisk groups. The `classify_pair` function is still useful for catching "related" markets within the same event that are NOT mutually exclusive.
- Consider a three-tier confidence system: Tier 1 (HIGH) = negRisk partition, Tier 2 (MEDIUM) = non-negRisk event with partition signals, Tier 3 (LOW) = event grouping only, no partition validation. Only execute Tier 1 opportunities. Paper-trade Tier 2. Log-only Tier 3.

**Warning signs:**
- Baskets detected from non-NegRisk events where `sum(YES_ask_i) > 1.5` or `< 0.3` -- these are likely independent markets, not partitions.
- Multiple legs in a basket resolve YES simultaneously. In a true partition, exactly one resolves YES.
- Significant increase in detected opportunities after removing pairwise filters -- most of the "new" opportunities are false positives from non-exclusive groups.

**Phase to address:** Group Structure Validation phase. This is the FIRST thing to implement -- all basket pricing and execution depends on correctly identifying partitions.

---

### Pitfall 5: Removing Fire-Sale Hedge Without a Safe Alternative Creates Stranded Positions

**What goes wrong:** The v2.0 plan removes the fire-sale hedge (`SELL at $0.01`) as the default fallback when a leg fails. The rationale is sound -- selling at $0.01 loses nearly 100% of filled legs' value. But if the replacement strategy is "abort early and do nothing," the bot is left holding partial positions with no exit plan. These positions have value that decays over time and require manual intervention to close.

**Why it happens:**
- The v1.2 hedge logic (`engine.py` lines 210-241) sells ALL filled legs at $0.01 when ANY subsequent leg fails. This is aggressive and costly, but it is also automatic and immediate. No manual intervention required.
- "Abort early" means stopping execution after a leg failure but NOT selling the filled legs. The bot now holds YES tokens on legs 1..N-1 of a basket where leg N could not be filled. These tokens are individually priced at their market value but the basket arbitrage opportunity is gone.
- The filled positions might still be profitable if the winning outcome is one of the filled legs -- but this is a GAMBLE, not arbitrage. The bot has transformed from a risk-free arb strategy to a directional bet.
- With <$1k capital and $50 max per trade (5% of $1k), stranded positions can accumulate and lock up capital.

**How to avoid:**
- Replace fire-sale hedge with a GRADUATED exit strategy: (a) first attempt: retry the failed leg 2-3 times with 500ms delay (existing pattern), (b) second attempt: place the failed leg at a WIDER price (e.g., best ask + 2 ticks) to improve fill probability, (c) third attempt: if still unfilled, SELL filled legs at best BID (not $0.01). Best bid is typically $0.01-0.05 less than the ask, recovering most of the value.
- Alternatively: use a limit order book to OFFER the filled legs for sale at their purchase price. If sold, the position unwinds at zero loss (minus fees). If not sold within a configurable timeout (e.g., 60s), then fall back to selling at best bid.
- NEVER leave positions stranded with no exit path. Every filled leg must have a planned exit, even if the exit is "hold for resolution and accept directional risk."
- Track stranded positions in a `positions` table. Add a background task that periodically checks stranded positions and attempts to close them at best bid if they have been open for > N minutes.

**Warning signs:**
- `positions` table shows growing open position count with no corresponding closes.
- Capital utilization percentage rises steadily (capital tied up in positions, not available for new trades).
- Bot detects opportunities but cannot execute because all capital is locked in stranded positions from previous partial fills.

**Phase to address:** Execution Improvements phase. The hedge replacement strategy must be designed and tested BEFORE removing the fire-sale hedge. Never leave the system without a fallback.

---

### Pitfall 6: Parallel Execution Exhausts USDC Balance Before All Legs Submit

**What goes wrong:** Sequential execution naturally gates capital -- each leg reduces available balance before the next leg submits. The CLOB validates available balance at order submission time. With parallel execution, all N legs submit simultaneously, each requesting `leg_cost_i` USDC. If `sum(leg_cost_i) > available_balance`, one or more legs are rejected with insufficient balance, even though the bot "planned" for total cost to be within budget.

**Why it happens:**
- Polymarket's order book reserves balance at submission time: "maximum order size equals balance minus any amounts reserved by existing open orders" (from Order Lifecycle docs).
- Sequential execution works because leg 1 reserves its cost, leg 2 sees reduced balance but the bot already sized for total cost. Each leg is individually within remaining balance.
- Parallel execution submits ALL legs simultaneously. Each leg sees the FULL balance and tries to reserve its share. If the CLOB processes them in any order, the first few succeed and later ones fail due to insufficient unreserved balance.
- FAK orders that fill immediately release the "reserved" balance concept, but there is a race: between submission and fill confirmation, the balance is reserved. With parallel FAK orders, all N legs try to reserve simultaneously.

**How to avoid:**
- If using the batch order endpoint (`POST /orders`), verify whether Polymarket's batch processing deducts balance atomically (all-or-nothing) or sequentially. If sequential, the batch endpoint has the same problem.
- Pre-validate: before submitting any orders, compute `total_basket_cost = sum(leg_size_usd_i)` and check `total_basket_cost <= available_balance * 0.95` (5% safety margin for rounding and tick-size adjustments).
- If true parallel execution is required, use the FOK order type instead of FAK for the most expensive leg. FOK rejects entirely if not fully fillable, preventing partial reservation of the largest chunk. Other legs can use FAK.
- Consider a staged approach: submit the first 2-3 legs in parallel (testing balance atomicity), then submit remaining legs in a second batch. This limits the blast radius of balance collision.

**Warning signs:**
- Order rejection with "insufficient balance" errors despite the bot having enough total balance for the basket.
- Rejection rate correlates with basket size (more legs = more collision probability).
- First N legs fill, last M legs rejected -- consistent with sequential CLOB processing of parallel submissions.

**Phase to address:** Execution Improvements phase. Must test with real (small) orders on testnet or mainnet to verify CLOB balance reservation behavior for parallel submissions.

---

### Pitfall 7: Dropping YES/NO Arb Removes the Only Detection Path That Has Zero False Positives

**What goes wrong:** The v2.0 plan drops YES/NO arb to focus exclusively on cross-market basket arb. YES/NO detection is structurally simple (two tokens, same market, mathematically verifiable). Cross-market detection has 93% historical false positive rate (v1.2 finding, now reduced by filters but not eliminated). By dropping the zero-false-positive strategy and going all-in on the high-false-positive strategy, the bot's overall detection quality degrades.

**Why it happens:**
- YES/NO arb has detected ZERO opportunities in dry-run because the market is efficient at the 1.5% threshold. Dropping it seems logical -- it produces nothing.
- However, "zero detected at 1.5%" does not mean "zero exist." Market efficiency varies over time. During high-volatility events, YES/NO spreads can momentarily widen past 1.5%. These are the most reliable opportunities because they require no group validation and have zero false-positive risk.
- Cross-market detection requires partition validation, VWAP across N legs, parallel execution, and hedge logic. YES/NO requires none of this. The operational complexity difference is 10x.

**How to avoid:**
- Keep YES/NO detection as a lightweight background scanner even while focusing on basket arb. It costs nearly zero compute (single price comparison per market, no grouping) and catches the rare high-confidence YES/NO opportunities during volatile events.
- If YES/NO detection must be removed from the main scan loop for code cleanliness, extract it to a separate lightweight async task that runs every 5-10 seconds on the same PriceCache data.
- At minimum, keep the YES/NO detection code intact and importable. Do not delete `yes_no_arb.py`. The cost of keeping dead code is trivial; the cost of reimplementing it when a YES/NO opportunity finally appears is significant.

**Warning signs:**
- After removing YES/NO arb, a profitable YES/NO spread appears in the logs (from price monitoring) but the bot cannot act on it.
- Manual inspection of market data shows temporary YES+NO < $0.985 during volatile events -- opportunities the bot could have captured trivially.

**Phase to address:** Architecture/cleanup phase. Decision to keep or drop YES/NO should be made explicitly with documented rationale, not as an implicit side effect of focusing on basket arb.

---

## Moderate Pitfalls

### Pitfall 8: WebSocket Multi-Level Ask Data Is Discarded by the Current Cache

**What goes wrong:** The WebSocket `market` channel sends order book updates with full ask/bid arrays (`sells`/`buys` in WebSocket field naming). The current `ws_client.py` processes these messages but the `PriceCache` only stores `yes_ask` (single float) and `yes_depth` (single float). All other levels are discarded. The v2.0 VWAP basket pricing needs multi-level data, but it will not be available from the cache without schema changes.

**Why it happens:**
- The v1.0 design stored only best ask because that was sufficient for ask-sum pricing.
- The WebSocket data IS already arriving with multi-level information. The discard happens in the normalization step (ws_client -> PriceCache.update()).
- Developers will try to use `simulate_vwap()` with cached data and not realize it is single-level. The function handles multi-level input correctly -- the bug is in the data source, not the VWAP function.

**How to avoid:**
- Extend `MarketPrice` dataclass to include `yes_ask_levels: list[tuple[float, float]]` -- a list of (price, size) tuples for the top N ask levels.
- Update `ws_client.py` normalization to populate all ask levels from the `sells` array (remembering to sort ascending -- Polymarket sends asks descending, per MEMORY.md critical finding).
- Update `http_poller.py` to populate ask levels from REST order book responses.
- Keep backward compatibility: `yes_ask` and `yes_depth` continue to represent level 0. The new `yes_ask_levels` field is additive.

**Warning signs:**
- `len(cached.yes_ask_levels)` is always 1 after implementation -- means WebSocket normalization is still discarding levels.
- VWAP results are identical to best-ask pricing for all baskets. (Same as Pitfall 1 warning sign.)

**Phase to address:** Basket Pricing phase. Cache extension is a prerequisite for meaningful VWAP computation.

---

### Pitfall 9: Liquidity-Driven Filtering Without Spread Check Creates Dead-Spread Opportunities

**What goes wrong:** The v2.0 plan replaces dead-leg price heuristics with "liquidity-driven filtering" (depth/spread/stale checks). If the filter checks depth (sufficient liquidity exists) but not spread (the cost of that liquidity), it passes legs where there is $500 of depth but the ask is $0.999 (near-resolved market). The depth is excellent, the spread is zero. The old dead-leg price floor ($0.005 minimum ask) caught this. Liquidity-alone filtering does not.

**Why it happens:**
- "Liquidity-driven" sounds like a strictly better approach than price heuristics, but liquidity and price are orthogonal signals. A market can have deep liquidity at an unfavorable price.
- Near-resolved markets often have excellent depth (many limit orders near $0.99-1.00) but zero arb value. The existing `has_dead_leg()` filter (`filters.py` line 29-31) catches these via ask floor.
- Replacing price heuristics with liquidity checks removes the floor that filters 90%+ of false positives.

**How to avoid:**
- Liquidity-driven filtering must INCLUDE a spread component. The filter should be: `depth >= min_depth AND ask >= min_ask AND spread_contribution >= min_contribution`. Where `spread_contribution = 1.0 / N - VWAP_i` (how much this leg contributes to the basket spread after VWAP).
- Keep the dead-leg ask floor as a FIRST-PASS filter (cheap O(1) check). Apply liquidity filtering as a SECOND-PASS on groups that pass the ask floor.
- The existing `DETECT-03` filter (`has_dead_leg` with `min_cross_leg_ask` threshold) should be preserved in the new pipeline. Rename it if needed for clarity, but do not remove it.

**Warning signs:**
- Detection passes groups where one or more legs have `ask > 0.95` -- these are near-resolved markets that cannot contribute to basket arb.
- False positive rate increases after replacing price heuristics with liquidity-only filtering.
- `total_yes` is close to `N * 0.99` for detected baskets -- all legs are near-resolved, no actual spread.

**Phase to address:** Liquidity Filtering phase. Ensure the filter combines depth AND price signals.

---

### Pitfall 10: CLOB Rate Limits Are Higher Than Expected But Relayer Limit Is 25 req/min

**What goes wrong:** The bot's MEMORY.md records CLOB rate limits as "60 req/10s." The actual Polymarket rate limit documentation (fetched 2026-04-26) shows CLOB POST/order at 3,500 req/10s burst. This is 58x higher than assumed. However, the Relayer `/submit` endpoint has a restrictive 25 req/1min limit. If the signing or order finalization pathway goes through the Relayer (which handles on-chain settlement), parallel execution of even 5 legs could hit the Relayer limit.

**Why it happens:**
- Different Polymarket API surfaces have vastly different rate limits. CLOB API (centralized matching) is high-throughput. Relayer (on-chain settlement) is heavily restricted.
- The py-clob-client SDK abstracts which endpoint is called internally. `create_order()` may call the CLOB for tick_size validation, and `post_order()` may interact with the Relayer for settlement preparation.
- Developers optimizing for the 3,500 req/10s CLOB limit could inadvertently overwhelm the 25 req/min Relayer limit.

**How to avoid:**
- Profile which endpoints `create_order()` and `post_order()` actually call under the hood. Use `httpx` request logging or network capture to identify the full HTTP call chain.
- If the Relayer is in the critical path, limit total order submissions to 20/min (80% of 25 limit, leaving headroom for retries and hedges).
- For batch orders, verify that the batch endpoint counts as 1 Relayer call (for the batch) rather than N calls (one per order). This determines whether batch ordering avoids or compounds the Relayer limit.
- Update MEMORY.md with the corrected rate limits: CLOB POST/order = 3,500 req/10s burst / 36,000 req/10min sustained. Relayer = 25 req/1min. Gamma = 200-500 req/10s per endpoint. These numbers are from the official docs as of 2026-04-26.

**Warning signs:**
- 429 errors that only appear when submitting orders (not on market data queries). The Relayer is the likely bottleneck.
- Errors mentioning "rate limit" after only 5-10 orders in quick succession, despite CLOB limit being 3,500.
- Orders succeed individually but fail in batches -- Relayer counting each batch item separately.

**Phase to address:** Execution Improvements phase. Rate limit characterization must happen BEFORE parallel execution design.

---

### Pitfall 11: ArbitrageOpportunity Dataclass Lacks Basket-Specific Fields

**What goes wrong:** The `ArbitrageOpportunity` dataclass (`opportunity.py`) was designed for YES/NO arb and extended with a `legs` list for cross-market. The v2.0 basket engine needs fields that do not exist: `basket_vwap_cost` (total VWAP across all legs), `common_size_shares` (pre-computed fillable size), `partition_confidence` (from group validation), `min_leg_depth` (weakest leg liquidity), `basket_id` (unique group identifier for dedup). Without these fields, the detection -> execution -> logging pipeline cannot carry basket-specific metadata.

**Why it happens:**
- The dataclass has 17 fields, all oriented toward two-token (YES/NO) arb. Fields like `yes_ask`, `no_ask`, `vwap_yes`, `vwap_no` are meaningless for N-leg baskets.
- Adding fields to the dataclass requires updating: (a) the constructor in `detect_cross_market_opportunities()`, (b) the SQLite `opportunities` table schema, (c) the `AsyncWriter.enqueue()` method, (d) the paper trading simulator, (e) the dashboard queries. Missing any one of these creates data loss or runtime errors.

**How to avoid:**
- Define a new `BasketOpportunity` dataclass specifically for basket arb, rather than overloading `ArbitrageOpportunity`. Keep `ArbitrageOpportunity` for YES/NO (if retained) and create `BasketOpportunity` with: `basket_id`, `event_id`, `legs` (with per-leg VWAP, depth, token_id), `total_vwap_cost`, `common_size_shares`, `partition_source` (negRisk | event | heuristic), `partition_confidence`, `net_spread`, `estimated_fees`, `detected_at`.
- If a single dataclass is preferred, deprecate YES/NO-specific fields and add basket fields with Optional types. But this creates a confusing union type.
- Update SQLite schema with a migration (ALTER TABLE ADD COLUMN for each new field, with DEFAULT values for existing rows). Test that all existing queries still work after migration.

**Warning signs:**
- `opp.yes_ask` is populated with `legs[0]["ask"]` as a workaround -- fields are being repurposed rather than designed.
- Basket metadata is computed in detection but lost by the time it reaches paper trading or logging.
- SQLite INSERT errors from new fields not present in the schema.

**Phase to address:** Group Structure Validation phase (first phase). Dataclass/schema changes must be done BEFORE any detection or pricing code is written.

---

### Pitfall 12: Removing Pairwise Dependency Detection Before Group Validation Is Production-Ready

**What goes wrong:** The v2.0 plan replaces pairwise `classify_pair()` with group-level partition validation. If the pairwise filter is removed in an early phase but group validation is not ready until a later phase, there is a gap where cross-market detection has NO exclusivity validation at all. During this gap, the bot will detect and potentially paper-trade non-exclusive groups as if they were partitions.

**Why it happens:**
- Multi-phase roadmaps create temporal gaps between "remove old thing" and "add new thing."
- The pairwise filter runs on every detected group (`cross_market.py` lines 218-257). Removing it is a one-line change (`continue` -> noop). Adding group validation is a multi-day implementation.
- Developers want to "clean up" old code before writing new code, but in a live system, the old code is the safety net.

**How to avoid:**
- Keep `classify_pair()` active in audit mode (existing `config.dependency_audit_mode = True` setting) until group validation is implemented AND validated. Never remove a safety filter before its replacement is tested.
- Implementation order: (1) build group validation module, (2) run both pairwise and group validation in parallel for N cycles, (3) compare rejection lists -- group validation should reject a superset of what pairwise rejects, (4) only then disable pairwise.
- Mark `dependency.py` as "deprecated but active" rather than deleting it.

**Warning signs:**
- After removing pairwise filters, detected opportunity count spikes by 5-10x. Most new detections are false positives from non-exclusive groups.
- Paper trading P&L shows unrealistically high returns during the gap period -- boosted by false positive detections.

**Phase to address:** Group Structure Validation phase. Pairwise filters stay active until group validation is validated.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Single-level VWAP from cache | Zero cache refactoring needed | VWAP basket pricing is meaningless -- just a renamed ask-sum | Never if claiming "VWAP-based executable cost" |
| Reusing `ArbitrageOpportunity` for baskets | No new dataclass/schema work | Basket metadata lost, YES/NO fields misused, confusing API | Only in a throwaway prototype |
| Sequential execution labeled as "batched" | No nonce/signing issues | Missing the latency improvement that justifies the v2.0 rewrite | During initial development, but must be replaced before production |
| Dropping dead-leg ask floor when adding liquidity filter | Cleaner, single-concern filter | 90% of false positives return if liquidity filter misses near-resolved markets | Never -- keep both filters as layered defenses |
| Hardcoded `negRisk=True` as only partition source | Simple, high-confidence grouping | Misses standard events that ARE partitions (elections, awards) | Acceptable for MVP if documented; extend later |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Polymarket CLOB: Parallel FAK orders | Assume `asyncio.gather()` on `place_fak_order()` is safe | Sequential signing + batch submit, OR sequential with 1ms delay between `create_order()` calls |
| Polymarket CLOB: Order book sort order | Assume asks arrive sorted ascending | ALWAYS sort ascending explicitly; CLOB returns asks DESCENDING (highest first) -- confirmed bug source in v1.0 |
| Polymarket CLOB: `OrderBookSummary` | Assume `get_order_book()` returns a dict | Returns a dataclass; access via `.asks`, `.bids`, `.asset_id` -- NOT dict keys |
| Polymarket WebSocket: field names | Use "asks"/"bids" in message parsing | WebSocket uses "sells"/"buys" -- different field names from REST |
| Polymarket WebSocket: subscription limit | Subscribe to all token IDs | Server silently drops subscriptions beyond ~2000 token IDs. No error returned. |
| Polymarket Gamma API: `negRisk` field | Treat as event-level field | `negRisk` is a market-level boolean within events, not on the event object itself |
| Polymarket CLOB: balance reservation | Assume balance is deducted only on fill | Balance is RESERVED at order submission time. Parallel orders compete for the same unreserved balance. |
| py-clob-client: `create_and_post_order()` | Use for all order types | FORBIDDEN -- defaults to GTC. Must use `create_order()` + `post_order(orderType=FAK)` separately |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| O(N^2) pairwise validation on large groups | Cycle time > 30s for groups with 15+ markets | Cap group size at 20 (existing `_MAX_GROUP_SIZE`); if removing pairwise validation, this cap can be relaxed but monitor latency | Groups > 20 markets |
| Fresh order book fetch for every leg in basket VWAP | 429 rate limit errors; detection cycle slows to 60s+ | Use cached multi-level data from WebSocket; fresh fetch only for the top 1-2 candidate baskets per cycle | > 10 baskets detected per cycle, each with 5+ legs |
| Binary search for common-size converging slowly | Detection latency spikes for baskets with irregular depth profiles | Set max iterations to 10; if not converged, use the last estimate with a 10% safety haircut | Legs with wildly different depth profiles (1 leg has $500 depth, another has $5) |
| `itertools.combinations(group, 2)` for 20-market groups | 190 pair comparisons per group; 10+ groups per cycle = 1900+ comparisons | Replace with group-level validation (the point of v2.0). If pairwise is retained during transition, cap at 100 pairs per group | Groups > 15 markets |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Parallel execution exposing wallet private key to multiple threads | Thread-safety of signing operations is not guaranteed by py-clob-client | Serialize all `create_order()` calls through a single thread or use a signing mutex |
| Not validating basket cost against balance before submission | Over-submission causes rejected orders AND may leak information about wallet balance to CLOB operator | Pre-validate `total_basket_cost <= balance * 0.95` before any order submission |
| Removing fire-sale hedge without position tracking | Stranded positions accumulate untracked; manual intervention needed to discover them | Every filled order must be tracked in a `positions` table with a planned exit path |

## "Looks Done But Isn't" Checklist

- [ ] **VWAP basket pricing:** Often missing multi-level data -- verify `len(ask_levels) > 1` for cached prices and that `simulate_vwap()` actually walks multiple levels
- [ ] **Common-size computation:** Often uses best-ask instead of VWAP -- verify `total_cost_at_common_size` matches `kelly_usd` to within 1%
- [ ] **Partition validation:** Often checks event_id only -- verify `negRisk` flag is checked on every market in the group
- [ ] **Parallel execution:** Often tested with 2-leg baskets -- verify with 5+ legs and confirm no nonce collision or balance exhaustion
- [ ] **Hedge replacement:** Often implements "abort early" without exit plan -- verify every filled leg has a tracked position with a planned close
- [ ] **Ask sort order:** Often assumed ascending -- verify explicit `sorted(asks, key=lambda a: float(a.price))` before every VWAP calculation
- [ ] **Liquidity filter:** Often checks depth only -- verify dead-leg ask floor (`DETECT-03`) is still active alongside new liquidity checks
- [ ] **Dataclass migration:** Often adds fields to code but not to SQLite schema -- verify `ALTER TABLE` migration for all new fields
- [ ] **Paper trading consistency:** Often simulates baskets differently than live -- verify paper trade VWAP uses the same cache/multi-level data as live detection
- [ ] **Rate limit awareness:** Often uses 60 req/10s assumption -- verify actual endpoint-specific limits (CLOB = 3,500/10s burst, Relayer = 25/min)

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Single-level VWAP (Pitfall 1) | MEDIUM | Extend cache schema, update WebSocket normalization, no code logic changes needed |
| Nonce collision (Pitfall 2) | LOW | Add signing mutex or switch to batch endpoint; no architectural change |
| Common-size mismatch (Pitfall 3) | MEDIUM | Implement iterative convergence function; update sizing in detection and execution |
| Partition false positives (Pitfall 4) | HIGH | Must audit all paper trades, rebuild detection pipeline with negRisk check, potentially revert v2.0 changes |
| Stranded positions (Pitfall 5) | HIGH | Manual position close required; implement position tracking table; may require emergency wallet drain |
| Balance exhaustion (Pitfall 6) | LOW | Add pre-validation check; no architectural change needed |
| Lost YES/NO detection (Pitfall 7) | LOW | Re-enable `detect_yes_no_opportunities()` in scan loop; code still exists |
| Non-exclusive basket execution | CRITICAL | If live execution bought a non-exclusive basket, capital is at directional risk until resolution. No automated recovery possible. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1: Single-level VWAP | Basket Pricing | `assert len(cached.yes_ask_levels) >= 3` for cached tokens with WebSocket data |
| 2: Nonce collision | Execution Improvements | Submit 5 FAK orders in < 1 second; verify all 5 get unique order IDs and none rejected as duplicate |
| 3: Common-size vs VWAP mismatch | Basket Pricing | `assert abs(sum(vwap_i * common_size) - kelly_usd) / kelly_usd < 0.02` |
| 4: Partition false positives | Group Structure Validation | Run group validation on 100 Gamma events; manually verify all groups labeled "partition" are actually mutually exclusive |
| 5: Stranded positions | Execution Improvements | Paper-trade 100 baskets; verify every partial fill has a corresponding position entry and planned exit |
| 6: Balance exhaustion | Execution Improvements | Submit 5 parallel orders totaling 90% of balance; verify no "insufficient balance" rejections |
| 7: Lost YES/NO detection | Architecture decision | Code review: `yes_no_arb.py` still importable and callable |
| 8: WebSocket cache discard | Basket Pricing | Log `len(price.yes_ask_levels)` per WS update; verify > 1 for actively traded markets |
| 9: Dead-spread from liquidity filter | Liquidity Filtering | Run filter on 1000 markets; verify no market with `ask > 0.95` passes the filter |
| 10: Relayer rate limit | Execution Improvements | Submit 30 orders in 60 seconds; check for 429 errors from Relayer endpoint |
| 11: Dataclass missing fields | Group Structure Validation | `BasketOpportunity` has all required fields; SQLite schema matches |
| 12: Gap in exclusivity validation | Group Structure Validation | Pairwise filter stays in audit mode until group validation is validated |

---

## Sources

- Direct code inspection: `src/bot/detection/cross_market.py` -- event grouping, detection gates, pairwise dependency integration
- Direct code inspection: `src/bot/execution/engine.py` -- VWAP simulation, Kelly sizing, sequential cross-market execution, hedge logic
- Direct code inspection: `src/bot/execution/order_client.py` -- FAK order placement, run_in_executor pattern, nonce defaults
- Direct code inspection: `src/bot/execution/kelly.py` -- Modified Kelly formula, depth cap, capital ceiling
- Direct code inspection: `src/bot/paper/simulator.py` -- single-level VWAP from cache, cross-market hedge simulation
- Direct code inspection: `src/bot/scanner/price_cache.py` -- MarketPrice dataclass (single-level only), PriceCache API
- Direct code inspection: `src/bot/detection/opportunity.py` -- ArbitrageOpportunity dataclass (17 fields, YES/NO-oriented)
- Direct code inspection: `src/bot/detection/filters.py` -- DETECT-01 through DETECT-05, dead-leg filter
- Direct code inspection: `src/bot/detection/dependency.py` -- classify_pair, 5-signal weighted scorer
- Direct code inspection: `src/bot/dry_run.py` -- scan loop, paper trade integration, cross-market cap at 100 markets
- Polymarket API docs (fetched 2026-04-26): Rate limits -- CLOB POST/order 3,500 req/10s burst, Relayer 25 req/1min
- Polymarket API docs (fetched 2026-04-26): Batch orders -- up to 15 orders per request, processed in parallel
- Polymarket API docs (fetched 2026-04-26): Order lifecycle -- balance reserved at submission, FAK fills or cancels remainder
- Polymarket API docs (fetched 2026-04-26): Order types -- GTC, GTD, FOK, FAK supported
- v1.0 execution research: `.planning/milestones/v1.0-phases/03-execution-risk-controls/03-RESEARCH.md` -- nonce=0 default, EIP-712 signing, create_order+post_order pattern
- Project MEMORY.md -- ask sort order, OrderBookSummary dataclass, WebSocket field names, subscription limits, Gamma API structure
- v1.2 PITFALLS.md -- Gamma events not always exclusive, 93% false positive rate, probability sum validation
- `.planning/PROJECT.md` -- v2.0 target features, known technical debt

---
*Pitfalls research for: Basket VWAP Pricing, Multi-Leg Parallel Execution, and Group Structure Validation (v2.0)*
*Researched: 2026-04-26*
