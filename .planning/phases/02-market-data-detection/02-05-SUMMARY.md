---
phase: 02-market-data-detection
plan: 05
subsystem: detection
tags: [cross-market, arbitrage, keyword-grouping, tdd]
dependency_graph:
  requires:
    - 02-04  # ArbitrageOpportunity dataclass, fee_model, price_cache
  provides:
    - cross_market_detection  # detect_cross_market_opportunities()
  affects:
    - scanner_loop  # will call detect_cross_market_opportunities() in Phase 2 scan cycle
tech_stack:
  added: []
  patterns:
    - BFS connected-components for keyword-based market grouping
    - Weakest-link depth gate across group members
    - Counter().most_common() for dominant category selection
key_files:
  created:
    - src/bot/detection/cross_market.py
    - tests/test_cross_market.py
  modified: []
decisions:
  - Keyword extraction: strip punctuation, require len>=4, alpha-only — eliminates stopwords without a stopword list
  - BFS connected components: transitive grouping so A~B~C all land in one group even if A and C don't directly share words
  - fees = total_yes_asks * taker_fee (single-sided — only buying YES tokens, not YES+NO)
  - dominant_category = most common category across group members — used for threshold/fee lookup
  - LLM-based dependency detection deferred to Phase 3 per D-03
metrics:
  duration_minutes: 2
  completed_date: "2026-03-28"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_modified: 0
---

# Phase 02 Plan 05: Cross-Market Arbitrage Detection Summary

**One-liner:** Keyword-grouped cross-market arb detection checking mutual exclusivity (sum YES asks < $1.00) with BFS connected-components grouping and weakest-link depth gate.

## What Was Built

`src/bot/detection/cross_market.py` implements `detect_cross_market_opportunities(markets, cache, config) -> list[ArbitrageOpportunity]` using a two-stage approach:

1. **Grouping** (`_group_markets`): Extracts significant keywords (len>=4, alpha-only) from each market's question text. Builds an adjacency map of market pairs sharing >=2 keywords. BFS finds connected components — markets that form a chain (A~B, B~C) are all placed in one group. Groups outside the [2, 20] size range are discarded.

2. **Exclusivity check**: For each group, collects YES ask prices from the `PriceCache`. Applies the weakest-link depth gate (min depth across all members must be >= `min_order_book_depth`). Computes `gross_spread = 1.0 - sum(YES asks)`, `estimated_fees = total_yes * taker_fee` (single-sided — buying YES only), `net_spread = gross_spread - fees`. Returns an `ArbitrageOpportunity` with `opportunity_type="cross_market"` when `net_spread >= threshold`.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| RED | Failing test suite | b71d02e | tests/test_cross_market.py |
| GREEN | Implementation | 17d6bc7 | src/bot/detection/cross_market.py |

## Test Results

```
tests/test_cross_market.py: 5 passed
Full suite: 50 passed, 5 skipped
```

Tests cover: exclusivity detected, unrelated markets not grouped, insufficient depth skips whole group, sum>=1.0 not returned, single-market group not returned.

## Deviations from Plan

None — plan executed exactly as written. Implementation matches the provided code template in the plan action block.

## Known Stubs

None. All logic is fully implemented for Phase 2 scope. LLM-based dependency detection is intentionally deferred to Phase 3 (D-03) and documented in the module docstring.

## Self-Check

Files created:
- `src/bot/detection/cross_market.py` — created
- `tests/test_cross_market.py` — created

Commits verified:
- b71d02e (test RED)
- 17d6bc7 (feat GREEN)
