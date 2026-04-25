---
phase: 02-detection-quality-filters
plan: 02
subsystem: detection
tags: [filters, dedup, detectors, quality, integration]

# Dependency graph
requires:
  - "02-01: Stateless filter functions, DedupTracker, FilterDiagnostics, BotConfig threshold fields"
provides:
  - "YES/NO detector with DETECT-01/02/05 quality gates and FilterDiagnostics return"
  - "Cross-market detector with DETECT-03/04/05 quality gates and FilterDiagnostics return"
  - "Updated detector tests covering filter rejection behavior and diagnostic counters"
affects: [02-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Detector functions return tuple[list[ArbitrageOpportunity], FilterDiagnostics]"
    - "Optional DedupTracker parameter for cross-cycle dedup suppression"
    - "Filter gates inserted before existing gates (DETECT-01/02 before resolved check, DETECT-03/04 before depth gate)"
    - "Dedup gate always last (before append) to avoid timestamping rejected opportunities"

key-files:
  created: []
  modified:
    - src/bot/detection/yes_no_arb.py
    - src/bot/detection/cross_market.py
    - src/bot/dry_run.py
    - src/bot/live_run.py
    - tests/test_yes_no_arb.py
    - tests/test_cross_market.py
    - tests/test_dry_run.py
    - tests/test_live_run.py

key-decisions:
  - "Filter gates placed BEFORE existing resolved/depth gates to reject dead markets early (saves fee computation)"
  - "Dedup gate placed LAST to avoid recording timestamps for quality-rejected opportunities (Pitfall 5 from research)"
  - "total_yes computed once before DETECT-04, reused by existing exclusivity check (removed duplicate computation)"

patterns-established:
  - "Detector return type is always tuple[list[ArbitrageOpportunity], FilterDiagnostics] -- callers must unpack"
  - "Filter diagnostic counters increment inline at each gate, then returned for cycle-level reporting"
  - "DedupTracker passed as optional parameter (None = no dedup), not module-level singleton"

requirements-completed: [DETECT-01, DETECT-02, DETECT-03, DETECT-04, DETECT-05]

# Metrics
duration: 12min
completed: 2026-04-25
---

# Phase 02 Plan 02: Detector Filter Integration Summary

**Wired DETECT-01 through DETECT-05 quality gates into both YES/NO and cross-market detectors with FilterDiagnostics return type, updated all 4 caller sites and 15 test mocks**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-25T15:11:30Z
- **Completed:** 2026-04-25T15:23:43Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Integrated DETECT-01 (ask floor) and DETECT-02 (sum cap) gates into YES/NO detector before existing resolved-market gate
- Integrated DETECT-03 (dead leg) and DETECT-04 (total YES floor) gates into cross-market detector before depth gate
- Added DETECT-05 dedup gate as final gate in both detectors (prevents timestamping rejected opportunities)
- Changed both detector return types to `tuple[list[ArbitrageOpportunity], FilterDiagnostics]`
- Updated all caller sites (dry_run.py, live_run.py) and all test mocks (test_dry_run.py, test_live_run.py)
- Added 6 new filter-specific tests (3 per detector) covering rejection behavior and diagnostic counter assertions
- All 59 affected tests passing (10 YES/NO + 11 cross-market + 23 filter + 3 dry_run + 12 live_run)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire filters into both detectors and change return types** - `aa84c62` (feat)
2. **Task 2: Update all detector tests for new return type and filter behavior** - `5964041` (test)
3. **Deviation: Update all callers for new detector return type** - `4cc9da8` (fix)

## Files Created/Modified
- `src/bot/detection/yes_no_arb.py` - Added DETECT-01/02/05 gates, import filters, return (opps, diag) tuple
- `src/bot/detection/cross_market.py` - Added DETECT-03/04/05 gates, import filters, return (opps, diag) tuple
- `src/bot/dry_run.py` - Updated caller to unpack (opps, diag) tuple
- `src/bot/live_run.py` - Updated caller to unpack (opps, diag) tuple
- `tests/test_yes_no_arb.py` - Updated 7 existing tests + added 3 new filter tests (10 total)
- `tests/test_cross_market.py` - Updated 8 existing tests + added 3 new filter tests (11 total)
- `tests/test_dry_run.py` - Updated 3 mocks to return (list, FilterDiagnostics) tuple
- `tests/test_live_run.py` - Updated 12 mocks to return (list, FilterDiagnostics) tuple

## Decisions Made
- Filter gates placed BEFORE existing resolved/depth gates -- rejects dead markets early, avoids unnecessary fee computation
- Dedup gate placed LAST (before append) -- prevents DedupTracker from recording timestamps on quality-rejected opportunities (Pitfall 5 from research)
- `total_yes = sum(yes_asks)` computed once before DETECT-04 gate, reused by existing exclusivity check (eliminated duplicate computation)
- INFO summary log updated to include `floor_rej`, `sum_rej`, `dedup` counters alongside existing `depth_fails` and `spread_fails`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated all caller sites for new return type**
- **Found during:** Task 2 (after committing test updates)
- **Issue:** Changing detector return types from `list` to `tuple[list, FilterDiagnostics]` breaks `dry_run.py` line 105, `live_run.py` line 300, and all 15 test mocks in `test_dry_run.py` and `test_live_run.py` (Pitfall 6 from research)
- **Fix:** Updated `dry_run.py` and `live_run.py` to unpack `opps, diag = detect_*()`. Updated all test mocks from `return_value=[]` to `return_value=([], FilterDiagnostics())`.
- **Files modified:** `src/bot/dry_run.py`, `src/bot/live_run.py`, `tests/test_dry_run.py`, `tests/test_live_run.py`
- **Verification:** All 59 tests pass including 3 dry_run + 12 live_run async tests
- **Committed in:** `4cc9da8`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix -- without it, bot would crash at runtime with `TypeError: cannot unpack non-sequence list`. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both detectors now enforce all 5 DETECT requirements (DETECT-01 through DETECT-05)
- FilterDiagnostics returned from both detectors, ready for cycle-level summary logging in Plan 03
- DedupTracker parameter available but not yet instantiated in dry_run.py/live_run.py scan loops (Plan 03 scope)
- All 59 tests green, no regressions

## Self-Check: PASSED

- [x] src/bot/detection/yes_no_arb.py -- FOUND
- [x] src/bot/detection/cross_market.py -- FOUND
- [x] src/bot/dry_run.py -- FOUND
- [x] src/bot/live_run.py -- FOUND
- [x] tests/test_yes_no_arb.py -- FOUND
- [x] tests/test_cross_market.py -- FOUND
- [x] tests/test_dry_run.py -- FOUND
- [x] tests/test_live_run.py -- FOUND
- [x] Commit aa84c62 -- FOUND
- [x] Commit 5964041 -- FOUND
- [x] Commit 4cc9da8 -- FOUND

---
*Phase: 02-detection-quality-filters*
*Completed: 2026-04-25*
