---
phase: 03-execution-risk-controls
plan: "04"
subsystem: risk-gate
tags: [risk, stop-loss, circuit-breaker, kill-switch, tdd]
dependency_graph:
  requires:
    - 03-01  # BotConfig Phase 3 fields: daily_stop_loss_pct, circuit_breaker_*
  provides:
    - RiskGate class (src/bot/risk/gate.py)
    - bot.risk package
  affects:
    - 03-05  # live_run.py instantiates and checks RiskGate each cycle
tech_stack:
  added: []
  patterns:
    - Sliding-window error counting (deque-like list trimmed per call)
    - Exponential backoff multiplier with hard cap (1x → 2x → 4x → 4x)
    - Midnight UTC reset via datetime.datetime.utcnow()
key_files:
  created:
    - src/bot/risk/__init__.py
    - src/bot/risk/gate.py
    - tests/test_risk_gate.py
  modified: []
decisions:
  - "RiskGate is a plain class (not frozen dataclass) — mutable state required for in-place updates via test attribute access"
  - "daily_stop_loss_pct used as constructor parameter name (not daily_loss_limit_pct from RESEARCH.md) to match BotConfig field naming"
  - "_cb_cooldown_multiplier doubles on each trip and caps at 4 (4×300=1200=20m max cooldown)"
  - "Pre-existing test_market_filter failure confirmed unrelated (fails without our changes)"
metrics:
  duration_seconds: 152
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_created: 3
  files_modified: 0
---

# Phase 3 Plan 04: RiskGate — Stop-Loss, Circuit Breaker, Kill Switch Summary

**One-liner:** In-memory RiskGate with 5% daily stop-loss (midnight UTC reset), 5-error/60s circuit breaker with exponential backoff (5m→10m→20m), and kill-switch supremacy via is_blocked() combinator.

## What Was Built

`src/bot/risk/gate.py` — `RiskGate` class implementing three independent risk controls consumed by `live_run.py` (plan 05) and `execute_opportunity()` (plan 03) before every execution cycle.

### Stop-Loss (RISK-02, D-06)

- `record_loss(loss_usd)` accumulates realized losses (not unrealized/open positions)
- `is_stop_loss_triggered()` returns True when `_daily_loss_usd >= total_capital_usd * daily_stop_loss_pct`
- `_check_day_reset()` compares `_day_reset_timestamp` against today's midnight UTC timestamp; resets accumulator when triggered
- At $1k capital and 5% threshold: trip at $50 cumulative daily realized loss

### Circuit Breaker (RISK-03, D-07)

- `record_order_error()` appends timestamp to `_error_timestamps` and trims to `circuit_breaker_window_seconds` sliding window
- When `len(_error_timestamps) >= circuit_breaker_errors`, trips: sets `_cb_cooldown_until = now + cooldown`, doubles `_cb_cooldown_multiplier` (capped at 4), clears timestamps
- `is_circuit_breaker_open()` returns `time.time() < _cb_cooldown_until`
- Backoff: 1st trip=300s, 2nd=600s, 3rd+=1200s (capped)

### Kill Switch (RISK-04, D-08)

- `activate_kill_switch()` sets `_kill_switch_active = True` — never reverts without restart
- Triggered externally by SIGTERM handler or `/app/data/KILL` file check (plan 05)
- `is_kill_switch_active()` returns flag directly
- Kill switch overrides expired circuit breaker — `is_blocked()` stays True

### is_blocked() Combinator

```python
def is_blocked(self) -> bool:
    return (
        self.is_kill_switch_active()
        or self.is_stop_loss_triggered()
        or self.is_circuit_breaker_open()
    )
```

Short-circuits: kill switch checked first, stop-loss second, circuit breaker third.

## TDD Results

| Phase | Status | Tests |
|-------|--------|-------|
| RED | Confirmed import error `ModuleNotFoundError: No module named 'bot.risk'` | 15 tests |
| GREEN | All 15 passed in 0.03s | 15 tests |

Full suite: 41 passed, 5 skipped, 1 pre-existing failure (`test_market_filter.py` — unrelated to this plan).

## Deviations from Plan

### Pre-Existing Test Failure (Out of Scope)

`test_fetch_liquid_markets_filters_by_volume` in `tests/test_market_filter.py` was already failing before this plan's changes. Confirmed by stashing our changes and re-running — same failure. Logged to deferred items (out of scope for this plan).

No other deviations — plan executed exactly as written.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Plain class (not dataclass) | Tests directly mutate `_day_reset_timestamp`, `_cb_cooldown_until`, `_error_timestamps` — plain class attrs require no special handling |
| Constructor param: `daily_stop_loss_pct` | Matches `BotConfig.daily_stop_loss_pct` field name; RESEARCH.md used `daily_loss_limit_pct` but plan spec took precedence |
| Cap multiplier at 4 | 4×300=1200s=20min; matches D-07 "cap at 20m" |
| record_clean_cycle() is no-op | Error timestamps naturally expire via sliding window; no explicit reset needed |

## Self-Check: PASSED

| Check | Status |
|-------|--------|
| src/bot/risk/__init__.py exists | FOUND |
| src/bot/risk/gate.py exists | FOUND |
| tests/test_risk_gate.py exists | FOUND |
| commit f9ceb81 (RED tests) | FOUND |
| commit 1a3b8ee (GREEN impl) | FOUND |
