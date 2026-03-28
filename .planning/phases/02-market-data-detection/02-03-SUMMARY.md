---
phase: 02-market-data-detection
plan: 03
subsystem: scanner
tags: [normalizer, http-poller, price-cache, tdd, data-pipeline]
dependency_graph:
  requires: [02-01, 02-02]
  provides: [normalize_order_book, poll_stale_markets]
  affects: [detection-engine, price-cache]
tech_stack:
  added: []
  patterns: [pure-function-normalizer, async-polling-fallback, tdd-red-green]
key_files:
  created:
    - src/bot/scanner/normalizer.py
    - src/bot/scanner/http_poller.py
    - tests/test_normalizer.py
    - tests/test_http_poller.py
  modified: []
decisions:
  - "normalize_order_book() returns valid MarketPrice for resolved markets (ask=1.0) — detection engine skips them separately"
  - "yes_bid defaults to 0.0 on empty bids list (bid not critical for arb detection — ask prices drive strategy per D-05)"
  - "poll_stale_markets() uses per-token isolation: HTTP error on one token does not stop others"
metrics:
  duration_minutes: 8
  completed_date: "2026-03-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 0
---

# Phase 02 Plan 03: HTTP Polling Fallback + Order Book Normalizer Summary

**One-liner:** Pure-function CLOB order book normalizer with HTTP polling fallback that refreshes only stale WebSocket tokens, isolated per-token error handling, and full TDD coverage (10 tests).

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Order book normalizer (pure function) | 030586e | src/bot/scanner/normalizer.py, tests/test_normalizer.py |
| 2 | HTTP polling fallback for stale markets | bb438ca | src/bot/scanner/http_poller.py, tests/test_http_poller.py |

## What Was Built

### normalizer.py — `normalize_order_book(book: dict) -> MarketPrice | None`

Pure function with no I/O or side effects. Converts raw CLOB HTTP API order book responses to `MarketPrice` objects. Handles all edge cases:

- Missing `asset_id` → `None` (logged as warning)
- Empty `asks` list → `None` (no ask price available)
- Non-numeric price strings → `None` (logged as warning)
- Empty `bids` list → `MarketPrice` with `yes_bid=0.0` (bid not critical for arb detection)
- Resolved market (`asks[0].price == "1.0"`) → valid `MarketPrice` with `yes_ask=1.0` (detection engine skips these separately — not the normalizer's job)

All produced `MarketPrice` objects have `source="http"` for traceability vs WebSocket data.

### http_poller.py — `async def poll_stale_markets(client, cache, markets, config) -> int`

Async polling fallback that runs each scan cycle. For each token in each market:

1. Checks `PriceCache.is_stale(token_id, config.ws_stale_threshold_seconds)` — skips fresh tokens
2. Calls `client.get_order_book(token_id)` (sync, no await needed)
3. Normalizes via `normalize_order_book()` — skips if None
4. Updates cache via `cache.update(token_id, price)`
5. Catches all exceptions per-token — one failure does not stop others

Returns integer count of successfully refreshed tokens (not total stale checked).

## Test Coverage

10 unit tests total, all marked `@pytest.mark.unit` (no network access):

**test_normalizer.py (7 tests):**
- `test_normalize_normal_order_book` — happy path, check token_id, ask, bid, source
- `test_normalize_resolved_market` — ask=1.0 returns valid MarketPrice
- `test_normalize_empty_asks_returns_none` — empty asks list
- `test_normalize_empty_bids_returns_price_with_zero_bid` — empty bids → yes_bid=0.0
- `test_normalize_malformed_price_returns_none` — non-numeric string
- `test_normalize_missing_asset_id_returns_none` — missing asset_id key
- `test_normalize_depth_from_ask_size` — yes_depth from asks[0].size

**test_http_poller.py (3 tests):**
- `test_poll_stale_markets_refreshes_stale` — stale polled, fresh skipped, cache updated with source="http"
- `test_poll_returns_count_of_refreshed` — count excludes normalize failures (empty asks)
- `test_poll_http_error_does_not_stop_others` — exception on one token, other token succeeds

## Decisions Made

1. **Resolved markets return valid MarketPrice.** The normalizer's job is data conversion — not filtering. Returning `None` for resolved markets (ask=1.0) would conflate "bad data" with "valid but uninteresting data". The detection engine handles the skip separately. This keeps the normalizer's contract clean.

2. **yes_bid defaults to 0.0 on empty bids.** Per D-05, ask prices drive all arb detection. Bid prices are informational. A missing bid is not a data error — it's just an incomplete picture that doesn't block detection.

3. **Per-token exception isolation in poller.** Each token's HTTP fetch is wrapped independently. A timed-out fetch for one token should not starve the rest of the scan cycle. Pattern mirrors WebSocket reconnection isolation from 02-02.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. Both functions are fully wired. `no_ask` and `no_bid` fields on the produced `MarketPrice` are set to `0.0` because the normalizer processes a single token's order book (one token = YES side). Pairing with the NO token is handled upstream by the caller. This is intentional design, not a stub.

## Self-Check

Files created:
- src/bot/scanner/normalizer.py — FOUND
- src/bot/scanner/http_poller.py — FOUND
- tests/test_normalizer.py — FOUND
- tests/test_http_poller.py — FOUND

Commits:
- 030586e — FOUND
- bb438ca — FOUND

Tests: 10 passed, 0 failed.

## Self-Check: PASSED
