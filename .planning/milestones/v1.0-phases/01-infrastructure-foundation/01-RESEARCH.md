# Phase 1: Infrastructure Foundation - Research

**Researched:** 2026-03-27
**Domain:** Polymarket CLOB integration, Docker containerization, secrets management, VPS setup, Polygon RPC
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Use Hetzner London datacenter, CX32 tier (4 vCPU, 8GB RAM, ~8 EUR/mo)
- **D-02:** CX32 gives comfortable headroom for bot process + SQLite + future Phase 4 dashboard without over-provisioning
- **D-03:** Use Docker Compose `env_file` pointing to a `secrets.env` file on the VPS only — file is never committed to git, only lives on the server
- **D-04:** `secrets.env` must contain these slots (all required before bot starts): `POLY_API_KEY`, `POLY_API_SECRET`, `POLY_API_PASSPHRASE`, `WALLET_PRIVATE_KEY`, `POLYGON_RPC_HTTP`, `POLYGON_RPC_WS`, `TELEGRAM_BOT_TOKEN`, `DISCORD_WEBHOOK_URL`
- **D-05:** `secrets.env.example` template (with placeholder values) IS committed to git
- **D-06:** Bot fails fast at startup if any required secret is missing — no silent fallbacks
- **D-07:** Single container for the bot process, orchestrated via `docker-compose.yml`
- **D-08:** SQLite data stored on a named Docker volume (not bind mount) for persistence
- **D-09:** Container restart policy: `restart: unless-stopped`
- **D-10:** Phase 4 dashboard added as second service at that time — no multi-container pre-setup needed now
- **D-11:** Use Alchemy as the dedicated Polygon PoS RPC provider
- **D-12:** Configure both HTTP and WebSocket endpoints
- **D-13:** Alchemy Growth tier expected to cover usage; validate CU consumption after Phase 2

### Claude's Discretion

- Python base image selection (3.12-slim recommended for size vs compatibility)
- Dockerfile layer ordering and build cache optimization
- Health check implementation (`HEALTHCHECK` in Dockerfile — verify API connectivity)
- Project folder structure (`src/` layout vs flat)
- Latency benchmark script implementation details
- How to verify trade-only API key permissions programmatically

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Deploy bot to London VPS (eu-west-2) for low-latency Polymarket access | Hetzner uk-lon1 datacenter confirmed; Docker install path documented; latency benchmark script approach researched |
| INFRA-02 | Configure dedicated RPC endpoints ($200-400/month budget) | Alchemy Polygon endpoint URL format confirmed; HTTP + WebSocket both available; Growth/Pay-as-you-go tier starts at $0.40/1M CUs |
| INFRA-03 | Set up Docker containerization for reproducible deployment | Python 3.12-slim image confirmed current (updated 2026-03-20); Docker Compose env_file pattern documented; healthcheck syntax verified |
| INFRA-04 | Implement secure API key management (runtime injection, trade-only keys, no withdrawal permissions) | Polymarket CLOB L2 auth requires api_key + api_secret + api_passphrase (3 fields, not 2); fail-fast pattern with os.environ (not os.getenv) researched |
| INFRA-05 | Integrate non-custodial wallet for Polymarket CLOB signing | py-clob-client uses eth-account (not ethers.py) internally; EOA wallet = signature_type=0; Signer class accepts raw private key |

</phase_requirements>

---

## Summary

Phase 1 establishes the foundational infrastructure: a Dockerized Python bot process on a Hetzner London VPS, connected to Polymarket's CLOB API with a non-custodial wallet, using Alchemy as the dedicated Polygon RPC provider. The phase is greenfield — no existing code — and sets the conventions all subsequent phases follow.

The two critical discoveries from research are: (1) Polymarket's API credentials have three components (`api_key`, `api_secret`, `api_passphrase`), not two as might be assumed from other APIs; and (2) the wallet signing library used by py-clob-client is `eth-account` (a dependency of the package), not `ethers.py` — the CLAUDE.md reference to "ethers.py" is incorrect for Python. The bot uses `signature_type=0` for an EOA (directly-controlled private key) wallet, which requires no funder address when the signing key and funded address are the same.

