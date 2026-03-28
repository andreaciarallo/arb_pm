---
phase: 02-market-data-detection
plan: "02"
subsystem: scanner
tags: [price-cache, websocket, real-time-data, auto-reconnect, tdd]
dependency_graph:
  requires: [02-01]
  provides: [price-cache, ws-client]
  affects: [02-03, 02-04]
tech_stack:
  added: [websockets]
  patterns: [dataclass, async-context-manager, exponential-backoff, tdd]
key_files:
  created:
    - src/bot/scanner/price_cache.py
    - src/bot/scanner/ws_client.py
    - tests/test_price_cache.py
    - tests/test_ws_client.py
  modified: []
decisions:
  - "Prices parsed from 'sells' array (ask side) only — never 'buys' (D-05)"
  - "is_stale() returns True for unknown tokens — treat missing as stale (D-09)"
  - "Each token stored independently in cache; detection engine pairs YES+NO by condition_id"
  - "_max_reconnects guard on WebSocketClient enables clean test termination without timeout"
  - "Async context manager mock used for reconnect test — side_effect must return CM not raise directly"
metrics:
  duration_minutes: 15
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_created: 4
---

# Phase 02 Plan 02: Price Cache and WebSocket Client Summary

**One-liner:** In-memory MarketPrice cache with staleness detection and CLOB WebSocket client with 1→2→4→8→30s exponential backoff reconnection.

## What Was Built

### src/bot/scanner/price_cache.py

`MarketPrice` dataclass stores a price snapshot for a single YES or NO token with fields: `token_id`, `yes_ask`, `no_ask`, `yes_bid`, `no_bid`, `yes_depth`, `no_depth`, `timestamp`, `source`.

`PriceCache` provides O(1) dict operations:
- `update(token_id, price)` — store/overwrite
- `get(token_id) -> MarketPrice | None` — retrieve or None
- `is_stale(token_id, threshold_seconds) -> bool` — True if old OR unknown (treat missing as stale per D-09)
- `get_all_fresh(threshold_seconds) -> dict` — returns only non-stale entries

### src/bot/scanner/ws_client.py

`WebSocketClient` subscribes to Polymarket CLOB WebSocket (`wss://ws-subscriptions-clob.polymarket.com/ws/market`) for real-time order book updates.

- `_connect_once(ws)` — sends subscribe message with all token_ids, reads messages until connection closes
- `_handle_message(raw)` — parses `book` events, extracts ask price from `sells[0]` (never `buys`, D-05), updates PriceCache
- `run()` — infinite reconnect loop with exponential backoff: 1→2→4→8→30s cap; never raises

## Tests

| File | Tests | Coverage |
|------|-------|----------|
| tests/test_price_cache.py | 7 | update/get, staleness, unknown token, get_all_fresh, source field |
| tests/test_ws_client.py | 3 | subscribe message, cache update on book event, reconnect on disconnect |

All 10 tests pass. No network access required.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed async iterator mock in test_subscribe_message_sent_on_connect**
- **Found during:** Task 2 GREEN phase
- **Issue:** Plan's test template used `mock_ws.__aiter__ = MagicMock(return_value=iter([...]))` — returns a sync iterator, but `async for` requires an async iterator. `unittest.mock.AsyncMock.__aiter__` also passes `self` as first arg, causing `TypeError: takes 0 positional arguments but 1 was given`
- **Fix:** Replaced mock with a custom `_FakeWS` class implementing `__aiter__` as an async generator method. Tracks `send()` calls in a list.
- **Files modified:** tests/test_ws_client.py
- **Commit:** da11858

**2. [Rule 1 - Bug] Fixed async context manager mock in test_reconnects_on_disconnect**
- **Found during:** Task 2 GREEN phase
- **Issue:** Plan's test template used `async def fake_connect(*args, **kwargs): raise websockets.ConnectionClosed(...)` as `side_effect`. Since `websockets.connect` is used as `async with`, the mock must return an object with `__aenter__`/`__aexit__` — not raise in the function body itself. `connect_calls` stayed at 0.
- **Fix:** Replaced `async def fake_connect` with a regular function returning `_FailingCM` — an async context manager class that records calls and raises `ConnectionClosed` in `__aenter__`.
- **Files modified:** tests/test_ws_client.py
- **Commit:** da11858

## Known Stubs

None — all fields are populated from real WebSocket events. The `no_ask`, `no_bid`, `no_depth` fields are initialized to `0.0` on each token event intentionally — the detection engine in 02-04 pairs YES and NO tokens by `condition_id` and reads each token's `yes_ask` field directly. This is by design, not a stub.

## Self-Check

### Files exist:

- `src/bot/scanner/price_cache.py` — FOUND
- `src/bot/scanner/ws_client.py` — FOUND
- `tests/test_price_cache.py` — FOUND
- `tests/test_ws_client.py` — FOUND

### Commits exist:

- `b13b1e2` — feat(02-02): MarketPrice dataclass and PriceCache
- `da11858` — feat(02-02): WebSocket client with auto-reconnect

## Self-Check: PASSED
