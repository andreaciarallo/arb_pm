# Polymarket Arbitrage Bot

## What This Is

A fully automated arbitrage trading bot live on Polymarket prediction markets. The bot runs continuously on a Hetzner VPS (Helsinki, FI), scans 44k+ markets in real time via WebSocket + HTTP polling fallback, detects YES/NO and cross-market mispricing, and executes FAK orders automatically with Modified Kelly position sizing, circuit breakers, and Telegram alerting.

## Core Value

Ultra-low latency detection and execution of cross-market arbitrage opportunities on Polymarket before they disappear.

## Requirements

### Validated

- ✓ Deploy bot to low-latency VPS for continuous Polymarket access — v1.0 (Hetzner HEL1, <35ms median CLOB latency)
- ✓ Configure Docker containerization for reproducible deployment — v1.0
- ✓ Implement secure API key management (runtime injection, no withdrawal permissions) — v1.0
- ✓ Integrate non-custodial EOA wallet for Polymarket CLOB signing — v1.0 (USDC.e, MAX_UINT256 allowances)
- ✓ Implement WebSocket subscription for real-time market data (primary) — v1.0
- ✓ Implement HTTP polling fallback when WebSocket data is stale — v1.0
- ✓ Normalize market data to unified price format with timestamp alignment — v1.0
- ✓ Detect YES+NO cross-market mispricing opportunities — v1.0
- ✓ Calculate fee-adjusted profitability before scoring opportunities — v1.0
- ✓ Implement dry-run/simulation mode — v1.0
- ✓ Execute arbitrage trades automatically via CLOB API — v1.0 (FAK orders, token ID wiring complete)
- ✓ Use FAK orders via create_order() + post_order(OrderType.FAK) — v1.0
- ✓ Handle partial fills and one-leg execution risk (retry-then-hedge) — v1.0
- ✓ Verify every order via REST API after fill — v1.0
- ✓ Enforce maximum capital limit per trade (Modified Kelly, 5% ceiling) — v1.0
- ✓ Implement daily stop-loss (5% daily loss limit) — v1.0
- ✓ Implement circuit breaker on high error rates (CB trips + notifies CB) — v1.0 (NO-leg wiring fixed in Phase 8)
- ✓ Implement emergency kill switch for immediate position closure — v1.0
- ✓ Log all trades to SQLite database (PnL, execution costs, capital efficiency) — v1.0
- ✓ Send instant alerts via Telegram for trade executions, kill switch, and CB trips — v1.0 (live count accuracy fixed in Phase 8)
- ✓ Provide local FastAPI dashboard with live metrics (port 8080) — v1.0
- ✓ Track per-arb analytics: entry/exit prices, hold time, net profit after fees — v1.0

### Active

_(None — v1.0 shipped all requirements. Next milestone to be defined.)_

### Out of Scope

- Multi-exchange arbitrage — Polymarket-only focus for v1
- AI/ML opportunity filtering — adds complexity; basic detection works first
- Multi-wallet support — not needed for <$1k capital
- Market making mode — requires $3k+ capital
- REST API for external access — nice-to-have, not core
- Serverless deployment — VPS deployment only

## Context

**Status:** v1.0 shipped 2026-04-18. Bot is live in `--live` mode on HEL1.

**VPS:** Hetzner CPX31, Helsinki FI (204.168.164.145). Previously Ashburn VA — geo-blocked by Polymarket, migrated to Helsinki.

**Wallet:** `0x0036F15972166642fCb242F11fa5D1b6AD58Bc70`. Collateral: USDC.e (`0x2791...`). Balance: ~5.88 USDC.e, ~25 MATIC.

**Codebase:** 3,853 LOC Python (src), 3,039 LOC tests. 183 commits over 22 days.

**Tech stack:** Python 3.12, py-clob-client 0.34.6, httpx, websockets, loguru, FastAPI, SQLite, python-telegram-bot, Docker.

**Known issues / technical debt:**
- Cross-market detection uses keyword heuristic only — LLM mutual exclusivity validation deferred to v1.1
- YES/NO arb threshold 1.5% — market is efficient, 0 detected in dry-run; strategy may need tuning
- WebSocket subscription capped at ~2000 token IDs (server silently drops beyond that)

## Constraints

- **Tech stack:** Must integrate with Polymarket's official API
- **Latency:** Ultra-low latency execution required for strategy effectiveness
- **Capital:** Under $1k total capital at risk
- **Deployment:** Must run continuously on cloud VPS

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Official Polymarket API (py-clob-client) | Simpler integration, documented interface | ✓ Good — SDK handled auth, order types, WebSocket |
| Efficient scanning over brute-force | Full market scan may be inefficient | ✓ Good — WS subscription + HTTP rotation works |
| Modified Kelly sizing (√p denominator) | Execution-probability-adjusted Kelly | ✓ Good — conservative sizing enforced |
| FAK orders via create_order+post_order | GTC-only create_and_post_order excluded | ✓ Good — FAK fires and forgets correctly |
| Hetzner HEL1 (Helsinki) VPS | Ashburn VA was geo-blocked | ✓ Good — <35ms, not blocked |
| USDC.e collateral (not native USDC) | Polymarket uses bridged USDC | ✓ Critical — native USDC causes silent failures |
| hasattr guard for record_order_error | Defensive call at both YES-verify and NO-exhaust | ✓ Good — consistent pattern, test-mockable |
| `_last_trip_count` captured before clear() | CB alert must show live count, not static threshold | ✓ Good — order matters, before .clear() |

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*Last updated: 2026-04-18 after v1.0 milestone completion (all 23 v1 requirements shipped)*
