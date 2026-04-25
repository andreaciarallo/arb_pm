# Phase 3: Dependency Detection Core - Context

**Gathered:** 2026-04-25 (assumptions mode, --auto)
**Status:** Ready for planning

<domain>
## Phase Boundary

A standalone dependency detection module that can score any pair of market questions for subset/related/independent relationships using five weighted signals (semantic overlap, keyword implication, numeric relation, time relation, event bonus). The module is a pure function with no dependency on scanner state or network I/O. Integration into the live scanner is Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Module Architecture
- **D-01:** New standalone file `src/bot/detection/dependency.py` containing all preprocessing, signal extraction, scoring, and classification logic. Follows the one-module-per-concern pattern (like `filters.py`, `fee_model.py`, `yes_no_arb.py`).
- **D-02:** Single file, not a subpackage. DEP-01 through DEP-08 represent preprocessing + 5 signal functions + 1 scorer + 1 classifier — similar scope to `filters.py` (96 lines) and `fee_model.py` (87 lines). If signal implementations grow unwieldy, refactoring to a subpackage is low-cost since no external callers exist until Phase 4.
- **D-03:** Zero imports from scanner, execution, or network modules. All inputs passed as function parameters. Satisfies success criterion 5 (pure function, no scanner state dependency).

### Text Preprocessing (DEP-01)
- **D-04:** Python stdlib only: `str.lower()` + `re.findall(r'\w+', text)` for tokenization and punctuation stripping. No NLP libraries (spaCy, NLTK, transformers) — per project constraint on Docker image size.
- **D-05:** Stopword list is a hardcoded `frozenset` of ~30-50 common English words (articles, prepositions, conjunctions, common verbs like "is", "are", "does"). Follows the pattern of hardcoded frozensets in `fee_model.py` (lines 16-28). Preserves domain-relevant tokens like "win", "reach", "pass" that carry signal in implication detection.

### Signal Extraction (DEP-02 through DEP-06)
- **D-06:** All signals operate on the `question` string field already available on market dicts (used by `fee_model.py` line 55 and logged in `yes_no_arb.py`/`cross_market.py`). No additional API calls needed.
- **D-07:** Each signal function returns a `float` in range `[0.0, 1.0]` for uniform weighted combination.
- **D-08:** Semantic overlap (DEP-02): Jaccard similarity on preprocessed token sets.
- **D-09:** Keyword implication (DEP-03): Pattern matching for subset relationships (e.g., "win by X%" implies "win", "reach $X" where X > Y implies "reach $Y"). Curated implication rules as a list of `(pattern, parent_pattern)` tuples.
- **D-10:** Numeric relation (DEP-04): Regex extraction of percentages (`r'\d+\.?\d*%'`), dollar amounts (`r'\$[\d,]+[kKmMbB]?'`), and plain numbers. Containment check — if one question's number range is a subset of another's, signals subset relationship.
- **D-11:** Time relation (DEP-05): Regex extraction of years (`r'\b20\d{2}\b'`), month names, and date patterns. Earlier deadlines imply subset of later deadlines for the same question stem.
- **D-12:** Event bonus (DEP-06): Binary signal — `1.0` if both markets share the same `event_id`, `0.0` otherwise. Event ID passed as parameter (from `_event_groups` dict in `cross_market.py`).

### Weighted Scoring and Classification (DEP-07, DEP-08)
- **D-13:** Weighted linear combination: `score = sum(signal_i * weight_i)` where each weight is a float. Consistent with codebase's arithmetic scoring approach (no ML frameworks).
- **D-14:** Weights and thresholds are function parameters with sensible defaults — NOT in `BotConfig` yet. Phase 3 is a standalone module; BotConfig integration happens in Phase 4 when the module is wired into the scanner.
- **D-15:** Three-way classification using two thresholds:
  - `score >= subset_threshold` → `"subset"`
  - `related_threshold <= score < subset_threshold` → `"related"`
  - `score < related_threshold` → `"independent"`
