---
status: partial
phase: 03-execution-risk-controls
source: [03-VERIFICATION.md]
started: 2026-03-29T19:30:00Z
updated: 2026-03-29T19:30:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live FAK order placement
expected: Submitting an actual order via `place_fak_order()` with real credentials produces `status='matched'|'unmatched'` with no GTC residual remaining in the CLOB. Confirm no open orders left after FAK settlement.
result: [pending]

### 2. SIGTERM active close
expected: When a Docker container running `--live` receives SIGTERM, `cancel_all()` is called, open positions are sold (FAK SELL at 0.01), and the process exits cleanly within 30 seconds.
result: [pending]

### 3. Midnight UTC loss reset
expected: After running continuously past 00:00 UTC, the `RiskGate` daily loss accumulator resets to 0.0 and unblocks execution — without requiring a bot restart.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
