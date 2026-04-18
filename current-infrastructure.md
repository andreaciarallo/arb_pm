# Current Infrastructure

**Project:** Polymarket Arbitrage Bot
**Last Updated:** 2026-04-18
**Status:** LIVE — all phases complete, bot running in live execution mode

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VPS: Hetzner CPX31                                │
│                           Helsinki, FI (HEL1)                               │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        Docker Container: arbbot                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │  src/bot/                                                        │  │ │
│  │  │  ├── main.py          (entrypoint)                               │  │ │
│  │  │  ├── config.py        (BotConfig, fail-fast secrets)             │  │ │
│  │  │  ├── client.py        (ClobClient factory, signature_type=0)     │  │ │
│  │  │  ├── health.py        (Docker HEALTHCHECK)                       │  │ │
│  │  │  ├── dry_run.py       (24h scanner loop)                         │  │ │
│  │  │  ├── live_run.py      (Phase 3: live execution)                  │  │ │
│  │  │  │                                                              │  │ │
│  │  │  ├── detection/       (arb opportunity detection)                │  │ │
│  │  │  │   ├── yes_no_arb.py                                          │  │ │
│  │  │  │   ├── cross_market.py                                        │  │ │
│  │  │  │   └── fee_model.py                                           │  │ │
│  │  │  │                                                              │  │ │
│  │  │  ├── scanner/         (market data ingestion)                    │  │ │
│  │  │  │   ├── ws_client.py     (WebSocket primary)                    │  │ │
│  │  │  │   ├── http_poller.py   (HTTP fallback)                        │  │ │
│  │  │  │   ├── market_filter.py (liquidity filtering)                  │  │ │
│  │  │  │   ├── price_cache.py   (in-memory LRU cache)                  │  │ │
│  │  │  │   └── normalizer.py    (price normalization)                  │  │ │
│  │  │  │                                                              │  │ │
│  │  │  ├── execution/       (Phase 3: order placement)                 │  │ │
│  │  │  │   ├── engine.py        (trade orchestration)                  │  │ │
│  │  │  │   ├── order_client.py  (FAK orders, fill verification)        │  │ │
│  │  │  │   └── kelly.py         (position sizing)                      │  │ │
│  │  │  │                                                              │  │ │
│  │  │  ├── risk/            (Phase 3: risk gates)                      │  │ │
│  │  │  │   └── gate.py          (circuit breakers, limits)             │  │ │
│  │  │  │                                                              │  │ │
│  │  │  └── storage/         (SQLite persistence)                       │  │ │
│  │  │      ├── schema.py        (DB initialization)                    │  │ │
│  │  │      └── writer.py        (async queue writer)                   │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                        │ │
│  │  Volume Mount: bot_data → /app/data (SQLite DB)                        │ │
│  │  Secrets: env_file: secrets.env (runtime injection)                    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                          │
                          │ HTTP/2 + WebSocket
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  External Services                                                          │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐ │
│  │ Polymarket CLOB     │  │ Alchemy Polygon RPC │  │ Telegram Alerts     │ │
│  │ clob.polymarket.com │  │ https + wss         │  │ Daily P&L summary   │ │
│  │ - Order book        │  │ - Balance checks    │  │ Arb complete alerts │ │
│  │ - Order placement   │  │ - Token approvals   │  │                     │ │
│  │ - Fill notifications│  │                     │  │                     │ │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Inventory

### 1. VPS Infrastructure

| Field | Value |
|-------|-------|
| **Provider** | Hetzner Cloud |
| **Server Type** | CPX31 (4 vCPU, 8GB RAM) |
| **Location** | Helsinki, FI (HEL1) |
| **IP Address** | 204.168.164.145 |
| **Bot Directory** | `/opt/arbbot` |
| **Geoblock Status** | Not blocked (`country: FI`) |
| **Latency to CLOB** | ~35ms median (gate: <100ms) |

---

### 2. Docker Containerization

| Field | Value |
|-------|-------|
| **Base Image** | `python:3.12-slim` (Debian, NOT Alpine) |
| **Container Name** | `arbbot` |
| **Service Name** | `bot` |
| **Restart Policy** | `unless-stopped` |
| **Healthcheck** | `python -m bot.health` (30s interval, 10s timeout, 3 retries) |
| **Volume** | `bot_data:/app/data` (SQLite persistence) |
| **Log Rotation** | 5 files × 10MB = 50MB max |
| **Build Command** | `docker compose build bot` |
| **Deploy Command** | `docker compose up -d` |

**Why NOT Alpine:** Alpine uses musl libc which breaks `eth-account`/`cryptography` manylinux wheels.

---

### 3. Application Modules

| Module | File | Role | Phase |
|--------|------|------|-------|
| **Config** | `src/bot/config.py` | BotConfig dataclass, fail-fast secret validation (6 REQUIRED_SECRETS) | 1 |
| **Client** | `src/bot/client.py` | ClobClient factory with signature_type=0 (EOA wallet) | 1 |
| **Health** | `src/bot/health.py` | CLOB reachability check for Docker HEALTHCHECK | 1 |
| **Main** | `src/bot/main.py` | Entrypoint: config → health → dry_run/live_run | 1 |
| **Dry Run** | `src/bot/dry_run.py` | 24h scanner loop, zero trades, SQLite logging | 2 |
| **Live Run** | `src/bot/live_run.py` | Phase 3 live execution with risk gates | 3 |
| **Detection** | `src/bot/detection/` | YES/NO arb, cross-market arb, fee modeling | 2 |
| **Scanner** | `src/bot/scanner/` | WebSocket client, HTTP poller, market filter, price cache | 2 |
| **Execution** | `src/bot/execution/` | FAK order placement, dual fill verification, Kelly sizing | 3 |
| **Risk** | `src/bot/risk/` | Circuit breakers, daily loss limits, position caps | 3 |
| **Storage** | `src/bot/storage/` | SQLite schema, async queue writer | 2 |
| **Dashboard** | `src/bot/dashboard/` | FastAPI dashboard on port 8080 | 4 |
| **Notifications** | `src/bot/notifications/` | Telegram alerts (arb complete, daily summary) | 4 |

