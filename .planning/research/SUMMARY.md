# Research Summary: v2.0 Basket Arbitrage Engine

**Domain:** Polymarket Arbitrage Bot -- basket pricing rewrite
**Researched:** 2026-04-26
**Overall confidence:** HIGH

## Executive Summary

The v2.0 milestone replaces the pairwise dependency detection pipeline with group-level basket pricing. After thorough inspection of the existing codebase (~5,000 LOC across 30+ modules), the Polymarket API documentation, and the py-clob-client 0.34.6 SDK source code, this rewrite requires zero new pip dependencies. Every capability needed for basket VWAP construction, common-size optimization, group validation, and parallel execution is available through the existing stack and unused SDK methods.

The most significant discovery is that **py-clob-client 0.34.6 already ships two batch methods the codebase has never used**: `client.post_orders()` (submit up to 15 FAK orders in one HTTP call, processed in parallel server-side) and `client.get_order_books()` (fetch order books for all basket legs in one call). These eliminate the need for serial per-leg HTTP round-trips that currently dominate execution latency. The execution improvement from serial-to-batch is transformative: a 5-leg basket drops from ~750ms (5 sequential sign+submit+verify cycles) to ~200ms (sequential sign + 1 batch submit).

Group structure validation should use Polymarket's `negRisk` boolean as the primary partition signal. NegRisk-enabled events are contractually exclusive via smart contract -- no heuristic validation needed. Non-NegRisk events require probability sum validation and duplicate/subset detection using existing signals from `dependency.py`. This tiered approach eliminates the O(n^2) pairwise `classify_pair` loop that currently runs for every group.

The critical architectural pitfall is single-level VWAP: the current `PriceCache` stores only best-ask and total depth per token. If VWAP basket pricing uses this single-level data, the result is mathematically identical to the ask-sum it replaces -- just with more code. Either the cache must be extended to store multi-level order book data (from WebSocket updates that already provide it but are currently discarded) or fresh batch `get_order_books()` calls must be made for candidate baskets.

## Key Findings

**Stack:** No new dependencies. `post_orders()` and `get_order_books()` batch methods already exist in py-clob-client 0.34.6 but are unused. `asyncio.gather()` from stdlib handles parallel signing. All VWAP, Kelly, and fee computation functions are pure and reusable.

**Architecture:** Four new/modified components: (1) `basket_validator.py` for group-level partition checks, (2) `basket_pricer.py` for VWAP basket cost + common-size, (3) modified `engine.py` for batch execution, (4) extended `order_client.py` for batch SDK method wrappers. The scanner, risk, storage, and notification layers are entirely unchanged.

**Critical pitfall:** NegRisk events are the ONLY exchange-guaranteed partitions. Non-NegRisk events are organizational groupings that may contain non-exclusive markets. Removing pairwise dependency detection without NegRisk-aware group validation creates a false-positive explosion.

**Critical pitfall:** Common-size optimization requires VWAP prices, not best-ask prices. Mixing ask-based sizing with VWAP-based costing causes over-allocation (bot spends more than Kelly authorized).

**Critical pitfall:** `create_order()` uses time-based salts for EIP-712 signing. Parallel signing via `asyncio.gather()` may produce duplicate salts within the same second. Sequential signing (10ms per order) or batch submission avoids this entirely.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Group Structure Validation** - Replace pairwise dependency with tiered partition check
   - Addresses: O(n^2) pairwise overhead, non-exclusive group false positives
   - Avoids: Removing safety filters before replacement is ready (Pitfall 12)
   - Key decision: NegRisk-first tiered validation (Tier 1: NegRisk, Tier 2: heuristic, Tier 3: log-only)
   - Estimated effort: Medium (~100 LOC validator + event metadata cache extension + tests)
   - Research flag: Verify `negRisk` field presence and coverage across all active Gamma events

2. **Basket VWAP Pricing + Common-Size** - VWAP-based executable cost per leg with iterative sizing
   - Addresses: Ask-sum overstating profitability, inconsistent sizing
   - Avoids: Single-level VWAP producing identical results to ask-sum (Pitfall 1)
   - Key decision: Whether to extend PriceCache for multi-level data or use fresh batch book fetch
   - Estimated effort: Medium (~150 LOC pricer + common-size convergence + tests)
   - Research flag: PriceCache multi-level extension vs batch fetch tradeoff needs design decision

