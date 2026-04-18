---
phase: 3
slug: execution-risk-controls
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.4 + pytest-asyncio 0.25.0 |
| **Config file** | `pytest.ini` (asyncio_mode=auto) |
| **Quick run command** | `PYTHONPATH=src pytest tests/test_kelly.py tests/test_risk_gate.py -x -q` |
| **Full suite command** | `PYTHONPATH=src pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONPATH=src pytest tests/test_kelly.py tests/test_risk_gate.py tests/test_order_client.py tests/test_execution_engine.py -x -q`
- **After every plan wave:** Run `PYTHONPATH=src pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | RISK-01 | unit | `PYTHONPATH=src pytest tests/test_kelly.py -x -q` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | EXEC-01, EXEC-02 | unit | `PYTHONPATH=src pytest tests/test_order_client.py -x -q` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | EXEC-03, EXEC-04 | unit | `PYTHONPATH=src pytest tests/test_execution_engine.py -x -q` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 2 | RISK-02, RISK-03, RISK-04 | unit | `PYTHONPATH=src pytest tests/test_risk_gate.py -x -q` | ❌ W0 | ⬜ pending |
| 03-05-01 | 05 | 3 | EXEC-01..04, RISK-01..04 | integration | `PYTHONPATH=src pytest tests/test_live_run.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_kelly.py` — stubs for RISK-01 (Kelly formula: normal case, p=0 edge, b≤0 skip, floor/ceiling)
- [ ] `tests/test_order_client.py` — stubs for EXEC-01, EXEC-02 (FAK order creation, post_order mock, run_in_executor wrapping)
- [ ] `tests/test_execution_engine.py` — stubs for EXEC-03, EXEC-04 (retry-then-hedge state machine, VWAP simulation, dual verification)
- [ ] `tests/test_risk_gate.py` — stubs for RISK-02, RISK-03, RISK-04 (stop-loss cumulative tracking, circuit breaker error counter, kill switch active close)
- [ ] `tests/test_live_run.py` — stubs for integration (live_run.py orchestration, zero real orders, SQLite trade log write)

*Existing infrastructure covers: pytest.ini (asyncio_mode=auto), conftest.py with real_config fixture, PYTHONPATH=src pattern*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SIGTERM triggers kill switch | RISK-04 | Cannot mock OS signal in standard pytest | `docker compose exec bot kill -TERM 1` → check logs for "kill switch triggered" |
| /app/data/KILL file detection | RISK-04 | File system side effect on VPS | `docker compose exec bot touch /app/data/KILL` → wait ≤30s → check logs |
| Daily stop-loss midnight UTC reset | RISK-02 | Requires wall-clock time advancement | Set daily_loss to 4.9% → check bot resumes after midnight UTC |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
