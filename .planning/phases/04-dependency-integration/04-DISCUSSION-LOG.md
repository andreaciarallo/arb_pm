# Phase 4: Dependency Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-26
**Phase:** 04-dependency-integration
**Mode:** --auto (all decisions auto-selected)
**Areas discussed:** Pair Generation, Audit Mode, Rejection Behavior, BotConfig Integration, Phase 3 Review Fixes

---

## Pair Generation (DEP-09)

| Option | Description | Selected |
|--------|-------------|----------|
| All combinations (itertools.combinations) | Covers every pair within group, O(N^2) but N<=20 so max 190 pairs | ✓ |
| Adjacent pairs only | Faster but misses non-adjacent dependencies | |

**User's choice:** [auto] All combinations (recommended — groups capped at 20 markets)
**Notes:** Pair generation scoped within event groups, not global. Groups already filtered by DETECT-03/04 before dependency check.

---

## Audit Mode (DEP-10)

| Option | Description | Selected |
|--------|-------------|----------|
| BotConfig flag `dependency_audit_mode: bool = True` | Default ON, log-only no rejection, graduated to rejection later | ✓ |
| Environment variable toggle | Separate from BotConfig, requires restart | |
| Always audit, separate rejection flag | Two flags adds complexity | |

**User's choice:** [auto] BotConfig flag (recommended — consistent with existing config pattern)

| Option | Description | Selected |
|--------|-------------|----------|
| Structured INFO with signal breakdown | Parseable, shows which signals triggered, visible in standard logs | ✓ |
| DEBUG level only | Hidden by default, harder to analyze | |

**User's choice:** [auto] Structured INFO (recommended — needed for threshold tuning from production data)

---

## Rejection Behavior (DEP-11)

| Option | Description | Selected |
|--------|-------------|----------|
| Reject entire group | If ANY pair is subset/related, skip entire group — conservative | ✓ |
| Exclude specific market | Remove non-independent market, evaluate remaining — complex | |

**User's choice:** [auto] Reject entire group (recommended — capital safety, simpler implementation)

---

## BotConfig Integration

| Option | Description | Selected |
|--------|-------------|----------|
| Individual float fields per weight | `dep_weight_jaccard: float = 0.20` etc., consistent with fee_pct_* | ✓ |
| Dict fields | `dep_weights: dict = {...}` — less verbose but inconsistent | |

**User's choice:** [auto] Individual float fields (recommended — matches established BotConfig pattern)

---

## Phase 3 Review Fixes

| Option | Description | Selected |
|--------|-------------|----------|
| Fix WR-01 and WR-02 as prerequisites | Implication false positives and KeyError affect integration correctness | ✓ |
| Defer to gap closure | Fix later, work around in Phase 4 | |

**User's choice:** [auto] Fix as prerequisites (recommended — WR-01 causes false positives, WR-02 crashes with partial overrides)

---

## Claude's Discretion

- Early-exit optimization for 2-market same-event groups
- Exact gate placement within detection function
- Cycle-level summary of dependency audit flags

## Deferred Ideas

- Embedding-based similarity (DEP-F01) — future requirement
- Named entity recognition (DEP-F02) — future requirement
- Dependency DAG (DEP-F03) — future requirement
- SQLite audit log persistence — future enhancement
- WR-03/WR-04 fixes — lower priority gap closure
