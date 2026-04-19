---
phase: 01-research-polymarket-market-mechanics-and-arb-math-to-fix-cro
plan: 02
subsystem: detection
tags: [cross-market, grouping, gamma-api, event-level, refactor]
dependency_graph:
  requires: [01-01]
  provides: [event-level grouping, _group_by_event, load_event_groups]
  affects: [src/bot/detection/cross_market.py, tests/test_cross_market.py]
tech_stack:
  added: [httpx (for load_event_groups Gamma API call)]
  patterns: [module-level cache dict, startup-time API fetch, fallback chain (Gamma -> neg_risk_market_id)]
key_files:
  modified:
    - src/bot/detection/cross_market.py
    - tests/test_cross_market.py
decisions:
  - PATH B chosen: Gamma API event grouping (CLOB has no event_id field)
  - load_event_groups() called once at startup, not in hot detection path
  - neg_risk_market_id retained as fallback in case Gamma API call fails
metrics:
  duration: ~15min
  completed: 2026-04-19T17:51:13Z
  tasks_completed: 2
  files_modified: 2
---

# Phase 01 Plan 02: Event-Level Grouping Rewrite Summary

**One-liner:** Replaced BFS keyword-heuristic grouping with Gamma API event-level grouping — `_group_by_event()` using `conditionId->event_id` mappings loaded once at startup via `load_event_groups()`.

## PATH Chosen: PATH B (Gamma API)

### Evidence from Live API Discovery

**Step 1a — CLOB market object keys (all fields):**
```
['accepting_order_timestamp', 'accepting_orders', 'active', 'archived', 'closed',
 'condition_id', 'description', 'enable_order_book', 'end_date_iso', 'fpmm',
 'game_start_time', 'icon', 'image', 'is_50_50_outcome', 'maker_base_fee',
 'market_slug', 'minimum_order_size', 'minimum_tick_size', 'neg_risk',
 'neg_risk_market_id', 'neg_risk_request_id', 'notifications_enabled', 'question',
 'question_id', 'rewards', 'seconds_delay', 'tags', 'taker_base_fee', 'tokens']
```

**Confirmed: NO direct `event_id` field on CLOB market objects.** PATH A is not available.

`neg_risk_market_id` exists but is empty string (`""`) for the majority of markets — only NegRisk-enabled events populate it. Sample from first 10 CLOB markets: all had `"neg_risk_market_id": ""`.

**Step 1b — Gamma API event structure (confirmed):**
```
GET https://gamma-api.polymarket.com/events?active=true&limit=3
→ Event keys: ['active', 'archived', 'category', 'closed', ..., 'id', ..., 'markets', ...]
→ Market keys include: 'conditionId', 'clobTokenIds', 'outcomePrices', 'negRisk', ...
→ conditionId sample: 0x064d33e3f5703792aafa92bfb0ee10e08f461b1b34c02c1f02671892ede1609a
```

`conditionId` in Gamma = `condition_id` in CLOB (confirmed). PATH B is the correct implementation.

## Functions Removed

| Function | Lines | Reason |
|----------|-------|--------|
| `_extract_keywords(question)` | ~8 | Keyword heuristic — replaced by event-level grouping |
| `_group_markets(markets)` | ~47 | BFS connected-components — replaced by `_group_by_event()` |

**Constants removed:** `_MIN_WORD_LENGTH = 4`, `_MIN_SHARED_WORDS = 2`

## Functions Added

| Function | Purpose |
|----------|---------|
| `load_event_groups(condition_ids=None)` | Fetches `condition_id -> event_id` from Gamma API once at startup. Populates module-level `_event_groups` dict. |
| `_group_by_event(markets)` | Groups markets by event using `_event_groups`, falls back to `neg_risk_market_id` / `neg_risk_id` if not found. Replaces `_group_markets()`. |

## Architecture: Startup-Time vs Hot-Path

