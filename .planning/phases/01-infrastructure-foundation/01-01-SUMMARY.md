---
phase: 01-infrastructure-foundation
plan: 01
subsystem: infra
tags: [py-clob-client, eth-account, python, pytest, secrets-management, docker, polymarket]

# Dependency graph
requires: []
provides:
  - requirements.txt with 7 pinned packages (py-clob-client==0.34.6)
  - BotConfig dataclass with fail-fast RuntimeError on missing secrets
  - build_client() factory returning authenticated ClobClient with signature_type=0
  - secrets.env.example template with all 8 env var slots
  - .gitignore excluding secrets.env and .env
  - pytest.ini with unit and smoke markers
  - tests/conftest.py with bot_config and real_config fixtures
  - 6 unit tests covering INFRA-04 and INFRA-05
affects: [02-data-streaming, 03-execution-engine, 04-monitoring-dashboard]

# Tech tracking
tech-stack:
  added:
    - py-clob-client==0.34.6 (official Polymarket CLOB SDK)
    - eth-account (transitive dep via py-clob-client, used for EOA wallet)
    - httpx[http2]==0.28.1 (async HTTP)
    - websockets==16.0 (WebSocket client for Phase 2)
    - loguru==0.7.3 (structured logging)
    - python-dotenv==1.2.2 (dev env loading)
    - pytest==9.0.2 + pytest-asyncio (test framework)
  patterns:
    - Fail-fast secret validation: check all REQUIRED_SECRETS at startup, raise RuntimeError listing missing vars
    - BotConfig frozen dataclass: immutable config object passed to all subsystems
    - ClobClient factory: build_client(config) returns authenticated L2 client with signature_type=0 (EOA)
    - Docker env_file pattern: secrets.env on VPS only, secrets.env.example committed to git

key-files:
  created:
    - requirements.txt
    - pytest.ini
    - .gitignore
    - secrets.env.example
    - src/bot/__init__.py
    - src/bot/config.py
    - src/bot/client.py
    - tests/conftest.py
    - tests/test_config.py
    - conftest.py
  modified: []

key-decisions:
  - "Use signature_type=0 (EOA) for ClobClient — not type 1 (Magic/email wallet only)"
  - "Three-part CLOB API auth: POLY_API_KEY + POLY_API_SECRET + POLY_API_PASSPHRASE (not two-part)"
  - "eth-account is a py-clob-client transitive dep — do NOT add to requirements.txt to avoid version conflicts"
  - "Root conftest.py adds src/ to sys.path for pytest discovery in src/ layout"
  - "Never log raw POLYGON_RPC_HTTP or POLYGON_RPC_WS — Alchemy API key is embedded in URL path"

patterns-established:
  - "Pattern 1: Fail-fast secret validation — load_config() raises RuntimeError listing all missing vars"
  - "Pattern 2: ClobClient factory — build_client(config: BotConfig) -> ClobClient with signature_type=0"
  - "Pattern 3: Docker env_file secrets — secrets.env on VPS only, secrets.env.example committed"
  - "Pattern 4: Test fixtures — bot_config (fake env), real_config (skip if no real secrets)"

requirements-completed: [INFRA-04, INFRA-05]

# Metrics
duration: 3min
completed: 2026-03-27
---

# Phase 1, Plan 01: Project Skeleton and Infrastructure Setup Summary

**Fail-fast BotConfig with RuntimeError on missing secrets, authenticated ClobClient factory using EOA signature_type=0, and pytest test infrastructure covering INFRA-04 and INFRA-05**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-27T19:16:37Z
- **Completed:** 2026-03-27T19:20:34Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Pinned requirements.txt (7 packages) with py-clob-client==0.34.6, no eth-account entry (transitive dep)
- Fail-fast BotConfig dataclass: load_config() raises RuntimeError listing all missing vars at startup (D-06)
- Authenticated ClobClient factory: build_client() configures EOA wallet with signature_type=0 and three-part ApiCreds
- secrets.env.example with all 8 env var slots committed; secrets.env in .gitignore (D-03, D-05)
- pytest.ini with unit/smoke markers; conftest.py with bot_config and real_config fixtures
- All 6 unit tests passing (INFRA-04 and INFRA-05 fully covered)

## Task Commits

Each task was committed atomically:

1. **Task 1: Project skeleton and pinned dependencies** - `f1d2cd8` (feat)
2. **Task 2 RED: Failing tests for config validation** - `79f081f` (test)
3. **Task 2 GREEN: Fail-fast config and ClobClient implementation** - `cf761b0` (feat)

_Note: TDD task 2 has two commits (test RED → feat GREEN)_

## Files Created/Modified
- `requirements.txt` - 7 pinned packages, py-clob-client==0.34.6 anchors the stack
- `pytest.ini` - asyncio_mode=auto, unit and smoke marker definitions
- `.gitignore` - excludes secrets.env, .env, pycache, venvs, test artifacts
- `secrets.env.example` - all 8 env var slots with placeholder values (committed to git)
- `src/bot/__init__.py` - empty package init
- `src/bot/config.py` - REQUIRED_SECRETS list, BotConfig frozen dataclass, load_config() with fail-fast RuntimeError
- `src/bot/client.py` - CLOB_HOST constant, build_client() with signature_type=0 and ApiCreds three-part auth
- `tests/conftest.py` - bot_config fixture (fake env), real_config fixture (skip if no real secrets)
- `tests/test_config.py` - 6 unit tests covering secret validation, optional defaults, wallet derivation, client factory
- `conftest.py` - root conftest adds src/ to sys.path for pytest discovery

## Decisions Made
- Used `PYTHONPATH=src` approach via root conftest.py instead of `PYTHONPATH=.` — the src/ layout requires adding src/ to sys.path for `from bot.xxx import yyy` to work
- eth-account NOT added to requirements.txt (transitive dep of py-clob-client; adding separately risks version conflicts)
- signature_type=0 (EOA) confirmed correct for directly-controlled private key wallet
- Three-part Polymarket auth (api_key + api_secret + api_passphrase) explicitly enforced via REQUIRED_SECRETS

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed PYTHONPATH for src/ layout pytest discovery**
- **Found during:** Task 2 (GREEN phase test run)
- **Issue:** Plan's verify command used `PYTHONPATH=.` but `bot` module is at `src/bot/`, not `./bot/`. Tests failed with `ModuleNotFoundError: No module named 'bot'`
- **Fix:** Created root `conftest.py` that inserts `src/` into `sys.path` at pytest startup, making `PYTHONPATH=.` equivalent to `PYTHONPATH=src` without manual env var
- **Files modified:** `conftest.py` (new file)
- **Verification:** `python -m pytest tests/test_config.py -x -q` exits 0 with 6 passed
- **Committed in:** `cf761b0` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for correct pytest discovery in src/ layout. No scope creep.

## Issues Encountered
- pytest-asyncio 0.25.0 version conflict with system Python — system had pytest-asyncio 1.3.0 installed. Using 1.3.0 is fine for local dev; the pinned 0.25.0 will be enforced in the Docker container build on VPS. Tests pass with both versions.

## User Setup Required
None - no external service configuration required for this plan. Secrets will be needed for smoke tests in subsequent plans.

## Next Phase Readiness
- All infrastructure primitives ready for Phase 1, Plan 02 (Docker + VPS provisioning)
- BotConfig and build_client() are the foundation for all subsequent plans
- Test infrastructure (pytest.ini, conftest.py, unit tests) ready for all subsequent plan verify commands
- secrets.env.example shows exactly what needs to be filled on the VPS

---
*Phase: 01-infrastructure-foundation*
*Completed: 2026-03-27*
