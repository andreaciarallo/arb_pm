# Milestones

## v1.0 MVP (Shipped: 2026-04-18)

**Phases completed:** 8 phases, 25 plans
**Timeline:** 2026-03-27 → 2026-04-18 (22 days)
**Scale:** 183 commits, 174 files, +35k LOC, 3,853 src + 3,039 test lines

**Key accomplishments:**

- Deployed live bot on Hetzner HEL1 Helsinki VPS (migrated from geo-blocked Ashburn VA) with <35ms median CLOB latency, Docker containerization, and USDC.e collateral with MAX_UINT256 allowances
- Implemented real-time WebSocket scanner across 44k Polymarket markets with HTTP polling fallback, price normalization, and YES/NO + cross-market arbitrage detection
- Built full FAK order execution engine with Modified Kelly position sizing (√p denominator, arxiv 2508.03474), VWAP slippage gate, and retry-then-hedge one-leg risk mitigation
- Deployed RiskGate with circuit breaker (5→10→20min exponential backoff), 5% daily stop-loss, and emergency kill switch responding to SIGTERM and KILL file
- Shipped SQLite trade logging, FastAPI dashboard (port 8080), and Telegram fire-and-forget alerts for trade executions, kill switch, and circuit breaker trips
- Closed four integration gaps: token ID wiring through ArbitrageOpportunity, CB alert live error count accuracy (OBS-02), NO-leg CB wiring in engine.py (RISK-03), and formal OBS requirement verification

**Archive:** `.planning/milestones/v1.0-ROADMAP.md` | `.planning/milestones/v1.0-REQUIREMENTS.md`

---
