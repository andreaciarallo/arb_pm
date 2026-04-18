---
phase: 5
slug: fix-token-id-execution-wiring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.4 + pytest-asyncio |
| **Config file** | `pytest.ini` (project root) |
| **Quick run command** | `python -m pytest tests/test_execution_engine.py tests/test_yes_no_arb.py tests/test_cross_market.py -v` |
| **Full suite command** | `python -m pytest tests/ -v -m "not smoke"` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_execution_engine.py tests/test_yes_no_arb.py tests/test_cross_market.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v -m "not smoke"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 0 | EXEC-01 | — | N/A | unit | `python -m pytest tests/test_yes_no_arb.py -xvs -k "token_id"` | ❌ Wave 0 | ⬜ pending |
| 05-01-02 | 01 | 1 | EXEC-01 | — | N/A | unit | `python -m pytest tests/test_yes_no_arb.py -xvs` | ✅ | ⬜ pending |
| 05-01-03 | 01 | 1 | EXEC-01 | — | N/A | unit | `python -m pytest tests/test_cross_market.py -xvs` | ✅ | ⬜ pending |
| 05-02-01 | 02 | 0 | EXEC-01,EXEC-02 | — | N/A | unit | `python -m pytest tests/test_execution_engine.py -xvs` | ✅ (update) | ⬜ pending |
| 05-02-02 | 02 | 1 | EXEC-01,EXEC-02 | — | N/A | unit | `python -m pytest tests/test_execution_engine.py::test_full_success_returns_two_filled_results -xvs` | ✅ | ⬜ pending |
| 05-02-03 | 02 | 1 | EXEC-03 | — | N/A | unit | `python -m pytest tests/test_execution_engine.py::test_no_leg_retry_then_hedge -xvs` | ✅ | ⬜ pending |
| 05-02-04 | 02 | 1 | EXEC-04 | — | N/A | unit | `python -m pytest tests/test_execution_engine.py::test_yes_verify_false_aborts_no_leg -xvs` | ✅ | ⬜ pending |
| 05-02-05 | 02 | 1 | RISK-01 | — | N/A | unit | `python -m pytest tests/test_execution_engine.py::test_kelly_zero_returns_skipped -xvs` | ✅ | ⬜ pending |
| 05-02-06 | 02 | 2 | EXEC-01 | — | N/A | integration | `grep "place_fak_order\|Gate 0 pass" logs` (live-mode dry run) | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_yes_no_arb.py` — add test asserting `opp.yes_token_id` and `opp.no_token_id` are non-empty strings on the returned `ArbitrageOpportunity` from `detect_yes_no_opportunities()` (verifies wiring fix)
- [ ] `tests/test_execution_engine.py` — update `_opp()` helper to accept and default `yes_token_id="yes_tok"`, `no_token_id="no_tok"`; update 5 call sites to pass token IDs via opp instead of as kwargs to `execute_opportunity()`; add `client.get_order_book` mock to Gate 1+ tests

*Existing infrastructure covers all other phase requirements — no framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| At least one FAK order call reached in live-mode dry run | EXEC-01, EXEC-02 | Requires live CLOB credentials and real opportunity detection | Run `python -m src.bot.main --live` with valid `.env`, wait for detection cycle, grep logs for "place_fak_order" or "Gate 0 pass" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
