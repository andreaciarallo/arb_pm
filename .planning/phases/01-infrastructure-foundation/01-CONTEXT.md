# Phase 1: Infrastructure Foundation - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Set up the foundational stack so the bot can connect to Polymarket APIs securely from a low-latency London environment. This phase delivers: a Hetzner VPS running a Dockerized Python bot process with a dedicated Alchemy Polygon RPC endpoint, runtime-injected secrets, and a non-custodial wallet capable of signing CLOB messages. Phase ends when sub-100ms latency to Polymarket APIs is verified.

No market scanning, no execution, no dashboard. Infrastructure only.

</domain>

<decisions>
## Implementation Decisions

### VPS Provider
- **D-01:** Use **Hetzner London datacenter**, CX32 tier (4 vCPU, 8GB RAM, ~€8/mo)
- **D-02:** CX32 gives comfortable headroom for bot process + SQLite + future Phase 4 dashboard without over-provisioning

### Secrets / Key Injection
- **D-03:** Use **Docker Compose `env_file` pointing to a `secrets.env` file on the VPS only** — file is never committed to git, only lives on the server
- **D-04:** `secrets.env` must contain these slots (all required before bot starts):
  - `POLY_API_KEY` — Polymarket CLOB API key
  - `POLY_API_SECRET` — Polymarket CLOB API secret
  - `WALLET_PRIVATE_KEY` — Non-custodial wallet private key for CLOB message signing
  - `POLYGON_RPC_HTTP` — Alchemy Polygon HTTP endpoint URL (contains API key)
  - `POLYGON_RPC_WS` — Alchemy Polygon WebSocket endpoint URL (contains API key)
  - `TELEGRAM_BOT_TOKEN` — Telegram bot token (Phase 4, slot reserved now)
  - `DISCORD_WEBHOOK_URL` — Discord webhook URL (Phase 4, slot reserved now)
- **D-05:** `secrets.env.example` template (with placeholder values) IS committed to git so developers know what to create
- **D-06:** Bot fails fast at startup if any required secret is missing — no silent fallbacks

### Docker Architecture
- **D-07:** **Single container** for the bot process, orchestrated via `docker-compose.yml`
- **D-08:** SQLite data stored on a **named Docker volume** (not bind mount) for persistence across container rebuilds
- **D-09:** Container restart policy: `restart: unless-stopped` — auto-recovers from crashes and VPS reboots, respects manual `docker compose stop`
- **D-10:** Phase 4 dashboard will be added as a second service in docker-compose.yml at that time — no multi-container pre-setup needed now

### RPC Provider
- **D-11:** Use **Alchemy** as the dedicated Polygon PoS RPC provider
- **D-12:** Configure **both HTTP and WebSocket endpoints** — HTTP for synchronous calls (wallet signing, order placement verification), WebSocket for event subscriptions in Phase 2
- **D-13:** Alchemy Growth tier expected to cover usage; validate CU consumption after Phase 2 data scanning is live

### Claude's Discretion
- Python base image selection (3.12-slim recommended for size vs compatibility)
- Dockerfile layer ordering and build cache optimization
- Health check implementation (`HEALTHCHECK` in Dockerfile — verify API connectivity)
- Project folder structure (`src/` layout vs flat)
- Latency benchmark script implementation details
- How to verify trade-only API key permissions programmatically

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Polymarket Integration
- `CLAUDE.md` — Tech stack decisions (Python, py-clob-client, ethers.py, httpx, websockets, Docker) with rationale; planner must not deviate from specified libraries
- `.planning/REQUIREMENTS.md` §INFRA — Full requirement set with IDs INFRA-01 through INFRA-05; every requirement must map to a plan task

### Project Constraints
- `.planning/PROJECT.md` — Capital constraints (<$1k), latency requirement (ultra-low), deployment target (cloud VPS), and key architectural decisions

No external specs beyond project docs — infrastructure decisions are fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project. No existing code to reuse or replicate.

### Established Patterns
- None yet. Phase 1 sets the patterns that all subsequent phases follow.

### Integration Points
- Phase 1 outputs are consumed by Phase 2: the Alchemy WS endpoint URL, py-clob-client auth config, and Docker setup will be the foundation for data streaming.

</code_context>

<specifics>
## Specific Ideas

- Hetzner CX32 specifically chosen for cost-efficiency (not AWS despite eu-west-2 being specified in ROADMAP — Hetzner London achieves equivalent latency at ~10x lower cost)
- `secrets.env.example` pattern ensures onboarding clarity without exposing real credentials
- The wallet in Phase 1 is purely for CLOB message signing — no on-chain transaction sending needed until execution is live in Phase 3

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-infrastructure-foundation*
*Context gathered: 2026-03-27*
