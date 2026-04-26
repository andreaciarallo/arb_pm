# Roadmap

**Project:** Polymarket Arbitrage Bot
**Last Updated:** 2026-04-26

---

## Milestones

- ✅ **v1.0 MVP** -- Phases 1-8 (shipped 2026-04-18)
- ✅ **v1.1 Cross-Market Fixes** -- Phase 1 (shipped 2026-04-19)
- ✅ **v1.2 Detection Quality & Paper Trading** -- Phases 2-5 (shipped 2026-04-26)
- **v2.0 Basket Arbitrage Engine** -- Phases 6-9 (in progress)

---

## Phases

<details>
<summary>v1.0 MVP (Phases 1-8) -- SHIPPED 2026-04-18</summary>

- [x] Phase 1: Infrastructure Foundation (4/4 plans) -- completed 2026-03-28
- [x] Phase 2: Market Data & Detection (6/6 plans) -- completed 2026-03-28
- [x] Phase 3: Execution & Risk Controls (5/5 plans) -- completed 2026-03-29
- [x] Phase 4: Observability & Monitoring (4/4 plans) -- completed 2026-04-15
- [x] Phase 5: Fix Token ID Execution Wiring (2/2 plans) -- completed 2026-04-18
- [x] Phase 6: Wire Critical Telegram Alerts (1/1 plan) -- completed 2026-04-18
- [x] Phase 7: Formal Verification -- Phase 04 & 06 (1/1 plan) -- completed 2026-04-18
- [x] Phase 8: Fix Circuit Breaker & Alert Accuracy (2/2 plans) -- completed 2026-04-18

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>v1.1 Cross-Market Fixes (Phase 1) -- SHIPPED 2026-04-19</summary>

- [x] Phase 1: Fix Cross-Market False Positives & Wiring (4/4 plans) -- completed 2026-04-19

Full details: `.planning/milestones/v1.1-ROADMAP.md`

</details>

<details>
<summary>v1.2 Detection Quality & Paper Trading (Phases 2-5) -- SHIPPED 2026-04-26</summary>

- [x] Phase 2: Detection Quality Filters (3/3 plans) -- completed 2026-04-25
- [x] Phase 3: Dependency Detection Core (2/2 plans) -- completed 2026-04-25
- [x] Phase 4: Dependency Integration (2/2 plans) -- completed 2026-04-26
- [x] Phase 5: Paper Trading Simulation (3/3 plans) -- completed 2026-04-26

Full details: `.planning/milestones/v1.2-ROADMAP.md`

</details>

### v2.0 Basket Arbitrage Engine (In Progress)

**Milestone Goal:** Replace pairwise dependency detection with group-level structure validation and VWAP-based basket pricing for executable cross-market arbitrage.

- [ ] **Phase 6: Group Structure Validation** - Validate event groups as true one-of-N partitions before any pricing or execution
- [ ] **Phase 7: Basket VWAP Pricing & Liquidity Filtering** - Compute executable basket cost from full order book depth with liquidity and profitability gates
- [ ] **Phase 8: Batch Execution Engine** - Submit basket legs via batch API with graduated unwind on partial failure
- [ ] **Phase 9: Pipeline Integration & Cleanup** - Wire validation/pricing/execution pipeline end-to-end and remove dead code

---

## Phase Details

### Phase 6: Group Structure Validation
**Goal**: Bot correctly identifies which event groups are valid one-of-N partitions suitable for basket arbitrage
**Depends on**: Nothing (first phase of v2.0, builds on existing Gamma event grouping from v1.1)
**Requirements**: GV-01, GV-02, GV-03, GV-04, GV-05
**Success Criteria** (what must be TRUE):
  1. NegRisk-enabled event groups are automatically accepted as valid partitions without heuristic checks
  2. Non-NegRisk event groups with duplicate markets (Jaccard > 0.9) are rejected with diagnostic logging
  3. Non-NegRisk event groups with subset/implication relations between markets are rejected with diagnostic logging
  4. Non-NegRisk event groups failing completeness heuristic (mid-price sum outside 0.7-1.3) are rejected
  5. Event metadata (market count per event) is cached from Gamma API at startup and available for partition verification
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

