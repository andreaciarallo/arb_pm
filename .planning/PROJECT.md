# Polymarket Arbitrage Bot

## What This Is

A fully automated arbitrage trading bot live on Polymarket prediction markets. The bot runs continuously on a Hetzner VPS (Helsinki, FI), scans 44k+ markets in real time via WebSocket + HTTP polling fallback, detects YES/NO and cross-market mispricing, and executes FAK orders automatically with Modified Kelly position sizing, circuit breakers, and Telegram alerting.

## Core Value

Ultra-low latency detection and execution of cross-market arbitrage opportunities on Polymarket before they disappear.

## Requirements

### Validated

- ✓ Deploy bot to low-latency VPS for continuous Polymarket access — v1.0 (Hetzner HEL1, <35ms median CLOB latency)
- ✓ Configure Docker containerization for reproducible deployment — v1.0
- ✓ Implement secure API key management (runtime injection, no withdrawal permissions) — v1.0
- ✓ Integrate non-custodial EOA wallet for Polymarket CLOB signing — v1.0 (USDC.e, MAX_UINT256 allowances)
- ✓ Implement WebSocket subscription for real-time market data (primary) — v1.0
- ✓ Implement HTTP polling fallback when WebSocket data is stale — v1.0
- ✓ Normalize market data to unified price format with timestamp alignment — v1.0
- ✓ Detect YES+NO cross-market mispricing opportunities — v1.0
- ✓ Calculate fee-adjusted profitability before scoring opportunities — v1.0
- ✓ Implement dry-run/simulation mode — v1.0
- ✓ Execute arbitrage trades automatically via CLOB API — v1.0 (FAK orders, token ID wiring complete)
- ✓ Use FAK orders via create_order() + post_order(OrderType.FAK) — v1.0
- ✓ Handle partial fills and one-leg execution risk (retry-then-hedge) — v1.0
- ✓ Verify every order via REST API after fill — v1.0
- ✓ Enforce maximum capital limit per trade (Modified Kelly, 5% ceiling) — v1.0
- ✓ Implement daily stop-loss (5% daily loss limit) — v1.0
- ✓ Implement circuit breaker on high error rates (CB trips + notifies CB) — v1.0 (NO-leg wiring fixed in Phase 8)
- ✓ Implement emergency kill switch for immediate position closure — v1.0
- ✓ Log all trades to SQLite database (PnL, execution costs, capital efficiency) — v1.0
- ✓ Send instant alerts via Telegram for trade executions, kill switch, and CB trips — v1.0 (live count accuracy fixed in Phase 8)
- ✓ Provide local FastAPI dashboard with live metrics (port 8080) — v1.0
- ✓ Track per-arb analytics: entry/exit prices, hold time, net profit after fees — v1.0
- ✓ Filter dead/near-resolved markets with ask price floor and sum cap — v1.2 (filters.py: DETECT-01 through DETECT-04)
- ✓ Deduplicate repeated opportunities within configurable time window — v1.2 (DedupTracker: DETECT-05)
- ✓ Multi-stage dependency detection pipeline (Jaccard, implication, numeric, temporal, event bonus) — v1.2 (dependency.py: DEP-01 through DEP-08)
- ✓ Wire dependency classifier into cross-market detector with audit/rejection modes — v1.2 (DEP-09 through DEP-11)
- ✓ Simulate VWAP + Kelly sizing on detected opportunities in dry-run mode — v1.2 (PAPER-01 through PAPER-03)
- ✓ Cross-market paper trades with N-leg execution, partial fill, and hedge scenarios — v1.2 (PAPER-04)
- ✓ Summary queries for total P&L, win rate, avg spread, per-category breakdown — v1.2 (PAPER-05)

### Active

#### Current Milestone: v2.0 Basket Arbitrage Engine

**Goal:** Replace pairwise dependency detection with group-level structure validation and VWAP-based basket pricing for executable cross-market arbitrage.

**Target features:**
- Group structure validation (one-of-N partition check replaces pairwise dependency rejection)
- VWAP-based basket construction (executable cost per leg, not quoted ask sum)
- Common-size trade sizing (max fillable depth across all legs before trade decision)
- Liquidity-driven filtering (replace dead-leg price heuristics with depth/spread/stale checks)
- Profitability gate with fees + slippage buffer
- Execution improvements (parallel/batched legs, abort-early instead of fire-sale hedge)
- YES/NO arb removed — cross-market basket arb only

### Out of Scope

- Multi-exchange arbitrage — Polymarket-only focus for v1
- AI/ML opportunity filtering — adds complexity; basic detection works first
- Multi-wallet support — not needed for <$1k capital
- Market making mode — requires $3k+ capital
- REST API for external access — nice-to-have, not core
- Serverless deployment — VPS deployment only

## Context

