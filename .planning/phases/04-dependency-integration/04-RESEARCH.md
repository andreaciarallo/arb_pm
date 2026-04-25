# Phase 4: Dependency Integration - Research

**Researched:** 2026-04-26
**Domain:** Python integration wiring -- connecting standalone dependency module to live cross-market scanner
**Confidence:** HIGH

## Summary

Phase 4 wires the standalone dependency detection module (`dependency.py`, built in Phase 3) into the live cross-market scanner (`cross_market.py`) so that event groups are validated for mutual exclusivity before arbitrage detection runs. The phase adds three capabilities: (1) pair generation scoped within event groups (DEP-09), (2) audit mode for threshold tuning from production logs (DEP-10), and (3) dependency-based group rejection in the cross-market detector (DEP-11). It also promotes weights/thresholds from function parameters to BotConfig fields and fixes two Phase 3 review findings (WR-01, WR-02).

This is a pure integration phase -- no new algorithms, no new dependencies, no new external APIs. All changes are within existing Python modules using established patterns (gate-style filtering, frozen dataclass fields, Loguru structured logging, diagnostic counters). The technical risk is LOW because every integration point is well-understood from the codebase analysis.

**Primary recommendation:** Plan as 3 sequential plans: (1) prerequisite bug fixes (WR-01, WR-02) + BotConfig fields, (2) dependency gate implementation in cross_market.py with audit mode, (3) integration tests covering audit/rejection modes and diagnostic counters.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Generate all C(N,2) pairs within each event group using `itertools.combinations(group, 2)`. Groups are capped at `_MAX_GROUP_SIZE = 20` (190 pairs worst case), so O(N^2) within-group is acceptable. No global cross-group comparisons.
- **D-02:** Pair generation happens inside `detect_cross_market_opportunities()` in `cross_market.py`, AFTER price collection and filter gates but BEFORE the exclusivity/spread calculation. This keeps the dependency module pure (Phase 3 D-03) and avoids running dependency checks on groups that would be filtered anyway.
- **D-03:** Each pair passes `question` strings and `event_id` (from `_event_groups` dict) to `classify_pair()`.
- **D-04:** New BotConfig field `dependency_audit_mode: bool = True` -- default ON. When audit mode is active, dependency results are logged but groups are NOT rejected. When False, non-independent pairs cause group rejection per DEP-11.
- **D-05:** Audit log format is structured INFO level: `DEP-AUDIT: {label} | score={score:.3f} | jaccard={j:.2f} impl={i:.2f} num={n:.2f} temp={t:.2f} evt={e:.2f} | q1="{q1[:50]}" q2="{q2[:50]}"`. This is parseable for threshold analysis and visible in standard log output.
- **D-06:** When `dependency_audit_mode=False` (rejection active), rejected groups still get a DEBUG-level log with the same signal breakdown for forensics.
- **D-07:** If ANY pair within an event group classifies as `subset` or `related`, the ENTIRE group is rejected from cross-market arbitrage detection. Conservative approach.
- **D-08:** New diagnostic counter `dep_rejects` added to `FilterDiagnostics` dataclass. Tracks how many groups were rejected (or would have been, in audit mode: `dep_audit_flags`).
- **D-09:** Rejection gate goes AFTER the existing DETECT-03/DETECT-04 filter gates and BEFORE the exclusivity/spread check.
- **D-10:** Add individual float fields for each dependency weight to `BotConfig`: `dep_weight_jaccard`, `dep_weight_implication`, `dep_weight_numeric`, `dep_weight_temporal`, `dep_weight_event_bonus`.
- **D-11:** Add threshold fields: `dep_threshold_subset: float = 0.50`, `dep_threshold_related: float = 0.30`.
- **D-12:** `cross_market.py` builds `weights` and `thresholds` dicts from BotConfig fields and passes to `classify_pair()`. The dependency module itself remains pure.
- **D-13:** Fix WR-01 (implication false positives): `_keyword_implication()` must check that exactly ONE question matches the child pattern and the OTHER matches ONLY the parent pattern.
- **D-14:** Fix WR-02 (KeyError on partial dicts): `classify_pair()` must merge caller overrides onto defaults (`{**DEFAULT_WEIGHTS, **weights}`).

