---
phase: 03-execution-risk-controls
asvs_level: 1
generated_by: gsd-security-auditor
date: 2026-04-17
threats_total: 10
threats_closed: 10
threats_open: 0
block_on: critical
verdict: SECURED
---

# Phase 03 Security Report — Execution & Risk Controls

## Summary

**Phase:** 03 — execution-risk-controls
**Threats Closed:** 10/10
**ASVS Level:** 1
**Verdict:** SECURED — no open threats, no implementation gaps found.

---

## Threat Verification

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| EXEC-01 | Order safety — FAK enforcement | mitigate | `order_client.py:60` — `post_order(signed, orderType=OrderType.FAK)` present. Zero `OrderType.GTC` references in executable code. |
| EXEC-02 | GTC residual exposure — `create_and_post_order` forbidden | mitigate | `order_client.py:5,34` — both occurrences of `create_and_post_order` are in docstring/comment text only; zero executable calls. Verified by line-level grep. |
| EXEC-03 | One-legged risk — retry-then-hedge | mitigate | `engine.py:36,349,395,408` — `_NO_RETRY_COUNT=3`, `range(_NO_RETRY_COUNT)` loop, `asyncio.sleep(_NO_RETRY_DELAY)` between retries, `_HEDGE_PRICE=0.01` SELL on exhaustion. |
| EXEC-04 | Fill verification — REST polling | mitigate | `engine.py:299` — `verify_fill_rest(client, yes_order_id)` called after YES leg. `order_client.py:101-114` — polls `get_order()` every 500ms, up to 10 iterations (5s). WebSocket user channel deferral documented as intentional (undocumented format). |
| RISK-01 | Position sizing — Kelly hard caps | mitigate | `kelly.py:64-70` — `max_by_depth = depth * 0.5`, `max_by_capital = total_capital * max_capital_pct`, `min(size, max_by_depth, max_by_capital)`, floor check returns 0.0. Six `return 0.0` guards for all edge cases. |
| RISK-02 | Daily stop-loss — 5% capital limit | mitigate | `gate.py:165-166` — `limit = total_capital_usd * daily_stop_loss_pct`, `triggered = _daily_loss_usd >= limit`. `live_run.py:385-386` — `is_stop_loss_triggered()` logged and execution skipped when triggered. |
| RISK-03 | Circuit breaker — 5 errors/60s cooldown | mitigate | `gate.py:118-125` — sliding window trim, trip at `circuit_breaker_errors` threshold, `_cb_cooldown_multiplier` doubles (cap=4x, max=20m). `live_run.py:295,387-388` — `is_blocked()` gates execution; specific CB warning logged. |
| RISK-04 | Kill switch — SIGTERM + KILL file + active close | mitigate | `live_run.py:237-238` — `loop.add_signal_handler(signal.SIGTERM, _handle_signal)` and `SIGINT` registered. `live_run.py:263-265` — `os.path.exists(_KILL_FILE)` checked every cycle. `live_run.py:67,87` — `cancel_all()` + FAK SELL of open YES positions at price=0.01 in `_execute_kill_switch()`. |
| RISK-05 | Private key — local signing only, never transmitted | mitigate | `client.py:26` — `key=config.wallet_private_key` passed to `ClobClient` constructor for local EIP-712 signing only. No logging of key in `client.py` (no logger calls). `order_client.py` — signing is done by `create_order()` locally before `post_order()` submits the signed payload. Key never appears in log calls across `live_run.py`, `engine.py`, or `order_client.py`. |
| RISK-06 | Event loop blocking — all sync SDK calls wrapped | mitigate | `order_client.py:56,58-61,103` — `create_order`, `post_order`, and `get_order` all wrapped in `loop.run_in_executor(None, ...)`. `live_run.py:67` — `cancel_all()` also wrapped in `run_in_executor`. |

---

## Accepted Risks Log

No threats are accepted in Phase 03. All declared threats are mitigated.

