---
phase: 02-detection-quality-filters
reviewed: 2026-04-25T14:32:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - src/bot/detection/filters.py
  - src/bot/config.py
  - src/bot/detection/yes_no_arb.py
  - src/bot/detection/cross_market.py
  - src/bot/dry_run.py
  - src/bot/live_run.py
  - tests/test_filters.py
  - tests/test_yes_no_arb.py
  - tests/test_cross_market.py
  - tests/test_dry_run.py
  - tests/test_live_run.py
findings:
  critical: 0
  warning: 5
  info: 2
  total: 7
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-04-25T14:32:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Reviewed the detection quality filter pipeline (DETECT-01 through DETECT-05), the YES/NO and cross-market arbitrage detectors, both run loops (dry/live), and all associated test files. The filter functions in `filters.py` are clean -- pure, stateless, well-tested. The `DedupTracker` and `FilterDiagnostics` are well-designed. Test coverage is thorough with good boundary-value testing.

The primary concern is a **fee model underestimation bug** present in both detection engines: neither `yes_no_arb.py` nor `cross_market.py` correctly accounts for the exit/redemption taker fee on the winning position's $1.00 payout. This could cause the detectors to signal profitable opportunities that are actually unprofitable after all fees, leading to real losses in live mode. A second concern is missing pagination in `load_event_groups()` which could cause silent detection gaps. There is also a fire-and-forget alert task in `live_run.py` that risks being cancelled before delivery.

## Warnings

### WR-01: YES/NO fee model missing exit fee on $1.00 resolution payout

**File:** `src/bot/detection/yes_no_arb.py:130`
**Issue:** The estimated fees calculation only accounts for entry fees (buying YES and NO tokens) but omits the exit fee charged when the winning position pays out $1.00 at resolution. The current formula is `estimated_fees = (yes_ask + no_ask) * taker_fee`, but the correct total should include the exit fee on the $1.00 payout: `taker_fee * (1.0 + yes_ask + no_ask)`. For a politics market (1.0% fee), this underestimates fees by $0.01 per contract. For crypto (1.8%), it is $0.018. This missing fee could cause the detector to flag opportunities as profitable when they are actually below the profit threshold after full fee accounting, leading to unprofitable trades in live mode.
**Fix:**
```python
# Line 130: Include exit fee on the winning position's $1.00 payout
entry_fees = (yes_ask + no_ask) * taker_fee
exit_fee = 1.0 * taker_fee  # winner pays out $1.00, taxed at taker rate
estimated_fees = entry_fees + exit_fee
```

### WR-02: Cross-market fee model uses incorrect exit fee basis

**File:** `src/bot/detection/cross_market.py:212`
**Issue:** The exit fee is calculated as `(total_yes / len(group)) * taker_fee`, which uses the average entry cost per leg as the fee basis. But the actual exit event is the winning position resolving/selling at $1.00 per share, so the exit fee should be `1.0 * taker_fee`. When `total_yes` is much less than `len(group)` (e.g., 3-way race with total_yes = 0.75, average = 0.25), the current formula yields `0.25 * taker_fee` instead of the correct `1.0 * taker_fee`, underestimating exit fees by 4x in this example.
**Fix:**
```python
# Lines 211-213: Fix exit fee to use actual payout value
entry_fees = total_yes * taker_fee
exit_fee = 1.0 * taker_fee  # winning leg resolves at $1.00
estimated_fees = entry_fees + exit_fee
```

### WR-03: load_event_groups() does not paginate beyond 500 events