### Claude's Discretion
- Whether to add an early-exit optimization (skip dependency check if group has only 2 markets with identical event_id -- they're always related)
- Exact placement of the dependency gate within the existing gate sequence in `detect_cross_market_opportunities()`
- Whether to log a cycle-level summary of dependency audit flags (similar to dedup_suppressed count in dry_run.py)

### Deferred Ideas (OUT OF SCOPE)
- Embedding-based cosine similarity boost (DEP-F01) -- future requirement, not v1.2
- Named entity recognition (DEP-F02) -- future requirement
- Dependency DAG graph structure (DEP-F03) -- future requirement
- Per-pair audit log persistence to SQLite for offline analysis -- future enhancement
- WR-03 (invalid calendar dates) and WR-04 from Phase 3 review -- lower priority, address in gap closure
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEP-09 | Pair generator scopes comparisons within event groups (not global O(n^2)) | D-01 locks `itertools.combinations(group, 2)` within each group. `_MAX_GROUP_SIZE = 20` caps worst case at C(20,2) = 190 pairs. Existing `_group_by_event()` already partitions markets by event_id. |
| DEP-10 | Audit mode logs what dependency filters would reject before actually rejecting | D-04 adds `dependency_audit_mode: bool = True` to BotConfig. D-05 specifies exact log format. D-08 adds `dep_audit_flags` counter to `FilterDiagnostics`. |
| DEP-11 | Cross-market detector uses dependency results to validate group exclusivity before arb detection | D-07 specifies ANY non-independent pair rejects entire group. D-09 places gate after DETECT-03/04 and before exclusivity check. D-12 bridges BotConfig to classify_pair() interface. |
</phase_requirements>

## Standard Stack

### Core (No New Dependencies)

This phase requires zero new packages. All work uses existing stdlib and project modules.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `itertools` | 3.10+ | `combinations(group, 2)` for pair generation | Built-in, zero import cost, exact fit for C(N,2) pair enumeration |
| `bot.detection.dependency` | In-repo | `classify_pair()`, `DependencyResult`, `DEFAULT_WEIGHTS`, `DEFAULT_THRESHOLDS` | Phase 3 module -- the sole new import for cross_market.py |
| `loguru` | 0.7+ | Structured audit logging (DEP-10) | Already used across all detection modules |
| `pytest` | 8.x | Test framework | Already configured in `pytest.ini` with `asyncio_mode = auto` |

[VERIFIED: codebase grep -- no new pip packages needed]

### Alternatives Considered

None -- this is a pure integration phase wiring existing modules together. No library choices to make.

## Architecture Patterns

### Recommended Change Map

```
src/bot/detection/dependency.py    # FIX: WR-01 (_keyword_implication), WR-02 (classify_pair merge)
src/bot/detection/filters.py       # ADD: dep_rejects + dep_audit_flags fields to FilterDiagnostics
src/bot/config.py                  # ADD: 8 new BotConfig fields (5 weights + 2 thresholds + 1 audit bool)
src/bot/detection/cross_market.py  # ADD: import dependency, pair gen + classify + gate logic
tests/test_dependency.py           # ADD: WR-01/WR-02 regression tests
tests/test_cross_market.py         # ADD: dependency integration tests (audit mode, rejection mode)
```

### Pattern 1: Gate-Style Filtering (Established)

**What:** Sequential `if condition: continue` blocks in `detect_cross_market_opportunities()` that reject groups early.
**When to use:** The dependency gate follows this exact pattern -- it goes after DETECT-04 (line 199) and before depth/exclusivity checks (line 201).
**Example:**
```python
# Source: existing cross_market.py pattern, lines 183-199
# DETECT-03 dead legs
if has_dead_leg(leg_ask_values, config.min_cross_leg_ask):
    diag.leg_floor_rejects += 1
    continue

# DETECT-04 total_yes floor
if is_total_yes_reject(total_yes, config.min_cross_total_yes):
    diag.total_yes_rejects += 1
    continue

# NEW: Dependency gate (DEP-09/10/11) -- inserted here
# ... pair generation + classify_pair + audit/reject logic ...

# Depth gate (existing)
min_depth = min(depths)
if min_depth < config.min_order_book_depth:
    continue
```
[VERIFIED: cross_market.py lines 183-204]

### Pattern 2: BotConfig Individual Float Fields (Established)

**What:** Each configurable parameter is a separate named field with a default value on the frozen `BotConfig` dataclass. No nested dicts or config objects.
**When to use:** The 8 new dependency fields follow this exactly.
**Example:**
```python
# Source: existing config.py pattern, lines 49-54
fee_pct_crypto: float = 0.018
fee_pct_politics: float = 0.010
fee_pct_sports: float = 0.0075

# NEW fields follow same pattern:
dep_weight_jaccard: float = 0.20
dep_weight_implication: float = 0.15
dep_weight_numeric: float = 0.10
dep_weight_temporal: float = 0.30
dep_weight_event_bonus: float = 0.25
dep_threshold_subset: float = 0.50
dep_threshold_related: float = 0.30
dependency_audit_mode: bool = True
```
[VERIFIED: config.py lines 49-70]

### Pattern 3: FilterDiagnostics Counter Extension (Established)

**What:** Add new `int = 0` fields to the `FilterDiagnostics` dataclass for each new filter gate. Counters are incremented per rejection and returned alongside opportunities.
**When to use:** DEP-08 requires two new counters: `dep_rejects` and `dep_audit_flags`.
**Example:**
```python
# Source: existing filters.py lines 88-95
@dataclass
class FilterDiagnostics:
    ask_floor_rejects: int = 0
    sum_cap_rejects: int = 0
    leg_floor_rejects: int = 0
    total_yes_rejects: int = 0
    dedup_suppressed: int = 0
    # NEW:
    dep_rejects: int = 0       # groups rejected by dependency gate (rejection mode)
    dep_audit_flags: int = 0   # groups that WOULD be rejected (audit mode)
```
[VERIFIED: filters.py lines 88-95]

### Pattern 4: Audit Logging Format (New, D-05 Specified)

**What:** Structured INFO-level log lines with a fixed prefix for downstream parsing.
**When to use:** Every non-independent pair classification in audit mode gets one log line.
**Example:**
```python
# Source: D-05 from CONTEXT.md
logger.info(
    f'DEP-AUDIT: {result.label} | score={result.score:.3f} | '
    f'jaccard={result.jaccard:.2f} impl={result.implication:.2f} '
    f'num={result.numeric:.2f} temp={result.temporal:.2f} '
    f'evt={result.event_bonus:.2f} | '
    f'q1="{q1[:50]}" q2="{q2[:50]}"'
)
```
[VERIFIED: D-05 in 04-CONTEXT.md]

### Anti-Patterns to Avoid

- **Global O(n^2) pair comparison:** Never compare markets across different event groups. The `_group_by_event()` function already partitions by event_id. Pair generation is strictly within-group via `itertools.combinations`.
- **Modifying dependency.py's interface:** The dependency module must remain pure (Phase 3 D-03). It takes strings and optional dicts, returns a dataclass. The integration layer in `cross_market.py` adapts BotConfig to the dependency module's interface -- never the reverse.
- **Running dependency checks on unpriced/filtered groups:** Per D-02, dependency checks run AFTER price collection and DETECT-03/04 gates. This avoids wasting CPU on groups that would be filtered anyway.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pair enumeration | Manual nested loops | `itertools.combinations(group, 2)` | Off-by-one errors, duplicate pairs, harder to read |
| Dict merge with defaults | Manual key-by-key merge | `{**DEFAULT_WEIGHTS, **weights}` | One-liner, standard Python idiom, WR-02 fix |
| Structured logging | Custom log parser | Loguru f-string with fixed prefix `DEP-AUDIT:` | Already standard in codebase, grep-parseable |

**Key insight:** This phase is pure integration glue -- every algorithmic component already exists. The risk is wiring errors, not algorithm bugs.

## Common Pitfalls

### Pitfall 1: Breaking Existing Tests When Adding BotConfig Fields

**What goes wrong:** Adding fields to `BotConfig` (frozen dataclass) causes all test helper functions that construct BotConfig to fail if they use positional arguments or if the new fields don't have defaults.
**Why it happens:** `_make_config()` helpers across test files (test_cross_market.py, test_yes_no_arb.py, etc.) construct BotConfig with only the 6 required secret fields and rely on defaults for everything else.
**How to avoid:** All 8 new fields MUST have default values (they do per D-10/D-11/D-04). Verify by running the full test suite after adding fields -- all 224 existing tests must still pass.
**Warning signs:** `TypeError: __init__() missing required argument` errors across multiple test files.
[VERIFIED: test_cross_market.py line 13-20, config.py frozen dataclass pattern]

### Pitfall 2: Event ID Lookup Mismatch

**What goes wrong:** `classify_pair()` expects `event_id_a` and `event_id_b` as parameters, but `_event_groups` maps `condition_id -> event_id`, and the group iteration variable is a `list[dict]` of market dicts. The question is: how to get the event_id for each market in a pair?
**Why it happens:** Within a group, all markets share the same event_id (that's how they were grouped). But you need to look it up from `_event_groups` using each market's `condition_id`.
**How to avoid:** Since all markets in a group share the same event_id (by definition of `_group_by_event()`), look up the event_id once per group: `event_id = _event_groups.get(group[0].get("condition_id", ""))`. Pass the same `event_id` as both `event_id_a` and `event_id_b` to `classify_pair()`. This is correct because within-group pairs always share the same event.
**Warning signs:** `event_bonus` signal always returns `0.0` when it should return `1.0` for same-group pairs.
[VERIFIED: cross_market.py _group_by_event() groups by shared event_id]

### Pitfall 3: Dependency Gate Placement Relative to Dedup

**What goes wrong:** If the dependency gate runs AFTER the dedup check (DETECT-05), a group could be dedup-suppressed on cycle 1 (when it would have been flagged by dependency), then on cycle 2 (after dedup expires) it passes through without dependency checking because the dedup window cleared.
**Why it happens:** Dedup is currently the LAST gate before `opportunities.append()`. If dependency runs after dedup, some groups skip dependency entirely.
**How to avoid:** Per D-09, the dependency gate goes AFTER DETECT-03/04 but BEFORE exclusivity/dedup. This ensures every group that passes the cheap gates also gets dependency-checked. The current code structure at lines 199-204 (after DETECT-04, before depth gate) is the correct insertion point.
**Warning signs:** `dep_audit_flags` count is suspiciously low compared to expected non-independent pairs.
[VERIFIED: cross_market.py lines 199-260 gate ordering]

### Pitfall 4: Audit Mode Counter Semantics

**What goes wrong:** Ambiguity about whether `dep_audit_flags` counts pairs or groups. D-08 says "Tracks how many groups were rejected," but in audit mode, multiple pairs might flag within the same group.
**Why it happens:** A group with 5 markets has C(5,2)=10 pairs. If 3 pairs are non-independent, is `dep_audit_flags` incremented by 3 (pairs) or 1 (group)?
**How to avoid:** Increment `dep_audit_flags` once per GROUP (not per pair) -- consistent with `dep_rejects` which counts groups. The individual pair classifications are logged via DEP-AUDIT lines. The counter tracks group-level impact.
**Warning signs:** Counter value seems inflated compared to the number of groups processed.

### Pitfall 5: `question` Field Access on Market Dicts

**What goes wrong:** Market dict `question` field might be empty string or missing for some markets, causing `classify_pair()` to process empty strings.
**Why it happens:** Not all market dicts from the CLOB API have populated `question` fields (though Gamma API markets usually do).
**How to avoid:** Use `market.get("question", "")` consistently (already the pattern in cross_market.py line 228). `classify_pair()` handles empty strings gracefully -- `_preprocess("")` returns `frozenset()`, Jaccard returns `0.0`, regex extractors return `None`/`0.0`.
**Warning signs:** `classify_pair` called with two empty strings returns `independent` -- technically correct but wastes CPU.
[VERIFIED: dependency.py _preprocess("") returns frozenset(), all signals handle empty gracefully]

## Code Examples

### WR-01 Fix: Implication False Positive Prevention

```python
# Source: REVIEW.md WR-01 fix recommendation, verified against dependency.py lines 138-147
def _keyword_implication(question_a: str, question_b: str) -> float:
    """Pattern matching for subset relationships on original question strings."""
    for child_pat, parent_pat in _IMPLICATION_RULES:
        a_child = bool(child_pat.search(question_a))
        b_child = bool(child_pat.search(question_b))
        a_parent = bool(parent_pat.search(question_a))
        b_parent = bool(parent_pat.search(question_b))
        # One must be specific (child) and the other general (parent-only)
        if a_child and b_parent and not b_child:
            return 1.0
        if b_child and a_parent and not a_child:
            return 1.0
    return 0.0
```

### WR-02 Fix: Partial Dict Merge

```python
# Source: REVIEW.md WR-02 fix recommendation, verified against dependency.py lines 299-302
if weights is None:
    weights = DEFAULT_WEIGHTS
else:
    weights = {**DEFAULT_WEIGHTS, **weights}
if thresholds is None:
    thresholds = DEFAULT_THRESHOLDS
else:
    thresholds = {**DEFAULT_THRESHOLDS, **thresholds}
```

### Dependency Gate Integration in cross_market.py

```python
# Source: D-01, D-02, D-03, D-07, D-09, D-12 from CONTEXT.md
# Inserted after DETECT-04 gate (line 199), before depth gate (line 201)
import itertools
from bot.detection.dependency import classify_pair

# Build weight/threshold dicts from BotConfig (D-12)
dep_weights = {
    "jaccard": config.dep_weight_jaccard,
    "implication": config.dep_weight_implication,
    "numeric": config.dep_weight_numeric,
    "temporal": config.dep_weight_temporal,
    "event_bonus": config.dep_weight_event_bonus,
}
dep_thresholds = {
    "subset": config.dep_threshold_subset,
    "related": config.dep_threshold_related,
}

# Inside the group loop, after DETECT-04 gate:
# DEP-09: Generate pairs within event group
event_id = _event_groups.get(group[0].get("condition_id", ""))
group_flagged = False
for m_a, m_b in itertools.combinations(group, 2):
    result = classify_pair(
        m_a.get("question", ""),
        m_b.get("question", ""),
        event_id_a=event_id,
        event_id_b=event_id,
        weights=dep_weights,
        thresholds=dep_thresholds,
    )
    if result.label != "independent":
        # DEP-10: Audit logging
        if config.dependency_audit_mode:
            logger.info(
                f'DEP-AUDIT: {result.label} | score={result.score:.3f} | '
                f'jaccard={result.jaccard:.2f} impl={result.implication:.2f} '
                f'num={result.numeric:.2f} temp={result.temporal:.2f} '
                f'evt={result.event_bonus:.2f} | '
                f'q1="{m_a.get("question", "")[:50]}" '
                f'q2="{m_b.get("question", "")[:50]}"'
            )
        else:
            logger.debug(
                f'DEP-REJECT: {result.label} | score={result.score:.3f} | '
                f'jaccard={result.jaccard:.2f} impl={result.implication:.2f} '
                f'num={result.numeric:.2f} temp={result.temporal:.2f} '
                f'evt={result.event_bonus:.2f} | '
                f'q1="{m_a.get("question", "")[:50]}" '
                f'q2="{m_b.get("question", "")[:50]}"'
            )
        group_flagged = True
        break  # One non-independent pair is enough to flag/reject the group (D-07)

# DEP-11: Reject or audit-flag the group
if group_flagged:
    if config.dependency_audit_mode:
        diag.dep_audit_flags += 1
        # Audit mode: DON'T continue -- let group proceed through remaining gates
    else:
        diag.dep_rejects += 1
        continue  # Rejection mode: skip this group entirely
```

### Dry-run Cycle Summary Integration

```python
# Source: dry_run.py line 121-128 pattern for cycle summary logging
# Add dep diagnostics to cycle summary:
logger.info(
    f"Cycle {cycle + 1} | "
    f"{len(yes_no_opps)} YES/NO + {len(cross_opps)} cross-market opps | "
    f"dep_flags={cm_diag.dep_audit_flags} dep_rejects={cm_diag.dep_rejects} | "
    f"dedup_suppressed={yn_diag.dedup_suppressed + cm_diag.dedup_suppressed} | "
    f"cycle={cycle_duration:.2f}s"
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| BFS keyword heuristic for market grouping | Gamma API event-level grouping | v1.1 (2026-04-19) | Catches all mutually exclusive groups, not just overlapping text |
| No mutual exclusivity validation | Weighted 5-signal dependency classifier | v1.2 Phase 3 (2026-04-25) | Distinguishes subset/related/independent market pairs |
| Global O(n^2) market comparison | Event-scoped pair generation | v1.2 Phase 4 (this phase) | C(20,2)=190 worst case per group instead of C(44000,2) globally |

## Assumptions Log

> All claims in this research were verified from codebase analysis. No external assumptions needed.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| -- | (none) | -- | -- |

**All claims were verified directly from codebase source files -- no user confirmation needed.**

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x with pytest-asyncio |
| Config file | `pytest.ini` |
| Quick run command | `python -m pytest tests/test_dependency.py tests/test_cross_market.py -x -q` |
| Full suite command | `python -m pytest -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEP-09 | Pair generation scoped within event groups | unit | `pytest tests/test_cross_market.py::test_dependency_pairs_within_group -x` | Wave 0 |
| DEP-10 | Audit mode logs dependency flags without rejecting | unit | `pytest tests/test_cross_market.py::test_audit_mode_logs_not_rejects -x` | Wave 0 |
| DEP-11 | Non-independent pairs cause group rejection | unit | `pytest tests/test_cross_market.py::test_dependency_rejects_non_independent_group -x` | Wave 0 |
| WR-01 | Implication no false positive on equally-specific pairs | unit | `pytest tests/test_dependency.py::test_implication_no_false_positive_equal_specificity -x` | Wave 0 |
| WR-02 | Partial weight/threshold dicts don't crash | unit | `pytest tests/test_dependency.py::test_classify_partial_weights_no_crash -x` | Wave 0 |
| D-08 | FilterDiagnostics has dep_rejects and dep_audit_flags | unit | `pytest tests/test_cross_market.py::test_diagnostics_dep_counters -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_dependency.py tests/test_cross_market.py -x -q`
- **Per wave merge:** `python -m pytest -x -q` (full 224+ test suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_dependency.py` -- add WR-01 regression test (equally-specific questions), WR-02 regression test (partial dicts)
- [ ] `tests/test_cross_market.py` -- add dependency integration tests (audit mode, rejection mode, diagnostic counters, pair generation scoping)

## Security Domain

> This phase has minimal security surface -- it modifies detection logic only, no auth, no I/O, no user input, no crypto.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | -- |
| V3 Session Management | no | -- |
| V4 Access Control | no | -- |
| V5 Input Validation | no | Market question strings come from Gamma API (trusted source), not user input |
| V6 Cryptography | no | -- |

### Known Threat Patterns

None applicable -- this phase operates entirely on in-memory data structures with no external I/O, no eval/exec, no deserialization of untrusted data.

## Sources

### Primary (HIGH confidence)
- `src/bot/detection/dependency.py` -- Phase 3 module: classify_pair() interface, DependencyResult, DEFAULT_WEIGHTS/THRESHOLDS
- `src/bot/detection/cross_market.py` -- Detection loop structure, gate ordering, _event_groups dict, _group_by_event()
- `src/bot/detection/filters.py` -- FilterDiagnostics dataclass pattern, counter naming convention
- `src/bot/config.py` -- BotConfig frozen dataclass, field naming convention (dep_ prefix follows fee_pct_ pattern)
- `.planning/phases/04-dependency-integration/04-CONTEXT.md` -- All 14 locked decisions (D-01 through D-14)
- `.planning/phases/03-dependency-detection-core/REVIEW.md` -- WR-01 and WR-02 exact fix recommendations
- `tests/test_dependency.py` -- 40 existing tests, all passing
- `tests/test_cross_market.py` -- 11 existing tests, all passing
- `src/bot/dry_run.py` -- Scanner lifecycle, cycle summary logging pattern

### Secondary (MEDIUM confidence)
- None needed -- all research sourced from codebase

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing modules
- Architecture: HIGH -- all patterns directly observed in codebase, every integration point read and verified
- Pitfalls: HIGH -- identified from actual code analysis, not hypothetical scenarios

**Research date:** 2026-04-26
**Valid until:** 2026-05-26 (stable -- no external dependency changes expected)
