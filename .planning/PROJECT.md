# Polymarket Arbitrage Bot

## What This Is

A fully automated arbitrage trading bot that identifies and executes cross-market mispricing opportunities on Polymarket prediction markets. The bot continuously scans markets, detects arbitrage opportunities, and automatically executes trades to capture price discrepancies.

## Core Value

Ultra-low latency detection and execution of cross-market arbitrage opportunities on Polymarket before they disappear.

## Requirements

### Validated

- [x] Connect to Polymarket API for market data and trade execution — Validated in Phases 1-2
- [x] Implement efficient market scanning strategy (not brute-force full scan) — Validated in Phase 2
- [x] Detect cross-market mispricing opportunities in real-time — Validated in Phase 2
- [x] Execute arbitrage trades automatically when opportunities found — Validated in Phases 3 + 5 (token ID wiring complete; EXEC-01–04 + RISK-01 reachable)
- [x] Enforce maximum capital limit risk management — Validated in Phase 3 + 5 (Kelly gate, stop-loss, circuit breaker)
- [x] Provide local dashboard with live metrics — Validated in Phase 4
- [x] Deploy to cloud VPS for continuous operation — Validated in Phases 1 + VPS migration

### Active

- [ ] Send alerts via Telegram/Discord — Phase 6 (kill switch + circuit breaker wiring)
- [ ] Track comprehensive metrics: PnL, per-arb analytics, execution costs, capital efficiency

### Out of Scope

- [ ] Multi-exchange arbitrage — Polymarket-only focus for v1
- [ ] Manual execution mode — fully automated from launch
- [ ] Serverless deployment — VPS deployment only

## Context

**Reference implementation:** https://www.binance.com/en/square/post/300294926912497 — use this as a reference for unspecified details, asking user whether to follow same approach or do something different.

**Market:** Polymarket prediction markets only (not multi-exchange).

**Arbitrage type:** Cross-market mispricing — related outcomes that are mispriced relative to each other.

**Capital:** Under $1k starting capital.

**Risk mode:** Aggressive position sizing within capital limits.

**Infrastructure:** Cloud deployment on VPS for 24/7 operation.

**Speed:** Ultra-low latency is critical — milliseconds matter for capturing opportunities.

## Constraints

- **Tech stack:** Must integrate with Polymarket's official API
- **Latency:** Ultra-low latency execution required for strategy effectiveness
- **Capital:** Under $1k total capital at risk
- **Deployment:** Must run continuously on cloud VPS

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Official Polymarket API over on-chain | Simpler integration, documented interface | — Pending |
| Efficient scanning over brute-force | Full market scan may be inefficient; need state-of-the-art approach | — Pending |
| Aggressive sizing | User preference for maximizing capture | — Pending |
| VPS deployment | Continuous operation required for 24/7 markets | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-27 after project initialization*
