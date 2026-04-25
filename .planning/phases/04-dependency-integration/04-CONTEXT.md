# Phase 4: Dependency Integration - Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase wires the standalone dependency detection module (`dependency.py`, built in Phase 3) into the live cross-market scanner so that event groups are validated for mutual exclusivity before arbitrage detection runs. It adds pair generation scoped within event groups (DEP-09), audit mode for threshold tuning (DEP-10), and dependency-based group rejection in the cross-market detector (DEP-11). It also promotes weights/thresholds from function parameters to BotConfig fields and fixes two Phase 3 review findings (WR-01, WR-02) that directly impact integration correctness.

</domain>

<decisions>
## Implementation Decisions

### Pair Generation (DEP-09)
- **D-01:** Generate all C(N,2) pairs within each event group using `itertools.combinations(group, 2)`. Groups are capped at `_MAX_GROUP_SIZE = 20` (190 pairs worst case), so O(N^2) within-group is acceptable. No global cross-group comparisons.
- **D-02:** Pair generation happens inside `detect_cross_market_opportunities()` in `cross_market.py`, AFTER price collection and filter gates but BEFORE the exclusivity/spread calculation. This keeps the dependency module pure (Phase 3 D-03) and avoids running dependency checks on groups that would be filtered anyway.
- **D-03:** Each pair passes `question` strings and `event_id` (from `_event_groups` dict) to `classify_pair()`.

### Audit Mode (DEP-10)
- **D-04:** New BotConfig field `dependency_audit_mode: bool = True` — default ON. When audit mode is active, dependency results are logged but groups are NOT rejected. When False, non-independent pairs cause group rejection per DEP-11.
- **D-05:** Audit log format is structured INFO level: `DEP-AUDIT: {label} | score={score:.3f} | jaccard={j:.2f} impl={i:.2f} num={n:.2f} temp={t:.2f} evt={e:.2f} | q1="{q1[:50]}" q2="{q2[:50]}"`. This is parseable for threshold analysis and visible in standard log output.
- **D-06:** When `dependency_audit_mode=False` (rejection active), rejected groups still get a DEBUG-level log with the same signal breakdown for forensics.

### Rejection Behavior (DEP-11)
- **D-07:** If ANY pair within an event group classifies as `subset` or `related`, the ENTIRE group is rejected from cross-market arbitrage detection. Conservative approach — safer for capital, avoids partial group evaluation complexity.
- **D-08:** New diagnostic counter `dep_rejects` added to `FilterDiagnostics` dataclass. Tracks how many groups were rejected (or would have been, in audit mode: `dep_audit_flags`).
- **D-09:** Rejection gate goes AFTER the existing DETECT-03/DETECT-04 filter gates and BEFORE the exclusivity/spread check. This avoids running dependency checks on groups already filtered by simpler gates.

### BotConfig Integration
- **D-10:** Add individual float fields for each dependency weight to `BotConfig`, consistent with `fee_pct_*` pattern:
  - `dep_weight_jaccard: float = 0.20`
  - `dep_weight_implication: float = 0.15`
  - `dep_weight_numeric: float = 0.10`
  - `dep_weight_temporal: float = 0.30`
  - `dep_weight_event_bonus: float = 0.25`
- **D-11:** Add threshold fields:
  - `dep_threshold_subset: float = 0.50`
  - `dep_threshold_related: float = 0.30`
- **D-12:** `cross_market.py` builds `weights` and `thresholds` dicts from BotConfig fields and passes to `classify_pair()`. The dependency module itself remains pure — it accepts dicts, not BotConfig.

### Phase 3 Review Fixes (Prerequisites)
- **D-13:** Fix WR-01 (implication false positives): `_keyword_implication()` must check that exactly ONE question matches the child pattern and the OTHER matches ONLY the parent pattern (not also the child). Prevents false positives on equally-specific question pairs.
- **D-14:** Fix WR-02 (KeyError on partial dicts): `classify_pair()` must merge caller overrides onto defaults (`{**DEFAULT_WEIGHTS, **weights}`) so partial dicts don't crash.

