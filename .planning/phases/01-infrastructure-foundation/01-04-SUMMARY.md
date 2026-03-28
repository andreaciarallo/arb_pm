---
phase: 01-infrastructure-foundation
plan: 04
subsystem: infra
tags: [docker, hetzner, vps, latency-benchmark, deployment, polymarket, alchemy, smoke-tests]

# Dependency graph
requires:
  - plan: "01-01"
    provides: "BotConfig, build_client(), secrets.env.example, .gitignore, pytest infrastructure"
  - plan: "01-02"
    provides: "scripts/benchmark_latency.py, scripts/create_api_key.py, tests/test_connectivity.py, src/bot/health.py"
  - plan: "01-03"
    provides: "Dockerfile, docker-compose.yml, src/bot/main.py"
provides:
  - Verified: arbbot container running (healthy) on Hetzner CPX31 in Ashburn, VA
  - Verified: benchmark_latency.py median 92.4ms from VPS — Median < 100ms: PASS
  - Verified: startup logs show correct wallet address 0x0036F15972166642fCb242F11fa5D1b6AD58Bc70 and CLOB reachable
  - Verified: secrets.env with chmod 600 and all 6 required values populated
  - Phase 1 INFRA-01 through INFRA-03 all confirmed on live VPS hardware
affects: [02-data-streaming, 03-execution-engine, 04-monitoring-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "VPS deploy pattern: rsync --exclude=.git --exclude=secrets.env, then create secrets.env on-VPS only"
    - "Latency gate: median < 100ms from VPS to clob.polymarket.com confirmed via 20-sample HTTP/2 benchmark"
    - "Docker health confirmation: docker compose ps shows 'running (healthy)' within 30s of start"

key-files:
  created: []
  modified: []

key-decisions:
  - "VPS location changed to Ashburn VA (us-east) from planned London (uk-lon1) — London not available in user's Hetzner account; Ashburn met the sub-100ms latency requirement (median 92.4ms)"
  - "Server type CPX31 used instead of CX32 — equivalent spec (4 vCPU, 8GB RAM), CPX31 is the US region naming convention for Hetzner"
  - "pytest pinned to 8.3.4 (not 9.0.2) to resolve version conflict discovered during VPS Docker build"
  - "PYTHONPATH added to Dockerfile to resolve import resolution inside container"

patterns-established:
  - "Pattern 8: VPS deploy confirmation — always run docker compose ps then logs bot before latency benchmark"
  - "Pattern 9: Latency gate is VPS-only — local dev machine results do not satisfy INFRA-01"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03]

# Metrics
duration: human-verification
completed: 2026-03-28
---

# Phase 1, Plan 04: VPS Deployment Verification Summary

**Hetzner CPX31 in Ashburn VA running arbbot Docker container (healthy) with 92.4ms median latency to Polymarket CLOB — all Phase 1 INFRA requirements verified on live VPS hardware**

## Performance

- **Duration:** Human verification (async)
- **Started:** 2026-03-27 (plan issued)
- **Completed:** 2026-03-28
- **Tasks:** 3 (all human-verified)
- **Files modified:** 0 (verification-only plan)

## Accomplishments
- Hetzner CPX31 (4 vCPU, 8 GB RAM) provisioned in Ashburn VA with Docker 24+ and code deployed at /opt/arbbot/
- secrets.env created on VPS with chmod 600 and all 6 required values (POLY_API_KEY, POLY_API_SECRET, POLY_API_PASSPHRASE, WALLET_PRIVATE_KEY, POLYGON_RPC_HTTP, POLYGON_RPC_WS)
- docker compose ps confirms: arbbot running (healthy) after docker compose up -d
- Startup logs confirmed: secrets loaded, CLOB reachable, wallet address 0x0036F15972166642fCb242F11fa5D1b6AD58Bc70, Polygon RPC HTTP configured, Polygon RPC WS configured, bot idle loop running
- Latency benchmark (20 samples, HTTP/2): mean 92.8ms, median 92.4ms, P95 99.7ms, min 85.6ms, max 102.7ms — Median < 100ms: PASS
- Container survived docker compose restart with volume and data intact

## Task Commits

This plan is verification-only — no code was committed during plan execution.

1. **Task 1: Provision Hetzner VPS and prepare environment** — Human completed (no commit)
2. **Task 2: Build Docker image and verify container health** — Human completed (no commit)
3. **Task 3: Run latency benchmark from VPS** — Human completed, result: PASS

Two post-plan bug fixes were applied and committed to resolve issues discovered during VPS build:
- `pytest 9.0.2 → 8.3.4` (version conflict in Docker build)
- `PYTHONPATH` added to Dockerfile (import resolution inside container)

