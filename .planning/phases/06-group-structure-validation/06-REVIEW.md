---
phase: 06-group-structure-validation
reviewed: 2026-04-26T18:42:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - src/bot/detection/cross_market.py
  - src/bot/detection/filters.py
  - src/bot/detection/group_validator.py
  - src/bot/dry_run.py
  - tests/test_cross_market.py
  - tests/test_event_info.py
  - tests/test_group_validator.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-04-26T18:42:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 6 introduces group structure validation (`group_validator.py`) for Polymarket event groups, enriches `_event_groups` with an `EventInfo` frozen dataclass, and adds a GV gate in the cross-market detection loop. The `filters.py` module is clean and well-structured. Test coverage is solid for the validator logic itself.

However, there is one critical integration gap: `validate_groups()` is never called at startup in the dry-run (or live-run) entry point. This means `_valid_groups` remains an empty set, and the GV gate in `cross_market.py` silently rejects ALL cross-market groups with a known event ID -- completely disabling cross-market arbitrage detection in production.

## Critical Issues

### CR-01: `validate_groups()` never called -- GV gate blocks ALL cross-market detection

**File:** `src/bot/dry_run.py:76-78`
**Issue:** The detection loop in `cross_market.py:239` checks `if eid and eid not in get_valid_groups()` and rejects groups not in `_valid_groups`. But `_valid_groups` is initialized as an empty `set()` (in `group_validator.py:25`) and is only populated when `validate_groups()` is called. Neither `dry_run.py` nor any other entry point calls `validate_groups()` after `load_event_groups()`. Consequently, every group with a resolved `eid` (i.e., every group that has Gamma API data) hits `eid not in get_valid_groups()` == `True` and is rejected. This silently disables ALL cross-market arbitrage detection.

The test suite does not catch this because `test_cross_market.py` uses `_patch_valid_groups()` to manually inject valid event IDs, bypassing the real startup flow.

**Fix:** Call `validate_groups()` in `dry_run.py` (and `live_run.py`) immediately after `load_event_groups()`:

```python
# In dry_run.py, after line 78:
from bot.detection.group_validator import validate_groups

try:
    load_event_groups()
except Exception as exc:  # pragma: no cover
    logger.warning(f"load_event_groups startup call failed: {exc}")

# Validate loaded groups (GV gate requires this)
try:
    valid = validate_groups()
    logger.info(f"Group validation: {len(valid)} valid event groups")
except Exception as exc:  # pragma: no cover
    logger.warning(f"validate_groups startup call failed: {exc}")
```

## Warnings

### WR-01: `passes_completeness_check` silently ignores markets with unparseable prices

**File:** `src/bot/detection/group_validator.py:94-95`
**Issue:** When `json.loads(outcome_prices_raw)` raises `JSONDecodeError`, the market is silently skipped via `continue`. Its YES price contributes 0 to `mid_sum`. In a 3-market group where one market has corrupt `outcomePrices`, the `mid_sum` will be artificially low (e.g., 0.7 instead of 1.0), potentially causing a valid group to fail the completeness check. There is no log or counter for this case.

**Fix:** Log a warning when a market's prices cannot be parsed, and consider whether the group should be skipped entirely rather than computed with incomplete data:

```python
except (json.JSONDecodeError, ValueError) as exc:
    logger.warning(
        f"GV: unparseable outcomePrices for market in group: {outcome_prices_raw!r}"
    )
    continue
```

### WR-02: Numeric threshold subset check may reject legitimate range-bucket groups

**File:** `src/bot/detection/group_validator.py:66-70`
**Issue:** The `is_subset_pair` function flags any two questions with Jaccard > 0.6 and different numeric values as a "subset" relationship. This is correct for threshold-style markets ("BTC reaches $100k" implies "BTC reaches $50k"), but Polymarket also has legitimate one-of-N range-bucket events like "BTC price at year end: $50k-$60k" vs "$60k-$70k" vs "$70k-$80k". These are mutually exclusive (exactly one resolves YES) but would be flagged as subsets because they share most tokens and have different numbers. This would incorrectly reject valid arbitrage groups.

**Fix:** Consider checking whether the numeric values have a containment relationship (one is strictly greater), not just whether they differ. Alternatively, exempt NegRisk groups from this check (they already auto-pass via GV-01), and for non-NegRisk groups, require that the implication direction is confirmed (e.g., the market with the higher threshold should have a lower price):

```python
# Only flag as subset if one number contains the other
# (threshold-style: $100k implies $50k, but $50k-$60k does NOT imply $60k-$70k)
if num_a is not None and num_b is not None and num_a != num_b:
    # Check if questions look like range buckets (contain "-" or "between")
    if not re.search(r'\d+\s*[-–]\s*\d+|between', question_a, re.I) and \
       not re.search(r'\d+\s*[-–]\s*\d+|between', question_b, re.I):
        return True, "numeric_threshold"
```

### WR-03: Lazy import inside hot-path detection loop

**File:** `src/bot/detection/cross_market.py:235`
**Issue:** `from bot.detection.group_validator import get_valid_groups` is inside the `for group in groups:` loop body. While Python's import system caches modules after the first import (so subsequent iterations hit the cache), the import machinery still performs a dictionary lookup and module-attribute access on every iteration. The comment says it avoids circular dependency, but the import could be moved to just above the loop (still inside the function, still lazy) to avoid per-iteration overhead.

**Fix:** Move the import above the loop:

```python
# Move from line 235 to just before line 173 (before the for loop)
from bot.detection.group_validator import get_valid_groups

for group in groups:
    # ... existing code ...
    if eid and eid not in get_valid_groups():
        diag.gv_rejects += 1
        continue
```

## Info

### IN-01: `datetime.utcnow()` is deprecated since Python 3.12

**File:** `src/bot/detection/cross_market.py:287`
**Issue:** `datetime.utcnow()` has been deprecated since Python 3.12 in favor of `datetime.now(datetime.timezone.utc)`. The project targets Python 3.10+ so this works but will emit deprecation warnings on 3.12+.

**Fix:** Replace with timezone-aware equivalent:

```python
from datetime import datetime, timezone

detected_at=datetime.now(timezone.utc),
```

### IN-02: Test cleanup relies on manual try/finally rather than pytest fixtures

**File:** `tests/test_cross_market.py:119-131`, `tests/test_group_validator.py:18-44`
**Issue:** Every test in `test_cross_market.py` manually calls `_patch_event_groups` / `_patch_valid_groups` with try/finally restoration. This pattern is repeated 10+ times. A `@pytest.fixture(autouse=False)` or explicit fixture would reduce boilerplate and eliminate the risk of forgetting cleanup in future tests. The `test_group_validator.py` tests use `_setup_test_data` / `_cleanup` which is slightly better but still manual.

**Fix:** Convert to pytest fixtures:

```python
@pytest.fixture
def event_groups():
    """Fixture that auto-restores _event_groups and _valid_groups after test."""
    import bot.detection.cross_market as cm
    import bot.detection.group_validator as gv
    orig_eg = dict(cm._event_groups)
    orig_vg = set(gv._valid_groups)
    yield cm, gv
    cm._event_groups.clear()
    cm._event_groups.update(orig_eg)
    gv._valid_groups.clear()
    gv._valid_groups.update(orig_vg)
```

---

_Reviewed: 2026-04-26T18:42:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