- **D-16:** Initial weight/threshold values need to be reasonable but not perfect — Phase 4 adds audit mode (DEP-10) specifically for threshold tuning from production data.

### Interface Contract
- **D-17:** Public API is a single pure function: `classify_pair(question_a: str, question_b: str, event_id_a: str | None = None, event_id_b: str | None = None, weights: ... = DEFAULT_WEIGHTS, thresholds: ... = DEFAULT_THRESHOLDS) -> DependencyResult`
- **D-18:** `DependencyResult` is a dataclass containing: `label` (str: "subset"/"related"/"independent"), `score` (float), and individual signal scores (for Phase 4 audit mode observability per DEP-10).
- **D-19:** Follows codebase pattern of structured result dataclasses (`ArbitrageOpportunity`, `FilterDiagnostics`, `MarketPrice`).

### Claude's Discretion
- Internal organization within `dependency.py` (helper function order, private naming conventions)
- Exact regex patterns for numeric/time extraction (optimize for Polymarket question text patterns)
- Exact default weight values (as long as they're reasonable starting points)
- Exact stopword list composition (as long as it's 30-50 common English words)
- Whether `DependencyResult` includes a human-readable `reason` field or just scores

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — DEP-01 through DEP-08 define exact signal descriptions and classifier behavior

### Phase 3 Description
- `.planning/ROADMAP.md` — Phase 3 section defines goal, dependencies, success criteria

### Prior Phase Context
- `.planning/phases/02-detection-quality-filters/02-CONTEXT.md` — Phase 2 decisions (filter patterns, BotConfig conventions, diagnostic counter approach)

### Existing Detection Code
- `src/bot/detection/cross_market.py` — Event grouping via `_event_groups` dict, `question` field usage, `detect_cross_market_opportunities()` function structure
- `src/bot/detection/yes_no_arb.py` — Detection loop pattern, `question` field logging, gate-style filtering
- `src/bot/detection/filters.py` — Phase 2 quality filters: stateless functions + stateful DedupTracker, `FilterDiagnostics` dataclass pattern
- `src/bot/detection/opportunity.py` — `ArbitrageOpportunity` dataclass (reference for result dataclass design)
- `src/bot/detection/fee_model.py` — Hardcoded `frozenset` keyword matching pattern on `market.get("question", "").lower()`, precedent for text processing approach

### Configuration
- `src/bot/config.py` — `BotConfig` frozen dataclass pattern (Phase 4 will add weights/thresholds here)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `fee_model.py` keyword frozensets: established pattern for hardcoded vocabulary/term matching in detection modules
- `FilterDiagnostics` dataclass in `filters.py`: template for `DependencyResult` structured result
- `ArbitrageOpportunity` in `opportunity.py`: reference for detection result dataclasses
- `_event_groups` dict in `cross_market.py`: existing `condition_id → event_id` mapping (Phase 4 will pass event IDs to dependency module)

### Established Patterns
- One-module-per-concern in `src/bot/detection/`: each file handles a single detection responsibility
- Gate-style sequential filtering: `if condition: continue` blocks in detection loops
- Loguru for all logging (`logger.info`, `logger.debug`)
- Hardcoded frozensets for vocabulary (no external NLP/data dependencies)
- Arithmetic scoring (simple formulas, no ML frameworks)
- Frozen dataclasses for structured results

### Integration Points
- Phase 4 will import `classify_pair()` from `dependency.py` and call it within `cross_market.py`'s detection loop
- Phase 4 will pass `event_id` from `_event_groups` dict as parameter to `classify_pair()`
- Phase 4 will add weight/threshold fields to `BotConfig` and pass them through

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- Embedding-based cosine similarity boost (DEP-F01) — future requirement, explicitly out of scope for v1.2
- Named entity recognition for states, teams, candidates (DEP-F02) — future requirement
- Dependency DAG graph structure for transitive relationships (DEP-F03) — future requirement
- Feedback loop validation against price inconsistencies (DEP-F04) — future requirement

</deferred>

---

*Phase: 03-dependency-detection-core*
*Context gathered: 2026-04-25*
