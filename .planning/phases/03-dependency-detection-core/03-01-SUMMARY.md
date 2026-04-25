---
phase: 03-dependency-detection-core
plan: 01
subsystem: detection
tags: [nlp, regex, jaccard, dependency-detection, pure-functions, tdd]

# Dependency graph
requires:
  - phase: 02-detection-quality-filters
    provides: "Pure function pattern (filters.py), frozen dataclass pattern (FilterDiagnostics), frozenset keyword matching (fee_model.py)"
provides:
  - "_preprocess: tokenization + stopword removal returning frozenset"
  - "_jaccard_similarity: set overlap signal [0.0, 1.0]"
  - "_keyword_implication: subset pattern matching signal [0.0, 1.0]"
  - "_numeric_relation: numeric threshold containment signal [0.0, 1.0]"
  - "_time_relation: deadline ordering signal [0.0, 1.0] covering 4 Polymarket date formats"
  - "_event_bonus: binary same-event signal"
  - "DependencyResult frozen dataclass with label, score, and 5 individual signal scores"
  - "DEFAULT_WEIGHTS and DEFAULT_THRESHOLDS constants"
affects: [03-02-PLAN, 04-dependency-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: ["pure signal extraction functions returning float [0.0, 1.0]", "compiled regex patterns at module level", "stdlib-only text processing (re, calendar, dataclasses)"]

key-files:
  created:
    - src/bot/detection/dependency.py
    - tests/test_dependency.py
  modified: []

key-decisions:
  - "Implication regex patterns use optional verb conjugation suffixes (reach|reaches, win|wins) to match real Polymarket question text"
  - "Date extraction uses a single compiled regex with alternation for all 4 Polymarket formats rather than separate passes"
  - "Numeric extraction uses priority cascade: percentages > dollar amounts > plain decimals"

patterns-established:
  - "Signal function pattern: private pure function taking original question strings, returning float [0.0, 1.0]"
  - "Preprocessing separation: only Jaccard uses preprocessed tokens; other signals operate on original strings (Pitfall 3 avoidance)"

requirements-completed: [DEP-01, DEP-02, DEP-03, DEP-04, DEP-05, DEP-06]

# Metrics
duration: 9min
completed: 2026-04-25
---

# Phase 3 Plan 1: Dependency Detection Signals Summary

**Five pure signal extraction functions (Jaccard, implication, numeric, temporal, event bonus) with TDD coverage using real Polymarket question patterns**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-25T17:31:49Z
- **Completed:** 2026-04-25T17:40:49Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Built preprocessing layer with stopword-stripping tokenization returning frozensets for set operations
- Implemented all 5 signal extractors as pure functions with float [0.0, 1.0] return values
- Created DependencyResult frozen dataclass with label, composite score, and 5 individual signal scores
- 25 unit tests covering DEP-01 through DEP-06 using real Polymarket question strings from Gamma API
- Full test suite green: 204 passed, 5 skipped, 0 failed
- T-03-02 regex DoS mitigation verified: adversarial 1210-char string processed in 0.0001s

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for preprocessing and all 5 signal functions (RED)** - `c008539` (test)
2. **Task 2: Implement preprocessing and all 5 signal functions to pass tests (GREEN)** - `0659635` (feat)

_TDD plan: RED then GREEN, no refactor needed._

## Files Created/Modified
- `src/bot/detection/dependency.py` - Preprocessing, 5 signal extractors, DependencyResult dataclass, DEFAULT_WEIGHTS/DEFAULT_THRESHOLDS constants (~250 lines)
- `tests/test_dependency.py` - 25 unit tests covering DEP-01 through DEP-06 plus DependencyResult dataclass validation (~170 lines)

## Decisions Made
- **Verb conjugation in implication regex:** Plan specified `reach\s+\$` but real Polymarket questions use "reaches $150k". Added optional suffixes (`reach(?:es)?`, `win(?:s)?`) to handle conjugated forms. This is a Rule 1 auto-fix (regex did not match expected input).
- **Single compiled regex for dates:** Used one `_DATE_PATTERN` with alternation groups rather than multiple separate passes, matching the RESEARCH.md code example pattern.
- **Numeric extraction priority:** Percentages checked before dollar amounts before plain decimals, preventing `$5` in "win by 5%" from being matched as a dollar amount.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed verb conjugation in implication regex patterns**
- **Found during:** Task 2 (GREEN phase, test_implication_reach_higher_implies_lower)
- **Issue:** Plan specified `reach\s+\$` but test used "Bitcoin reaches $150k?" -- the `es` suffix caused no match
- **Fix:** Changed patterns to `reach(?:es)?`, `win(?:s)?`, `beat(?:s)?`, `pass(?:es)?` to handle conjugated verb forms
- **Files modified:** src/bot/detection/dependency.py
- **Verification:** All 25 tests pass including test_implication_reach_higher_implies_lower
- **Committed in:** 0659635 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential for correctness -- regex must match real Polymarket question text patterns. No scope creep.

## Issues Encountered
None beyond the auto-fixed regex deviation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 5 signal functions ready for Plan 02 (weighted scorer + classifier)
- DependencyResult dataclass ready to be returned by classify_pair()
- DEFAULT_WEIGHTS and DEFAULT_THRESHOLDS constants defined for Plan 02 to consume
- Module is pure (zero scanner/execution/network imports) -- ready for Phase 4 integration

## Self-Check: PASSED

- [x] src/bot/detection/dependency.py exists
- [x] tests/test_dependency.py exists
- [x] 03-01-SUMMARY.md exists
- [x] Commit c008539 exists (Task 1 RED)
- [x] Commit 0659635 exists (Task 2 GREEN)

---
*Phase: 03-dependency-detection-core*
*Completed: 2026-04-25*
