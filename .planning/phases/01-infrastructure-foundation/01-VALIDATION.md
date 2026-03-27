---
phase: 1
slug: infrastructure-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pytest.ini` — Wave 0 creates this |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds (unit) / ~30 seconds (full with connectivity) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_config.py -x -q` (unit tests only, no network)
- **After every plan wave:** Run `pytest tests/ -x -q` (full suite including connectivity)
- **Before `/gsd:verify-work`:** Full suite must be green + latency benchmark PASS
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | INFRA-04 | unit | `pytest tests/test_config.py::test_missing_secret_raises -x` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | INFRA-04 | unit | `pytest tests/test_config.py::test_config_loads -x` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 0 | INFRA-05 | unit | `pytest tests/test_config.py::test_wallet_address_derivation -x` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | INFRA-01 | smoke | `pytest tests/test_connectivity.py::test_clob_http_reachable -x` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 1 | INFRA-01 | smoke | `pytest tests/test_connectivity.py::test_latency_under_100ms -x` | ❌ W0 | ⬜ pending |
| 1-02-03 | 02 | 1 | INFRA-02 | smoke | `pytest tests/test_connectivity.py::test_alchemy_http_rpc -x` | ❌ W0 | ⬜ pending |
| 1-02-04 | 02 | 1 | INFRA-02 | smoke | `pytest tests/test_connectivity.py::test_alchemy_ws_rpc -x` | ❌ W0 | ⬜ pending |
| 1-02-05 | 02 | 1 | INFRA-05 | smoke | `pytest tests/test_connectivity.py::test_clob_client_wallet_address -x` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 2 | INFRA-03 | manual | `docker build -t arbbot .` | — | ⬜ pending |
| 1-03-02 | 03 | 2 | INFRA-03 | manual | `docker compose up --wait` | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (read-only ClobClient, config with test env vars)
- [ ] `tests/test_config.py` — stubs for INFRA-04, INFRA-05 (secret validation unit tests)
- [ ] `tests/test_connectivity.py` — stubs for INFRA-01, INFRA-02 (network smoke tests; skip if no VPS env)
- [ ] `pytest.ini` — test marks definition (`smoke`, `unit`)
- [ ] `pip install pytest pytest-asyncio` — if not yet in requirements.txt

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker image builds without error | INFRA-03 | Requires Docker daemon + VPS environment | `docker build -t arbbot .` — expect exit 0 |
| Container starts and healthcheck passes | INFRA-03 | Requires running Docker with real secrets.env | `docker compose up --wait` — healthcheck must report healthy |
| Latency benchmark < 100ms median | INFRA-01 | Must run from VPS (not local dev machine) | `python scripts/benchmark_latency.py` — expect "Median < 100ms: PASS" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