`load_event_groups()` is called ONCE when the scanner loads markets. The `_event_groups` dict is a module-level cache that is never written during detection cycles. This keeps `detect_cross_market_opportunities()` hot-path free of any network I/O — addressing the tertiary threat from the plan's threat model.

The fallback chain in `_group_by_event()`:
1. `_event_groups[condition_id]` — Gamma API mapping (primary, catches all event types)
2. `market.get("neg_risk_market_id")` — CLOB field fallback (covers NegRisk if Gamma fails)
3. `market.get("neg_risk_id")` — alt field name fallback

## Detection Math: Unchanged

Lines after `_group_by_event()` call are byte-for-byte identical to the original `_group_markets()` version:
- `total_yes = sum(yes_asks)` — exactly 1 occurrence (confirmed by grep)
- `gross_spread = 1.0 - total_yes`
- Fee calculation (entry + exit), `net_spread`, `confidence` — all unchanged
- `ArbitrageOpportunity` construction — unchanged (including `no_token_id=""` and `legs=legs_data`)

## Test Results

**8 tests passing (5 original updated + 3 new):**

| Test | Status | Notes |
|------|--------|-------|
| test_exclusivity_constraint_detected | PASS | Updated: added event_id |
| test_unrelated_markets_not_grouped | PASS | Updated: docstring clarified |
| test_insufficient_depth_skips_group | PASS | Updated: added event_id |
| test_no_arb_when_sum_at_or_above_one | PASS | Updated: added event_id |
| test_single_market_group_not_returned | PASS | Updated: added event_id |
| test_event_grouping | PASS | New: 3-market event group → 1 opp |
| test_event_markets_no_id_ignored | PASS | New: no event_id → 0 opps |
| test_event_different_ids_not_grouped | PASS | New: separate event IDs stay separate |

**Test infrastructure note:** Tests inject `event_id` via `_patch_event_groups()` helper that populates `_event_groups` directly, bypassing the Gamma API HTTP call. This keeps unit tests fast and deterministic.

## Commits

| Hash | Message |
|------|---------|
| `04c8328` | feat(01-02): replace keyword grouping with event-level grouping via Gamma API |
| `643b0c8` | test(01-02): update cross-market tests for event-level grouping |

## Deviations from Plan

**1. [Rule 1 - Bug] Preserved existing `legs_data`/`legs=legs_data` code**
- **Found during:** Reading the current file before editing — the file had already been updated (by a prior commit `688fc9e`) to include `legs_data` collection and pass `legs=legs_data` to `ArbitrageOpportunity`.
- **Fix:** Preserved the `legs_data` logic exactly as-is. The plan stated "do NOT change anything else in the file" — this was already in the file, not something I added.
- **Files modified:** None (preserved existing behavior)

**2. [Rule 2 - Test infrastructure] Added `_patch_event_groups`/`_restore_event_groups` helpers**
- **Found during:** Task 2 — tests need to inject event mappings without making HTTP calls.
- **Fix:** Added two small test helpers that directly mutate and restore `_event_groups` module-level dict. This is the correct pattern for testing PATH B without network I/O.
- **Files modified:** `tests/test_cross_market.py`

## Known Stubs

None — `load_event_groups()` is a real HTTP call to the Gamma API. The module-level `_event_groups` dict is empty until `load_event_groups()` is called at scanner startup (caller responsibility). The caller wiring (scanner startup) is out of scope for this plan.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. `load_event_groups()` makes an outbound read-only HTTP GET to the public Gamma API, which is already used by the bot infrastructure.

## Self-Check: PASSED

- `src/bot/detection/cross_market.py` — exists, `py_compile` OK, imports OK
- `tests/test_cross_market.py` — exists, 8/8 tests pass
- Commits `04c8328` and `643b0c8` — present in git log
- `_group_markets` — absent (grep returns empty)
- `_group_by_event` — present (2 occurrences: definition + call)
- `total_yes = sum` — exactly 1 occurrence
