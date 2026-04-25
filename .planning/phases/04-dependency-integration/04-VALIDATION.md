---
phase: 04
slug: dependency-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (pytest section) |
| **Quick run command** | `python -m pytest tests/test_dependency.py tests/test_cross_market.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_dependency.py tests/test_cross_market.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 0 | DEP-09 | — | N/A | unit | `python -m pytest tests/test_dependency.py -x -q` | TBD | ⬜ pending |
| 04-02-01 | 02 | 1 | DEP-09 | — | N/A | unit | `python -m pytest tests/test_cross_market.py -x -q` | TBD | ⬜ pending |
| 04-02-02 | 02 | 1 | DEP-10 | — | N/A | unit | `python -m pytest tests/test_cross_market.py -x -q` | TBD | ⬜ pending |
| 04-02-03 | 02 | 1 | DEP-11 | — | N/A | unit | `python -m pytest tests/test_cross_market.py -x -q` | TBD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Fix WR-01 and WR-02 in `dependency.py` with regression tests in `tests/test_dependency.py`
- [ ] Add BotConfig fields for dependency weights/thresholds/audit_mode

*Existing test infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
