---
phase: 02-market-data-detection
plan: 01
subsystem: config + scanner
tags: [config, market-filter, tdd, phase2]
dependency_graph:
  requires: [01-infrastructure-foundation]
  provides: [BotConfig-phase2-fields, fetch_liquid_markets]
  affects: [all Phase 2 scanner modules]
tech_stack:
  added: []
  patterns: [TDD red-green, dataclass defaults, paginated API consumption]
key_files:
  created:
    - src/bot/scanner/__init__.py
    - src/bot/scanner/market_filter.py
    - tests/test_market_filter.py
  modified:
    - src/bot/config.py
decisions:
  - "Phase 2 config fields use dataclass defaults only — no new env vars, REQUIRED_SECRETS stays at 6 items"
  - "fetch_liquid_markets is async to match the bot's asyncio event loop even though get_markets is sync"
  - "token_ids extracted and added to each market dict at filter time to avoid re-extraction in downstream modules"
metrics:
  duration: "~10 minutes"
  completed: "2026-03-28"
  tasks: 2
  files: 4
---

# Phase 2 Plan 01: BotConfig Extension + Market Filter Summary

**One-liner:** Extended BotConfig with 12 Phase 2 scanning/fee fields and implemented paginated market fetching with volume + active-status filtering.

## What Was Built

### Task 1: BotConfig Phase 2 Fields
Added 12 new fields to `src/bot/config.py` (all with dataclass defaults, no env vars required):

- **Scanning parameters:** `min_market_volume=1000.0`, `scan_interval_seconds=30`, `ws_stale_threshold_seconds=5`, `min_order_book_depth=50.0`
- **Profit thresholds:** `min_net_profit_pct=0.015`, `min_net_profit_pct_crypto=0.020`, `min_net_profit_pct_geopolitics=0.0075`
- **Fee rates per side:** `fee_pct_crypto=0.018`, `fee_pct_politics=0.010`, `fee_pct_sports=0.0075`, `fee_pct_geopolitics=0.0`, `fee_pct_default=0.010`

REQUIRED_SECRETS list remains unchanged at 6 items.

### Task 2: Market Filter Module (TDD)
Created `src/bot/scanner/` package with `market_filter.py`:

- `fetch_liquid_markets(client, config)` — async function that paginates CLOB API, filters by `min_market_volume` and `closed=False`, adds `token_ids` list to each returned market dict
- Pagination stops when `next_cursor == "end"` or cursor is absent

## Test Results

| Test File | Tests | Result |
|-----------|-------|--------|
| tests/test_config.py | 6 | PASS |
| tests/test_market_filter.py | 5 | PASS |
| **Total** | **11** | **ALL GREEN** |

Tests cover: volume threshold boundary (exact, above, below), closed market exclusion, empty list handling, multi-page pagination, token_ids field presence.

## Commit

- `038af81` — feat(02-01): extend BotConfig with Phase 2 fields + market_filter

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all fields wired to real defaults; fetch_liquid_markets reads live config values.
