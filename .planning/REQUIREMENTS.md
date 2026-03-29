# Requirements

**Project:** Polymarket Arbitrage Bot
**Version:** v1
**Last Updated:** 2026-03-27

---

## v1 Requirements

### INFRA — Infrastructure & Setup

| ID | Requirement | Priority |
|----|-------------|----------|
| INFRA-01 | Deploy bot to London VPS (eu-west-2) for low-latency Polymarket access | Must-have |
| INFRA-02 | Configure dedicated RPC endpoints ($200-400/month budget) | Must-have |
| INFRA-03 | Set up Docker containerization for reproducible deployment | Must-have |
| INFRA-04 | Implement secure API key management (runtime injection, trade-only keys, no withdrawal permissions) | Must-have |
| INFRA-05 | Integrate non-custodial wallet for Polymarket CLOB signing | Must-have |

### DATA — Market Data & Detection

| ID | Requirement | Priority |
|----|-------------|----------|
| DATA-01 | Implement WebSocket subscription for real-time market data (primary) | Must-have |
| DATA-02 | Implement HTTP polling fallback when WebSocket data is >5s stale | Must-have |
| DATA-03 | Normalize market data to unified price format with timestamp alignment | Must-have |
| DATA-04 | Detect YES+NO cross-market mispricing opportunities (gross spread calculation) | Must-have |
| DATA-05 | Calculate fee-adjusted profitability (taker fees, gas, slippage) before scoring | Must-have |
| DATA-06 | Implement dry-run/simulation mode for testing without real capital | Must-have |

### EXEC — Trade Execution

| ID | Requirement | Priority |
|----|-------------|----------|
| EXEC-01 | Execute arbitrage trades automatically via CLOB API when opportunities found | Must-have |
| EXEC-02 | Use FAK orders via create_order() + post_order(OrderType.FAK); create_and_post_order() excluded (GTC-only) | Must-have |
| EXEC-03 | Handle partial fills and one-leg execution risk mitigation | Must-have |
| EXEC-04 | Verify every order via REST API after WebSocket fill confirmation | Must-have |

### RISK — Risk Management

| ID | Requirement | Priority |
|----|-------------|----------|
| RISK-01 | Enforce maximum capital limit per trade (0.5-1.5% of total capital) | Must-have |
| RISK-02 | Implement daily stop-loss (5-8% daily loss limit) | Must-have |
| RISK-03 | Implement circuit breaker that pauses trading on high error rates | Must-have |
| RISK-04 | Implement emergency kill switch for immediate position closure | Must-have |

### OBS — Observability & Monitoring

| ID | Requirement | Priority |
|----|-------------|----------|
| OBS-01 | Log all trades to SQLite database (PnL, execution costs, capital efficiency) | Must-have |
| OBS-02 | Send instant alerts via Telegram/Discord for trade executions and errors | Must-have |
| OBS-03 | Provide local dashboard with live metrics (bot status, open positions, daily PnL) | Must-have |
| OBS-04 | Track comprehensive metrics: per-arb analytics, execution costs, capital efficiency | Must-have |

---

## Out of Scope (v2+)

| ID | Requirement | Reason |
|----|-------------|--------|
| V2-01 | AI/ML opportunity filtering | Adds complexity; basic detection works first |
| V2-02 | Kelly Criterion position sizing | Advanced feature; start with fixed percentage |
| V2-03 | Multi-wallet support | Not needed for <$1k capital |
| V2-04 | Cross-platform arbitrage | Polymarket-only focus per project constraints |
| V2-05 | Market making mode | Requires $3k+ capital; out of scope for <$1k |
| V2-06 | REST API for external access | Nice-to-have, not core to arbitrage capture |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Complete |
| INFRA-05 | Phase 1 | Complete |
| DATA-01 | Phase 2 | Complete |
| DATA-02 | Phase 2 | Complete |
| DATA-03 | Phase 2 | Complete |
| DATA-04 | Phase 2 | Pending |
| DATA-05 | Phase 2 | Complete |
| DATA-06 | Phase 2 | Complete |
| EXEC-01 | Phase 3 | Complete |
| EXEC-02 | Phase 3 | Complete |
| EXEC-03 | Phase 3 | Pending |
| EXEC-04 | Phase 3 | Complete |
| RISK-01 | Phase 3 | Complete |
| RISK-02 | Phase 3 | Pending |
| RISK-03 | Phase 3 | Pending |
| RISK-04 | Phase 3 | Pending |
| OBS-01 | Phase 4 | Pending |
| OBS-02 | Phase 4 | Pending |
| OBS-03 | Phase 4 | Pending |
| OBS-04 | Phase 4 | Pending |

**Total v1 Requirements:** 23
**Coverage:** 23/23 mapped