---

### 4. Secrets Management

| Secret | Purpose | Source |
|--------|---------|--------|
| `POLY_API_KEY` | Polymarket CLOB API key | Generated via `scripts/create_api_key.py` |
| `POLY_API_SECRET` | Polymarket CLOB API secret | Generated via `scripts/create_api_key.py` |
| `POLY_API_PASSPHRASE` | Polymarket CLOB API passphrase | Generated via `scripts/create_api_key.py` |
| `WALLET_PRIVATE_KEY` | EOA wallet for signing (signature_type=0) | User-generated |
| `POLYGON_RPC_HTTP` | Alchemy Polygon HTTP RPC | Alchemy dashboard |
| `POLYGON_RPC_WS` | Alchemy Polygon WebSocket RPC | Alchemy dashboard |

**Security Pattern:**
- `secrets.env` exists ONLY on VPS (chmod 600)
- `secrets.env.example` committed to git (placeholder values)
- Runtime injection via `env_file:` in docker-compose.yml
- Never logged, never committed

---

### 5. Wallet & On-Chain Setup

| Field | Value |
|-------|-------|
| **Wallet Address** | `0x0036F15972166642fCb242F11fa5D1b6AD58Bc70` |
| **Network** | Polygon (chain ID 137) |
| **Collateral Token** | USDC.e (`0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`) |
| **Balance** | ~5.88 USDC.e |
| **MATIC (gas)** | ~25 MATIC |

**Approved contracts (MAX_UINT256 allowance set on 2026-04-18):**
| Contract | Address |
|----------|---------|
| CTF Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| Neg Risk CTF Exchange | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| Neg Risk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |

**Key finding:** Polymarket CLOB uses **USDC.e** (bridged, `0x2791...`), not native USDC (`0x3c499...`).
USDC.e `approve()` requires ~67k gas — use 100k gas limit minimum.

---

### 6. External Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `py-clob-client` | 0.34.6 | Official Polymarket CLOB SDK |
| `httpx` | 0.28.1 | HTTP/2 client (lower latency) |
| `websockets` | 16.0 | Real-time order book updates |
| `loguru` | 0.7.3 | Structured logging with rotation |
| `python-dotenv` | 1.2.2 | Local .env loading (dev only) |
| `pytest` | 8.3.4 | Test framework |
| `pytest-asyncio` | 0.25.0 | Async test support |

---

## Known Issues

### RESOLVED: Geoblocking (INFRA-GEO-001)

| Field | Value |
|-------|-------|
| **Status** | RESOLVED 2026-04-18 |
| **Fix** | Migrated VPS from Ashburn VA (US, blocked) to Helsinki HEL1 (FI, allowed) |

---

### RESOLVED: Latency Headroom (INFRA-LAT-001)

| Field | Value |
|-------|-------|
| **Status** | RESOLVED 2026-04-18 |
| **Fix** | HEL1 latency ~35ms median vs previous 92.4ms on Ashburn VA |

---

### RESOLVED: pytest Version Conflict (BUILD-001)

**Fix:** Downgraded `pytest` from `9.0.2` to `8.3.4` in `requirements.txt`.

---

### RESOLVED: PYTHONPATH in Dockerfile (BUILD-002)

**Fix:** Added `ENV PYTHONPATH=/app/src` to Dockerfile.

---

### RESOLVED: place_fak_order size parameter semantics (EXEC-SIZE-001)

| Field | Value |
|-------|-------|
| **Issue ID** | EXEC-SIZE-001 |
| **Severity** | LOW (monitor) |
| **Status** | RESOLVED 2026-04-18 |

**Fix:** Added `size_tokens = size_usd / price` conversion in `place_fak_order` before
constructing `OrderArgs`. `OrderArgs.size` now receives token count, not USD.
Debug log updated to emit both `size_usd` and `size_tokens`. Regression tests added
to `tests/test_order_client.py` (3 new tests, all passing).

---

## Current Phase Status

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| **Phase 1** | Infrastructure Foundation | COMPLETE | HEL1 VPS running, latency ~35ms |
| **Phase 2** | Market Data & Detection | COMPLETE | Scanner operational |
| **Phase 3** | Execution & Risk Controls | COMPLETE | Live mode, FAK orders accepted |
| **Phase 4** | Observability & Monitoring | COMPLETE | Telegram alerts, FastAPI dashboard |

---

## UAT Test Results

### Original UAT — Ashburn VA (2026-04-02) — FAILED

| Step | Description | Result |
|------|-------------|--------|
| Step 1 | Git pull on VPS | PASS |
| Step 2 | Find safe test token ID | PASS |
| Step 3 | Place FAK order | FAIL — 403 Geoblocked |

### HEL1 Migration UAT (2026-04-18) — PASSED

| Step | Description | Result |
|------|-------------|--------|
| 4.1 | Geoblock check | PASS — `blocked: false, country: FI` |
| 4.2 | Latency benchmark | PASS — median ~35ms |
| 4.2.5 | Wallet funded | PASS — 5.88 USDC.e, 25 MATIC |
| 4.3 | FAK order placement | PASS — orderID returned, killed (no match at price=0.01) |
| 5.1 | Old VPS (5.161.94.245) stopped | PASS — `docker compose stop` graceful |
| 5.3 | Old VPS deleted | PASS — removed from Hetzner console |
