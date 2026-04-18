# Roadmap

**Project:** Polymarket Arbitrage Bot
**Version:** v1
**Last Updated:** 2026-03-28

---

## Phases

- [x] **Phase 1: Infrastructure Foundation** — VPS deployment, RPC endpoints, Docker containerization, wallet integration (completed 2026-03-28)
- [x] **Phase 2: Market Data & Detection** — Real-time scanning, YES+NO arbitrage detection, dry-run mode (completed 2026-03-28)
- [x] **Phase 3: Execution & Risk Controls** — Automated trade execution with circuit breakers and position limits (completed 2026-03-29)
- [x] **Phase 4: Observability & Monitoring** — Trade logging, alerts, live dashboard (completed 2026-04-15)
- [ ] **Phase 5: Fix Token ID Execution Wiring** — Wire yes_token_id/no_token_id through ArbitrageOpportunity to unblock live trade execution (gap closure)
- [ ] **Phase 6: Wire Critical Telegram Alerts** — Wire kill switch and circuit breaker trip Telegram notifications (gap closure)
- [ ] **Phase 7: Formal Verification — Phase 04 & 06** — Create VERIFICATION.md for Phase 04 (OBS-01, OBS-03, OBS-04) and Phase 06 (OBS-02); fix stale traceability entries (gap closure)
- [ ] **Phase 8: Fix Circuit Breaker & Alert Accuracy** — Fix NO-leg CB trip wiring (RISK-03) and CB alert live count bug (OBS-02) (gap closure)

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
  4. Position size per trade uses modified Kelly formula with 5% capital ceiling (D-01)
  5. Daily stop-loss pauses trading when loss limit reached (5-8% configured threshold)
  6. Circuit breaker pauses trading on high error rates (verified by simulated error injection)
  7. Emergency kill switch immediately closes positions when triggered
**Plans**: 5 plans

Plans:
- [x] 03-01-PLAN.md — BotConfig Phase 3 params + Modified Kelly position sizing (RISK-01)
- [x] 03-02-PLAN.md — FAK order client: create_order+post_order(FAK) + REST fill verification (EXEC-01, EXEC-02, EXEC-04)
- [x] 03-03-PLAN.md — Execution engine: VWAP gate + retry-then-hedge one-leg risk (EXEC-03, EXEC-04)
- [x] 03-04-PLAN.md — RiskGate: stop-loss, circuit breaker (5m→10m→20m backoff), kill switch (RISK-02, RISK-03, RISK-04)
- [x] 03-05-PLAN.md — live_run.py integration + trades table + --live flag in main.py (EXEC-01, EXEC-02, EXEC-03, EXEC-04, RISK-01, RISK-02, RISK-03, RISK-04)

### Phase 4: Observability & Monitoring
**Goal**: User has full visibility into bot performance and receives instant notifications
**Depends on**: Phase 3
**Requirements**: OBS-01, OBS-02, OBS-03, OBS-04
**Success Criteria** (what must be TRUE):
  1. All trades are logged to SQLite with PnL, execution costs, and capital efficiency metrics
  2. User receives instant Telegram alerts for trade executions and errors (Telegram only per D-01)
  3. Local dashboard displays live metrics: bot status, open positions, daily PnL
  4. Per-arb analytics are tracked and viewable (entry/exit prices, hold time, net profit after fees)
**Plans**: 4 plans

Plans:
- [x] 04-01-PLAN.md — Wave 0: test scaffolds (test_storage.py extensions, test_telegram.py, test_dashboard.py) + requirements.txt additions (OBS-01, OBS-02, OBS-03, OBS-04)
- [x] 04-02-PLAN.md — Storage layer: arb_pairs table + insert_arb_pair() + insert_trade() fees_usd fix + BotConfig update (OBS-01, OBS-04)
- [x] 04-03-PLAN.md — TelegramAlerter: fire-and-forget notifications module (OBS-02)
- [x] 04-04-PLAN.md — Dashboard + integration: FastAPI app + live_run.py wiring + engine.py arb_id + docker-compose port 8080 (OBS-01, OBS-02, OBS-03, OBS-04)

### Phase 5: Fix Token ID Execution Wiring
**Goal**: Live trade execution actually fires — ArbitrageOpportunity carries token IDs through to engine.py so Gate 0 no longer blocks every opportunity
**Depends on**: Phase 4
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, RISK-01
**Gap Closure**: Closes TOKEN-ID-GAP integration gap and "Trade Execution" E2E flow from v1.0 audit
**Success Criteria** (what must be TRUE):
  1. `ArbitrageOpportunity` dataclass has `yes_token_id` and `no_token_id` fields
  2. `yes_no_arb.py` and `cross_market.py` populate both fields (no longer discarded as local vars)
  3. `engine.py` Gate 0 reads token IDs from `opp` and no longer returns `status='skipped'` for valid opportunities
  4. At least one simulated FAK order call is reached in a live-mode dry run (verified via logs)
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md — ArbitrageOpportunity dataclass extension + yes_no_arb.py + cross_market.py wiring + token ID test (EXEC-01)
- [x] 05-02-PLAN.md — engine.py Gate 0/Gate 1 upgrade + test_execution_engine.py updates (EXEC-01, EXEC-02, EXEC-03, EXEC-04, RISK-01)