The infrastructure is straightforward to implement: Python 3.12-slim Docker image, py-clob-client 0.34.6 with its bundled eth-account dependency, Docker Compose env_file for secrets, and a startup validation script that calls `os.environ[key]` (raises KeyError immediately if missing, satisfying D-06). The Polymarket CLOB HTTP host is `https://clob.polymarket.com` and the WebSocket endpoint is `wss://ws-subscriptions-clob.polymarket.com/ws/market` (confirmed from official example code).

**Primary recommendation:** Follow the locked decisions exactly. The only discretionary choices are image tag (use `python:3.12-slim`), folder structure (use `src/` layout with `src/bot/` subpackage), and healthcheck (HTTP GET to `https://clob.polymarket.com/time`).

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| py-clob-client | 0.34.6 | Polymarket CLOB API client | Official Polymarket Python SDK; handles auth, order building, EIP-712 signing |
| eth-account | 0.13.7 | Wallet signing | Bundled as py-clob-client dependency; used by ClobClient.Signer internally |
| httpx | 0.28.1 | Async HTTP | HTTP/2 support, bundled with py-clob-client, also used directly for health checks |
| websockets | 16.0 | WebSocket client | Used for Polymarket WS stream (Phase 2); install now to confirm compatibility |
| python-dotenv | 1.2.2 | .env loading | Development only; secrets.env loaded via Docker env_file in production |
| loguru | 0.7.3 | Structured logging | Zero-config, JSON serialization, automatic rotation |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 | Test runner | All test files; Phase 1 uses it for connectivity and secret-validation tests |
| pytest-asyncio | 0.25+ | Async test support | Any test that awaits coroutines (WebSocket connectivity tests) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python:3.12-slim | python:3.13-slim | 3.13 is newer but py-clob-client not yet validated on it; 3.12-slim is LTS path |
| python:3.12-slim | python:3.12-alpine | Alpine has musl libc which breaks eth-account/cryptography wheels; do not use Alpine |
| eth-account (bundled) | ethers (0.1.1 PyPI) | `ethers` PyPI package is a thin stub (v0.1.1, minimal maintenance); py-clob-client already bundles eth-account — no separate install needed |

**Installation (in Dockerfile):**
```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

**requirements.txt:**
```
py-clob-client==0.34.6
httpx[http2]==0.28.1
websockets==16.0
loguru==0.7.3
python-dotenv==1.2.2
pytest==9.0.2
pytest-asyncio==0.25.0
```

**Note on eth-account:** Do NOT add `eth-account` to requirements.txt. It is installed automatically as a py-clob-client dependency (0.13.7). Adding it separately risks version conflicts.

**Version verification (confirmed 2026-03-27 via PyPI):**
- py-clob-client: 0.34.6 (latest)
- httpx: 0.28.1 (latest)
- websockets: 16.0 (latest)
- loguru: 0.7.3 (latest)
- python-dotenv: 1.2.2 (latest)
- pytest: 9.0.2 (latest)

---

## Architecture Patterns

### Recommended Project Structure

```
src/
├── bot/
│   ├── __init__.py
│   ├── config.py          # Secret validation + ClobClient factory
│   ├── client.py          # Authenticated ClobClient singleton
│   └── health.py          # API connectivity check (used by HEALTHCHECK)
├── scripts/
│   └── benchmark_latency.py   # Latency measurement script (phase 1 deliverable)
tests/
├── conftest.py            # Shared fixtures (ClobClient read-only instance)
├── test_config.py         # Secret validation unit tests
└── test_connectivity.py   # API connectivity smoke tests
docker-compose.yml
Dockerfile
requirements.txt
secrets.env.example        # Committed to git (placeholder values only)
.gitignore                 # Must include: secrets.env, .env
```

### Pattern 1: Fail-Fast Secret Validation

**What:** Validate all required environment variables at startup using `os.environ[key]` which raises `KeyError` immediately on missing values. Never use `os.getenv()` for required secrets.

**When to use:** Always — this satisfies D-06.

```python
# src/bot/config.py
# Source: standard Python os.environ pattern; satisfies D-06

