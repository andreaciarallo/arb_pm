# Roadmap

**Project:** Polymarket Arbitrage Bot
**Last Updated:** 2026-04-26

---

## Milestones

- ✅ **v1.0 MVP** — Phases 1-8 (shipped 2026-04-18)
- ✅ **v1.1 Cross-Market Fixes** — Phase 1 (shipped 2026-04-19)
- 🚧 **v1.2 Detection Quality & Paper Trading** — Phases 2-5 (in progress)

---

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-8) — SHIPPED 2026-04-18</summary>

- [x] Phase 1: Infrastructure Foundation (4/4 plans) — completed 2026-03-28
- [x] Phase 2: Market Data & Detection (6/6 plans) — completed 2026-03-28
- [x] Phase 3: Execution & Risk Controls (5/5 plans) — completed 2026-03-29
- [x] Phase 4: Observability & Monitoring (4/4 plans) — completed 2026-04-15
- [x] Phase 5: Fix Token ID Execution Wiring (2/2 plans) — completed 2026-04-18
- [x] Phase 6: Wire Critical Telegram Alerts (1/1 plan) — completed 2026-04-18
- [x] Phase 7: Formal Verification — Phase 04 & 06 (1/1 plan) — completed 2026-04-18
- [x] Phase 8: Fix Circuit Breaker & Alert Accuracy (2/2 plans) — completed 2026-04-18

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v1.1 Cross-Market Fixes (Phase 1) — SHIPPED 2026-04-19</summary>

- [x] Phase 1: Fix Cross-Market False Positives & Wiring (4/4 plans) — completed 2026-04-19

Full details: `.planning/milestones/v1.1-ROADMAP.md`

</details>

### 🚧 v1.2 Detection Quality & Paper Trading (In Progress)

**Milestone Goal:** Eliminate false-positive opportunities, add multi-stage dependency detection for cross-market validation, and simulate execution P&L in dry-run mode to measure real profitability before going live.

- [x] **Phase 2: Detection Quality Filters** - Price floor gates and deduplication to eliminate 93% false positives
- [x] **Phase 3: Dependency Detection Core** - Preprocessing, feature extraction, weighted scoring, and classification module
- [ ] **Phase 4: Dependency Integration** - Pair generation, audit mode, and cross-market detector hookup
- [ ] **Phase 5: Paper Trading Simulation** - VWAP+Kelly simulation in dry-run with paper_trades table and summary queries

---

## Phase Details

### Phase 2: Detection Quality Filters
**Goal**: Bot produces only actionable arbitrage opportunities by filtering out dead markets, near-resolved markets, and duplicate detections
**Depends on**: Nothing (first phase in v1.2; builds on existing v1.1 detectors)
**Requirements**: DETECT-01, DETECT-02, DETECT-03, DETECT-04, DETECT-05
**Success Criteria** (what must be TRUE):
  1. Bot never logs a YES/NO opportunity where either ask is at or below $0.03
  2. Bot never logs a YES/NO opportunity where the ask sum exceeds $0.99
  3. Bot never logs a cross-market group containing a leg with ask at or below $0.005 or a group with total_yes below $0.10
  4. Bot logs each unique opportunity at most once per configurable time window (no repeated entries for the same arb within the window)
**Plans:** 3 plans
Plans:
- [x] 02-01-PLAN.md — Create filters module (TDD): threshold functions, DedupTracker, FilterDiagnostics, BotConfig fields
- [x] 02-02-PLAN.md — Wire filters into YES/NO and cross-market detectors, update detector tests
- [x] 02-03-PLAN.md — Wire DedupTracker lifecycle into dry_run and live_run, update orchestrator tests

### Phase 3: Dependency Detection Core
**Goal**: A standalone dependency detection module that can score any pair of market questions for subset/related/independent relationships using five weighted signals
**Depends on**: Phase 2 (clean detection output feeds into dependency analysis)
**Requirements**: DEP-01, DEP-02, DEP-03, DEP-04, DEP-05, DEP-06, DEP-07, DEP-08
**Success Criteria** (what must be TRUE):
  1. Given two market question strings, the module returns a classification of subset, related, or independent
  2. Preprocessing normalizes questions to lowercase tokens with stopwords stripped before any signal extraction
  3. All five feature signals (semantic overlap, keyword implication, numeric relation, time relation, event bonus) contribute to the final weighted score
  4. Score thresholds produce correct classifications on a validation set of known market pairs (e.g., "Will X win by 5%?" is subset of "Will X win?")
  5. Module is callable as a pure function with no dependency on scanner state or network I/O
