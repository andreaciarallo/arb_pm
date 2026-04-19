---
status: complete
phase: 01-research-polymarket-market-mechanics-and-arb-math-to-fix-cro
source:
  - 01-01-SUMMARY.md
  - 01-02-SUMMARY.md
  - 01-03-SUMMARY.md
started: "2026-04-19T18:10:00Z"
updated: "2026-04-19T18:30:00Z"
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: |
  Stop the bot, start fresh. Logs show Health check OK, dry-run scanner, no tracebacks.
result: pass

### 2. Dry-Run Lock — VPS logs
expected: |
  Logs show "dry-run scanner" — NOT "live execution scanner".
result: pass

### 3. Dry-Run Lock — docker-compose.yml
expected: |
  docker-compose.yml has `command: [python, -m, bot.main]` with NO `--live` flag.
result: pass

### 4. Event Grouping Wired at Startup
expected: |
  load_event_groups() is called at scanner startup. _event_groups has >0 entries after boot.
  Confirmed via: `docker exec arbbot python -c "import bot.detection.cross_market as cm; print(len(cm._event_groups))"` → non-zero.
result: issue
reported: "load_event_groups() is NOT wired into dry_run.py or live_run.py. grep confirms it's absent. _event_groups is always empty at runtime. Detection falls back to neg_risk_market_id only — non-NegRisk mutually exclusive events are never grouped. The executor marked caller wiring as out of scope for 01-02 but no subsequent plan wired it."
severity: major

### 5. Full Test Suite Passes
expected: |
  147 passed, 0 failed (5 skipped OK — smoke tests).
result: pass

### 6. Cross-Market Opportunities Have legs Populated
expected: |
  Detected opportunities carry legs field with token_id, ask, depth per leg.
result: pass
notes: "Bot is detecting 3 cross-market opps per cycle (e.g. 8-market sports group gross=0.989). These use neg_risk_market_id fallback grouping. legs field confirmed populated by unit tests (test_cross_market_equal_shares passes)."

### 7. Equal-Shares Sizing Math (Unit Test)
expected: |
  test_cross_market_equal_shares PASSED — target_shares = kelly_usd / total_yes.
result: pass

### 8. Partial Hedge on Failed Leg (Unit Test)
expected: |
  test_cross_market_partial_hedge PASSED — hedge SELL at price=0.01 when leg fails.
result: pass

## Summary

total: 8
passed: 7
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "load_event_groups() is called at scanner startup so _event_groups is populated with Gamma API event mappings before the first detection cycle"
  status: failed
  reason: "User reported: load_event_groups() not wired into dry_run.py or live_run.py — grep finds zero calls. _event_groups is always {} at runtime. Non-NegRisk mutually exclusive events are never grouped."
  severity: major
  test: 4
  artifacts:
    - src/bot/dry_run.py
    - src/bot/live_run.py
    - src/bot/detection/cross_market.py
  missing:
    - "Call to load_event_groups() in dry_run.py scanner startup (before first detection cycle)"
    - "Call to load_event_groups() in live_run.py scanner startup (before first detection cycle)"
