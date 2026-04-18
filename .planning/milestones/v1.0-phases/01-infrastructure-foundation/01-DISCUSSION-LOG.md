# Phase 1: Infrastructure Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 01-infrastructure-foundation
**Areas discussed:** VPS Provider, Secrets / Key Injection, Docker Architecture, RPC Provider

---

## VPS Provider

| Option | Description | Selected |
|--------|-------------|----------|
| Hetzner | Best price/performance for trading bots. CX/AX series in London. ~€30-60/mo. Popular in quant community. | ✓ |
| AWS EC2 (eu-west-2) | Managed, reliable, familiar. t3.small–c5.large range. $40-120/mo. | |
| DigitalOcean / Vultr London | Simple setup, good UX, $20-60/mo. Least latency-tunable. | |
| I already have a VPS | Existing server — just deploy to it. | |

**User's choice:** Hetzner

---

## Hetzner Server Size

| Option | Description | Selected |
|--------|-------------|----------|
| CX22 (€4/mo, 2 vCPU, 4GB RAM) | Minimal. Fine for Phase 1 testing. | |
| CX32 (€8/mo, 4 vCPU, 8GB RAM) | Comfortable headroom for bot + SQLite + future dashboard. | ✓ |
| CX42 (€16/mo, 8 vCPU, 16GB RAM) | Overkill for <$1k capital bot. | |

**User's choice:** CX32 (€8/mo, 4 vCPU, 8GB RAM)

---

## Secrets / Key Injection

| Option | Description | Selected |
|--------|-------------|----------|
| Docker Compose env_file on VPS only | secrets.env on VPS, never committed to git. docker-compose.yml references it via env_file. | ✓ |
| Docker secrets + Swarm mode | Native Docker secrets, more secure, requires Swarm. More ops overhead. | |
| Export vars in deploy script | Shell script exports keys into environment. Fragile across reboots. | |
| Encrypted secrets with sops + age | Secrets encrypted in git. More tooling to set up. | |

**User's choice:** Docker Compose env_file on VPS only

---

## Secrets to Include

| Secret | Selected |
|--------|----------|
| Polymarket API key + secret | ✓ |
| Wallet private key | ✓ |
| Polygon RPC URL | ✓ |
| Telegram / Discord bot token | ✓ |

**User's choice:** All four categories (all slots to be reserved in secrets.env.example)

---

## Docker Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Single container + docker-compose.yml | One container, SQLite volume, Phase 4 dashboard added later. | ✓ |
| Multi-container from the start | Pre-define all services in docker-compose.yml now. | |

**User's choice:** Single container + docker-compose.yml

---

## Restart Policy

| Option | Description | Selected |
|--------|-------------|----------|
| restart: unless-stopped | Restarts on crash/reboot, respects manual stop. Best for trading bots. | ✓ |
| restart: always | Restarts even after manual stop. | |
| No restart policy | Manual management only. | |

**User's choice:** unless-stopped

---

## RPC Provider

| Option | Description | Selected |
|--------|-------------|----------|
| Alchemy | Best Polygon WS support, sub-100ms from London, Growth tier ~$50-200/mo. | ✓ |
| QuickNode | Solid alternative, flat pricing, good WS support. $50-300/mo. | |
| Infura | Reliable but historically worse Polygon WS latency. | |
| Self-hosted Erigon node | Zero per-request cost but $200-400/mo VPS + 2TB+ storage + sync time. | |

**User's choice:** Alchemy

---

## RPC Connection Type

| Option | Description | Selected |
|--------|-------------|----------|
| HTTP + WebSocket both | HTTP for sync calls, WS for event subscriptions. | ✓ |
| WebSocket only | Lower overhead per connection but HTTP still useful. | |
| HTTP only | Simpler, but Data phase needs WS anyway. | |

**User's choice:** HTTP + WebSocket both

---

## Claude's Discretion

- Python base image selection
- Dockerfile layer ordering and build cache optimization
- Health check implementation
- Project folder structure
- Latency benchmark script implementation details
- Trade-only API key permission verification approach

## Deferred Ideas

None — discussion stayed within phase scope.