**Plans:** 2 plans
Plans:
- [x] 03-01-PLAN.md — TDD: Preprocessing + 5 signal extractors + DependencyResult dataclass (DEP-01 through DEP-06)
- [x] 03-02-PLAN.md — TDD: Weighted scorer + classifier + validation set (DEP-07, DEP-08)

### Phase 4: Dependency Integration
**Goal**: Dependency detection is wired into the live scanner so cross-market groups are validated for mutual exclusivity before arbitrage detection runs
**Depends on**: Phase 3 (dependency module must exist before integration)
**Requirements**: DEP-09, DEP-10, DEP-11
**Success Criteria** (what must be TRUE):
  1. Pair comparisons are scoped within event groups (not global O(n^2) across all markets)
  2. Audit mode logs which market pairs the dependency filter would reject, without actually rejecting them, so thresholds can be tuned from production data
  3. Cross-market detector consults dependency results and excludes groups containing non-independent (subset/related) market pairs from arbitrage detection
**Plans:** 2 plans
Plans:
- [x] 04-01-PLAN.md — Prerequisites: BotConfig dependency fields, FilterDiagnostics counters, WR-01/WR-02 bug fixes
- [x] 04-02-PLAN.md — Wire dependency gate into cross_market.py with audit/rejection modes and integration tests

### Phase 5: Paper Trading Simulation
**Goal**: Dry-run mode simulates full execution (VWAP, Kelly sizing, fees) on every detected opportunity and persists results so profitability can be measured before going live
**Depends on**: Phase 4 (paper trading must consume validated, dependency-filtered opportunities)
**Requirements**: PAPER-01, PAPER-02, PAPER-03, PAPER-04, PAPER-05
**Success Criteria** (what must be TRUE):
  1. Every detected opportunity in dry-run triggers a simulated VWAP + Kelly sizing calculation using cached prices
  2. Simulated trades are stored in a dedicated paper_trades SQLite table, completely isolated from the live trades table
  3. Each paper-trade record includes simulated size, VWAP price, Kelly allocation, estimated fees, and net P&L
  4. Cross-market paper trades simulate N-leg execution including partial fill and hedge scenarios
  5. User can query total simulated P&L, win rate, average spread captured, and per-category breakdown from the paper_trades table
**Plans**: TBD

---

## Progress

**Execution Order:** Phases execute in numeric order: 2 -> 3 -> 4 -> 5

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Infrastructure Foundation | v1.0 | 4/4 | Complete | 2026-03-28 |
| 2. Market Data & Detection | v1.0 | 6/6 | Complete | 2026-03-28 |
| 3. Execution & Risk Controls | v1.0 | 5/5 | Complete | 2026-03-29 |
| 4. Observability & Monitoring | v1.0 | 4/4 | Complete | 2026-04-15 |
| 5. Fix Token ID Execution Wiring | v1.0 | 2/2 | Complete | 2026-04-18 |
| 6. Wire Critical Telegram Alerts | v1.0 | 1/1 | Complete | 2026-04-18 |
| 7. Formal Verification — Phase 04 & 06 | v1.0 | 1/1 | Complete | 2026-04-18 |
| 8. Fix Circuit Breaker & Alert Accuracy | v1.0 | 2/2 | Complete | 2026-04-18 |
| 1. Fix Cross-Market False Positives & Wiring | v1.1 | 4/4 | Complete | 2026-04-19 |
| 2. Detection Quality Filters | v1.2 | 3/3 | Complete | 2026-04-25 |
| 3. Dependency Detection Core | v1.2 | 2/2 | Complete | 2026-04-25 |
| 4. Dependency Integration | v1.2 | 0/2 | Not started | - |
| 5. Paper Trading Simulation | v1.2 | 0/TBD | Not started | - |
