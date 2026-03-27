# Research Summary

**Project:** Polymarket Arbitrage Bot
**Synthesized:** 2026-03-27

---

## Executive Summary

This is a **low-latency crypto arbitrage bot** targeting YES/NO share price dislocations on Polymarket's prediction markets. The core opportunity: when YES + NO shares trade below $1.00, buying both guarantees $1.00 payout at resolution. However, these windows close in 15-50ms, making this an **infrastructure game first, strategy second**.

The recommended approach prioritizes **co-located infrastructure** (London VPS + dedicated RPC nodes) over complex strategies. Research shows 78% of crypto bot traders lose money due to latency gaps, not strategy flaws. The stack centers on Python 3.10+ with py-clob-client (official Polymarket SDK), httpx for async HTTP, and websockets for real-time data. SQLite handles trade logs initially; migration to PostgreSQL is only needed at scale.

Key risks are **infrastructure underestimation** (opportunities vanish before public RPC confirms), **silent API failures** (state desync between local bot and CLOB), **fee illusion** (apparent profits erased by taker fees + gas + slippage), and **oracle manipulation** (UMA voting can flip resolutions on large positions). Mitigation: budget $200-400/month for dedicated RPC from day one, implement dual-verification on all orders, calculate true spread after ALL costs before execution, and avoid holding positions through resolution windows on low-liquidity markets.

---

## Key Findings

### From STACK.md

| Technology | Rationale |
|------------|-----------|
| **Python 3.10+** | Best ecosystem for trading bots; py-clob-client is official Polymarket SDK |
| **py-clob-client** | Official SDK supporting full CLOB API including WebSocket streaming |
| **ethers.py v5+** | Required by py-clob-client for signer; simpler than web3.py |
| **httpx 0.28+** | HTTP/2 support reduces latency; cleaner API than aiohttp for <300 concurrent requests |
| **websockets 16.0+** | Official Polymarket SDK uses this internally; asyncio-native |
| **SQLite 3.40+** | Zero-config, sufficient for <100 trades/day; single-file deployment |
| **Loguru 0.7+** | Zero-configuration logging with JSON serialization |
| **Docker 24+** | Reproducible deployments, health checks, resource limits |

**Critical version note:** py-clob-client handles blockchain interaction internally—adding web3.py would be redundant unless direct contract calls are needed.

### From FEATURES.md

**Table Stakes (Must-Have):**
- Real-time market scanning via WebSocket (sub-200ms detection across 1,500+ markets)
- YES+NO arbitrage detection with fee-aware opportunity scoring
- Automated trade execution (manual execution too slow for 15-50ms windows)
- Position size limits (0.5-1.5% of capital per trade) and stop-loss (5-8% daily loss limit)
- PnL tracking, trade history logging, bot status monitoring
- Dry-run/simulation mode for testing before risking capital
- Telegram/Discord alerts for instant notifications

**Differentiators (Should-Have for v2):**
- Sub-50ms detection latency via dedicated RPC endpoints
- AI/ML opportunity filtering for false positive reduction
- 4-level drawdown heat system with dynamic position sizing
- Kelly Criterion position sizing (fractional Kelly 0.25-0.35)
- 15+ independent risk checks per trade

**Defer to v2+:**
- AI/ML filtering (adds complexity; basic detection works first)
- Momentum strategy engine (different strategy entirely)
- Market making mode (requires $3k+ capital; out of scope for <$1k)
- Cross-platform arbitrage (Polymarket-only per project constraints)
- REST API access (nice-to-have, not core to arbitrage capture)

### From ARCHITECTURE.md

**Major Components:**

| Component | Responsibility |
|-----------|---------------|
| **Data Ingestion** | WebSocket subscriptions (primary) + HTTP polling (fallback) for market data |
| **Normalization** | Unified price format, timestamp alignment, stale data detection |
| **Opportunity Engine** | Cross-market spread calculation, fee-adjusted profitability, liquidity filtering |
| **Risk Management** | Position limits, daily loss caps, circuit breakers, emergency kill switch |
| **Execution Engine** | Order placement via CLOB API, partial fill handling, one-leg risk mitigation |
| **Monitoring** | Live dashboard, Telegram/Discord alerts, trade logging |

**Key Patterns to Follow:**
1. **Async-First Data Ingestion** — Blocking HTTP calls add 100-500ms; opportunities vanish in <2s
2. **Conservative Profitability Calculation** — `net_spread = gross_spread - fees - slippage` before every execution
3. **Circuit Breaker Risk Control** — Auto-pause on error rates or daily loss thresholds
4. **Dual-Mode Connectivity** — WebSocket primary with HTTP fallback if >5s stale

### From PITFALLS.md

**Top 5 Critical Pitfalls:**