**File:** `src/bot/detection/cross_market.py:62`
**Issue:** The Gamma API request uses `limit=500` but never fetches subsequent pages. If Polymarket has more than 500 active events, any events beyond the first page will not be loaded into `_event_groups`, causing their markets to silently fall through to the `neg_risk_market_id` fallback. Standard binary markets without NegRisk in those missed events will have no grouping at all, meaning legitimate cross-market arbitrage opportunities will go undetected. The project memory notes the CLOB has 44k+ markets, so >500 events is plausible.
**Fix:**
```python
def load_event_groups(condition_ids: list[str] | None = None) -> None:
    global _event_groups
    try:
        offset = 0
        page_size = 500
        count = 0
        while True:
            params: dict = {"active": "true", "limit": page_size, "offset": offset}
            resp = httpx.get(_GAMMA_EVENTS_URL, params=params, timeout=10.0)
            resp.raise_for_status()
            events = resp.json()
            if not events:
                break
            for event in events:
                event_id = str(event.get("id", ""))
                if not event_id:
                    continue
                for market in event.get("markets", []):
                    cid = market.get("conditionId") or market.get("condition_id", "")
                    if cid:
                        _event_groups[cid] = event_id
                        count += 1
            offset += page_size
            if len(events) < page_size:
                break
        logger.info(
            f"load_event_groups: loaded {len(_event_groups)} condition_id->event_id "
            f"mappings ({count} from gamma API)"
        )
    except Exception as exc:
        logger.warning(f"load_event_groups: gamma API fetch failed: {exc}")
```

### WR-04: Kill switch Telegram alert may be cancelled before delivery

**File:** `src/bot/live_run.py:284`
**Issue:** The kill switch alert is dispatched via `asyncio.create_task(alerter.send_kill_switch(...))` on line 284, immediately followed by `await _execute_kill_switch(...)` and `break`. In the `finally` block (lines 445-458), all background tasks are cancelled. If the Telegram HTTP request takes longer than the kill switch execution, the alert task will be cancelled before the message is sent. This means the operator may not receive notification of a kill switch activation -- precisely the moment when notification matters most.
**Fix:**
```python
# Line 284-286: Await the alert before proceeding with kill switch
try:
    await asyncio.wait_for(alerter.send_kill_switch(trigger=_kill_trigger_ref[0]), timeout=5.0)
except (asyncio.TimeoutError, Exception) as exc:
    logger.warning(f"Kill switch alert failed: {exc}")
await _execute_kill_switch(client, conn, writer)
break
```

### WR-05: DedupTracker memory grows unbounded without periodic pruning

**File:** `src/bot/detection/filters.py:43-81` / `src/bot/dry_run.py:75` / `src/bot/live_run.py:257`
**Issue:** `DedupTracker` has a `prune()` method, but neither `dry_run.py` nor `live_run.py` ever calls it. The `_seen` dictionary grows indefinitely as new (market_id, opp_type) keys accumulate across scan cycles. Over a 24h dry-run or indefinite live-run with thousands of markets, this dictionary will hold entries for every unique opportunity ever detected, even after they expire. While each entry is small (~100 bytes), running for days with 44k+ markets could accumulate significant dead entries.
**Fix:**
Add a periodic prune call in both run loops, e.g., every 100 cycles:
```python
# In the scan loop, after detection:
if cycle % 100 == 0:
    pruned = dedup.prune()
    if pruned:
        logger.debug(f"Dedup pruned {pruned} expired entries")
```

## Info

### IN-01: Unused parameter `condition_ids` in load_event_groups()

**File:** `src/bot/detection/cross_market.py:51`
**Issue:** The `condition_ids` parameter is accepted but never referenced in the function body. It was likely intended for optional filtering but was not implemented.
**Fix:** Either implement filtering logic or remove the parameter:
```python
def load_event_groups() -> None:
```

### IN-02: datetime.utcnow() is deprecated since Python 3.12

**File:** `src/bot/detection/yes_no_arb.py:155`, `src/bot/detection/cross_market.py:239`, `src/bot/dry_run.py:85,90`, `src/bot/live_run.py:267,273,320,342,433`
**Issue:** `datetime.utcnow()` is deprecated in Python 3.12+ in favor of timezone-aware `datetime.now(datetime.timezone.utc)`. While not a bug on Python 3.10-3.11 (project spec), it will emit deprecation warnings on newer runtimes and returns a naive datetime that can cause subtle comparison bugs if mixed with timezone-aware datetimes elsewhere.
**Fix:** Replace all occurrences:
```python
from datetime import datetime, timezone
# Before: datetime.utcnow()
# After:  datetime.now(timezone.utc)
```

---

_Reviewed: 2026-04-25T14:32:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
