# Phase 5: Paper Trading Simulation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-26
**Phase:** 05-paper-trading-simulation
**Areas discussed:** Simulation architecture, Fill probability model, Cross-market partial fill simulation, Summary query interface
**Mode:** --auto (all decisions auto-selected)

---

## Simulation Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in dry_run.py | Hook simulation into existing scan loop after detection, before opportunity write | ✓ |
| Separate paper_run.py | Dedicated paper trading runner module | |
| Post-hoc batch processor | Process opportunities table after scan completes | |

**User's choice:** [auto] Inline in dry_run.py (recommended default)
**Notes:** Reuses existing scan loop, no new async orchestration needed. Paper trade simulation runs synchronously after detection since it uses cached prices only (no API calls). Aligns with STATE.md concern about rate limit exhaustion.

---

## Fill Probability Model

| Option | Description | Selected |
|--------|-------------|----------|
| Depth-gated deterministic | Fill if depth >= kelly_size, partial fill proportional to depth otherwise | ✓ |
| Always-success | Assume 100% fill rate for all legs | |
| Probabilistic | Random fill chance per leg based on depth/size ratio | |

**User's choice:** [auto] Depth-gated deterministic (recommended default)
**Notes:** Most realistic without being stochastic. Deterministic = reproducible results for threshold tuning. Satisfies PAPER-04 requirement for partial fill simulation. Always-success wouldn't model real execution risk. Probabilistic adds complexity without clear benefit at this stage.

---

## Cross-Market Partial Fill Simulation

| Option | Description | Selected |
|--------|-------------|----------|
| Sequential with depth check | Simulate legs in order, hedge on first insufficient depth | ✓ |
| All-or-nothing | Either all legs fill or none do | |
| Independent per-leg | Each leg evaluated independently, no hedge simulation | |

**User's choice:** [auto] Sequential with depth check (recommended default)
**Notes:** Matches live execution behavior (sequential legs with hedge on failure). Satisfies PAPER-04 requirement for N-leg execution with partial fill and hedge scenarios. All-or-nothing doesn't model the partial fill risk. Independent per-leg doesn't simulate the hedge path.

---

## Summary Query Interface

| Option | Description | Selected |
|--------|-------------|----------|
| Python functions in paper_summary.py | Testable functions returning dicts, consumable by CLI and dashboard | ✓ |
| Raw SQL in comments | Document queries as SQL strings for manual execution | |
| Dashboard endpoint only | FastAPI endpoint serving summary metrics | |

**User's choice:** [auto] Python functions in paper_summary.py (recommended default)
**Notes:** Testable, reusable, follows existing storage module patterns. Can be consumed by dashboard (PAPER-F01 future) or CLI. Raw SQL is fragile and untestable. Dashboard-only limits accessibility.

---

## Claude's Discretion

- Per-cycle paper trade summary logging (count, total simulated P&L)
- paper_trades table indexes (optimize for summary query patterns)
- Whether to add a thin CLI entrypoint for summary queries
- Whether paper_trade_enabled toggle is needed in BotConfig

## Deferred Ideas

- Dashboard panel for paper-trading metrics (PAPER-F01)
- Paper-trade vs live-trade comparison analytics (PAPER-F02)
- Stochastic fill probability model
- WebSocket-based real-time paper trade notifications
- Historical backtesting with stored order book snapshots
