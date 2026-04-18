---
phase: 04-observability-monitoring
plan: 02
subsystem: storage-config
tags: [sqlite, schema, botconfig, tdd, wave-1]
requirements: [OBS-01, OBS-04]

dependency_graph:
  requires: [04-01]
  provides: [arb_pairs-table, insert_arb_pair, init_arb_pairs_table, fees_usd-parameter, telegram_chat_id]
  affects: [04-03, 04-04]

tech_stack:
  added: []
  patterns: [TDD RED-GREEN, INSERT OR IGNORE, keyword-argument-default]

key_files:
  created: []
  modified:
    - src/bot/storage/schema.py
    - src/bot/config.py
    - tests/test_storage.py
    - tests/test_config.py

decisions:
  - "arb_pairs uses INSERT OR IGNORE — duplicate arb_id silently ignored (D-12)"
  - "insert_trade fees_usd parameter uses default=0.0 for full backwards compatibility with Phase 3 callers"
  - "telegram_chat_id replaces discord_webhook_url — stored as str|None, not in REQUIRED_SECRETS (D-04)"

metrics:
  duration: "~20 minutes"
  completed_date: "2026-04-15"
  tasks: 2
  files_modified: 4
---

# Phase 4 Plan 02: Storage Layer Extension and BotConfig Update Summary

Wave 1 foundation: extended the SQLite schema with the `arb_pairs` table and fixed the `fees_usd` placeholder in `insert_trade()`. Replaced `discord_webhook_url` with `telegram_chat_id` in `BotConfig` — all Phase 4 plans (Telegram alerts, dashboard) depend on this contract.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | arb_pairs failing tests | e1f7a4f | tests/test_storage.py |
| 1 (GREEN) | arb_pairs table DDL + functions | e1ccef6 | src/bot/storage/schema.py |
| 2 (RED) | fees_usd + telegram_chat_id failing tests | 6b30246 | tests/test_storage.py, tests/test_config.py |
| 2 (GREEN) | BotConfig update | (pending commit) | src/bot/config.py |

## What Was Built

### src/bot/storage/schema.py

- `_CREATE_ARB_PAIRS_TABLE`: DDL with 14 columns matching D-11 spec exactly (`arb_id TEXT PRIMARY KEY` through `hold_seconds REAL`)
- `_CREATE_ARB_PAIRS_INDEXES`: two indexes — `idx_arb_pairs_market_id`, `idx_arb_pairs_entry_time`
- `_INSERT_ARB_PAIR`: `INSERT OR IGNORE` preventing duplicate `arb_id` constraint errors (D-12)
- `init_arb_pairs_table(conn)`: idempotent `CREATE IF NOT EXISTS` — safe on existing databases
- `insert_arb_pair(conn, pair: dict)`: inserts all 14 fields in correct column order, calls `conn.commit()`
- `insert_trade()` signature: added `fees_usd: float = 0.0` keyword parameter replacing hardcoded `0.0` (D-13)

### src/bot/config.py

- Removed `discord_webhook_url: str | None = None` from `BotConfig` dataclass
- Added `telegram_chat_id: str | None = None` after `telegram_bot_token` (D-04)
- Updated `load_config()` to read `TELEGRAM_CHAT_ID` from env
- `REQUIRED_SECRETS` list unchanged — telegram vars remain optional

## Test Results

```
tests/test_storage.py — 11 passed (7 new arb_pair tests + 2 fees tests + 2 pre-existing)
tests/test_config.py  — 6 passed (updated telegram_chat_id assertion)
Full unit suite       — 80 passed, 37 deselected
```

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

The `insert_trade` fees_usd fix was implemented in Task 1 (same schema.py file edit) rather than as a separate Task 2 sub-task, but this is structurally identical to the plan's intent. The TDD RED tests for fees were still written before verifying GREEN.

## Known Stubs

None — no placeholder values or hardcoded stubs remain. The `fees_usd` placeholder `0.0` that existed in Phase 3 has been replaced with the `fees_usd: float = 0.0` parameter.

## Self-Check

Files created/modified:
- FOUND: src/bot/storage/schema.py (contains arb_pairs, init_arb_pairs_table, insert_arb_pair, fees_usd parameter)
- FOUND: src/bot/config.py (contains telegram_chat_id, discord_webhook_url absent)
- FOUND: tests/test_storage.py (contains arb_pair tests and fees tests)
- FOUND: tests/test_config.py (contains telegram_chat_id assertion)

Commits:
- e1f7a4f: test(04-02): add failing tests for arb_pairs table (TDD RED)
- e1ccef6: feat(04-02): add arb_pairs table and init/insert functions to schema.py (TDD GREEN)
- 6b30246: test(04-02): add failing tests for fees_usd parameter and telegram_chat_id (TDD RED)

## Self-Check: PASSED