### Phase 7: Basket VWAP Pricing & Liquidity Filtering
**Goal**: Bot computes realistic executable cost for each basket using full order book depth, rejects illiquid or unprofitable baskets
**Depends on**: Phase 6 (requires validated groups to price)
**Requirements**: BP-01, BP-02, BP-03, BP-04, LP-01, LP-02, LP-03, LP-04
**Success Criteria** (what must be TRUE):
  1. Basket cost per leg is computed from VWAP across multiple order book levels (not just best ask)
  2. Order books for all basket legs are fetched in a single batch call (not serial per-leg requests)
  3. Common-size (max fillable shares across all legs) is resolved through iterative VWAP/size convergence
  4. Baskets with any leg below minimum depth or exceeding maximum bid-ask spread are rejected before execution
  5. Fee-adjusted net edge (payout minus total VWAP cost minus fees minus slippage buffer) gates all baskets -- below-threshold baskets never reach execution
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

### Phase 8: Batch Execution Engine
**Goal**: Bot executes basket arbitrage trades via batch API with safe signing and graduated failure recovery
**Depends on**: Phase 7 (requires priced, liquidity-validated baskets)
**Requirements**: EX-01, EX-02, EX-03, EX-04
**Success Criteria** (what must be TRUE):
  1. All basket legs are submitted in a single batch `post_orders()` call (up to 15 FAK orders per request)
  2. Orders are signed sequentially to avoid nonce collision, then submitted as one batch
  3. Partial basket failures are detected from batch results and trigger graduated unwind (not fire-sale)
  4. Failed basket legs are unwound at market price using current order book data
**Plans**: TBD

Plans:
- [ ] 08-01: TBD
- [ ] 08-02: TBD

### Phase 9: Pipeline Integration & Cleanup
**Goal**: Bot runs the complete validation-pricing-execution pipeline end-to-end with YES/NO arb removed and paper trading updated
**Depends on**: Phase 8 (requires all three new components to wire together)
**Requirements**: PI-01, PI-02, PI-03
**Success Criteria** (what must be TRUE):
  1. YES/NO arb detection is completely removed from the scan loop -- bot only runs cross-market basket arb
  2. Dry-run mode exercises the full new pipeline (validation -> pricing -> execution simulation) with diagnostic output
  3. Paper trading simulation uses basket VWAP pricing and common-size instead of single-level ask prices
**Plans**: TBD

Plans:
- [ ] 09-01: TBD
- [ ] 09-02: TBD

---

## Progress

**Execution Order:**
Phases execute in numeric order: 6 -> 7 -> 8 -> 9

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Infrastructure Foundation | v1.0 | 4/4 | Complete | 2026-03-28 |
| 2. Market Data & Detection | v1.0 | 6/6 | Complete | 2026-03-28 |
| 3. Execution & Risk Controls | v1.0 | 5/5 | Complete | 2026-03-29 |
| 4. Observability & Monitoring | v1.0 | 4/4 | Complete | 2026-04-15 |
| 5. Fix Token ID Execution Wiring | v1.0 | 2/2 | Complete | 2026-04-18 |
| 6. Wire Critical Telegram Alerts | v1.0 | 1/1 | Complete | 2026-04-18 |
| 7. Formal Verification -- Phase 04 & 06 | v1.0 | 1/1 | Complete | 2026-04-18 |
| 8. Fix Circuit Breaker & Alert Accuracy | v1.0 | 2/2 | Complete | 2026-04-18 |
| 1. Fix Cross-Market False Positives & Wiring | v1.1 | 4/4 | Complete | 2026-04-19 |
| 2. Detection Quality Filters | v1.2 | 3/3 | Complete | 2026-04-25 |
| 3. Dependency Detection Core | v1.2 | 2/2 | Complete | 2026-04-25 |
| 4. Dependency Integration | v1.2 | 2/2 | Complete | 2026-04-26 |
| 5. Paper Trading Simulation | v1.2 | 3/3 | Complete | 2026-04-26 |
| 6. Group Structure Validation | v2.0 | 0/TBD | Not started | - |
| 7. Basket VWAP Pricing & Liquidity Filtering | v2.0 | 0/TBD | Not started | - |
| 8. Batch Execution Engine | v2.0 | 0/TBD | Not started | - |
| 9. Pipeline Integration & Cleanup | v2.0 | 0/TBD | Not started | - |