---

## Unregistered Flags

The following items were noted in SUMMARY.md files during Phase 03 execution but do not map to discrete threat IDs in the plans:

| Flag | Source | Classification | Notes |
|------|--------|----------------|-------|
| WebSocket user channel fill confirmation deferred | 03-03-SUMMARY.md, 03-05-SUMMARY.md | Intentional design deferral, not a security gap | REST-only polling (`verify_fill_rest`) is the declared Phase 03 mechanism. WebSocket user channel deferred to Phase 04 due to undocumented message format (RESEARCH.md Pattern 3: LOW confidence). No one-legged exposure created because YES fill is confirmed by REST before NO leg proceeds. |
| `simulate_vwap` not wired to live order book data | `engine.py:167-174` (WR-07 note) | Functional gap, not a security gap | VWAP gate uses `opp.vwap_yes/vwap_no` from detection engine (equal to best_ask in Phase 03). Gate still correctly rejects resolved markets (sentinel value 1.0). Does not affect risk controls or capital integrity. Phase 05 will supply live multi-level VWAP. |
| `yes_token_id`/`no_token_id` default to `""` | 03-03-SUMMARY.md | Intentional stub, not a security gap | Engine returns `status="skipped"` immediately when token IDs are missing (Gate 0 at `engine.py:144`). No orders are placed. Live run (`live_run.py`) must supply real token IDs or execution is safely blocked. |
| `test_market_filter` pre-existing failures | 03-01/02/03/04/05-SUMMARY.md | Pre-existing test failures, unrelated to Phase 03 | Confirmed pre-existing via git stash verification in all five plans. Not caused by Phase 03 changes. Out of scope for this audit. |

---

## Verification Methodology

Each threat was verified by direct code inspection of the files cited in the plan's mitigation specification:

- **EXEC-01/02**: Grep confirmed `OrderType.FAK` in executable code at `order_client.py:60`; `create_and_post_order` appears only in comments (lines 5, 34) with zero executable calls.
- **EXEC-03**: Named constants `_NO_RETRY_COUNT=3`, `_NO_RETRY_DELAY=0.5`, `_HEDGE_PRICE=0.01` in `engine.py:36-38`; retry loop at line 349; hedge SELL at line 408.
- **EXEC-04**: `verify_fill_rest` called at `engine.py:299`; polling implementation at `order_client.py:101-114` confirmed 500ms interval × 10 iterations.
- **RISK-01**: Six `return 0.0` guards in `kelly.py`; hard caps at lines 64-70 with `min(size, max_by_depth, max_by_capital)`.
- **RISK-02**: Stop-loss threshold and accumulator at `gate.py:165-166`; midnight UTC reset at `gate.py:207-224`; execution gate at `live_run.py:385-386`.
- **RISK-03**: Sliding-window circuit breaker at `gate.py:104-126`; exponential backoff multiplier (1x→2x→4x cap); execution gate at `live_run.py:295,387-388`.
- **RISK-04**: SIGTERM/SIGINT handlers at `live_run.py:237-238`; KILL file check at lines 263-265; `_execute_kill_switch` with `cancel_all()` + SELL at lines 47-93.
- **RISK-05**: Private key passed only to `ClobClient` constructor at `client.py:26` for local signing; no key material appears in any log call across all Phase 03 files.
- **RISK-06**: All three SDK calls (`create_order`, `post_order`, `get_order`) wrapped in `run_in_executor` at `order_client.py:56,58,103`; `cancel_all()` wrapped at `live_run.py:67`.

---

## Scope Notes

- Implementation files are READ-ONLY. This report records findings only.
- ASVS Level 1 applied: verification confirms declared mitigations are present in code. No additional vulnerability scanning performed beyond declared threat register.
- Phase 03 addresses requirements: EXEC-01, EXEC-02, EXEC-03, EXEC-04, RISK-01, RISK-02, RISK-03, RISK-04.