import os
from dataclasses import dataclass

REQUIRED_SECRETS = [
    "POLY_API_KEY",
    "POLY_API_SECRET",
    "POLY_API_PASSPHRASE",
    "WALLET_PRIVATE_KEY",
    "POLYGON_RPC_HTTP",
    "POLYGON_RPC_WS",
]

@dataclass(frozen=True)
class BotConfig:
    poly_api_key: str
    poly_api_secret: str
    poly_api_passphrase: str
    wallet_private_key: str
    polygon_rpc_http: str
    polygon_rpc_ws: str
    telegram_bot_token: str | None = None
    discord_webhook_url: str | None = None

def load_config() -> BotConfig:
    """Load and validate all required secrets. Raises KeyError on any missing."""
    missing = [k for k in REQUIRED_SECRETS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {missing}")
    return BotConfig(
        poly_api_key=os.environ["POLY_API_KEY"],
        poly_api_secret=os.environ["POLY_API_SECRET"],
        poly_api_passphrase=os.environ["POLY_API_PASSPHRASE"],
        wallet_private_key=os.environ["WALLET_PRIVATE_KEY"],
        polygon_rpc_http=os.environ["POLYGON_RPC_HTTP"],
        polygon_rpc_ws=os.environ["POLYGON_RPC_WS"],
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL"),
    )
```

### Pattern 2: ClobClient Initialization (EOA Wallet, L2 Auth)

**What:** Initialize authenticated ClobClient with L2 access (full order placement).

**When to use:** The bot wallet is a directly-controlled EOA (hardware-generated or newly created), so `signature_type=0`. No funder address needed when the private key's address is the funded address.

```python
# src/bot/client.py
# Source: py-clob-client README + ClobClient source (github.com/Polymarket/py-clob-client)

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import POLYGON
from .config import BotConfig

CLOB_HOST = "https://clob.polymarket.com"

def build_client(config: BotConfig) -> ClobClient:
    """Build fully authenticated L2 ClobClient."""
    client = ClobClient(
        CLOB_HOST,
        key=config.wallet_private_key,
        chain_id=POLYGON,          # 137
        signature_type=0,           # EOA: directly-controlled private key
        # funder= not needed when signing key == funded address
    )
    creds = ApiCreds(
        api_key=config.poly_api_key,
        api_secret=config.poly_api_secret,
        api_passphrase=config.poly_api_passphrase,
    )
    client.set_api_creds(creds)
    return client
```

### Pattern 3: Docker Compose with env_file Secrets

**What:** Docker Compose loads secrets from a file that only exists on the VPS.

```yaml
# docker-compose.yml
# Source: Docker Compose reference (docs.docker.com/reference/compose-file/services/#env_file)

services:
  bot:
    build: .
    restart: unless-stopped
    env_file:
      - secrets.env          # Must exist on VPS; never committed to git
    volumes:
      - bot_data:/app/data   # Named volume for SQLite persistence

volumes:
  bot_data:
```

### Pattern 4: Dockerfile for Python Bot

**What:** Multi-stage build is unnecessary here (pure Python). Use python:3.12-slim with layer caching optimization.

```dockerfile
# Dockerfile
# Source: Docker best practices + Docker Hub library/python (updated 2026-03-20)

FROM python:3.12-slim

WORKDIR /app

# Dependencies first for layer cache efficiency
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY src/ ./src/

# Health check: verify CLOB API is reachable
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('https://clob.polymarket.com/time', timeout=8); r.raise_for_status()" \
    || exit 1

CMD ["python", "-m", "bot.main"]
```

**Why NOT Alpine:** Alpine uses musl libc. The cryptography package (dependency of eth-account, dependency of py-clob-client) requires glibc and will fail to install from wheels on Alpine, forcing a slow compile-from-source that may fail on missing headers. Always use `-slim` (Debian-based).

### Pattern 5: Latency Benchmark Script

**What:** Measure round-trip latency to Polymarket CLOB from the VPS to verify sub-100ms requirement.

```python
# scripts/benchmark_latency.py
# Source: httpx docs + standard timing pattern

import statistics
import time
import httpx

CLOB_HOST = "https://clob.polymarket.com"
SAMPLES = 20

def benchmark():
    latencies = []
    with httpx.Client(http2=True) as client:
        # Warm-up
        client.get(f"{CLOB_HOST}/time")
        # Measure
        for _ in range(SAMPLES):
            t0 = time.perf_counter()
            resp = client.get(f"{CLOB_HOST}/time")
            resp.raise_for_status()
            latencies.append((time.perf_counter() - t0) * 1000)  # ms

    print(f"Samples: {SAMPLES}")
    print(f"Mean:    {statistics.mean(latencies):.1f} ms")
    print(f"Median:  {statistics.median(latencies):.1f} ms")
    print(f"P95:     {sorted(latencies)[int(SAMPLES * 0.95)]:.1f} ms")
    print(f"Min:     {min(latencies):.1f} ms")
    print(f"Max:     {max(latencies):.1f} ms")

    threshold = 100
    passing = statistics.median(latencies) < threshold
    print(f"\nMedian < {threshold}ms: {'PASS' if passing else 'FAIL'}")
    return passing

if __name__ == "__main__":
    benchmark()
```

### Anti-Patterns to Avoid

- **Using python:alpine:** musl libc breaks cryptography/eth-account wheel installation. Always use `-slim`.
- **Using `os.getenv()` for required secrets:** Returns None silently. Use `os.environ[key]` or explicit missing check.
- **Committing secrets.env:** The file containing real secrets must be in `.gitignore`. Only `secrets.env.example` (with placeholder values) is committed.
- **Using `signature_type=1` for EOA wallets:** Type 1 is for email/Magic wallets only. EOA = type 0.
- **Adding funder= param unnecessarily:** Only needed when the signing key is different from the funded address (proxy wallet pattern). Not needed for this bot.
- **Storing API credentials in the Python env before deriving them:** Use `create_or_derive_api_creds()` once at startup and cache the result; calling it repeatedly creates new keys.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| EIP-712 order signing | Custom signing logic | py-clob-client (includes eth-account) | Polymarket-specific signature format, nonce management, chain ID encoding are complex to get right |
| Polygon RPC calls for wallet state | Custom web3 integration | Alchemy endpoint via POLYGON_RPC_HTTP env var | py-clob-client abstracts chain interaction; direct RPC only needed for allowance setup (Phase 3+) |
| API key derivation from wallet | Custom ECDSA auth | `client.create_or_derive_api_creds()` | Polymarket's key derivation is deterministic from wallet; re-deriving is safer than storing |
| Docker secrets management | HashiCorp Vault, AWS Secrets Manager | Docker env_file | Overkill for single-server single-bot; env_file on VPS with 600 permissions is sufficient |
| Latency monitoring | Custom ping loop | httpx timing in benchmark script | Simple script run once to verify, not a continuous monitor (Phase 4 handles monitoring) |

**Key insight:** py-clob-client is a comprehensive abstraction layer. Do not reach past it to call the CLOB REST API directly in Phase 1 — it handles auth headers, request signing, and error normalization.

---

## Common Pitfalls

### Pitfall 1: Three-Part API Credentials (Not Two)

**What goes wrong:** Developer creates only `POLY_API_KEY` and `POLY_API_SECRET` env vars, missing `POLY_API_PASSPHRASE`. The `ApiCreds` dataclass requires all three; `set_api_creds()` will succeed but order placement fails with auth errors.

**Why it happens:** Many APIs use key + secret. Polymarket CLOB uses key + secret + passphrase (Coinbase-style).

**How to avoid:** The `secrets.env.example` must contain all three slots: `POLY_API_KEY`, `POLY_API_SECRET`, `POLY_API_PASSPHRASE`.

**Warning signs:** 401 errors when posting orders but 200 when fetching market data.

---

### Pitfall 2: Wrong Signature Type

**What goes wrong:** Using `signature_type=1` (email/Magic wallet) for a freshly-generated EOA key. Results in signature verification failures at the CLOB.

**Why it happens:** README examples show `signature_type=1` prominently because Magic wallet is the most common user path. For a bot with a directly-generated private key, type 0 is correct.

**How to avoid:** Use `signature_type=0` when the private key was generated locally (e.g., with eth-account or any standard key generator).

**Warning signs:** Orders rejected with signature errors despite correct key/secret/passphrase.

---

### Pitfall 3: Alpine Docker Image Breaking eth-account

**What goes wrong:** `pip install py-clob-client` inside an Alpine container fails with "No matching distribution found" or attempts to compile cryptography from source and errors on missing build tools.

**Why it happens:** Alpine uses musl libc; the cryptography package ships only manylinux/glibc wheels. Alpine install requires `musl-dev`, `gcc`, `libffi-dev` build dependencies and still may fail.

**How to avoid:** Always use `python:3.12-slim` (Debian-based). Never use Alpine for Python containers that depend on cryptographic libraries.

**Warning signs:** `pip install` hanging for minutes during Docker build, or error mentioning "no matching distribution" for `cryptography`.

---

### Pitfall 4: secrets.env File Not Found at Container Start

**What goes wrong:** Docker Compose starts the container but `secrets.env` doesn't exist on the VPS yet, causing `env_file` to fail and the container to not start.

**Why it happens:** Developer deploys code but forgets to create `secrets.env` on the VPS before running `docker compose up`.

**How to avoid:** VPS provisioning runbook must include: (1) copy `secrets.env.example` to `secrets.env`, (2) fill in all values, (3) `chmod 600 secrets.env`, then (4) `docker compose up -d`.

**Warning signs:** `docker compose up` fails immediately with "env_file secrets.env not found".

---

### Pitfall 5: Alchemy API Key in Endpoint URL

**What goes wrong:** Developer logs the `POLYGON_RPC_HTTP` or `POLYGON_RPC_WS` URL (which contains the Alchemy API key embedded in the path) to application logs. Key is exposed.

**Why it happens:** Alchemy's endpoint format is `https://polygon-mainnet.g.alchemy.com/v2/{API_KEY}` — the API key is part of the URL, not a header.

**How to avoid:** Loguru logger must never log the raw RPC URL. Log only "Polygon RPC HTTP: configured" (boolean presence check). Also: `secrets.env` permissions `chmod 600` on VPS.

**Warning signs:** Full Alchemy URL appearing in `docker compose logs`.

---

### Pitfall 6: Hetzner Location Name

**What goes wrong:** Specifying `location=eu-west-2` in Hetzner API calls (this is the AWS region name, not a Hetzner identifier).

**Why it happens:** The ROADMAP referenced `eu-west-2` which is the AWS designation for London. Hetzner uses `uk-lon1` for their London datacenter.

**How to avoid:** When provisioning via Hetzner API or CLI, use location name `uk-lon1`.

**Warning signs:** Hetzner API returning "location not found" errors.

---

## Code Examples

Verified patterns from official sources:

### Polymarket CLOB HTTP Endpoints (confirmed from py-clob-client source)

```python
# Source: github.com/Polymarket/py-clob-client/blob/main/py_clob_client/client.py
# Source: github.com/Polymarket/py-clob-client/blob/main/py_clob_client/constants.py

CLOB_HOST = "https://clob.polymarket.com"  # HTTP REST API
POLYGON_CHAIN_ID = 137                      # Polygon mainnet (POLYGON constant)

# Read-only health check (no auth)
client = ClobClient(CLOB_HOST)
ok = client.get_ok()    # returns "OK" if server is up
time = client.get_server_time()
```

### Polymarket CLOB WebSocket Endpoint (confirmed from official example)

```python
# Source: github.com/J-Verwey/pm_access_example - cell 20 (Polymarket-linked example)
# Confirmed WS endpoint format

WSS_MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
WSS_USER_URL   = "wss://ws-subscriptions-clob.polymarket.com/ws/user"

# Subscription message format (market channel):
subscription = {
    "type": "market",
    "assets_ids": [token_id],
    "custom_feature_enabled": True
}
# Must send "PING" every ~50s to keep connection alive; server responds with "PONG"
```

### Alchemy Polygon RPC Endpoint Format

```python
# Source: Alchemy documentation (standard endpoint format)
# API key is embedded in the URL path (not a header)

# HTTP (for synchronous RPC calls, order verification)
POLYGON_RPC_HTTP = "https://polygon-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"

# WebSocket (for event subscriptions in Phase 2)
POLYGON_RPC_WS = "wss://polygon-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
```

### API Credential Creation (one-time setup)

```python
# Source: github.com/Polymarket/py-clob-client/blob/main/examples/create_api_key.py
# Run this ONCE to generate creds, then store in secrets.env

from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

client = ClobClient(
    "https://clob.polymarket.com",
    key=WALLET_PRIVATE_KEY,
    chain_id=POLYGON,
    signature_type=0,   # EOA
)
# create_or_derive_api_creds tries create first, falls back to derive
creds = client.create_or_derive_api_creds()
print(f"POLY_API_KEY={creds.api_key}")
print(f"POLY_API_SECRET={creds.api_secret}")
print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")
```

### secrets.env.example Template

```bash
# secrets.env.example — COMMIT THIS FILE (placeholder values only)
# Copy to secrets.env on VPS and fill in real values

# Polymarket CLOB API credentials
POLY_API_KEY=your_poly_api_key_here
POLY_API_SECRET=your_poly_api_secret_here
POLY_API_PASSPHRASE=your_poly_api_passphrase_here

# Non-custodial EOA wallet private key (for CLOB message signing)
WALLET_PRIVATE_KEY=0x_your_private_key_here

# Alchemy Polygon RPC endpoints
POLYGON_RPC_HTTP=https://polygon-mainnet.g.alchemy.com/v2/your_alchemy_api_key
POLYGON_RPC_WS=wss://polygon-mainnet.g.alchemy.com/v2/your_alchemy_api_key

# Phase 4 notification slots (reserved now, unused until Phase 4)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_here
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| web3.py for Polygon signing | eth-account (via py-clob-client) | 2023+ | py-clob-client bundles eth-account; no separate web3.py needed |
| Docker secrets via CLI flags | Docker Compose env_file | 2020+ | env_file is the standard Compose pattern for per-environment secrets |
| Python 3.9 minimum (py-clob-client docs) | Python 3.9+ supported; 3.12 recommended | 2024 | 3.12-slim is current LTS; 3.13 available but not yet validated with py-clob-client |
| websockets 12.0 (py-clob-client requirements.txt) | websockets 16.0 (2026) | Jan 2026 | 16.0 has breaking API changes from 12.0 — install 16.0 since we use it directly, not through py-clob-client |

**Deprecated/outdated:**
- `ethers.py` (PyPI name `ethers`, version 0.1.1): Minimal stub library, not maintained. CLAUDE.md mentions "ethers.py" but py-clob-client uses `eth-account`. Do not install `ethers`.
- `web3.py` for signing: Not needed; eth-account handles all signing via py-clob-client.

---

## Open Questions

1. **Alchemy tier cost validation**
   - What we know: Pay-as-you-go is $0.40/1M CUs; Free tier gives 30M CUs/month
   - What's unclear: CU cost per Polygon `eth_call` / `eth_getLogs` not benchmarked against expected Phase 2 scan volume
   - Recommendation: Start on Free tier; upgrade to Growth after Phase 2 data scanning is live and CU consumption is measured (D-13 confirms this approach)

2. **EOA wallet permissions — trade-only vs withdrawal**
   - What we know: Polymarket does not have native "trade-only" API key scoping at the CLOB level; the private key controls all wallet actions
   - What's unclear: Whether Polymarket's API key (POLY_API_KEY) has a separate permission scope (trade-only) vs the wallet private key
   - Recommendation: INFRA-04 requires "trade-only permissions verified". Research for Phase 1: use a fresh wallet with minimal USDC balance and no withdrawal history; document that the API key is the authentication layer and the private key scope is limited by wallet balance, not by API permission flags. Verify via `client.get_api_keys()` to inspect key metadata.

3. **Hetzner CX32 exact spec confirmation**
   - What we know: CX32 is documented as 4 vCPU / 8GB RAM / ~8 EUR/mo (from CONTEXT.md)
   - What's unclear: Hetzner API returns 401 without auth token; cannot confirm spec from public API without account
   - Recommendation: Accept CONTEXT.md decision as authoritative. CX32 spec is widely documented.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | Bot runtime (local dev) | Yes | 3.10.10 | — |
| pip | Package install (local dev) | Yes | 22.3.1 | — |
| Docker | Container build + run | No | — | Install via `curl -fsSL https://get.docker.com \| sh` on VPS |
| Docker Compose | Multi-service orchestration | No | — | Bundled with Docker Engine 24+ (plugin) |
| SSH | VPS access | Yes | OpenSSH 10.2p1 | — |
| curl | API testing, Docker install | Yes | 8.18.0 | — |

**Missing dependencies with no fallback:**
- Docker + Docker Compose must be installed on the Hetzner VPS. Not on local dev machine — VPS is the target environment. Plan must include a VPS provisioning wave with Docker install.

**Missing dependencies with fallback:**
- Docker is absent locally but local development does not require it — the bot runs on VPS. Local dev can run `python src/bot/main.py` directly for testing connectivity scripts.

**External account prerequisites (not installable — must exist before Phase 1 begins):**
- Hetzner account with billing configured
- Alchemy account with Polygon app created (to obtain RPC URL)
- Polymarket account with USDC deposited (to generate API credentials)
- Telegram Bot or Discord webhook (Phase 4 slots — not needed for Phase 1 validation)

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pytest.ini` — Wave 0 creates this |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | Polymarket CLOB HTTP returns 200 from VPS | smoke | `pytest tests/test_connectivity.py::test_clob_http_reachable -x` | Wave 0 |
| INFRA-01 | Median HTTP latency to CLOB < 100ms | smoke | `pytest tests/test_connectivity.py::test_latency_under_100ms -x` | Wave 0 |
| INFRA-02 | Alchemy Polygon RPC HTTP responds | smoke | `pytest tests/test_connectivity.py::test_alchemy_http_rpc -x` | Wave 0 |
| INFRA-02 | Alchemy Polygon RPC WS connects | smoke | `pytest tests/test_connectivity.py::test_alchemy_ws_rpc -x` | Wave 0 |
| INFRA-03 | Docker image builds without error | manual | `docker build -t arbbot .` | — |
| INFRA-03 | Container starts and healthcheck passes | manual | `docker compose up --wait` | — |
| INFRA-04 | Config fails fast when secret is missing | unit | `pytest tests/test_config.py::test_missing_secret_raises -x` | Wave 0 |
| INFRA-04 | Config loads all secrets successfully | unit | `pytest tests/test_config.py::test_config_loads -x` | Wave 0 |
| INFRA-05 | Wallet can be derived from private key | unit | `pytest tests/test_config.py::test_wallet_address_derivation -x` | Wave 0 |
| INFRA-05 | ClobClient returns correct wallet address | smoke | `pytest tests/test_connectivity.py::test_clob_client_wallet_address -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_config.py -x -q` (unit tests only, no network)
- **Per wave merge:** `pytest tests/ -x -q` (full suite including connectivity)
- **Phase gate:** Full suite green + latency benchmark PASS before `/gsd:verify-work`

### Wave 0 Gaps

- `tests/conftest.py` — shared fixtures (read-only ClobClient, config with test env vars)
- `tests/test_config.py` — REQ INFRA-04, INFRA-05 (secret validation unit tests)
- `tests/test_connectivity.py` — REQ INFRA-01, INFRA-02 (network smoke tests; skip if no VPS env)
- `pytest.ini` — marks definition (`smoke`, `unit`)
- Framework install: `pip install pytest pytest-asyncio` — if not in virtual env

---

## Project Constraints (from CLAUDE.md)

| Directive | Constraint |
|-----------|-----------|
| Tech stack | Python + py-clob-client. No alternative language or unofficial SDK. |
| Latency | Sub-100ms to Polymarket APIs. Must be verified with benchmark script. |
| Capital | Under $1k total. No position sizing that risks full capital. |
| Deployment | Cloud VPS, continuous operation. Docker containerization required. |
| Library: HTTP | Use httpx (not requests, not aiohttp) |
| Library: WebSocket | Use websockets 16.0+ (not websocket-client) |
| Library: Logging | Use loguru (not stdlib logging, not structlog) |
| Library: Blockchain | eth-account via py-clob-client (not web3.py, not the ethers PyPI stub) |
| Library: Database | SQLite for Phase 1-3, TimescaleDB optional for Phase 4+ |
| GSD Workflow | All code changes go through GSD commands; no direct repo edits outside workflow |

---

## Sources

### Primary (HIGH confidence)

- `github.com/Polymarket/py-clob-client` — ClobClient source, constants, auth levels, ApiCreds dataclass, signer (eth-account), endpoints, README examples
- `github.com/Polymarket/py-clob-client` `.env.example` — Confirmed env var names: PK, CLOB_API_KEY, CLOB_SECRET, CLOB_PASS_PHRASE, CLOB_API_URL
- `github.com/Polymarket/clob-client` `examples/socketConnection.ts` — WS_URL format confirmed: `{host}/ws/{type}` (market or user channel)
- `github.com/J-Verwey/pm_access_example` notebook cell 20 — Confirmed WebSocket URL: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- PyPI `pip index versions` — All package versions verified 2026-03-27
- Docker Hub `library/python` tags API — `python:3.12-slim` confirmed current (updated 2026-03-20)

### Secondary (MEDIUM confidence)

- `alchemy.com/pricing` — Pay-as-you-go pricing ($0.40/1M CUs), Growth tier confirmed; exact CU cost per Polygon call not verified
- `docs.docker.com/reference/compose-file/services/` — env_file attribute confirmed in Compose spec
- `docs.docker.com/reference/dockerfile/#healthcheck` — HEALTHCHECK instruction syntax confirmed

### Tertiary (LOW confidence)

- Hetzner CX32 spec (4 vCPU / 8GB / ~8 EUR): Sourced from CONTEXT.md decision; Hetzner API requires auth token to confirm. Accepted as authoritative from prior discussion.
- Hetzner London datacenter name (`uk-lon1`): Inferred from standard Hetzner naming conventions; could not confirm via public API without account token. Recommend verifying in Hetzner console.

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all versions verified against PyPI registry 2026-03-27
- Architecture patterns: HIGH — sourced from py-clob-client official source and examples
- Polymarket endpoints: HIGH — confirmed from official Polymarket Python and TypeScript clients
- Pitfalls: HIGH — derived from py-clob-client source code + known Docker/Python packaging issues
- Hetzner specs: MEDIUM — decision from CONTEXT.md; Hetzner API not publicly accessible without auth token

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable ecosystem — py-clob-client versions move slowly)