**Status:** v2.0 Phase 6 complete (2026-04-26). Group structure validation shipped — NegRisk auto-pass, partition validation (duplicate/subset/completeness), EventInfo enrichment. Rewriting cross-market arbitrage pipeline from pairwise dependency detection to group-level basket pricing. Bot is in dry-run mode on HEL1 with paper trading active from v1.2.

**VPS:** Hetzner CPX31, Helsinki FI (204.168.164.145). UFW + fail2ban active after SSH brute-force attack detected 2026-04-19.

**Wallet:** `0x0036F15972166642fCb242F11fa5D1b6AD58Bc70`. Collateral: USDC.e (`0x2791...`). Balance: ~5.88 USDC.e, ~25 MATIC.

**Codebase:** ~5,000 LOC Python (src), ~4,800 LOC tests. ~260 commits. 239 unit tests passing (5 skipped).

**Tech stack:** Python 3.12, py-clob-client 0.34.6, httpx, websockets, loguru, FastAPI, SQLite, python-telegram-bot, Docker.

**Known issues / technical debt:**
- YES/NO arb threshold 1.5% — market is efficient, 0 detected in dry-run; strategy may need tuning
- WebSocket subscription capped at ~2000 token IDs (server silently drops beyond that)
- Cross-market execution live path not yet validated in production (dry-run only)
- ~~Detection logs ~93% false positives from near-resolved markets ($0.001 asks) — no min ask floor~~ Fixed in Phase 2 (filters.py: ask floor, sum cap, dead leg, total_yes, dedup)
- ~~No paper-trading P&L — dry-run logs detection only, never simulates execution~~ Fixed in Phase 5 (paper trading: VWAP+Kelly simulation inline in dry_run.py, paper_trades table, summary queries)
- ~~Cross-market dependency detection is flat (event grouping only) — no heuristic/logical filtering~~ Fixed in Phase 4 (dependency.py: 5-signal weighted scorer + classify_pair wired into cross_market.py with audit/rejection modes)

## Constraints

- **Tech stack:** Must integrate with Polymarket's official API
- **Latency:** Ultra-low latency execution required for strategy effectiveness
- **Capital:** Under $1k total capital at risk
- **Deployment:** Must run continuously on cloud VPS

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Official Polymarket API (py-clob-client) | Simpler integration, documented interface | ✓ Good — SDK handled auth, order types, WebSocket |
| Efficient scanning over brute-force | Full market scan may be inefficient | ✓ Good — WS subscription + HTTP rotation works |
| Modified Kelly sizing (√p denominator) | Execution-probability-adjusted Kelly | ✓ Good — conservative sizing enforced |
| FAK orders via create_order+post_order | GTC-only create_and_post_order excluded | ✓ Good — FAK fires and forgets correctly |
| Hetzner HEL1 (Helsinki) VPS | Ashburn VA was geo-blocked | ✓ Good — <35ms, not blocked |
| USDC.e collateral (not native USDC) | Polymarket uses bridged USDC | ✓ Critical — native USDC causes silent failures |
| hasattr guard for record_order_error | Defensive call at both YES-verify and NO-exhaust | ✓ Good — consistent pattern, test-mockable |
| `_last_trip_count` captured before clear() | CB alert must show live count, not static threshold | ✓ Good — order matters, before .clear() |
| PATH B (Gamma API) for cross-market grouping | CLOB market objects have no `event_id` field; Gamma `conditionId` = CLOB `condition_id` | ✓ Good — correct, covers all event types |
| Equal shares not equal dollars (cross-market) | `target_shares = kelly_usd / total_yes` — same payout regardless of winner | ✓ Good — correct arb sizing math |
| `load_event_groups()` called once at startup | Not in hot detection path — module-level cache dict populated before first cycle | ✓ Good — zero latency impact on scan loop |
| Partial hedge at price=0.01 | Sell ALL filled legs immediately on any leg failure — aggressive but recovers capital | ✓ Good — prevents stranded positions |
| Stateless threshold filters (no state across cycles) | Simpler, testable, no false-negative risk from stale state | ✓ Good — 5 filters cover 93% false positive elimination |
| DedupTracker with monotonic clock | Prevents repeated logging of same opportunity within configurable window | ✓ Good — time.monotonic avoids clock skew issues |
| 5-signal weighted dependency scorer (stdlib only) | No ML/NLP deps; Jaccard + implication + numeric + temporal + event bonus | ✓ Good — zero Docker image bloat, covers real Polymarket patterns |
| Audit mode before rejection mode | Log what dependency filters would reject before actually rejecting | ✓ Good — validated scorer accuracy before enabling rejection |
| Paper trade aggregation by paper_arb_id | Win/loss determined per arb (sum of legs), not individual legs | ✓ Good — matches real trading P&L semantics |
| PaperTradeWriter as clean copy (not subclass) | Avoid coupling paper trading lifecycle to live AsyncWriter | ✓ Good — independent shutdown, independent schema |

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*Last updated: 2026-04-26 after Phase 6 complete (Group Structure Validation — NegRisk auto-pass, partition validation, EventInfo enrichment)*
