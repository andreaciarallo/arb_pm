---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 03-03-PLAN.md (execution engine with VWAP gate and retry-then-hedge)
last_updated: "2026-03-29T17:01:10.361Z"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 15
  completed_plans: 13
  percent: 87
---

# Project State

**Project:** Polymarket Arbitrage Bot
**Last Updated:** 2026-03-28

---

## Project Reference

| Field | Value |
|-------|-------|
| **Core Value** | Ultra-low latency detection and execution of cross-market arbitrage opportunities on Polymarket before they disappear |
| **Current Focus** | Phase 1: Infrastructure Foundation |
| **Current Phase** | 1/4 |
| **Current Plan** | Not started |

---

## Current Position

Phase: 03 (execution-risk-controls) — EXECUTING
Plan: 1 of 5
**Phase:** 2
**Plan:** 06 (COMPLETE)
**Status:** Executing Phase 03

**Progress:**

[█████████░] 87%

**Active Branch:** None

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases Complete | 0/4 |
| Plans Complete | 0/23 |
| Requirements Validated | 0/23 |
| Technical Debt Items | 0 |

---
| Phase 01-infrastructure-foundation P01 | 3 | 2 tasks | 10 files |
| Phase 01-infrastructure-foundation P03 | 5 | 2 tasks | 4 files |
| Phase 01 P02 | 2 | 2 tasks | 3 files |
| Phase 02 P02 | 15 | 2 tasks | 4 files |
| Phase 02 P03 | 8 | 2 tasks | 4 files |
| Phase 02 P05 | 2 | 1 task | 2 files |
| Phase 02 P06 | 15 | 2 tasks | 7 files |
| Phase 03 P01 | 7 | 2 tasks | 4 files |
| Phase 03 P02 | 169 | 2 tasks | 2 files |
| Phase 03 P03 | 4 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Official Polymarket API over on-chain | Simpler integration, documented interface | Pending |
| Efficient scanning over brute-force | Full market scan may be inefficient; need state-of-the-art approach | Pending |
| Aggressive sizing | User preference for maximizing capture | Pending |
| VPS deployment | Continuous operation required for 24/7 markets | Pending |

