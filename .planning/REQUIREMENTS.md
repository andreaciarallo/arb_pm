# Requirements: Polymarket Arbitrage Bot

**Defined:** 2026-04-26
**Core Value:** Ultra-low latency detection and execution of cross-market arbitrage opportunities on Polymarket before they disappear.

## v2.0 Requirements

Requirements for Basket Arbitrage Engine milestone. Each maps to roadmap phases.

### Group Validation

- [ ] **GV-01**: Bot validates event groups using NegRisk boolean as primary partition signal (NegRisk=true auto-passes as one-of-N)
- [ ] **GV-02**: Bot detects duplicate markets within event groups via Jaccard similarity (>0.9 threshold) on preprocessed question tokens
- [ ] **GV-03**: Bot detects subset/implication relations within event groups using keyword implication and temporal signals
- [ ] **GV-04**: Bot applies completeness heuristic (0.7 <= sum(mid_prices) <= 1.3) to non-NegRisk groups
- [ ] **GV-05**: Bot caches event metadata (market count per event) from Gamma API at startup for partition verification

### Basket Pricing

- [ ] **BP-01**: Bot computes per-leg VWAP cost using full order book depth (not just best ask)
- [ ] **BP-02**: Bot fetches order books for all basket legs in one call via batch `get_order_books()`
- [ ] **BP-03**: Bot resolves VWAP/size circular dependency via iterative fixed-point convergence (3 iterations)
- [ ] **BP-04**: Bot stores multi-level ask data (top N levels) from WebSocket in PriceCache for VWAP computation

### Liquidity & Profitability

- [ ] **LP-01**: Bot rejects basket legs with insufficient depth at target size (configurable min depth per leg)
- [ ] **LP-02**: Bot rejects baskets where any leg has bid-ask spread exceeding configurable threshold
- [ ] **LP-03**: Bot computes fee-adjusted net edge (payout - total VWAP cost - fees - slippage buffer) and rejects below threshold
- [ ] **LP-04**: Bot computes common-size as max shares fillable across all legs simultaneously

### Execution

- [ ] **EX-01**: Bot submits all basket legs via batch `post_orders()` endpoint (up to 15 FAK orders per request)
- [ ] **EX-02**: Bot signs orders sequentially (avoid nonce collision) then submits batch
- [ ] **EX-03**: Bot detects partial basket failures from batch results and initiates graduated unwind
- [ ] **EX-04**: Bot unwinds failed baskets at market price (not fire-sale $0.01 hedge)

### Pipeline Integration

- [ ] **PI-01**: Bot removes YES/NO arb detection from scan loop (cross-market basket arb only)
- [ ] **PI-02**: Bot wires new validation -> pricing -> execution pipeline into dry_run.py and live_run.py
- [ ] **PI-03**: Bot updates paper trading simulation to use basket VWAP pricing and common-size

## Future Requirements

### Cross-Event Arbitrage

- **CE-01**: Bot discovers arbitrage across different Gamma events (not grouped by event_id)
- **CE-02**: Bot uses dependency detector to identify cross-event mutual exclusivity
- **CE-03**: Bot constructs mini-baskets from cross-event pairs

### Advanced Execution

- **AE-01**: Bot performs abort-early evaluation (check if partial basket is still profitable mid-execution)
- **AE-02**: Bot caches multi-level order book data from WebSocket for sub-millisecond VWAP updates

## Out of Scope

| Feature | Reason |
|---------|--------|
| YES/NO arbitrage | Market is efficient (0 detected in dry-run); removing to focus on cross-market |
| AI/ML group validation | NegRisk boolean + heuristics sufficient; ML adds complexity without proportional value |
| Cross-event arbitrage | Requires advanced NLP/LLM for mutual exclusivity; deferred to future milestone |
| Multi-wallet execution | Not needed for <$1k capital |
| Market making mode | Requires $3k+ capital |
| Atomic multi-leg execution | Polymarket API does not support atomic batch orders |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| GV-01 | Phase 6 | Pending |
| GV-02 | Phase 6 | Pending |
| GV-03 | Phase 6 | Pending |
| GV-04 | Phase 6 | Pending |
| GV-05 | Phase 6 | Pending |
| BP-01 | Phase 7 | Pending |
| BP-02 | Phase 7 | Pending |
| BP-03 | Phase 7 | Pending |
| BP-04 | Phase 7 | Pending |
| LP-01 | Phase 7 | Pending |
| LP-02 | Phase 7 | Pending |
| LP-03 | Phase 7 | Pending |
| LP-04 | Phase 7 | Pending |
| EX-01 | Phase 8 | Pending |
| EX-02 | Phase 8 | Pending |
| EX-03 | Phase 8 | Pending |
| EX-04 | Phase 8 | Pending |
| PI-01 | Phase 9 | Pending |
| PI-02 | Phase 9 | Pending |
| PI-03 | Phase 9 | Pending |

**Coverage:**
- v2.0 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0

---
*Requirements defined: 2026-04-26*
*Last updated: 2026-04-26 after roadmap creation (traceability populated)*