| Pitfall | Prevention Strategy |
|---------|---------------------|
| **Latency Infrastructure Underestimation** | Budget $200-400/month for dedicated RPC; deploy VPS in London (eu-west-2); track detection-to-capture ratio (target >10%) |
| **Silent API Failures / State Desync** | Always use `create_and_post_order()` (not `create_order`); dual-verify every order via REST after WebSocket fill; cache signature type at startup |
| **Oracle/Resolution Risk** | Avoid holding positions through resolution on <$100k liquidity markets; check UMA voter concentration (avoid if top 10 control >60%) |
| **Fee Illusion (Negative EV)** | Calculate true spread including taker fees (2x 0.5%), gas, withdrawal fees, slippage; minimum 0.5% profit threshold after ALL costs |
| **API Key Security** | Never store in `.env`; runtime injection only; trade-only keys with NO withdrawal permissions; IP whitelisting; bind services to 127.0.0.1 |

**Moderate Pitfalls:** Rate limit mismanagement (use WebSockets, implement request queue), slippage miscalculation (check order book depth, not just top-of-book), no circuit breakers for black swan events.

---

## Implications for Roadmap

### Suggested Phase Structure

Based on component dependencies and risk prioritization:

**Phase 1: Infrastructure Foundation**
- **Rationale:** Cannot build anything without reliable, low-latency connectivity to Polymarket APIs
- **Delivers:** VPS deployment in London, dedicated RPC endpoints, secure API key management, Docker containerization
- **Features:** Non-custodial wallet integration setup, environment configuration
- **Pitfalls to Avoid:** Latency underestimation (Pitfall 1), API key exposure (Pitfall 5)
- **Research Flag:** YES — infrastructure choices are high-stakes; validate VPS provider latency benchmarks

**Phase 2: Data Pipeline & Opportunity Detection**
- **Rationale:** Must reliably ingest and normalize market data before detecting opportunities
- **Delivers:** WebSocket subscription handling, HTTP fallback, data normalization, YES+NO spread detection
- **Features:** Real-time market scanning, fee-aware opportunity scoring, dry-run mode
- **Pitfalls to Avoid:** Silent API failures (Pitfall 2), fee illusion (Pitfall 4), rate limit mismanagement (Pitfall 6), slippage miscalculation (Pitfall 7)
- **Research Flag:** NO — well-documented patterns from py-clob-client and Polymarket docs

**Phase 3: Execution & Risk Controls**
- **Rationale:** Detection is useless without safe execution; risk controls prevent catastrophic loss
- **Delivers:** Order placement via CLOB API, position sizing, stop-loss limits, circuit breakers
- **Features:** Automated trade execution, position size limits, stop-loss/daily loss limits
- **Pitfalls to Avoid:** Single-leg execution (Anti-Pattern 3), no circuit breakers (Pitfall 8)
- **Research Flag:** NO — py-clob-client provides order management; circuit breaker pattern is standard

**Phase 4: Observability & Monitoring**
- **Rationale:** Need visibility into bot performance and health for production operation
- **Delivers:** Trade logging to SQLite, Telegram/Discord alerts, basic dashboard metrics
- **Features:** PnL tracking, trade history logging, bot status monitoring, alerts
- **Pitfalls to Avoid:** Data loss from log rotation (Pitfall 9)
- **Research Flag:** NO — Loguru + python-telegram-bot are straightforward integrations

**Phase 5: Optimization & Advanced Features**
- **Rationale:** Once core loop is profitable, optimize for edge cases and scale
- **Delivers:** Kelly Criterion sizing, AI/ML filtering (optional), multi-wallet support
- **Features:** Advanced risk management, gas optimization, custom RPC endpoints
- **Pitfalls to Avoid:** Strategy obsolescence (Pitfall 10), oracle risk (Pitfall 3)
- **Research Flag:** YES — AI/ML filtering and advanced strategies need validation

### Phase Dependencies

```
Phase 1 (Infrastructure)
         │
         ▼
Phase 2 (Data + Detection)
         │
         ▼
Phase 3 (Execution + Risk)
         │
         ▼
Phase 4 (Observability)
         │
         ▼
Phase 5 (Optimization)
```

**Rationale for ordering:**
- Infrastructure is foundational; everything else depends on low-latency connectivity
- Data ingestion must be reliable before detection logic can be trusted
- Risk controls must be in place BEFORE live execution (safety first)
- Observability adds value but doesn't block core functionality
- Optimization is iterative; only meaningful after baseline profitability is proven

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| **Stack** | HIGH | py-clob-client is verified official SDK from docs.polymarket.com; Python/HTTPX/websockets choices backed by benchmark comparisons and 2025-2026 sources |
| **Features** | HIGH | Table stakes derived from multiple 2026 Polymarket bot guides and open-source projects; MVP prioritization aligns with industry patterns |
| **Architecture** | HIGH | Component boundaries follow standard trading bot architecture; patterns verified from Polymarket-specific case studies and AgentBets.ai guides |
| **Pitfalls** | HIGH | Critical pitfalls sourced from production post-mortems (FlashArb, runtime notes), 2026 security reports, and documented oracle manipulation incidents |