### Claude's Discretion
- Whether to add an early-exit optimization (skip dependency check if group has only 2 markets with identical event_id — they're always related)
- Exact placement of the dependency gate within the existing gate sequence in `detect_cross_market_opportunities()`
- Whether to log a cycle-level summary of dependency audit flags (similar to dedup_suppressed count in dry_run.py)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — DEP-09, DEP-10, DEP-11 define pair generation, audit mode, and detector integration behavior

### Phase 4 Description
- `.planning/ROADMAP.md` — Phase 4 section defines goal, dependencies, success criteria

### Prior Phase Context
- `.planning/phases/03-dependency-detection-core/03-CONTEXT.md` — Phase 3 decisions (module architecture, signal design, interface contract, BotConfig deferral)
- `.planning/phases/02-detection-quality-filters/02-CONTEXT.md` — Phase 2 decisions (filter patterns, BotConfig conventions, diagnostic counter approach)

### Phase 3 Code Review
- `.planning/phases/03-dependency-detection-core/REVIEW.md` — WR-01 (implication false positives) and WR-02 (KeyError on partial dicts) must be fixed as Phase 4 prerequisites

### Existing Detection Code
- `src/bot/detection/dependency.py` — Phase 3 dependency module: `classify_pair()`, `DependencyResult`, `DEFAULT_WEIGHTS`, `DEFAULT_THRESHOLDS`
- `src/bot/detection/cross_market.py` — Cross-market detector: `detect_cross_market_opportunities()`, `_group_by_event()`, `_event_groups` dict, `load_event_groups()`
- `src/bot/detection/filters.py` — `FilterDiagnostics` dataclass (add dep counters here), `DedupTracker`, threshold filter functions
- `src/bot/detection/opportunity.py` — `ArbitrageOpportunity` dataclass

### Configuration
- `src/bot/config.py` — `BotConfig` frozen dataclass: add weight, threshold, and audit_mode fields

### Tests
- `tests/test_dependency.py` — Phase 3 dependency tests (update for WR-01/WR-02 fixes)
- `tests/test_cross_market.py` — Cross-market detector tests (add dependency integration tests)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `classify_pair()` in `dependency.py`: Single public function, accepts question strings + event IDs + optional weight/threshold overrides, returns `DependencyResult` frozen dataclass
- `_event_groups` dict in `cross_market.py`: Already maps `condition_id -> event_id`, populated at startup by `load_event_groups()` — provides `event_id` for `classify_pair()` calls
- `FilterDiagnostics` dataclass in `filters.py`: Existing diagnostic counter pattern — extend with `dep_rejects` and `dep_audit_flags` fields
- `BotConfig` frozen dataclass in `config.py`: 30+ fields following `field_name: type = default` pattern — add 8 new dependency fields

### Established Patterns
- Gate-style sequential filtering in `detect_cross_market_opportunities()`: `if condition: continue` blocks (DETECT-03, DETECT-04, depth, exclusivity, dedup)
- Loguru for all logging (`logger.info`, `logger.debug`)
- Diagnostic counters incremented per rejection, returned alongside opportunities
- BotConfig individual float fields for per-category params (not nested dicts)

### Integration Points
- `detect_cross_market_opportunities()` at line ~200 (after DETECT-04 total_yes gate, before exclusivity check): insert dependency pair generation + classification gate
- `FilterDiagnostics` dataclass: add `dep_rejects: int = 0` and `dep_audit_flags: int = 0` fields
- `BotConfig` dataclass: add 8 new fields (5 weights + 2 thresholds + 1 audit mode bool)
- `_keyword_implication()` in `dependency.py:138-147`: fix WR-01 false positive logic
- `classify_pair()` in `dependency.py:299-302`: fix WR-02 partial dict merge

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- Embedding-based cosine similarity boost (DEP-F01) — future requirement, not v1.2
- Named entity recognition (DEP-F02) — future requirement
- Dependency DAG graph structure (DEP-F03) — future requirement
- Per-pair audit log persistence to SQLite for offline analysis — future enhancement
- WR-03 (invalid calendar dates) and WR-04 from Phase 3 review — lower priority, address in gap closure

</deferred>

---

*Phase: 04-dependency-integration*
*Context gathered: 2026-04-26*
