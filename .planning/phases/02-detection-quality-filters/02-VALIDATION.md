---
phase: 2
slug: detection-quality-filters
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pytest.ini` (asyncio_mode = auto) |
| **Quick run command** | `python -m pytest tests/ -m unit -x -q` |
| **Full suite command** | `python -m pytest tests/ -m unit -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -m unit -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -m unit -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | DETECT-01 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_ask_floor_reject -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | DETECT-01 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_ask_floor_boundary -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | DETECT-02 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_sum_cap_reject -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | DETECT-02 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_sum_cap_boundary -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 1 | DETECT-03 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_dead_leg_reject -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 1 | DETECT-03 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_dead_leg_boundary -x` | ❌ W0 | ⬜ pending |
| 02-01-07 | 01 | 1 | DETECT-04 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_total_yes_reject -x` | ❌ W0 | ⬜ pending |
| 02-01-08 | 01 | 1 | DETECT-04 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_total_yes_boundary -x` | ❌ W0 | ⬜ pending |
| 02-01-09 | 01 | 1 | DETECT-05 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_dedup_suppresses -x` | ❌ W0 | ⬜ pending |
| 02-01-10 | 01 | 1 | DETECT-05 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_dedup_expires -x` | ❌ W0 | ⬜ pending |
| 02-01-11 | 01 | 1 | DETECT-05 | — | N/A | unit | `python -m pytest tests/test_filters.py::test_dedup_separate_types -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | DETECT-01,02,05 | — | N/A | unit | `python -m pytest tests/test_yes_no_arb.py -x` | ✅ (update) | ⬜ pending |
| 02-02-02 | 02 | 2 | DETECT-03,04,05 | — | N/A | unit | `python -m pytest tests/test_cross_market.py -x` | ✅ (update) | ⬜ pending |
| 02-02-03 | 02 | 2 | DETECT-05 | — | N/A | unit | `python -m pytest tests/test_dry_run.py -x` | ✅ (update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_filters.py` — stubs for DETECT-01 through DETECT-05 with boundary tests
- [ ] Update `tests/test_yes_no_arb.py` — adapt to new return type (list, diagnostics)
- [ ] Update `tests/test_cross_market.py` — adapt to new return type + dedup param
- [ ] Update `tests/test_dry_run.py` — mock new return types, verify dedup_suppressed in log

*Existing infrastructure covers test framework (pytest already installed and configured).*

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
