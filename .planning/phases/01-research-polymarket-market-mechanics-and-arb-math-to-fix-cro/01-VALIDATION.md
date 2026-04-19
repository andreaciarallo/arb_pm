---
phase: 1
slug: research-polymarket-market-mechanics-and-arb-math-to-fix-cro
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-19
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with asyncio_mode=auto |
| **Config file** | `pytest.ini` (project root) |
| **Quick run command** | `PYTHONPATH=src pytest tests/test_cross_market.py -m unit -x` |
| **Full suite command** | `PYTHONPATH=src pytest tests/ -m unit -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONPATH=src pytest tests/test_cross_market.py -m unit -x`
- **After every plan wave:** Run `PYTHONPATH=src pytest tests/ -m unit -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | DRY-RUN | — | N/A | manual | `ssh root@204.168.164.145 "docker compose logs --tail=5 bot"` | N/A | ⬜ pending |
| 1-02-01 | 02 | 2 | CROSS-DETECT | — | N/A | unit | `PYTHONPATH=src pytest tests/test_cross_market.py -m unit -x` | ✅ | ⬜ pending |
| 1-02-02 | 02 | 2 | CROSS-DETECT | — | N/A | unit | `PYTHONPATH=src pytest tests/test_cross_market.py::test_neg_risk_grouping -x` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 3 | CROSS-EXEC | — | N/A | unit | `PYTHONPATH=src pytest tests/test_execution_engine.py -m unit -x` | ✅ | ⬜ pending |
| 1-03-02 | 03 | 3 | CROSS-EXEC | — | N/A | unit | `PYTHONPATH=src pytest tests/test_execution_engine.py::test_cross_market_legs_gate -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_cross_market.py::test_neg_risk_grouping` — test that `_group_by_neg_risk()` groups markets by `neg_risk_market_id` correctly
- [ ] `tests/test_execution_engine.py::test_cross_market_legs_gate` — test that cross-market opportunity with `legs` list passes Gate 0

*Existing infrastructure covers the rest of the phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| VPS bot running in dry-run mode | DRY-RUN | Requires SSH to VPS; no local test environment | `ssh root@204.168.164.145 "docker compose logs --tail=10 bot \| grep 'dry-run\|live'"` — must see "dry-run scanner" |
| `neg_risk_market_id` field present in live API response | CROSS-DETECT | Requires live Polymarket API call; cannot be mocked reliably | Run `python -c "..."` on VPS to print a raw market dict and confirm field name |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
