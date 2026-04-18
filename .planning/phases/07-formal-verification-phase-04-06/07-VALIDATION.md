---
phase: 7
slug: formal-verification-phase-04-06
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (existing) |
| **Config file** | `pytest.ini` (asyncio_mode=auto) |
| **Quick run command** | `pytest tests/ -m unit -x -q` |
| **Full suite command** | `pytest tests/ -m unit -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -m unit -x -q`
- **After every plan wave:** Run `pytest tests/ -m unit -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 7-01-01 | 01 | 1 | OBS-01, OBS-03, OBS-04, OBS-02 | — | N/A (docs only) | static grep | `grep -n "send_kill_switch\|send_circuit_breaker_trip" src/bot/live_run.py` | ✅ | ⬜ pending |
| 7-01-02 | 01 | 1 | OBS-01, OBS-03, OBS-04 | — | N/A (docs only) | static grep | `grep -n "OBS-01\|OBS-03\|OBS-04" .planning/REQUIREMENTS.md` | ✅ | ⬜ pending |
| 7-01-03 | 01 | 1 | OBS-01, OBS-03, OBS-04, OBS-02 | — | N/A (docs only) | file check | `test -f .planning/phases/07-formal-verification-phase-04-06/07-01-SUMMARY.md` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. This is a documentation-only phase — no new test files are needed. The existing 103-test suite is the regression baseline.

Run before and after edits to confirm no regressions:
```
pytest tests/ -m unit -q
```

*Expected: 103 passed, 37 deselected*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase 06 VERIFICATION.md created and accurate | OBS-02 | File existence + content quality review | Read `.planning/phases/06-wire-critical-telegram-alerts/VERIFICATION.md`; confirm all 3 success criteria have VERIFIED status with correct line citations |
| REQUIREMENTS.md rows updated correctly | OBS-01, OBS-03, OBS-04 | Row-level table edit verification | `grep -A1 "OBS-01\|OBS-03\|OBS-04" .planning/REQUIREMENTS.md` — each row must show `Complete` status |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
