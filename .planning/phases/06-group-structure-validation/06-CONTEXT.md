# Phase 6: Group Structure Validation - Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate event groups as true one-of-N partitions suitable for basket arbitrage. NegRisk groups auto-pass; non-NegRisk groups are checked for structural violations (duplicates, subsets, overlaps) and completeness. This phase does NOT price baskets or execute trades — it produces a validated set of event IDs that downstream phases consume.

</domain>

<decisions>
## Implementation Decisions

### Validation Architecture
- **D-01:** Create new standalone module `src/bot/detection/group_validator.py`. Group validation is its own concern, separate from detection and fee logic in `cross_market.py`.
- **D-02:** Validation runs ONCE at startup (alongside `load_event_groups()`). Pre-compute a `set[str]` of valid event IDs. Detection loop checks membership — zero latency impact on hot path.
- **D-03:** Remove the existing inline pairwise dependency gate in `cross_market.py` (lines 218-257). It becomes redundant once `group_validator.py` runs at startup. Simplifies the detection hot path.

### NegRisk Data Flow
- **D-04:** Enrich `_event_groups` from `dict[str, str]` (condition_id → event_id) to `dict[str, EventInfo]` where `EventInfo` is a dataclass holding `event_id`, `neg_risk` (bool), and `market_count` (int). Single dict lookup serves both validator and detector.
- **D-05:** `EventInfo` dataclass and enriched dict stay in `cross_market.py` where `load_event_groups()` already lives. `group_validator.py` imports them.

### Partition Validation Logic (CRITICAL REFRAME)
- **D-06:** Group validation is **partition structure validation**, NOT dependency rejection. In a valid one-of-N group, all pairs ARE mutually exclusive (dependent) — that's expected structure. The validator detects **structural violations** that break the partition:
  - **Subset** (A implies B, e.g., "Trump wins" vs "Trump wins by >5%") → breaks partition → REJECT
  - **Duplicate** (A ≈ B, Jaccard > 0.9, e.g., "Biden wins" vs "Joe Biden wins") → double counting → REJECT
  - **Overlap** (A and B can both be true, e.g., "Trump wins PA" vs "Republicans win PA Senate") → not exclusive → REJECT
- **D-07:** Write fresh, purpose-built validation functions in `group_validator.py`: `is_subset_pair()`, `is_duplicate_pair()`, `is_overlapping_pair()`. Do NOT reuse `classify_pair()` from `dependency.py` — its "subset / related / independent" labels encode the wrong mental model (dependency detection vs partition validation). May reuse low-level utilities like `_preprocess()` if helpful, but classification logic must be partition-aware from the start.

### Rejection Diagnostics
- **D-08:** Structured per-violation logging. Each structural violation gets its own log line with violation type (subset/duplicate/overlap), the two offending market questions, and signal scores. Pattern: `GV-REJECT: {type} | q1="{...}" q2="{...}" | score={...}`. Matches existing `DEP-AUDIT` log pattern.
- **D-09:** `validate_groups()` returns `set[str]` of valid event IDs. Rejections are logged only. Detection loop checks `if event_id in valid_set`. Simple interface, no structured report needed yet.

### Claude's Discretion
- **D-10:** NegRisk auto-pass logging level and format. Recommendation: debug-level aggregate count at startup ("GV: N NegRisk groups auto-validated, M non-NegRisk queued for validation"), no per-group log for NegRisk passes.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Polymarket API
- `src/bot/detection/cross_market.py` — Current event grouping, `load_event_groups()`, `_group_by_event()`, detection loop with inline dependency gate to be removed
- `src/bot/detection/dependency.py` — Existing 5-signal weighted scorer; reference for signal patterns but NOT to be reused for partition validation (D-07)
- `src/bot/detection/opportunity.py` — `ArbitrageOpportunity` dataclass consumed by downstream phases
- `src/bot/detection/filters.py` — Existing filter patterns (`has_dead_leg`, `is_total_yes_reject`, `DedupTracker`)
- `src/bot/config.py` — `BotConfig` with dependency weights/thresholds (some may need extension for GV thresholds)

### Requirements
- `.planning/REQUIREMENTS.md` §Group Validation — GV-01 through GV-05 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `load_event_groups()` in `cross_market.py:54` — Gamma API pagination logic; will be extended to capture `negRisk` and `market_count` per event
- `_group_by_event()` in `cross_market.py:95` — Groups markets by event_id with size filtering [2, 20]; validator will consume the same grouped structure
- `_preprocess()` in `dependency.py:115` — Tokenize + stopword removal; may be useful for duplicate/subset detection in group_validator.py
- `_jaccard_similarity()` in `dependency.py:125` — Low-level Jaccard computation; could be imported as a utility for GV-02 duplicate detection
- `FilterDiagnostics` in `filters.py` — Pattern for tracking rejection counts; group_validator.py can follow same pattern

### Established Patterns
- Module-level cache dict populated once at startup (`_event_groups` pattern) — validator will follow same pattern with `_valid_groups: set[str]`
- Loguru structured logging with signal scores (see `DEP-AUDIT` pattern in `cross_market.py:232`)
- `BotConfig` dataclass for all configurable thresholds
- Detection functions return `(results, diagnostics)` tuples

### Integration Points
- `load_event_groups()` is called from scanner startup — validator will be called immediately after
- `detect_cross_market_opportunities()` will replace inline dependency gate with `valid_set` membership check
- `_group_by_event()` produces the group lists that validator consumes

</code_context>

<specifics>
## Specific Ideas

- The user emphasized that this is fundamentally a **partition validation** problem, not a dependency detection problem. The mental model must be: "does this group form a valid one-of-N partition?" not "are these markets dependent?"
- In a valid partition, all pairs ARE mutually exclusive (dependent) — that's expected. Only structural violations (subset, duplicate, overlap) should cause rejection.
- The existing `classify_pair()` in `dependency.py` encodes the wrong mental model and should NOT be reused for group validation logic.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-group-structure-validation*
*Context gathered: 2026-04-26*
