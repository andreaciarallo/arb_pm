# Roadmap

**Project:** Polymarket Arbitrage Bot
**Version:** v1
**Last Updated:** 2026-03-28

---

## Phases

- [x] **Phase 1: Infrastructure Foundation** — VPS deployment, RPC endpoints, Docker containerization, wallet integration (completed 2026-03-28)
- [x] **Phase 2: Market Data & Detection** — Real-time scanning, YES+NO arbitrage detection, dry-run mode (completed 2026-03-28)
- [ ] **Phase 3: Execution & Risk Controls** — Automated trade execution with circuit breakers and position limits
- [ ] **Phase 4: Observability & Monitoring** — Trade logging, alerts, live dashboard

---

## Phase Details

### Phase 1: Infrastructure Foundation
**Goal**: Bot can connect to Polymarket APIs securely from a low-latency environment
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05
**Success Criteria** (what must be TRUE):
  1. Bot runs in Docker container on London VPS (eu-west-2) with verified sub-100ms latency to Polymarket APIs
  2. Bot connects via dedicated RPC endpoint (not public) with latency benchmarks logged
  3. API keys are injected at runtime (not stored in .env) with trade-only permissions verified
  4. Non-custodial wallet is configured and can sign messages for Polymarket CLOB
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md — Project skeleton, fail-fast config, EOA wallet client (INFRA-04, INFRA-05)
- [x] 01-02-PLAN.md — Health check, latency benchmark, connectivity smoke tests (INFRA-01, INFRA-02)
- [x] 01-03-PLAN.md — Dockerfile and docker-compose.yml containerization (INFRA-03)
- [x] 01-04-PLAN.md — Human verification: VPS deploy, Docker health, latency benchmark gate (INFRA-01, INFRA-02, INFRA-03)

### Phase 2: Market Data & Detection
**Goal**: Bot can detect arbitrage opportunities in real-time without executing trades
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06
**Success Criteria** (what must be TRUE):
  1. Bot receives real-time market data via WebSocket subscription (updates within 200ms)
  2. Bot falls back to HTTP polling when WebSocket data is >5s stale (verified by forced disconnect test)
  3. Bot detects YES+NO mispricing opportunities and logs them with gross spread calculation
  4. Bot calculates fee-adjusted profitability (taker fees, gas, slippage) before scoring opportunities
  5. Dry-run mode logs detected opportunities without placing orders (verified by running 24h with zero trades)
**Plans**: TBD
**UI hint**: yes

### Phase 3: Execution & Risk Controls
**Goal**: Bot can safely execute arbitrage trades automatically with enforced risk limits
**Depends on**: Phase 2
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, RISK-01, RISK-02, RISK-03, RISK-04
**Success Criteria** (what must be TRUE):
  1. Bot executes arbitrage trades automatically when fee-adjusted spread exceeds threshold
  2. Every order is dual-verified via REST API after WebSocket fill confirmation
  3. Bot handles partial fills and mitigates one-leg execution risk (verified by simulated partial fill)
  4. Position size per trade is capped at configured percentage of total capital (0.5-1.5%)
  5. Daily stop-loss pauses trading when loss limit reached (5-8% configured threshold)
  6. Circuit breaker pauses trading on high error rates (verified by simulated error injection)
  7. Emergency kill switch immediately closes positions when triggered
**Plans**: 5 plans

Plans:
- [ ] 03-01-PLAN.md — BotConfig Phase 3 params + Modified Kelly position sizing (RISK-01)
- [ ] 03-02-PLAN.md — FAK order client: create_order+post_order(FAK) + REST fill verification (EXEC-01, EXEC-02, EXEC-04)
- [ ] 03-03-PLAN.md — Execution engine: VWAP gate + retry-then-hedge one-leg risk (EXEC-03, EXEC-04)
- [ ] 03-04-PLAN.md — RiskGate: stop-loss, circuit breaker (5m→10m→20m backoff), kill switch (RISK-02, RISK-03, RISK-04)
- [ ] 03-05-PLAN.md — live_run.py integration + trades table + --live flag in main.py (EXEC-01, EXEC-02, EXEC-03, EXEC-04, RISK-01, RISK-02, RISK-03, RISK-04)

### Phase 4: Observability & Monitoring
**Goal**: User has full visibility into bot performance and receives instant notifications
**Depends on**: Phase 3
**Requirements**: OBS-01, OBS-02, OBS-03, OBS-04
**Success Criteria** (what must be TRUE):
  1. All trades are logged to SQLite with PnL, execution costs, and capital efficiency metrics
  2. User receives instant Telegram/Discord alerts for trade executions and errors
  3. Local dashboard displays live metrics: bot status, open positions, daily PnL
  4. Per-arb analytics are tracked and viewable (entry/exit prices, hold time, net profit after fees)
**Plans**: TBD
**UI hint**: yes

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure Foundation | 4/4 | Complete   | 2026-03-28 |
| 2. Market Data & Detection | 6/6 | Complete   | 2026-03-28 |
| 3. Execution & Risk Controls | 0/5 | Not started | - |
| 4. Observability & Monitoring | 0/4 | Not started | - |

---

## Coverage

| Metric | Count |
|--------|-------|
| Total v1 Requirements | 23 |
| Mapped to Phases | 23 |
| Orphaned | 0 |
| Coverage | 100% |
