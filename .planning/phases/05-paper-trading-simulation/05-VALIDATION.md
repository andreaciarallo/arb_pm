---
phase: 5
slug: paper-trading-simulation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pytest.ini (existing) |
| **Quick run command** | `python -m pytest tests/test_paper_trading.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_paper_trading.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | PAPER-02 | — | N/A | unit | `pytest tests/test_paper_trading.py::test_paper_trades_table_creation -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | PAPER-03 | — | N/A | unit | `pytest tests/test_paper_trading.py::test_paper_trade_record_schema -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | PAPER-01 | — | N/A | unit | `pytest tests/test_paper_trading.py::test_yes_no_simulation -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | PAPER-04 | — | N/A | unit | `pytest tests/test_paper_trading.py::test_cross_market_simulation -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | PAPER-05 | — | N/A | unit | `pytest tests/test_paper_summary.py -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | PAPER-01 | — | integration | `pytest tests/test_paper_trading.py::test_dry_run_integration -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_paper_trading.py` — stubs for PAPER-01, PAPER-02, PAPER-03, PAPER-04
- [ ] `tests/test_paper_summary.py` — stubs for PAPER-05
- [ ] Shared fixtures for paper trade test data (ArbitrageOpportunity, PriceCache mocks)

*Existing pytest infrastructure covers framework requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
