---
phase: 06
slug: wire-critical-telegram-alerts
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pytest.ini` (asyncio_mode=auto) |
| **Quick run command** | `pytest tests/ -m unit -x -q` |
| **Full suite command** | `pytest tests/ -m unit -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -m unit -x -q`
- **After every plan wave:** Run `pytest tests/ -m unit -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | OBS-02 | — | N/A | unit | `pytest tests/ -m unit -x -q` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | OBS-02 | — | N/A | unit | `pytest tests/ -m unit -x -q` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | OBS-02 | — | N/A | manual grep | `grep -n "send_kill_switch" src/bot/live_run.py` | N/A | ⬜ pending |
| 06-01-04 | 01 | 1 | OBS-02 | — | N/A | manual grep | `grep -n "send_circuit_breaker_trip" src/bot/live_run.py` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_live_run.py` — extend with 4 new alert wiring tests for OBS-02:
  - `test_kill_switch_alert_fires_kill_file` — kill trigger "KILL file"
  - `test_kill_switch_alert_fires_sigterm` — kill trigger "SIGTERM"
  - `test_cb_alert_fires_on_trip` — CB closed→open transition fires alert
  - `test_cb_alert_no_duplicate` — CB already open, no duplicate alert

*Existing test infrastructure (`asyncio_mode=auto`, `AsyncMock`, `MagicMock`, `_test_config()` fixture) covers all requirements. No new conftest entries needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `send_kill_switch` has ≥1 call site | OBS-02 | Grep verification per ROADMAP success criteria | `grep -n "send_kill_switch" src/bot/live_run.py` — must return ≥1 result |
| `send_circuit_breaker_trip` has ≥1 call site | OBS-02 | Grep verification per ROADMAP success criteria | `grep -n "send_circuit_breaker_trip" src/bot/live_run.py` — must return ≥1 result |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
