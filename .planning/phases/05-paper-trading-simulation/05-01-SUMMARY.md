---
phase: 05-paper-trading-simulation
plan: 01
subsystem: paper-trading
tags: [sqlite, dataclass, vwap, kelly, simulation, tdd]

# Dependency graph
requires:
  - phase: 03-execution-risk-controls
    provides: simulate_vwap(), kelly_size(), get_taker_fee() pure functions
  - phase: 02-detection-quality-filters
    provides: ArbitrageOpportunity dataclass, PriceCache, BotConfig fee fields
provides:
  - PaperTrade dataclass (20 fields, mutable for cross-market P&L distribution)
  - simulate_yes_no() pure function returning 2 PaperTrade rows or []
  - paper_trades SQLite table with 20 data columns + autoincrement id
  - init_paper_trades_table() and insert_paper_trade() schema functions
affects: [05-02-cross-market-simulation, 05-03-summary-queries, dry-run-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns: [depth-gated-deterministic-fill, shares-not-dollars-pnl, single-level-vwap-from-cache]

key-files:
  created:
    - src/bot/paper/__init__.py
    - src/bot/paper/simulator.py
    - tests/test_paper_simulator.py
    - tests/test_paper_storage.py
  modified:
    - src/bot/storage/schema.py

key-decisions:
  - "PaperTrade is a non-frozen dataclass (mutable net_pnl_usd for cross-market P&L distribution in Plan 02)"
  - "VWAP uses single-level ask list from PriceCache per D-02 -- no fresh API calls"
  - "P&L uses effective_shares = min(yes_shares, no_shares) per D-09 -- shares not dollars"
  - "Depth-gated deterministic fill: fill_ratio = min(kelly_usd, depth) / kelly_usd per D-07"
  - "INSERT OR IGNORE for paper_trade_id uniqueness constraint"

patterns-established:
  - "Paper trade simulator as pure function module: accepts ArbitrageOpportunity + PriceCache + BotConfig, returns list[PaperTrade]"
  - "paper_trades table follows init_*_table() / insert_*() pattern from schema.py exactly"

requirements-completed: [PAPER-01, PAPER-02, PAPER-03]

# Metrics
duration: 13min
completed: 2026-04-26
---

# Phase 5 Plan 1: YES/NO Paper Trade Simulator Summary

**PaperTrade dataclass with 20 fields and simulate_yes_no() using cached VWAP + Kelly sizing + depth-gated fill, persisted to isolated paper_trades SQLite table**

## Performance

- **Duration:** 13 min
- **Started:** 2026-04-26T00:25:56Z
- **Completed:** 2026-04-26T00:38:44Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- PaperTrade dataclass with 20 fields per D-06, mutable for cross-market P&L distribution
- simulate_yes_no() computes VWAP from PriceCache (D-02), runs kelly_size (D-08), applies depth-gated fill (D-07), calculates P&L with shares not dollars (D-09)
- paper_trades SQLite table with 20 data columns, autoincrement id, and 5 indexes for query optimization
- insert_paper_trade() with parameterized queries (T-05-02) and INSERT OR IGNORE for idempotency
- 12 new tests (7 simulator + 5 storage) all passing, full suite 224 passed

## Task Commits

Each task was committed atomically (TDD RED-GREEN):

1. **Task 1: PaperTrade dataclass and simulate_yes_no() (TDD)**
   - `c307eaf` (test: RED - 7 failing tests for PaperTrade and simulate_yes_no)
   - `fc10b26` (feat: GREEN - implement PaperTrade dataclass and simulate_yes_no)
2. **Task 2: paper_trades SQLite table and insert_paper_trade() (TDD)**
   - `02c178e` (test: RED - 5 failing tests for paper_trades table)
   - `0a5943f` (feat: GREEN - add paper_trades table and insert_paper_trade to schema)

## Files Created/Modified
- `src/bot/paper/__init__.py` - Package init (empty)
- `src/bot/paper/simulator.py` - PaperTrade dataclass (20 fields) and simulate_yes_no() pure function
- `src/bot/storage/schema.py` - paper_trades table DDL, 5 indexes, init_paper_trades_table(), insert_paper_trade()
- `tests/test_paper_simulator.py` - 7 unit tests for PaperTrade and simulate_yes_no
- `tests/test_paper_storage.py` - 5 unit tests for paper_trades table and insert_paper_trade

## Decisions Made
- PaperTrade is a non-frozen dataclass -- net_pnl_usd must be mutable for cross-market P&L distribution after all legs are computed (Plan 02 needs this, per A1 in RESEARCH.md)
- VWAP constructs single-element ask list from MarketPrice: `[{"price": mp.yes_ask, "size": mp.yes_depth}]` -- single-level book degenerates to best-ask when depth exceeds target size (Pitfall 1)
- P&L uses `effective_shares = min(yes_filled / vwap_yes, no_filled / vwap_no)` -- excess shares on one side are not hedged in YES/NO arb (Pitfall 2)
- INSERT OR IGNORE handles duplicate paper_trade_id gracefully -- first insertion wins

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PaperTrade dataclass and simulate_yes_no() ready for Plan 02 (cross-market simulation) to extend with simulate_cross_market()
- paper_trades table and insert_paper_trade() ready for Plan 02/03 to persist cross-market trades and run summary queries
- Full test suite green (224 passed, 5 skipped)

## Self-Check: PASSED

- All 5 created/modified files verified on disk
- All 4 task commits verified in git log (c307eaf, fc10b26, 02c178e, 0a5943f)
- All 21 acceptance criteria from plan verified via grep
- 12 new tests passing (7 simulator + 5 storage)
- Full test suite: 224 passed, 5 skipped

---
*Phase: 05-paper-trading-simulation*
*Completed: 2026-04-26*
