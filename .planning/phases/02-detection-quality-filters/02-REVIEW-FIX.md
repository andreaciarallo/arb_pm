---
phase: 02-detection-quality-filters
fixed_at: 2026-04-25T14:45:00Z
review_path: .planning/phases/02-detection-quality-filters/02-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-04-25T14:45:00Z
**Source review:** .planning/phases/02-detection-quality-filters/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0

## Fixed Issues

### WR-01: YES/NO fee model missing exit fee on $1.00 resolution payout

**Files modified:** `src/bot/detection/yes_no_arb.py`
**Commit:** ae934de
**Applied fix:** Split `estimated_fees` into explicit `entry_fees` (taker fee on YES + NO token buys) and `exit_fee` (taker fee on the winning position's $1.00 payout at resolution). Previously only entry fees were accounted for, underestimating total fees by `1.0 * taker_fee` per contract. This is a logic fix: requires human verification.

### WR-02: Cross-market fee model uses incorrect exit fee basis

**Files modified:** `src/bot/detection/cross_market.py`
**Commit:** 80a953c
**Applied fix:** Changed exit fee calculation from `(total_yes / len(group)) * taker_fee` (average entry cost basis) to `1.0 * taker_fee` (actual $1.00 payout basis). The previous formula used the average entry cost per leg as the fee basis, but the actual taxable event is the winning position resolving at $1.00 per share. This is a logic fix: requires human verification.

### WR-03: load_event_groups() does not paginate beyond 500 events

**Files modified:** `src/bot/detection/cross_market.py`
**Commit:** 2422dac
**Applied fix:** Wrapped the single Gamma API call in a pagination loop using `offset` parameter. Fetches pages of 500 events each until an empty page or a page smaller than `page_size` is returned. This ensures all active events are loaded into `_event_groups`, preventing silent detection gaps for events beyond the first 500.

### WR-04: Kill switch Telegram alert may be cancelled before delivery

**Files modified:** `src/bot/live_run.py`
**Commit:** 5deacee
**Applied fix:** Replaced fire-and-forget `asyncio.create_task()` with `await asyncio.wait_for(..., timeout=5.0)` wrapped in try/except. The alert is now awaited (with a 5-second timeout) before proceeding with kill switch execution, ensuring the operator receives the notification. If the alert fails or times out, a warning is logged and the kill switch proceeds regardless.

### WR-05: DedupTracker memory grows unbounded without periodic pruning

**Files modified:** `src/bot/dry_run.py`, `src/bot/live_run.py`
**Commit:** 2bf7fb3
**Applied fix:** Added periodic `dedup.prune()` call every 100 scan cycles in both `dry_run.py` and `live_run.py` run loops, placed after the cycle counter increment. Pruned count is logged at DEBUG level when entries are removed. This prevents the `_seen` dictionary from growing indefinitely during long-running sessions.

## Skipped Issues

None -- all findings were fixed.

---

_Fixed: 2026-04-25T14:45:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
