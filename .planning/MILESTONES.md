# Milestones

## v1.2 Detection Quality & Paper Trading (Shipped: 2026-04-26)

**Phases completed:** 4 phases, 10 plans, 19 tasks

**Key accomplishments:**

- Stateless threshold filters (ask floor, sum cap, dead leg, total YES) + DedupTracker with monotonic clock + FilterDiagnostics dataclass, all TDD with 23 boundary-condition tests
- Wired DETECT-01 through DETECT-05 quality gates into both YES/NO and cross-market detectors with FilterDiagnostics return type, updated all 4 caller sites and 15 test mocks
- DedupTracker wired into dry_run.py and live_run.py scan loops with dedup_suppressed reporting in cycle summary log
- Five pure signal extraction functions (Jaccard, implication, numeric, temporal, event bonus) with TDD coverage using real Polymarket question patterns
- classify_pair() public API with weighted 5-signal scoring and three-way classification, validated against 7 real Polymarket question pairs
- 1. [Rule 1 - Bug] Updated existing test that encoded buggy behavior
- PaperTrade dataclass with 20 fields and simulate_yes_no() using cached VWAP + Kelly sizing + depth-gated fill, persisted to isolated paper_trades SQLite table
- simulate_cross_market() with equal-shares sizing, depth-gated partial fill with hedge, PaperTradeWriter, and full dry_run.py integration
- 4 pure query functions for paper trade analytics, aggregating by paper_arb_id per D-14

---

## v1.1 Cross-Market Fixes (Shipped: 2026-04-19)

**Phases completed:** 1 phase, 4 plans
**Timeline:** 2026-04-18 → 2026-04-19 (1 day)
**Scale:** 22 commits, 116 files, +3,603/-110 lines

**Key accomplishments:**

- Switched VPS from `--live` to dry-run mode via docker-compose.yml override; hardened VPS with UFW + fail2ban after SSH brute-force attack
- Replaced BFS keyword-heuristic cross-market grouping with Gamma API event-level grouping (`conditionId → event_id`) — eliminates false positives from unrelated markets
- Implemented `_execute_cross_market()` with equal-shares sizing (`target_shares = kelly_usd / total_yes`), per-leg FAK BUY orders, and partial-fill hedge (SELL at $0.01)
- Wired `load_event_groups()` into both scanner runners so `_event_groups` is populated before first detection cycle; 109 unit tests passing

**Archive:** `.planning/milestones/v1.1-ROADMAP.md`

---

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
