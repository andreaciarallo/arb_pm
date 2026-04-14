---
phase: 4
slug: observability-monitoring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-14
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.4 + pytest-asyncio 0.25.0 |
| **Config file** | `pytest.ini` (root) — `asyncio_mode = auto` |
| **Quick run command** | `pytest tests/ -m unit -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -m unit -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 0 | OBS-01, OBS-04 | — | N/A | unit | `pytest tests/test_storage.py -k "fees or arb_pair" -x` | ❌ W0 | ⬜ pending |
| 4-01-02 | 01 | 0 | OBS-02 | — | Telegram failures never propagate to caller | unit | `pytest tests/test_telegram.py -k "noop or error" -x` | ❌ W0 | ⬜ pending |
| 4-01-03 | 01 | 0 | OBS-03 | — | N/A | unit | `pytest tests/test_dashboard.py -k "status or html" -x` | ❌ W0 | ⬜ pending |
| 4-02-01 | 02 | 1 | OBS-01 | — | fees_usd uses real fee computation (not 0.0) | unit | `pytest tests/test_storage.py -k "fees" -x` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 1 | OBS-01, OBS-04 | — | arb_pairs row only written after both legs filled | unit | `pytest tests/test_storage.py -k "arb_pair" -x` | ❌ W0 | ⬜ pending |
| 4-03-01 | 03 | 2 | OBS-02 | — | Telegram send is fire-and-forget (asyncio.create_task) | unit | `pytest tests/test_telegram.py -x` | ❌ W0 | ⬜ pending |
| 4-04-01 | 04 | 3 | OBS-03 | — | /api/status returns JSON with required keys | unit | `pytest tests/test_dashboard.py -k "status" -x` | ❌ W0 | ⬜ pending |
| 4-04-02 | 04 | 3 | OBS-03 | — | / returns HTML with setInterval(refresh, 10000) | unit | `pytest tests/test_dashboard.py -k "html" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_telegram.py` — stubs for OBS-02 (TelegramAlerter unit tests with mocked `telegram.Bot`)
- [ ] `tests/test_dashboard.py` — stubs for OBS-03 (FastAPI TestClient tests for `/` and `/api/status`)
- [ ] `tests/test_storage.py` additions — new test cases for `arb_pairs` schema (OBS-01, OBS-04) and `fees_usd` fix
- [ ] `pip install fastapi==0.135.3 uvicorn==0.44.0 python-telegram-bot==22.7` (dev environment setup)

*FastAPI's TestClient (from starlette.testclient) is synchronous — no running server needed for unit tests.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dashboard accessible in browser at port 8080 | OBS-03 | Requires running Docker container + browser | `docker compose up -d && curl http://localhost:8080/` returns HTML |
| Telegram alert received on mobile | OBS-02 | Requires real Telegram token + chat_id | Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env, trigger a trade or circuit breaker trip |
| Daily summary fires at midnight UTC | OBS-02 | Requires 24h runtime | Check Telegram at 00:01 UTC for summary message |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
