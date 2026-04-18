---
phase: 8
slug: fix-circuit-breaker-alert-accuracy
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (existing) |
| **Config file** | `pytest.ini` (asyncio_mode=auto) |
| **Quick run command** | `pytest tests/test_execution_engine.py tests/test_live_run.py tests/test_risk_gate.py -x` |
| **Full suite command** | `pytest -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_execution_engine.py tests/test_live_run.py tests/test_risk_gate.py -x`
- **After every plan wave:** Run `pytest -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 8-W0-01 | Wave 0 | 0 | RISK-03 | — | N/A | unit | `pytest tests/test_execution_engine.py::test_no_exhaustion_calls_record_order_error -x` | ❌ Wave 0 | ⬜ pending |
| 8-W0-02 | Wave 0 | 0 | RISK-03 | — | N/A | unit (regression) | `pytest tests/test_execution_engine.py::test_yes_verify_failure_calls_record_order_error -x` | ❌ Wave 0 | ⬜ pending |
| 8-W0-03 | Wave 0 | 0 | OBS-02 | — | N/A | unit | `pytest tests/test_live_run.py::test_cb_alert_shows_live_count_not_static_threshold -x` | ❌ Wave 0 | ⬜ pending |
| 8-W0-04 | Wave 0 | 0 | OBS-02 | — | N/A | regression | `pytest tests/test_live_run.py::test_cb_alert_fires_on_trip -x` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Tests must be written BEFORE or IN THE SAME PLAN as the production code changes they verify.

### New tests required (Wave 0 gaps)

- [ ] `tests/test_execution_engine.py` — add `test_no_exhaustion_calls_record_order_error`: verifies `record_order_error()` called once when all NO retries fail (RISK-03)
- [ ] `tests/test_execution_engine.py` — add `test_yes_verify_failure_calls_record_order_error`: verifies `record_order_error()` still called on YES verify False after fix (RISK-03 regression)
- [ ] `tests/test_live_run.py` — add `test_cb_alert_shows_live_count_not_static_threshold`: verifies `send_circuit_breaker_trip` called with `error_count=7` (live count), not `error_count=5` (static threshold) (OBS-02)
- [ ] `tests/test_live_run.py` — update existing `test_cb_alert_fires_on_trip`: add `mock_rg.last_trip_error_count = 5` so assertion continues passing after live_run.py fix (OBS-02 regression)

Run after wave 0:
```
pytest tests/test_execution_engine.py tests/test_live_run.py tests/test_risk_gate.py -x
```

*Expected: all existing tests pass + 3 new tests pass*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CB trips in production when NO-leg exhausts | RISK-03 | Requires live trade execution path | Run `--live` mode and verify CB status in dashboard after repeated NO-leg failures |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING test references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