### Phase 6: Wire Critical Telegram Alerts
**Goal**: User receives Telegram notifications for kill switch and circuit breaker trip events
**Depends on**: Phase 5
**Requirements**: OBS-02
**Gap Closure**: Closes TELEGRAM-PARTIAL integration gap and "Kill Switch Telegram Alert" E2E flow from v1.0 audit
**Success Criteria** (what must be TRUE):
  1. `_execute_kill_switch()` in `live_run.py` calls `alerter.send_kill_switch()` via `asyncio.create_task()`
  2. Circuit breaker trip event in scan loop calls `alerter.send_circuit_breaker_trip()` via `asyncio.create_task()`
  3. Both alert methods have verified call sites (grep confirms ≥1 call site each)
**Plans**: 1 plan

Plans:
- [x] 06-01-PLAN.md — Wire kill switch + CB trip alert call sites in live_run.py + unit tests (OBS-02)

### Phase 7: Formal Verification — Phase 04 & 06
**Goal**: Formally verify Phase 04 observability implementations and Phase 06 alert wiring to satisfy OBS-01, OBS-03, OBS-04; fix stale traceability entries
**Depends on**: Phase 6
**Requirements**: OBS-01, OBS-03, OBS-04, OBS-02 (Phase 06 verification portion)
**Gap Closure**: Closes OBS-01, OBS-03, OBS-04 requirement gaps from v1.0 audit (Phase 04 missing VERIFICATION.md); closes Phase 06 VERIFICATION.md gap
**Success Criteria** (what must be TRUE):
  1. Phase 04 VERIFICATION.md exists and confirms OBS-01 (trade logging to SQLite), OBS-03 (FastAPI dashboard port 8080), OBS-04 (arb_pairs table + insert_arb_pair) satisfied via static code verification
  2. Phase 06 VERIFICATION.md exists and confirms kill switch + CB trip alert call sites wired (OBS-02 Phase 06 portion)
  3. REQUIREMENTS.md traceability corrected: DATA-04, EXEC-01–04, RISK-01 status updated from Pending to Complete
**Plans**: 1 plan

Plans:
- [x] 07-01-PLAN.md — Create Phase 06 VERIFICATION.md, flip OBS-01/03/04 to Complete in REQUIREMENTS.md, write Phase 07 SUMMARY (OBS-01, OBS-02, OBS-03, OBS-04) (completed 2026-04-18)

### Phase 8: Fix Circuit Breaker & Alert Accuracy
**Goal**: Fix two integration bugs leaving RISK-03 and OBS-02 partially broken in production
**Depends on**: Phase 7
**Requirements**: RISK-03, OBS-02
**Gap Closure**: Closes RISK-03 integration gap (NO-leg failures don't trip CB) and OBS-02 accuracy gap (CB alert shows static threshold not live count) from v1.0 audit
**Success Criteria** (what must be TRUE):
  1. `engine.py` calls `risk_gate.record_order_error()` after the NO-leg retry loop exits with `not no_filled` (approx lines 369–415)
  2. `gate.py` captures the triggering error count before clearing `_error_timestamps` and exposes it as a property
  3. `live_run.py` passes the live triggering count (not static configured threshold) to `alerter.send_circuit_breaker_trip()`
  4. Unit tests confirm both fixes: NO-leg exhaustion trips CB; CB alert message shows live count
**Plans**: TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure Foundation | 4/4 | Complete   | 2026-03-28 |
| 2. Market Data & Detection | 6/6 | Complete   | 2026-03-28 |
| 3. Execution & Risk Controls | 5/5 | Complete   | 2026-03-29 |
| 4. Observability & Monitoring | 4/4 | Complete   | 2026-04-15 |
| 5. Fix Token ID Execution Wiring | 0/2 | Pending | — |
| 6. Wire Critical Telegram Alerts | 0/1 | Pending | — |
| 7. Formal Verification — Phase 04 & 06 | 0/TBD | Pending | — |
| 8. Fix Circuit Breaker & Alert Accuracy | 0/TBD | Pending | — |

---

## Coverage

| Metric | Count |
|--------|-------|
| Total v1 Requirements | 23 |
| Mapped to Phases | 23 |
| Orphaned | 0 |
| Coverage | 100% |
