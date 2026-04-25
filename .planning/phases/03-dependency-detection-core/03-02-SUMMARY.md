---
phase: 03-dependency-detection-core
plan: 02
subsystem: detection
tags: [weighted-scorer, classifier, validation-set, tdd, pure-functions]

# Dependency graph
requires:
  - phase: 03-dependency-detection-core
    plan: 01
    provides: "_preprocess, _jaccard_similarity, _keyword_implication, _numeric_relation, _time_relation, _event_bonus, DependencyResult, DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS"
provides:
  - "classify_pair: public API function combining 5 weighted signals into three-way classification"
  - "Complete dependency detection module ready for Phase 4 integration"
affects: [04-dependency-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: ["weighted linear combination scoring", "two-threshold three-way classification", "validation set testing against real Polymarket question pairs"]

key-files:
  created: []
  modified:
    - src/bot/detection/dependency.py
    - tests/test_dependency.py

key-decisions:
  - "Weights tuned: temporal=0.30 (highest, deadline variants dominate), event_bonus=0.25, jaccard=0.20 (reduced per Pitfall 1), implication=0.15, numeric=0.10"
  - "Thresholds lowered: subset>=0.50 and related>=0.30 (calibrated against 7 real Polymarket validation pairs)"
  - "Fixed _DATE_PATTERN regex with word boundary to prevent 'Bitcoin' suffix matching as 'in' prefix"

patterns-established:
  - "Validation set testing: real Polymarket question strings from Gamma API as ground truth for classification correctness"
  - "Weight/threshold tuning documented with margin analysis in code comments"

requirements-completed: [DEP-07, DEP-08]

# Metrics
duration: 9min
completed: 2026-04-25
---

# Phase 3 Plan 2: Weighted Scorer and Classifier Summary

**classify_pair() public API with weighted 5-signal scoring and three-way classification, validated against 7 real Polymarket question pairs**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-25T17:47:42Z
- **Completed:** 2026-04-25T17:56:40Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Built `classify_pair()` as the single public function of the dependency detection module
- Weighted linear combination of 5 signals (Jaccard, implication, numeric, temporal, event bonus) into composite score
- Three-way classification: subset (>= 0.50), related (>= 0.30), independent (< 0.30)
- Validated against 7 real Polymarket question pairs: 3 subset (deadline variants), 2 related (candidate variants), 2 independent (cross-domain)
- Candidate-variant pairs correctly classified as "related" not "subset" (Pitfall 1 avoided)
- 40 unit tests passing (25 existing DEP-01-06 + 15 new DEP-07-08)
- Full test suite green: 219 passed, 5 skipped, 0 failed
- Module remains pure: zero scanner/execution/network imports

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for weighted scorer and classifier (RED)** - `b262876` (test)
2. **Task 2: Implement classify_pair to pass all tests (GREEN)** - `80cac71` (feat)

_TDD plan: RED then GREEN, no refactor needed._

## Files Created/Modified
- `src/bot/detection/dependency.py` - Added classify_pair() function (~60 lines), tuned DEFAULT_WEIGHTS and DEFAULT_THRESHOLDS, fixed _DATE_PATTERN regex word boundary
- `tests/test_dependency.py` - Added 15 new tests: 4 scorer tests (DEP-07) + 11 classifier tests with validation set (DEP-08)

## Decisions Made
- **Weight tuning:** Temporal signal gets highest weight (0.30) because most Polymarket multi-market events are deadline variants. Event bonus second (0.25) for candidate-variant discrimination. Jaccard reduced to 0.20 to prevent Pitfall 1 (high Jaccard alone pushing candidate-style pairs to "subset").
- **Threshold calibration:** subset >= 0.50 (deadline variants score 0.58-0.68), related >= 0.30 (candidate variants score 0.34-0.39), independent < 0.30 (cross-domain pairs score 0.02-0.04). All validation pairs have positive margins from their nearest boundary.
- **Regex word boundary:** Added `\b` before `(?:by|in|before)` in `_DATE_PATTERN` to prevent "Bitcoin" ending in "in" from triggering date extraction.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed _DATE_PATTERN regex missing word boundary**
- **Found during:** Task 2 (analysis of signal values for validation set)
- **Issue:** `_DATE_PATTERN` regex `(?:by|in|before)` matched the "in" suffix of "Bitcoin", causing "Bitcoin in 2025?" to incorrectly match as "Bitco[in] [in 20]25" instead of correctly extracting "(2025, 12, 31)"
- **Fix:** Changed `(?:by|in|before)` to `\b(?:by|in|before)` to enforce word boundary
- **Files modified:** src/bot/detection/dependency.py
- **Verification:** All 40 tests pass; "MicroStrategy sells any Bitcoin in 2025?" correctly extracts date (2025, 12, 31)
- **Committed in:** 80cac71 (Task 2 commit)

**2. [Rule 2 - Missing critical functionality] Tuned DEFAULT_WEIGHTS and DEFAULT_THRESHOLDS**
- **Found during:** Task 2 (validation set score analysis)
- **Issue:** Original weights (jaccard=0.30, temporal=0.15) and thresholds (subset=0.70, related=0.35) caused all 3 subset pairs to be misclassified as "related" and 1 related pair as "independent"
- **Fix:** Rebalanced weights to temporal=0.30, event_bonus=0.25, jaccard=0.20 and lowered thresholds to subset=0.50, related=0.30. Plan explicitly anticipated this: "If any validation test fails, adjust DEFAULT_WEIGHTS or DEFAULT_THRESHOLDS"
- **Files modified:** src/bot/detection/dependency.py
- **Verification:** All 7 validation pairs correctly classified with positive margins
- **Committed in:** 80cac71 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 critical functionality)
**Impact on plan:** Both fixes were essential for correctness. The regex bug was pre-existing from Plan 01 but only surfaced with the validation set. Weight/threshold tuning was anticipated by the plan.

## Issues Encountered
None beyond the auto-fixed deviations.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `classify_pair()` is the complete public API for Phase 4 integration
- Module exports: `classify_pair`, `DependencyResult`, `DEFAULT_WEIGHTS`, `DEFAULT_THRESHOLDS`
- Module is pure (zero scanner/execution/network imports) -- safe to import from cross_market.py
- Phase 4 can pass `event_id` from `_event_groups` dict and optional weight/threshold overrides from BotConfig

## Self-Check: PASSED

- [x] src/bot/detection/dependency.py exists
- [x] tests/test_dependency.py exists
- [x] 03-02-SUMMARY.md exists
- [x] Commit b262876 exists (Task 1 RED)
- [x] Commit 80cac71 exists (Task 2 GREEN)

---
*Phase: 03-dependency-detection-core*
*Completed: 2026-04-25*