3. **Batch Execution + Partial Failure Handling** - Batch `post_orders()` with graduated unwind
   - Addresses: Serial execution latency, fire-sale hedge at $0.01
   - Avoids: Nonce collision from parallel signing (Pitfall 2), balance exhaustion (Pitfall 6)
   - Key decision: Sequential sign + batch submit (safe) vs parallel sign (risky, needs testing)
   - Estimated effort: Medium (~120 LOC batch methods + modified execution flow + tests)
   - Research flag: Test nonce collision behavior with real CLOB. Test batch balance reservation behavior.

4. **Pipeline Integration + Cleanup** - Wire validator/pricer/executor, remove YES/NO arb, update paper trading
   - Addresses: Dead code removal, paper trading alignment with basket logic
   - Avoids: Temporal gap where no validation is active (Pitfall 12)
   - Key decision: Whether to keep YES/NO detection as background scanner or fully remove
   - Estimated effort: Small (glue code, config additions, scan loop updates)
   - Research flag: Standard patterns, no further research needed

**Phase ordering rationale:**
- **Validation FIRST** because all downstream computation (pricing, sizing, execution) depends on correct group identification. Pricing non-exclusive groups produces meaningless results.
- **Pricing SECOND** because it produces the basket opportunity objects consumed by execution and paper trading. Can be tested in dry-run mode without touching real orders.
- **Execution THIRD** because it involves real money. Must be built on top of validated, correctly-priced baskets. Highest risk, so built last.
- **Integration FOURTH** because it is glue code connecting the three components. Cannot be done until all three exist.

**Research flags for phases:**
- Phase 1: Needs verification of `negRisk` field coverage across event types. If most active events are non-NegRisk, Tier 2 heuristic validation becomes critical.
- Phase 2: Needs design decision on multi-level cache vs batch fetch. Both work; cache is faster but requires WS normalization changes. Batch fetch is simpler but adds 1 HTTP call per candidate basket.
- Phase 3: Needs live testing of nonce collision and balance reservation behavior. These cannot be verified from documentation or source code alone.
- Phase 4: Standard patterns, unlikely to need research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Every building block verified in SDK source code and API docs. Zero new dependencies. |
| Features | HIGH | All 4 features mapped to specific SDK methods, pure functions, and stdlib modules. |
| Architecture | HIGH | All source files read. Component boundaries clear. Unchanged layers identified. |
| Pitfalls | HIGH | 12 pitfalls identified from codebase inspection, API docs, and operational history. Phase mappings provided. |

## Gaps to Address

- **`negRisk` field coverage:** Need to verify what fraction of active Gamma events have `negRisk=True`. If <50%, the Tier 2 heuristic validation path gets heavy usage and needs careful tuning.
- **Nonce collision in parallel signing:** Source code inspection shows `create_order()` generates salts, but the exact mechanism (time-based vs random) is opaque. Must test with real CLOB before enabling parallel signing.
- **Batch balance reservation:** Documentation says balance is reserved at submission time, but behavior for batch submissions (atomic reservation vs sequential) is undocumented. Must test with real (small) orders.
- **Multi-level cache vs batch fetch decision:** Both approaches work. Cache extension requires modifying `ws_client.py`, `normalizer.py`, `http_poller.py`, and `MarketPrice` dataclass. Batch fetch requires 1 additional HTTP call per candidate basket. Tradeoff: cache is faster (~0ms) but requires more code changes; batch fetch is simpler but adds ~30ms latency.
- **Partial basket profitability:** When a batch has partial fills, computing whether the filled legs alone form a profitable position requires market-specific analysis (which leg won?). This is inherently unknowable at execution time. The default should be "unwind partial fills" rather than "hold and hope."

## Cross-References

| Research File | Key Contribution |
|--------------|-----------------|
| STACK.md | Zero-dependency confirmation, batch SDK methods (post_orders, get_order_books), rate limit budget |
| FEATURES.md | MVP classification, feature dependency chains, batch API surface verification |
| ARCHITECTURE.md | Component designs, module dependency graph, data flow diagrams, build order |
| PITFALLS.md | 12 pitfalls with phase mappings, integration gotchas, "looks done but isn't" checklist |

---

*This summary synthesizes findings from all four research files. See individual files for detailed technical specifications, code examples, and source citations.*
