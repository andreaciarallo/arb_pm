---
phase: 06-group-structure-validation
fixed_at: 2026-04-26T19:15:00Z
review_path: .planning/phases/06-group-structure-validation/06-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-04-26T19:15:00Z
**Source review:** .planning/phases/06-group-structure-validation/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: `validate_groups()` never called -- GV gate blocks ALL cross-market detection

**Files modified:** `src/bot/dry_run.py`, `src/bot/live_run.py`
**Commit:** e9534ec
**Applied fix:** Added `from bot.detection.group_validator import validate_groups` import and a `validate_groups()` call (wrapped in try/except for non-fatal failure) immediately after `load_event_groups()` in both `dry_run.py` and `live_run.py`. This populates `_valid_groups` at startup so the GV gate in `cross_market.py` no longer rejects all groups with known event IDs.

### WR-01: `passes_completeness_check` silently ignores markets with unparseable prices

**Files modified:** `src/bot/detection/group_validator.py`
**Commit:** 427862a
**Applied fix:** Changed the bare `except (json.JSONDecodeError, ValueError): continue` to capture the exception and emit a `logger.warning()` with the raw `outcomePrices` value before continuing. This makes silent data corruption visible in logs.

### WR-02: Numeric threshold subset check may reject legitimate range-bucket groups

**Files modified:** `src/bot/detection/group_validator.py`
**Commit:** aa20ede
**Applied fix:** Added range-bucket detection in `is_subset_pair()`. Before flagging a pair as `numeric_threshold` subset, the fix checks whether either question matches a range-bucket pattern (digits separated by dash/en-dash, or the word "between"). If a range pattern is detected, the pair is not flagged as a subset -- range-bucket markets like "$50k-$60k" vs "$60k-$70k" are mutually exclusive partitions, not implication pairs. Added `import re` to support the pattern matching.

### WR-03: Lazy import inside hot-path detection loop

**Files modified:** `src/bot/detection/cross_market.py`
**Commit:** b1d7de5
**Applied fix:** Moved `from bot.detection.group_validator import get_valid_groups` from inside the `for group in groups:` loop body (line 235) to just before the loop (after `FilterDiagnostics()` initialization). The import remains lazy (inside the function, not at module level) to avoid the circular dependency, but now executes once per function call instead of once per group iteration.

---

_Fixed: 2026-04-26T19:15:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
