# Phase 6: Group Structure Validation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-26
**Phase:** 06-group-structure-validation
**Areas discussed:** Validation architecture, NegRisk data flow, Dependency reuse vs new checks, Rejection diagnostics

---

## Validation Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| New module (Recommended) | Create src/bot/detection/group_validator.py as standalone module | ✓ |
| Extend cross_market.py | Add validation functions directly into cross_market.py | |
| You decide | Let Claude pick | |

**User's choice:** New module
**Notes:** Clean separation — validation is its own concern.

| Option | Description | Selected |
|--------|-------------|----------|
| At startup (Recommended) | Validate groups once when Gamma data loaded. Pre-compute valid set. | ✓ |
| Every detection cycle | Validate fresh each cycle. Adds O(n²) per cycle. | |
| You decide | Let Claude pick | |

**User's choice:** At startup
**Notes:** Aligns with existing load_event_groups() once-at-startup pattern.

| Option | Description | Selected |
|--------|-------------|----------|
| Remove it (Recommended) | Remove inline pairwise dependency loop (lines 218-257) from cross_market.py | ✓ |
| Keep both | Belt-and-suspenders: startup validation + per-cycle dependency check | |
| You decide | Let Claude pick | |

**User's choice:** Remove it
**Notes:** Redundant once group_validator.py runs at startup.

---

## NegRisk Data Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Enrich event_groups (Recommended) | Change dict to EventInfo dataclass with event_id, neg_risk, market_count | ✓ |
| Separate neg_risk set | Keep existing dict, add separate _neg_risk_events set | |
| You decide | Let Claude pick | |

**User's choice:** Enrich event_groups
**Notes:** Single dict lookup serves both validator and detector.

| Option | Description | Selected |
|--------|-------------|----------|
| In cross_market.py (Recommended) | Keep load_event_groups() and EventInfo where they are now | ✓ |
| New gamma_cache.py module | Separate Gamma data layer from detection entirely | |
| You decide | Let Claude pick | |

**User's choice:** In cross_market.py
**Notes:** Module already owns the Gamma API fetch.

---

## Dependency Reuse vs New Checks

| Option | Description | Selected |
|--------|-------------|----------|
| Import individual signals (Recommended) | Import _jaccard_similarity, _preprocess, _keyword_implication from dependency.py | |
| Call classify_pair() | Use existing classifier as-is | |
| Write new functions | Duplicate logic in group_validator.py | |

**User's choice:** Initially selected "Import individual signals", then CORRECTED the framing entirely.

### Critical Reframe (User Correction)

The user identified a fundamental conceptual error: the discussion was framing group validation as "dependency rejection" when it should be "partition structure validation."

**Key insight:** In a valid one-of-N partition, all pairs ARE mutually exclusive (dependent) — that's expected structure. The validator should only detect structural violations that break the partition: subset, duplicate, overlap.

The existing `classify_pair()` from dependency.py encodes the wrong mental model ("subset / related / independent" where "related" = bad) and should NOT be reused.

| Option | Description | Selected |
|--------|-------------|----------|
| Fresh validation functions | Purpose-built is_subset_pair(), is_duplicate_pair(), is_overlapping_pair() | ✓ |
| Wrap dependency signals | Import signals but apply new thresholds/interpretation | |
| You decide | Let Claude pick | |

**User's choice:** Fresh validation functions
**Notes:** Clean mental model from the start. Partition-aware classification, not dependency classification.

---

## Rejection Diagnostics

| Option | Description | Selected |
|--------|-------------|----------|
| Structured per-violation (Recommended) | Log each violation with type, offending markets, signal scores | ✓ |
| Summary per group | One log line per rejected group | |
| You decide | Let Claude pick | |

**User's choice:** Structured per-violation
**Notes:** Matches existing DEP-AUDIT log pattern.

| Option | Description | Selected |
|--------|-------------|----------|
| Debug-level count only (Recommended) | Aggregate count at startup for NegRisk auto-passes | |
| Log each NegRisk pass | Individual log per NegRisk auto-pass | |
| You decide | Let Claude pick | ✓ |

**User's choice:** You decide (Claude's discretion)
**Notes:** Claude will determine appropriate NegRisk logging level.

| Option | Description | Selected |
|--------|-------------|----------|
| Return valid set only (Recommended) | validate_groups() returns set[str] of valid event IDs | ✓ |
| Return ValidationReport | Structured report with valid_ids, rejected_ids, reasons, counts | |

**User's choice:** Return valid set only
**Notes:** Simple interface — detection loop checks membership.

---

## Claude's Discretion

- NegRisk auto-pass logging level and format

## Deferred Ideas

None — discussion stayed within phase scope
