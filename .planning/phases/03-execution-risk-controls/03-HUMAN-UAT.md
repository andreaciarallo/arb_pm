---
status: partial
phase: 03-execution-risk-controls
source: [03-VERIFICATION.md]
started: 2026-03-29T19:30:00Z
updated: 2026-04-05T00:00:00Z
---

## Current Test

UAT 1 — Live FAK order placement (awaiting VPS test)

## Tests

### 1. Live FAK order placement
expected: Submitting an actual order via `place_fak_order()` with real credentials produces `status='matched'|'unmatched'` with no GTC residual remaining in the CLOB. Confirm no open orders left after FAK settlement.
result: [pending] — VPS test script prepared, requires ~$1 USDC in wallet

### 2. SIGTERM active close
expected: When a Docker container running `--live` receives SIGTERM, `cancel_all()` is called, open positions are sold (FAK SELL at 0.01), and the process exits cleanly within 30 seconds.
result: PASSED — local mock test: kill switch fired in <1ms, process exited in 4.1s. Bug found and fixed: scan sleep was not interrupted on SIGTERM (27s delay). Fixed via asyncio stop event (commit aee2e40).

### 3. Midnight UTC loss reset
expected: After running continuously past 00:00 UTC, the `RiskGate` daily loss accumulator resets to 0.0 and unblocks execution — without requiring a bot restart.
result: PASSED — local script: backdated _day_reset_timestamp to yesterday, confirmed _daily_loss_usd reset from $60.00 → $0.00 and is_stop_loss_triggered() returned False without restart.

## Summary

total: 3
passed: 2
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