- [Phase 01-infrastructure-foundation]: Use signature_type=0 (EOA) for ClobClient — not type 1 (Magic/email wallet only)
- [Phase 01-infrastructure-foundation]: Three-part CLOB API auth: POLY_API_KEY + POLY_API_SECRET + POLY_API_PASSPHRASE enforced via REQUIRED_SECRETS
- [Phase 01-infrastructure-foundation]: eth-account excluded from requirements.txt — transitive dep of py-clob-client
- [Phase 01-infrastructure-foundation]: python:3.12-slim used for Docker base image — Alpine musl libc breaks eth-account/cryptography manylinux wheels
- [Phase 01-infrastructure-foundation]: restart: unless-stopped (not always) — allows docker compose stop on VPS for maintenance without restart loop
- [Phase 01-infrastructure-foundation]: Named volume bot_data at /app/data — SQLite persists across container rebuilds, never log raw RPC URLs (Alchemy key in path)
- [Phase 01-infrastructure-foundation]: health.py pre-committed in Plan 03 parallel execution — verified correct, not recreated in Plan 02
- [Phase 01-infrastructure-foundation]: Smoke tests use real_config fixture from Plan 01 conftest.py — auto-skip when POLY_API_KEY not set
- [Phase 01-infrastructure-foundation]: test_alchemy_ws_rpc is async def — asyncio_mode=auto from pytest.ini handles it automatically
- [Phase 01-infrastructure-foundation]: VPS location Ashburn VA (us-east) instead of London (uk-lon1) — London unavailable in Hetzner account; Ashburn median 92.4ms meets sub-100ms gate
- [Phase 01-infrastructure-foundation]: CPX31 used instead of CX32 — equivalent spec (4 vCPU, 8GB RAM), US region naming convention in Hetzner
- [Phase 01-infrastructure-foundation]: pytest downgraded 9.0.2→8.3.4 to resolve version conflict in VPS Docker build
- [Phase 02]: Phase 2 BotConfig fields use dataclass defaults only — no new env vars, REQUIRED_SECRETS stays at 6 items
- [Phase 02]: Prices parsed from sells array (ask side) only — never buys (D-05)
- [Phase 02]: is_stale() returns True for unknown tokens — treat missing as stale (D-09)
- [Phase 02]: Each token stored independently in cache; detection engine pairs YES+NO by condition_id
- [Phase 02-03]: normalize_order_book() returns valid MarketPrice for resolved markets (ask=1.0) — detection engine skips them separately, not the normalizer
- [Phase 02-03]: yes_bid defaults to 0.0 on empty bids list — bid not critical for arb detection per D-05
- [Phase 02-03]: poll_stale_markets() uses per-token exception isolation — one HTTP failure does not stop other polls
- [Phase 02-04]: NO token ask price read from no_price.yes_ask — MarketPrice stores each token's ask in yes_ask regardless of token type
- [Phase 02-04]: estimated_fees = (yes_ask + no_ask) * taker_fee — fees on notional, not unit position
- [Phase 02-04]: Sports and politics use base min_net_profit_pct (1.5%) — no tier override needed
- [Phase 02-04]: confidence_score = net_spread / (net_spread + 0.01) — simple Phase 2 proxy, refined in Phase 3
- [Phase 02-05]: Keyword extraction uses len>=4, alpha-only, strip punctuation — eliminates stopwords without a stopword list
- [Phase 02-05]: BFS connected-components grouping allows transitive chains (A~B~C all in one group even if A,C don't share words)
- [Phase 02-05]: fees = total_yes_asks * taker_fee (single-sided — buying YES only, not YES+NO pairs)
- [Phase 02-05]: LLM-based dependency detection deferred to Phase 3 per D-03; keyword heuristic used in Phase 2
- [Phase 02-06]: AsyncWriter uses asyncio.Queue(maxsize=1000) — full queue logs warning and drops; never blocks scan loop
- [Phase 02-06]: dry_run.run() accepts db_path parameter for testability (defaults to /data/bot.db from DATA_DIR env)
- [Phase 02-06]: check_health() called with NO args — plan had bug showing check_health(client); corrected from health.py signature
- [Phase 02-06]: Idle while-loop replaced with asyncio.run(dry_run.run(config, client)) in main.py
- [Phase 03]: kelly_size() returns 0.0 (not min floor) when Kelly formula yields below-minimum — caller decides to skip, never auto-promote (D-01)
- [Phase 03]: Modified Kelly uses sqrt(p) in denominator (arxiv 2508.03474): f = (b*p - q) / (b*sqrt(p)) — execution probability p = min(1.0, depth/target_size)
- [Phase 03]: PolyApiException(error_msg=...) — status_code kwarg not in SDK 0.34.6; plan documented wrong constructor
- [Phase 03]: FAK order client: create_order+post_order(FAK) two-step pattern; all REST calls in run_in_executor
- [Phase 03-03]: simulate_vwap returns 1.0 on empty book (worst case) — will fail VWAP gate and prevent order
- [Phase 03-03]: execute_opportunity accepts yes_token_id/no_token_id as optional params — defaults to empty string → skip (deferred to plan 05 caller)
- [Phase 03-03]: YES verification is REST-only via verify_fill_rest() — WebSocket user channel deferred to Phase 4 (undocumented message format)

### Open Questions

| Question | Context | Resolution |
|----------|---------|------------|
| Exact VPS provider | London eu-west-2 specified, but provider (AWS vs DigitalOcean vs Linode) needs selection | Pending |
| Dedicated RPC cost validation | $200-400/month estimate needs validation against Alchemy/QuickNode pricing | Pending |
| Minimum capital threshold | Need to specify minimum viable capital after fees/gas for <$1k constraint | Pending |

### Blockers

| Blocker | Impact | Resolution |
|---------|--------|------------|
| None | - | - |

### Notes

- Infrastructure is the differentiator — latency and connectivity matter more than strategy sophistication
- Fee awareness is non-negotiable — must be core to detection logic
- Risk management before execution — never enable live trading without circuit breakers
- Strategy obsolescence is inevitable — trade logging enables detection when strategy stops working

---

## Session Continuity

**Last Session:** 2026-03-29T17:01:10.358Z
**Stopped At:** Completed 03-03-PLAN.md (execution engine with VWAP gate and retry-then-hedge)
**Next Session:** Phase 2 complete — proceed to Phase 3 (live execution)

---

## Changelog

| Date | Event | Details |
|------|-------|---------|
| 2026-03-27 | Project Initialized | GSD workflow initialized with PROJECT.md |
| 2026-03-27 | Requirements Created | 23 v1 requirements across 4 categories |
| 2026-03-27 | Roadmap Created | 4 phases derived from requirements |
