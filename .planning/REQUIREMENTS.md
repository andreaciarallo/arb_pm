# Requirements: Polymarket Arbitrage Bot

**Defined:** 2026-04-25
**Core Value:** Ultra-low latency detection and execution of cross-market arbitrage opportunities on Polymarket before they disappear.

## v1.2 Requirements

Requirements for milestone v1.2 — Detection Quality & Paper Trading. Each maps to roadmap phases.

### Detection Quality

- [ ] **DETECT-01**: Bot skips YES/NO opportunities where either ask <= $0.03 (dead limit orders)
- [ ] **DETECT-02**: Bot skips YES/NO opportunities where yes_ask + no_ask > $0.99 (near-resolved markets)
- [ ] **DETECT-03**: Bot skips cross-market legs where any leg's ask <= $0.005 (dead cross-market legs)
- [ ] **DETECT-04**: Bot skips cross-market groups where total_yes < $0.10 (degenerate groups with phantom spreads)
- [ ] **DETECT-05**: Bot deduplicates opportunities within a configurable time window (no repeated logging of same opportunity)

### Dependency Detection

- [ ] **DEP-01**: Dependency detector preprocesses market questions (tokenize, normalize, strip stopwords)
- [ ] **DEP-02**: Detector extracts semantic overlap signal (Jaccard similarity on token sets)
- [ ] **DEP-03**: Detector extracts keyword implication signal (subset patterns like "by X%" ⊂ "win")
- [ ] **DEP-04**: Detector extracts numeric relation signal (threshold/range containment)
- [ ] **DEP-05**: Detector extracts time relation signal (date/deadline containment)
- [ ] **DEP-06**: Detector applies event_id bonus for same-event market pairs
- [ ] **DEP-07**: Weighted scorer combines all 5 signals + event bonus into dependency score
- [ ] **DEP-08**: Classifier labels market pairs as subset/related/independent based on score thresholds
- [ ] **DEP-09**: Pair generator scopes comparisons within event groups (not global O(n²))
- [ ] **DEP-10**: Audit mode logs what dependency filters would reject before actually rejecting
- [ ] **DEP-11**: Cross-market detector uses dependency results to validate group exclusivity before arb detection

### Paper Trading

- [ ] **PAPER-01**: Dry-run simulates VWAP + Kelly sizing on each detected opportunity
- [ ] **PAPER-02**: Simulated trades stored in separate paper_trades SQLite table (isolated from live trades table)
- [ ] **PAPER-03**: Paper-trade records include simulated size, VWAP price, Kelly allocation, estimated fees, and net P&L
- [ ] **PAPER-04**: Cross-market paper trades simulate N-leg execution with partial fill and hedge scenarios
- [ ] **PAPER-05**: Summary queries provide total simulated P&L, win rate, avg spread captured, per-category breakdown

## Future Requirements

### Dependency Detection Upgrades

- **DEP-F01**: Embedding-based cosine similarity boost for semantic matching
- **DEP-F02**: Named entity recognition for states, teams, candidates
- **DEP-F03**: Dependency DAG graph structure for transitive relationships
- **DEP-F04**: Feedback loop validation against price inconsistencies

### Paper Trading Upgrades

- **PAPER-F01**: Dashboard panel for paper-trading metrics (real-time P&L chart)
- **PAPER-F02**: Paper-trade vs live-trade comparison analytics

## Out of Scope

| Feature | Reason |
|---------|--------|
| LLM-based mutual exclusivity validation | Latency + cost overhead; weighted scoring covers same ground at zero cost |
| Cross-event dependency detection | Events A and B may be dependent but complexity is too high for v1.2 |
| Live trading activation | v1.2 is detection quality + paper trading only; live trading deferred until paper P&L validated |
| Embedding/NLP models (spaCy, transformers) | 400MB+ Docker image bloat for marginal improvement over stdlib |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DETECT-01 | Phase 2 | Pending |
| DETECT-02 | Phase 2 | Pending |
| DETECT-03 | Phase 2 | Pending |
| DETECT-04 | Phase 2 | Pending |
| DETECT-05 | Phase 2 | Pending |
| DEP-01 | Phase 3 | Pending |
| DEP-02 | Phase 3 | Pending |
| DEP-03 | Phase 3 | Pending |
| DEP-04 | Phase 3 | Pending |
| DEP-05 | Phase 3 | Pending |
| DEP-06 | Phase 3 | Pending |
| DEP-07 | Phase 3 | Pending |
| DEP-08 | Phase 3 | Pending |
| DEP-09 | Phase 4 | Pending |
| DEP-10 | Phase 4 | Pending |
| DEP-11 | Phase 4 | Pending |
| PAPER-01 | Phase 5 | Pending |
| PAPER-02 | Phase 5 | Pending |
| PAPER-03 | Phase 5 | Pending |
| PAPER-04 | Phase 5 | Pending |
| PAPER-05 | Phase 5 | Pending |

**Coverage:**
- v1.2 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0

---
*Requirements defined: 2026-04-25*
*Last updated: 2026-04-25 after roadmap creation*
