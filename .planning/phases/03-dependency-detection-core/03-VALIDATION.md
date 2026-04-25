---
phase: 03
slug: dependency-detection-core
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pytest.ini` (exists, `asyncio_mode = auto`) |
| **Quick run command** | `python3 -m pytest tests/test_dependency.py -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -x -q --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_dependency.py -x -q`
- **After every plan wave:** Run `python3 -m pytest tests/ -x -q --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | DEP-01 | — | N/A | unit | `python3 -m pytest tests/test_dependency.py -k "preprocess" -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | DEP-02 | — | N/A | unit | `python3 -m pytest tests/test_dependency.py -k "jaccard" -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | DEP-03 | — | N/A | unit | `python3 -m pytest tests/test_dependency.py -k "implication" -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | DEP-04 | — | N/A | unit | `python3 -m pytest tests/test_dependency.py -k "numeric" -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | DEP-05 | — | N/A | unit | `python3 -m pytest tests/test_dependency.py -k "temporal" -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 1 | DEP-06 | — | N/A | unit | `python3 -m pytest tests/test_dependency.py -k "event_bonus" -x` | ❌ W0 | ⬜ pending |
| 03-01-07 | 01 | 1 | DEP-07 | — | N/A | unit | `python3 -m pytest tests/test_dependency.py -k "score" -x` | ❌ W0 | ⬜ pending |
| 03-01-08 | 01 | 1 | DEP-08 | — | N/A | unit | `python3 -m pytest tests/test_dependency.py -k "classify" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_dependency.py` — stubs for DEP-01 through DEP-08
- No framework install needed — pytest 9.0.2 already available
- No conftest changes needed — module is pure, no config dependency

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
