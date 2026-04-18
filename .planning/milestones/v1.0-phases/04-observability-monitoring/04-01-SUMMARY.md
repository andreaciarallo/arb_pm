---
phase: 04-observability-monitoring
plan: "01"
subsystem: test-scaffolding
tags: [tdd, wave-0, fastapi, telegram, sqlite, testing]
requires: []
provides: [test-scaffolds-wave0, deps-fastapi, deps-uvicorn, deps-python-telegram-bot]
affects: [tests/test_storage.py, tests/test_telegram.py, tests/test_dashboard.py, requirements.txt]
tech-stack-added: [fastapi==0.135.3, uvicorn==0.44.0, python-telegram-bot==22.7]
tech-stack-patterns: [tdd-red-state, wave-0-scaffolding, pytest-mark-unit]
key-files-created:
  - tests/test_telegram.py
  - tests/test_dashboard.py
key-files-modified:
  - requirements.txt
  - tests/test_storage.py
decisions:
  - "Wave 0 test stubs import from not-yet-existing modules — intentional RED state guarantees no false greens"
  - "All 14 D-11 arb_pairs fields covered in test_insert_arb_pair_all_columns"
  - "test_dashboard.py uses starlette.testclient (sync) — no running ASGI server needed for unit tests"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-14T23:02:00Z"
  tasks: 2
  files: 4
requirements: [OBS-01, OBS-02, OBS-03, OBS-04]
---

# Phase 4 Plan 01: Wave 0 Test Scaffolds Summary

**One-liner:** Three test files with 15 RED-state stubs plus three new pinned dependencies (fastapi, uvicorn, python-telegram-bot) installed in dev environment.

---

## What Was Built

Wave 0 Nyquist compliance scaffolding for Phase 4. Every subsequent production task now has a failing test that transitions RED → GREEN when the implementation is complete.

### Task 1: requirements.txt — Three new dependencies

Added at exact pinned versions per threat model (supply chain pinning):

```
fastapi==0.135.3
uvicorn==0.44.0
python-telegram-bot==22.7
```

All three installed and verified via `pip show`.

### Task 2: Wave 0 test scaffolds (RED state)

**tests/test_storage.py** — 5 new tests appended to existing file:
- `test_insert_trade_fees_usd_not_zero` — asserts `fees_usd` kwarg is stored (fails: current `insert_trade` has no `fees_usd` param)
- `test_arb_pairs_table_exists` — asserts `init_arb_pairs_table()` creates table (fails: function doesn't exist yet)
- `test_insert_arb_pair_creates_row` — asserts `insert_arb_pair()` inserts row (fails: function doesn't exist yet)
- `test_insert_arb_pair_all_columns` — asserts all 14 D-11 schema columns are correct (fails: function doesn't exist yet)
- `test_insert_arb_pair_idempotent` — asserts INSERT OR IGNORE behavior (fails: function doesn't exist yet)

**tests/test_telegram.py** — 5 new tests (new file):
- `test_alerter_noop_when_no_token` — noop on missing token (fails: module doesn't exist)
- `test_alerter_noop_when_no_chat_id` — noop on missing chat_id (fails: module doesn't exist)
- `test_alerter_swallows_telegram_error` — TelegramError swallowed (fails: module doesn't exist)
- `test_alerter_swallows_generic_exception` — generic Exception swallowed (fails: module doesn't exist)
- `test_alerter_calls_send_message_with_html_parse_mode` — parse_mode="HTML" asserted (fails: module doesn't exist)

**tests/test_dashboard.py** — 5 new tests (new file):
- `test_status_endpoint_returns_required_keys` — all 17 required `/api/status` JSON keys (fails: module doesn't exist)
- `test_status_bot_status_running` — bot_status=="running" when not blocked (fails: module doesn't exist)
- `test_status_bot_status_blocked` — bot_status=="blocked" when CB open (fails: module doesn't exist)
- `test_root_returns_html` — GET / returns 200 text/html (fails: module doesn't exist)
- `test_root_html_contains_refresh_interval` — `setInterval(refresh, 10000)` in HTML (fails: module doesn't exist)

---

## Verification Results

```
pytest --collect-only: 19 tests collected (0 errors)
grep -c "fastapi==0.135.3" requirements.txt → 1
grep -c "uvicorn==0.44.0" requirements.txt → 1
grep -c "python-telegram-bot==22.7" requirements.txt → 1
grep -c "arb_pair" tests/test_storage.py → 29
wc -l tests/test_telegram.py → 62
wc -l tests/test_dashboard.py → 121
grep "setInterval(refresh, 10000)" tests/test_dashboard.py → 1 match
```

RED state confirmed: new tests fail with `TypeError: insert_trade() got an unexpected keyword argument 'fees_usd'` and `ModuleNotFoundError` as expected.

---

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | `7e8af97` | chore(04-01): add fastapi, uvicorn, python-telegram-bot dependencies |
| 2 | `0753ad9` | test(04-01): add Wave 0 test scaffolds in RED state |

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Known Stubs

None. The RED-state imports are intentional Wave 0 scaffolding, not implementation stubs. Each failing import corresponds to a module that will be created in Plans 02–04.

---

## Self-Check: PASSED

- [x] `tests/test_telegram.py` exists (62 lines)
- [x] `tests/test_dashboard.py` exists (121 lines)
- [x] `tests/test_storage.py` extended with 5 arb_pair/fees tests
- [x] `requirements.txt` has all 3 new dependencies
- [x] Commits `7e8af97` and `0753ad9` exist
- [x] 19 tests collected, 0 collection errors
