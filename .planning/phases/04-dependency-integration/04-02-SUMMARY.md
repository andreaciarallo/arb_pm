---
phase: 04-dependency-integration
plan: 02
title: "Wire dependency gate into cross-market detector with integration tests"
subsystem: detection
tags: [dependency, cross-market, integration, audit-mode, rejection-mode]
dependency_graph:
  requires: [04-01]
  provides: [dependency gate in cross-market detector, audit/rejection modes, cycle summary dep counters]
  affects: [dry_run cycle logging, cross-market detection accuracy]
tech_stack:
  added: []
  patterns: [itertools.combinations for within-group pair generation, break-on-first-match for group flagging]
key_files:
  created: []
  modified:
    - src/bot/detection/cross_market.py
    - src/bot/dry_run.py
    - tests/test_cross_market.py
decisions:
  - "Dependency gate placed after DETECT-04 (total_yes floor) and before depth gate, per D-09"
  - "Weight/threshold dicts built once outside group loop from BotConfig fields, per D-12"
  - "Break after first non-independent pair per group (D-07) -- one is enough to flag"
  - "DEP-AUDIT at INFO level, DEP-REJECT at DEBUG level, per D-05/D-06"
  - "dep_audit_flags and dep_rejects counted per GROUP not per pair, per D-08"
metrics:
  duration: "459s (~8 minutes)"
  completed: "2026-04-25T23:28:02Z"
  tasks: 2
  files_modified: 3
  tests_added: 6
  total_tests_passing: 212
requirements: [DEP-09, DEP-10, DEP-11]
---

# Phase 04 Plan 02: Wire Dependency Gate into Cross-Market Detector Summary

Dependency detection classify_pair() wired into cross-market detector with itertools.combinations pair generation, dual audit/rejection modes, DEP-AUDIT/DEP-REJECT logging, and 6 integration tests covering all modes and edge cases.

## What Was Done

### Task 1: Wire dependency gate into cross_market.py and update dry_run.py

- Added `import itertools` and `from bot.detection.dependency import classify_pair` to cross_market.py
- Built `dep_weights` and `dep_thresholds` dicts from BotConfig fields once before the group loop (D-12)
- Inserted dependency gate between DETECT-04 (total_yes floor) and depth gate (D-09):
  - Uses `itertools.combinations(group, 2)` for within-group C(N,2) pair generation (DEP-09)
  - Calls `classify_pair()` with question strings and event_id from `_event_groups`
  - Audit mode (default): logs `DEP-AUDIT:` at INFO with full signal breakdown, increments `diag.dep_audit_flags`, does NOT reject group (DEP-10)
  - Rejection mode: logs `DEP-REJECT:` at DEBUG, increments `diag.dep_rejects`, skips group via `continue` (DEP-11)
  - Breaks after first non-independent pair per group (D-07)
- Updated dry_run.py cycle summary to include `dep_flags=N dep_rejects=N` counters
- All 11 existing cross_market tests continue to pass
- **Commit:** `753854a`

### Task 2: Add 6 integration tests for dependency gate

- `test_dependency_audit_mode_logs_not_rejects`: Deadline-variant pair (subset) in audit mode -- group flagged but NOT rejected, opportunity produced, `dep_audit_flags=1`
- `test_dependency_rejection_mode_rejects_group`: Same pair with `dependency_audit_mode=False` -- group rejected, zero opportunities, `dep_rejects=1`
- `test_dependency_independent_pairs_pass_through`: Unrelated questions ("Acme stock" / "Mars colony") in same event -- independent classification, no flags, opportunity produced even in rejection mode
- `test_dependency_pairs_scoped_within_group`: Two separate event groups -- deadline variants in group A rejected, independent questions in group B pass through independently
- `test_dependency_diagnostics_dep_counters`: Empty market list produces `dep_rejects=0, dep_audit_flags=0`
- `test_dependency_audit_log_format`: Captures loguru stderr output, verifies `DEP-AUDIT:` prefix with `score=` and `jaccard=` signal values
- Full suite: 212 passed, 5 skipped
- **Commit:** `67f7ff0`

## Deviations from Plan

None -- plan executed exactly as written.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Gate after DETECT-04, before depth (D-09) | Avoids wasting classify_pair CPU on groups that fail cheap price checks |
| Build weight/threshold dicts once outside loop (D-12) | Avoids per-group dict construction overhead |
| Break on first non-independent pair (D-07) | One non-independent pair is enough to flag/reject entire group |
| Independent test uses unrelated questions | "Acme stock soar" / "Mars colony succeed" have Jaccard=0.0 and event_bonus=0.25 (score=0.250 < 0.30 threshold) ensuring independent classification |

## Verification Results

| Check | Result |
|-------|--------|
| `itertools.combinations` in cross_market.py | PASS (line 220) |
| `DEP-AUDIT` in cross_market.py | PASS (line 232) |
| `dep_flags` in dry_run.py | PASS (line 125) |
| 6 dependency tests in test_cross_market.py | PASS |
| `pytest tests/test_cross_market.py` | PASS (17 tests) |
| `pytest --ignore=test_risk_gate.py` (full suite) | PASS (212 passed, 5 skipped) |

## Self-Check: PASSED

All 3 modified files exist. All 2 commits verified (753854a, 67f7ff0).
