---
phase: 02-market-data-detection
plan: "04"
subsystem: detection
tags: [fee-model, arbitrage-detection, category-aware, yes-no-arb]
dependency_graph:
  requires: [02-01, 02-02, 02-03]
  provides: [detection-package, fee-model, arbitrage-opportunity-dataclass, yes-no-detection-engine]
  affects: [02-05, 02-06]
tech_stack:
  added: []
  patterns:
    - Category-aware fee lookup via BotConfig fields (D-18)
    - Tag-first, keyword-fallback category detection
    - TDD (RED then GREEN) for both modules
    - MarketPrice.yes_ask used for both YES and NO token ask prices
key_files:
  created:
    - src/bot/detection/__init__.py
    - src/bot/detection/fee_model.py
    - src/bot/detection/opportunity.py
    - src/bot/detection/yes_no_arb.py
    - tests/test_fee_model.py
    - tests/test_yes_no_arb.py
  modified: []
decisions:
  - "NO token ask price read from no_price.yes_ask (MarketPrice stores each token's ask in yes_ask field)"
  - "estimated_fees = (yes_ask + no_ask) * taker_fee — fees on notional, not unit position"
  - "Sports and politics use base min_net_profit_pct (1.5%) — no tier override"
  - "confidence_score = net_spread / (net_spread + 0.01) — simple Phase 2 proxy, refined in Phase 3"
metrics:
  duration: "171s"
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_created: 6
  tests_added: 14
---

# Phase 02 Plan 04: Category-Aware Fee Model + YES/NO Arbitrage Detection Engine Summary

**One-liner:** Category-aware fee model (crypto 1.8%, geopolitics 0%) and YES+NO structural arbitrage engine with 4-gate detection using CLOB ask prices.

## What Was Built

### `src/bot/detection/fee_model.py`

Three functions implementing the D-18 + D-12 fee and threshold structure:

- `get_market_category(market)` — detects category from official Polymarket tags first, then keyword fallback on question text. Priority: crypto > geopolitics > sports > politics > other.
- `get_taker_fee(category, config)` — maps category to per-side taker fee rate from BotConfig fields (crypto=1.8%, geopolitics=0%, sports=0.75%, politics=1.0%, default=1.0%).
- `get_min_profit_threshold(category, config)` — maps category to min net profit threshold (crypto=2.0%, geopolitics=0.75%, all others use base 1.5%).

### `src/bot/detection/opportunity.py`

`ArbitrageOpportunity` dataclass with 14 fields structured for direct SQLite insertion: market_id, market_question, opportunity_type, category, yes_ask, no_ask, gross_spread, estimated_fees, net_spread, depth, vwap_yes, vwap_no, confidence_score, detected_at.

### `src/bot/detection/yes_no_arb.py`

`detect_yes_no_opportunities(markets, cache, config)` applies 4 sequential gates:

1. Both YES and NO prices present in PriceCache (graceful skip if missing)
2. Neither ask >= 1.0 (resolved market guard)
3. min(yes_depth, no_depth) >= config.min_order_book_depth ($50)
4. net_spread >= category-specific threshold

Math: `gross = 1.0 - yes_ask - no_ask`, `fees = (yes_ask + no_ask) * taker_fee`, `net = gross - fees`.

Key: NO token's ask is `no_price.yes_ask` — MarketPrice stores each token's individual ask in the `yes_ask` field regardless of YES/NO token type.

## Test Coverage

| Test file | Tests | All pass |
|-----------|-------|----------|
| tests/test_fee_model.py | 8 | Yes |
| tests/test_yes_no_arb.py | 6 | Yes |
| **Total** | **14** | **Yes** |

Cases covered: crypto/geopolitics/sports/politics/other categories, keyword fallback (nato, bitcoin), resolved market skip, depth gate, missing cache graceful skip, geopolitics 0.75% threshold vs 1.5% base.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

- `vwap_yes` and `vwap_no` in `ArbitrageOpportunity` are set to `yes_ask`/`no_ask` (best ask). Plan documents this: "VWAP = best ask for now (Phase 3 adds multi-level VWAP)." This is intentional — detection goal is met, VWAP refinement is deferred.

## Self-Check: PASSED

Files exist:
- `src/bot/detection/__init__.py` — FOUND
- `src/bot/detection/fee_model.py` — FOUND
- `src/bot/detection/opportunity.py` — FOUND
- `src/bot/detection/yes_no_arb.py` — FOUND
- `tests/test_fee_model.py` — FOUND
- `tests/test_yes_no_arb.py` — FOUND

Commits: 244dbfc (Task 1), f598cd9 (Task 2) — both verified in git log.