**Gaps to Address During Planning:**

1. **Exact VPS provider recommendation** — Research mentions London eu-west-2 but doesn't specify provider (AWS vs. DigitalOcean vs. Linode). Latency benchmarks needed.
2. **Dedicated RPC cost validation** — $200-400/month estimate should be validated against Alchemy/QuickNode pricing for Polygon.
3. **Minimum capital threshold** — Research assumes "<$1k" but doesn't specify minimum viable capital after fees/gas.
4. **Backtesting data availability** — Historical Polymarket market data sources not fully documented; may need to build custom data collection.

---

## Sources

**Stack Research:**
- [Polymarket CLOB Client SDKs](https://docs.polymarket.com/api-reference/clients-sdks)
- [Polymarket Python Client GitHub](https://github.com/Polymarket/py-clob-client)
- [HTTPX vs AIOHTTP Benchmarks](https://decodo.com/blog/httpx-vs-requests-vs-aiohttp)
- [Loguru Documentation](https://loguru.org/)

**Features Research:**
- [Polymarket Arbitrage Bot Guide 2026](https://www.polytrackhq.app/blog/polymarket-arbitrage-bot-guide)
- [Polymarket Trading Bot — Open Source Features](https://dev.to/benjamin_martin_749c1d57f/polymarket-trading-bot-real-time-arbitrage-momentum-strategies-and-production-features-open-17m1)
- [The Arbitrage Bot Arms Race — Production Lessons](https://dev.to/chronocoders/the-arbitrage-bot-arms-race-what-we-learned-running-flasharb-in-production-10ij)

**Architecture Research:**
- [Polymarket API Guide - AgentBets.ai](https://agentbets.ai/guides/polymarket-api-guide/)
- [Polymarket Arbitrage Case Study - AgentBets.ai](https://agentbets.ai/blog/polymarket-arbitrage-bot-case-study/)
- [15min BTC Polymarket Bot Architecture - DeepWiki](https://deepwiki.com/gabagool222/15min-btc-polymarket-trading-bot/5.1-main-bot-architecture)

**Pitfalls Research:**
- [Solana arbitrage bot setup: why most fail before they start](https://medium.com/@yavorovych/solana-arbitrage-bot-setup-why-most-fail-before-they-start-1c24d8d72593)
- [The Arbitrage Bot Arms Race: What We Learned Running FlashArb in Production](https://dev.to/chronocoders/the-arbitrage-bot-arms-race-what-we-learned-running-flasharb-in-production-10ij)
- [Polymarket Has a Bot Problem](https://medium.com/@0xicaruss/polymarket-has-a-bot-problem-i-spent-2-weeks-figuring-out-whos-actually-human-b8aeef1980b2)
- [Before you run a Polymarket bot, read this](https://runtimenotes.com/blog/before-you-run-a-polymarket-bot/)
- [Polymarket encounters oracle manipulation attacks](https://www.aicoin.com/en/article/449974)

---

## Synthesis Notes

**Patterns Across Research Files:**

1. **Infrastructure is the differentiator** — All four files emphasize that latency and connectivity matter more than strategy sophistication. This contradicts typical "build the smartest algo first" instincts.

2. **Fee awareness is non-negotiable** — FEATURES.md lists "fee-aware opportunity scoring" as table stakes; ARCHITECTURE.md includes it in the Opportunity Engine; PITFALLS.md shows it as Pitfall 4 (fee illusion). This must be core to detection logic, not an afterthought.

3. **Risk management before execution** — PITFALLS.md's top pitfalls (silent API failures, oracle risk, no circuit breakers) all map to Risk Management layer in ARCHITECTURE.md. Phase 3 must include risk controls BEFORE enabling live execution.

4. **Observability enables iteration** — Multiple sources note that strategy obsolescence is inevitable (spreads compress over time). Trade logging and metrics tracking (Phase 4) are not optional—they're how you detect when the strategy stops working.

**What Changed My Mind:**

- Initially considered suggesting Node.js for WebSocket performance, but py-clob-client being Python-first and the trading ecosystem's Python dominance (pandas, numpy for backtesting) makes Python the clear choice.
- Considered suggesting PostgreSQL from the start, but SQLite's zero-config advantage for <$1k capital and <100 trades/day is compelling. Migration path is clear when scaling.
- AI/ML filtering seems glamorous, but research consistently shows infrastructure gaps cause 78% of failures—not strategy sophistication. Deferred to v2+.

---

*This summary is intended to inform roadmap creation. See individual research files for detailed source links and technical specifications.*
