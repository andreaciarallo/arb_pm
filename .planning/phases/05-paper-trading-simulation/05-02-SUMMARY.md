---
phase: 05-paper-trading-simulation
plan: 02
subsystem: paper-trading
tags: [cross-market, simulation, hedge, writer, dry-run, tdd]

# Dependency graph
requires:
  - phase: 05-paper-trading-simulation
    plan: 01
    provides: PaperTrade dataclass, simulate_yes_no(), paper_trades table, insert_paper_trade()
  - phase: 03-execution-risk-controls
    provides: simulate_vwap(), kelly_size(), _execute_cross_market() pattern
provides:
  - simulate_cross_market() pure function with equal-shares sizing, hedge logic
  - PaperTradeWriter async queue for paper_trades inserts
  - dry_run.py paper trade integration (inline after detection)
affects: [05-03-summary-queries]

# Tech tracking
tech-stack:
  added: []
  patterns: [equal-shares-sizing, sequential-hedge-on-partial, async-writer-clone]

key-files:
  created:
    - src/bot/paper/writer.py
  modified:
    - src/bot/paper/simulator.py
    - src/bot/dry_run.py
    - tests/test_paper_simulator.py

key-decisions:
  - "Equal shares sizing: target_shares = kelly_usd / total_yes (D-10)"
  - "Sequential leg execution with hedge at $0.01 on partial fill (D-11)"
  - "Fully-filled P&L: gross_pnl = (1.0 - total_yes) * target_shares (D-12)"
  - "Hedge rows have estimated_fees_usd=0.0 (fire-sale, no fee charge)"
  - "PaperTradeWriter is a clean copy of AsyncWriter, not a subclass (avoid coupling)"
  - "Paper simulation runs inline in dry_run.py after detection, before opp write (D-01)"

patterns-established:
  - "Cross-market simulator mirrors live _execute_cross_market() pattern but deterministic"
  - "Paper trade counters in cycle summary log for monitoring"

requirements-completed: [PAPER-01, PAPER-04]

# Metrics
duration: ~15min
completed: 2026-04-26
---

# Phase 5 Plan 2: Cross-Market Simulation & Dry-Run Wiring Summary

**simulate_cross_market() with equal-shares sizing, depth-gated partial fill with hedge, PaperTradeWriter, and full dry_run.py integration**

## Performance

- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- simulate_cross_market() with equal-shares sizing (D-10), sequential leg execution, depth-gated fill (D-07), hedge at $0.01 for all filled legs on partial failure (D-11)
- Fully-filled P&L: gross_pnl = (1.0 - total_yes) * target_shares (D-12), distributed evenly across legs
- PaperTradeWriter async queue cloned from AsyncWriter pattern, calls insert_paper_trade
- dry_run.py integration: init_paper_trades_table at startup, simulate_yes_no/simulate_cross_market inline after detection, paper_writer.enqueue for persistence
- Cycle summary logs paper_trades and kelly_skips counters
- 6 new cross-market tests (13 total simulator tests) all passing

## Task Commits

1. **Task 1: simulate_cross_market() and PaperTradeWriter (TDD)**
   - `f734955` (feat: implement cross-market simulation, PaperTradeWriter, and dry_run wiring)

## Files Created/Modified
- `src/bot/paper/simulator.py` - Added simulate_cross_market() (171 lines)
- `src/bot/paper/writer.py` - PaperTradeWriter async queue (92 lines)
- `src/bot/dry_run.py` - Paper trade imports, init, simulation loop, counters, shutdown
- `tests/test_paper_simulator.py` - 6 new cross-market tests + _make_cross_opp helper

## Deviations from Plan

Tasks 1 and 2 were committed together (single commit instead of separate RED/GREEN commits) due to execution recovery after context reset. All functionality and tests match the plan specification.

## Issues Encountered
None

---
*Phase: 05-paper-trading-simulation*
*Completed: 2026-04-26*
