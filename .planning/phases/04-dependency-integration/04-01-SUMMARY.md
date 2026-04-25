---
phase: 04-dependency-integration
plan: 01
title: "BotConfig dependency fields, FilterDiagnostics counters, and WR-01/WR-02 bug fixes"
subsystem: detection
tags: [config, filters, dependency, bugfix, regression-tests]
dependency_graph:
  requires: [03-01, 03-02]
  provides: [BotConfig dependency fields, FilterDiagnostics dep counters, fixed _keyword_implication, fixed classify_pair partial dict handling]
  affects: [04-02]
tech_stack:
  added: []
  patterns: [dict merge for partial overrides, guard clause for equally-specific pattern matching]
key_files:
  created: []
  modified:
    - src/bot/config.py
    - src/bot/detection/filters.py
    - src/bot/detection/dependency.py
    - tests/test_dependency.py
decisions:
  - "D-13: _keyword_implication requires exactly ONE question to match child and the OTHER to match ONLY parent (not also child)"
  - "D-14: Partial weight/threshold dicts merge onto defaults via {**DEFAULT, **overrides}"
  - "Updated test_implication_reach_higher_implies_lower to reflect corrected WR-01 behavior (both 'reaches $X' are equally specific, implication=0.0)"
metrics:
  duration: "681s (~11 minutes)"
  completed: "2026-04-25T23:14:57Z"
  tasks: 2
  files_modified: 4
  tests_added: 5
  tests_updated: 1
  total_tests_passing: 206
requirements: [DEP-09, DEP-10, DEP-11]
---

# Phase 04 Plan 01: BotConfig Dependency Fields, Counters, and Bug Fixes Summary

BotConfig gains 8 dependency detection fields (5 weights, 2 thresholds, 1 audit mode bool), FilterDiagnostics gains 2 dependency counters, and two Phase 3 review bugs (WR-01 implication false positives, WR-02 partial dict KeyError) are fixed with 5 regression tests.

## What Was Done

### Task 1: BotConfig dependency fields and FilterDiagnostics counters
- Added 8 new fields to `BotConfig` frozen dataclass after existing `dedup_window_seconds`:
  - `dep_weight_jaccard: float = 0.20`
  - `dep_weight_implication: float = 0.15`
  - `dep_weight_numeric: float = 0.10`
  - `dep_weight_temporal: float = 0.30`
  - `dep_weight_event_bonus: float = 0.25`
  - `dep_threshold_subset: float = 0.50`
  - `dep_threshold_related: float = 0.30`
  - `dependency_audit_mode: bool = True`
- Added 2 new counter fields to `FilterDiagnostics` dataclass:
  - `dep_rejects: int = 0` (groups rejected in rejection mode)
  - `dep_audit_flags: int = 0` (groups flagged in audit mode)
- All fields have defaults so existing `_make_config()` test helpers continue to work unchanged
- **Commit:** `2b19813`

### Task 2: Fix WR-01 and WR-02 bugs (TDD)
- **RED:** 5 new regression tests added, 3 initially failing as expected
- **GREEN:** Fixed both bugs:
  - **WR-01:** `_keyword_implication` now checks that exactly ONE question matches the child pattern and the OTHER matches ONLY parent (not also child). This prevents equally-specific pairs like "Bitcoin reaches $150k?" / "ETH reaches $5k?" from both matching child+parent and falsely returning 1.0.
  - **WR-02:** `classify_pair` now merges partial weight/threshold dicts onto defaults using `{**DEFAULT_WEIGHTS, **weights}` pattern, so missing keys use defaults instead of raising KeyError.
- Updated pre-existing test `test_implication_reach_higher_implies_lower` -> `test_implication_reach_both_specific_no_implication` to reflect corrected behavior (both "reaches $X" are equally specific, implication correctly returns 0.0)
- **Commits:** RED `1129373`, GREEN `8e0c93f`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test that encoded buggy behavior**
- **Found during:** Task 2 GREEN phase
- **Issue:** `test_implication_reach_higher_implies_lower` asserted `score > 0.0` for two "reaches $X" questions, which was the old buggy behavior. Both "Bitcoin reaches $150k?" and "Bitcoin reaches $100k?" match the child pattern, so the WR-01 fix correctly returns 0.0 for this pair.
- **Fix:** Renamed test to `test_implication_reach_both_specific_no_implication` and updated assertion to `score == 0.0`. The numeric containment signal (not implication) handles this case.
- **Files modified:** `tests/test_dependency.py`
- **Commit:** `8e0c93f`

## Pre-existing Issues (Out of Scope)

- `tests/test_risk_gate.py::test_midnight_reset_clears_daily_loss` fails on the unmodified codebase (pre-existing bug in day-reset logic). Not related to this plan's changes.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| D-13: Guard clause `not b_child` / `not a_child` in implication | Prevents equally-specific pairs from false-firing; only genuine child->parent relationships detected |
| D-14: `{**DEFAULT, **overrides}` merge pattern | Standard Python idiom for partial overrides; missing keys use defaults without KeyError |
| Updated test to match corrected behavior | Old test encoded the bug; "reaches $150k" vs "reaches $100k" are equally specific, not parent-child |

## Verification Results

| Check | Result |
|-------|--------|
| `dep_weight_jaccard` in config.py | PASS (line 73) |
| `dep_rejects` in filters.py | PASS (line 96) |
| `not b_child` in dependency.py | PASS (line 146) |
| `DEFAULT_WEIGHTS, **weights` in dependency.py | PASS (line 305) |
| `pytest tests/test_dependency.py` | PASS (45 tests) |
| `pytest --ignore=test_risk_gate.py` (full suite) | PASS (206 passed, 5 skipped) |

## Self-Check: PASSED

All 5 files exist. All 3 commits verified (2b19813, 1129373, 8e0c93f).