## Files Created/Modified

None — this plan specifies no file creation. All deliverables (Dockerfile, docker-compose.yml, scripts, tests) were created in Plans 01–03.

## Decisions Made

- VPS location: Ashburn VA (us-east) selected instead of planned London (uk-lon1). London was not available in the user's Hetzner account. Ashburn met the sub-100ms latency requirement — median 92.4ms confirms VPS location is adequate for strategy latency.
- Server type: CPX31 used instead of CX32. Equivalent spec (4 vCPU, 8 GB RAM). CPX31 is the Hetzner US region naming equivalent to CX32.
- pytest pinned to 8.3.4 (down from 9.0.2 in requirements.txt) to resolve a version conflict surfaced during VPS Docker image build.
- PYTHONPATH set in Dockerfile to resolve Python module import errors inside the container.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pytest version conflict on VPS Docker build**
- **Found during:** Task 2 (Docker image build on VPS)
- **Issue:** requirements.txt pinned pytest==9.0.2 caused a dependency version conflict during pip install inside the Docker container build
- **Fix:** Downgraded pytest pin to 8.3.4, which resolved the conflict without affecting test behavior
- **Files modified:** requirements.txt
- **Verification:** Docker image built successfully after pin change
- **Committed in:** Post-plan fix commit

**2. [Rule 1 - Bug] Missing PYTHONPATH in Dockerfile**
- **Found during:** Task 2 (Container startup verification)
- **Issue:** Python module imports failed inside the running container because PYTHONPATH was not set in the Dockerfile, causing ModuleNotFoundError for the bot package
- **Fix:** Added PYTHONPATH environment variable to Dockerfile so Python can resolve the src/ layout inside the container
- **Files modified:** Dockerfile
- **Verification:** Container started healthy, startup logs confirmed wallet address and CLOB reachable
- **Committed in:** Post-plan fix commit

### Planned Deviations (Location Change)

**VPS location: Ashburn VA instead of London (uk-lon1)**
- **Reason:** London (uk-lon1) not available in user's Hetzner account
- **Impact:** Median latency is 92.4ms vs ~45ms expected from London — still within the 100ms gate
- **Risk:** Latency is closer to the 100ms threshold; London would provide more headroom. Consider migrating if latency degrades or if strategy requires tighter timing.
- **Resolution:** Latency gate PASSED. Phase 1 INFRA-01 verified. No blocking impact on Phases 2-4.

---

**Total deviations:** 2 auto-fixed bugs (post-plan), 1 planned location deviation
**Impact on plan:** Bug fixes were required for correct Docker operation. Location change was unavoidable and still satisfies the 100ms gate.

## Issues Encountered

- Hetzner London (uk-lon1) was not available in the user's account — Ashburn VA was selected as the closest viable alternative
- pytest 9.0.2 caused version conflict in Docker pip install — downgraded to 8.3.4
- PYTHONPATH not set in Dockerfile — caused container startup failure until added

## User Setup Required

VPS is live and running. No additional setup required for Phase 2 development.

For ongoing maintenance:
- SSH access: `ssh root@<VPS_IP>`
- Bot status: `docker compose ps` from /opt/arbbot/
- Bot logs: `docker compose logs bot --tail=50`
- Restart: `docker compose restart bot`

## Next Phase Readiness

Phase 1 is complete. All 5 INFRA requirements (INFRA-01 through INFRA-05) are verified:
- INFRA-01: Sub-100ms latency to Polymarket CLOB confirmed from VPS (median 92.4ms)
- INFRA-02: Alchemy Polygon RPC endpoints configured and verified via startup logs
- INFRA-03: Docker container running (healthy) with restart: unless-stopped, named volume bot_data
- INFRA-04: BotConfig fail-fast config with all REQUIRED_SECRETS enforced (verified in Plans 01 + 02)
- INFRA-05: ClobClient with EOA signature_type=0, wallet 0x0036F15972166642fCb242F11fa5D1b6AD58Bc70 (verified via startup log)

Phase 2 (Market Data & Detection) can begin. The bot is running on VPS in idle loop — ready to add WebSocket subscription and arbitrage detection logic.

## Known Stubs

- `src/bot/main.py` idle loop — bot enters `while True: sleep(5)` placeholder. This is intentional: Phase 1 goal is infrastructure only. Phase 2 will replace the idle loop with WebSocket market data subscription and detection logic.

---
*Phase: 01-infrastructure-foundation*
*Completed: 2026-03-28*
