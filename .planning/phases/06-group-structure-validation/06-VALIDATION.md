---
phase: 6
slug: group-structure-validation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/conftest.py |
| **Quick run command** | `python -m pytest tests/test_group_validator.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_group_validator.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | GV-01 | — | N/A | unit | `python -m pytest tests/test_group_validator.py -k negris -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | GV-04 | — | N/A | unit | `python -m pytest tests/test_group_validator.py -k enriched -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | GV-02 | — | N/A | unit | `python -m pytest tests/test_group_validator.py -k duplicate -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | GV-03 | — | N/A | unit | `python -m pytest tests/test_group_validator.py -k subset -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 1 | GV-05 | — | N/A | unit | `python -m pytest tests/test_group_validator.py -k completeness -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_group_validator.py` — stubs for GV-01 through GV-05
- [ ] `tests/conftest.py` — shared fixtures (if not already existing)

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Gamma API NegRisk field consistency | GV-01 | Requires live API data | Query `GET /events?active=true&limit=100` and verify all markets in NegRisk events have `negRisk=True` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
