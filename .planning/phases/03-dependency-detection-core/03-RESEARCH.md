# Phase 3: Dependency Detection Core - Research

**Researched:** 2026-04-25
**Domain:** Text-based market question pair classification (NLP-lite, stdlib-only)
**Confidence:** HIGH

## Summary

Phase 3 builds a standalone dependency detection module (`src/bot/detection/dependency.py`) that classifies pairs of Polymarket market questions as subset, related, or independent. The module is pure (no scanner state, no network I/O) and uses Python stdlib only (no NLP libraries). It combines five weighted signals -- semantic overlap (Jaccard), keyword implication, numeric relation, time relation, and event bonus -- into a single score that maps to a three-way classification.

The research confirms that the codebase has well-established patterns for this kind of module: `fee_model.py` (87 lines) demonstrates frozenset-based keyword matching on `market.get("question", "")`, `filters.py` (96 lines) demonstrates pure stateless functions with a diagnostics dataclass, and `opportunity.py` shows the frozen dataclass result pattern. The module will follow all three precedents.

**Primary recommendation:** Build `dependency.py` as a single file with ~200-250 lines containing preprocessing, five signal extractors, a weighted scorer, and a classifier -- following the existing one-module-per-concern pattern in `src/bot/detection/`. Use TDD with a validation set of real Polymarket question pairs derived from Gamma API event data.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** New standalone file `src/bot/detection/dependency.py` containing all preprocessing, signal extraction, scoring, and classification logic
- **D-02:** Single file, not a subpackage
- **D-03:** Zero imports from scanner, execution, or network modules. All inputs passed as function parameters
- **D-04:** Python stdlib only: `str.lower()` + `re.findall(r'\w+', text)` for tokenization. No NLP libraries
- **D-05:** Stopword list is a hardcoded `frozenset` of ~30-50 common English words
- **D-06:** All signals operate on the `question` string field
- **D-07:** Each signal function returns a `float` in range `[0.0, 1.0]`
- **D-08:** Semantic overlap: Jaccard similarity on preprocessed token sets
- **D-09:** Keyword implication: Pattern matching for subset relationships
- **D-10:** Numeric relation: Regex extraction of percentages, dollar amounts, plain numbers
- **D-11:** Time relation: Regex extraction of years, month names, date patterns
- **D-12:** Event bonus: Binary signal (1.0 if same event_id, 0.0 otherwise)
- **D-13:** Weighted linear combination: `score = sum(signal_i * weight_i)`
- **D-14:** Weights and thresholds are function parameters with sensible defaults (NOT in BotConfig yet)
- **D-15:** Three-way classification: subset (>= subset_threshold), related (>= related_threshold), independent (below related_threshold)
- **D-16:** Initial weight/threshold values need to be reasonable but not perfect
- **D-17:** Public API: `classify_pair(question_a, question_b, event_id_a, event_id_b, weights, thresholds) -> DependencyResult`
- **D-18:** `DependencyResult` dataclass with label, score, and individual signal scores
- **D-19:** Follows codebase pattern of structured result dataclasses

### Claude's Discretion
- Internal organization within `dependency.py` (helper function order, private naming conventions)
- Exact regex patterns for numeric/time extraction (optimize for Polymarket question text patterns)
- Exact default weight values (as long as they're reasonable starting points)
- Exact stopword list composition (as long as it's 30-50 common English words)
- Whether `DependencyResult` includes a human-readable `reason` field or just scores

### Deferred Ideas (OUT OF SCOPE)
- Embedding-based cosine similarity boost (DEP-F01)
- Named entity recognition for states, teams, candidates (DEP-F02)
- Dependency DAG graph structure for transitive relationships (DEP-F03)
- Feedback loop validation against price inconsistencies (DEP-F04)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEP-01 | Preprocesses market questions (tokenize, normalize, strip stopwords) | Stdlib `re.findall(r'\w+', text.lower())` + hardcoded frozenset stopwords. Pattern proven in `fee_model.py` |
| DEP-02 | Extracts semantic overlap signal (Jaccard similarity on token sets) | Standard set intersection/union formula. Returns float in [0.0, 1.0] |
| DEP-03 | Extracts keyword implication signal (subset patterns like "by X%" implies "win") | Curated implication rules as `(pattern, parent_pattern)` tuples. Regex-based |
| DEP-04 | Extracts numeric relation signal (threshold/range containment) | Regex for percentages, dollar amounts, plain numbers. Containment logic |
| DEP-05 | Extracts time relation signal (date/deadline containment) | Regex for years, months, full dates. Earlier-deadline-implies-subset logic |
| DEP-06 | Applies event_id bonus for same-event market pairs | Binary 1.0/0.0. Event IDs passed as parameters |
| DEP-07 | Weighted scorer combines all 5 signals + event bonus into dependency score | Linear combination `sum(signal_i * weight_i)`. Weights as function params |
| DEP-08 | Classifier labels pairs as subset/related/independent based on thresholds | Two-threshold classification: subset >= T1, related >= T2, independent < T2 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **WebSearch is BLOCKED** -- org policy blocks web search tool. Use WebFetch for URL fetches
- **GSD Workflow Enforcement** -- all file changes go through GSD commands
- **Tech stack**: Python 3.10+, py-clob-client, loguru for logging
- **No NLP libraries** -- spaCy, NLTK, transformers explicitly out of scope (Docker image size constraint)
- **Stdlib-only text processing** -- per REQUIREMENTS.md out-of-scope section

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `re` | 3.10+ | Regex tokenization, numeric/time extraction | Locked decision D-04: no external NLP deps [VERIFIED: codebase constraint] |
| Python stdlib `dataclasses` | 3.10+ | `DependencyResult` structured output | Matches `ArbitrageOpportunity`, `FilterDiagnostics` patterns [VERIFIED: opportunity.py, filters.py] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `loguru` | 0.7+ | Debug logging of signal scores | Optional for debugging; module itself is pure [VERIFIED: used throughout codebase] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Jaccard similarity | Cosine similarity via sklearn | Deferred to DEP-F01; sklearn would add 100MB+ to Docker image |
| Hardcoded stopwords | NLTK stopwords corpus | NLTK adds ~40MB; 30-50 hardcoded words cover Polymarket question patterns |
| Regex-based NER | spaCy NER | Deferred to DEP-F02; 400MB+ model download |

**Installation:** No new packages required. All stdlib. [VERIFIED: codebase analysis]

## Architecture Patterns

### Recommended Project Structure
```
src/bot/detection/
    __init__.py            # existing
    cross_market.py        # existing — Phase 4 will call classify_pair() from here
    dependency.py          # NEW — Phase 3 deliverable
    fee_model.py           # existing — frozenset pattern reference
    filters.py             # existing — diagnostics dataclass pattern reference
    opportunity.py         # existing — result dataclass pattern reference
    yes_no_arb.py          # existing
```

### Pattern 1: Pure Stateless Signal Functions
**What:** Each of the five signal extractors is a private function that takes preprocessed tokens/strings and returns a float in [0.0, 1.0]. No side effects, no state.
**When to use:** All signal extraction (DEP-02 through DEP-06).
**Example:**
```python
# Source: Follows filters.py pure function pattern (lines 19-36)
def _jaccard_similarity(tokens_a: frozenset[str], tokens_b: frozenset[str]) -> float:
    """DEP-02: Semantic overlap via Jaccard similarity on preprocessed token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)
```

### Pattern 2: Frozen Dataclass for Results
**What:** `DependencyResult` as a frozen dataclass containing classification label, composite score, and individual signal scores for Phase 4 audit mode observability.
**When to use:** Return type of `classify_pair()`.
**Example:**
```python
# Source: Follows opportunity.py ArbitrageOpportunity pattern
@dataclass(frozen=True)
class DependencyResult:
    label: str          # "subset" | "related" | "independent"
    score: float        # weighted composite score
    jaccard: float      # DEP-02 individual signal
    implication: float  # DEP-03 individual signal
    numeric: float      # DEP-04 individual signal
    temporal: float     # DEP-05 individual signal
    event_bonus: float  # DEP-06 individual signal
```

### Pattern 3: Hardcoded Frozenset Vocabulary
**What:** Stopwords as a module-level `frozenset`, matching the `fee_model.py` pattern of `_CRYPTO_KEYWORDS`, `_GEO_KEYWORDS`, etc.
**When to use:** Preprocessing (DEP-01).
**Example:**
```python
# Source: Follows fee_model.py lines 16-28 frozenset pattern
_STOPWORDS = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "will", "be", "been",
    "do", "does", "did", "have", "has", "had", "of", "in", "to", "for",
    "on", "at", "by", "from", "with", "as", "or", "and", "but", "if",
    "it", "its", "this", "that", "than", "any", "more", "not", "no",
])
```

### Pattern 4: Configurable Weights/Thresholds as Parameters
**What:** Default weights and thresholds defined as module-level constants, overridable via function parameters. NOT in BotConfig (that is Phase 4).
**When to use:** `classify_pair()` signature (D-14).
**Example:**
```python
# Source: Decision D-14 — BotConfig integration deferred to Phase 4
DEFAULT_WEIGHTS = {
    "jaccard": 0.30,
    "implication": 0.25,
    "numeric": 0.15,
    "temporal": 0.15,
    "event_bonus": 0.15,
}

DEFAULT_THRESHOLDS = {
    "subset": 0.70,
    "related": 0.35,
}
```

### Anti-Patterns to Avoid
- **Importing from scanner/execution modules:** D-03 explicitly forbids this. All inputs come via function parameters. No `from bot.scanner import ...` or `from bot.execution import ...`
- **Using BotConfig for weights/thresholds:** D-14 defers this to Phase 4. Use function parameters with defaults
- **Global mutable state:** No module-level mutable dicts like `_event_groups` in `cross_market.py`. This module is pure
- **Over-engineering signal functions:** Each signal is ~5-15 lines. Don't build elaborate NLP pipelines with stdlib

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Set similarity metric | Custom distance function | Jaccard formula (`len(A&B)/len(A|B)`) | Jaccard is the standard for token-set overlap; well-understood properties, O(n) with frozensets |
| Date parsing | Full datetime parser | Targeted regexes for Polymarket patterns | Polymarket uses ~5 date formats (see Real-World Patterns below). Full parsing is overkill |
| Stopword corpus | Download NLTK/spaCy | Hardcoded frozenset of 30-50 words | Per D-04/D-05, Docker image size constraint makes libraries non-viable |

**Key insight:** This module is intentionally simple -- weighted linear combination of five regex/set-based signals. The sophistication comes from Phase 4 threshold tuning on production data, not from complex NLP in Phase 3.

## Real-World Polymarket Question Patterns

> Gathered from live Gamma API data (2026-04-25). These patterns drive the regex and implication rule design.

### Pattern Category 1: Deadline Variants (Most Common Multi-Market)
Same question stem with different deadlines. The dependency detection MUST classify earlier deadlines as **subset** of later ones.

| Event | Market Questions |
|-------|-----------------|
| MicroStrategy Bitcoin Sales | "MicroStrategy sells any Bitcoin in 2025?" / "...by March 31, 2026?" / "...by June 30, 2026?" / "...by December 31, 2026?" |
| Kraken IPO | "Kraken IPO in 2025?" / "...by March 31, 2026?" / "...by June 30, 2026?" / "...by December 31, 2026?" |
| Macron out | "Macron out in 2025?" / "...by June 30, 2026?" / "...by October 31, 2025?" |
| Russia capture Lyman | "...by November 30?" / "...by December 31?" / "...by March 31, 2026?" |

**Observed date formats:**
- `"in 2025?"` -- year-only
- `"by December 31?"` -- month + day, no year (implies current year)
- `"by March 31, 2026?"` -- month + day + year
- `"by June 30, 2026?"` -- month + day + year

[VERIFIED: gamma-api.polymarket.com/events live data]

### Pattern Category 2: Candidate/Outcome Variants (Election-Style)
Same question stem with different subjects. These are **related** (same event, mutually exclusive outcomes) but NOT subset.

| Event | Market Questions |
|-------|-----------------|
| LALIGA Winner | "Will Real Madrid win the 2025-26 La Liga?" / "Will Barcelona win...?" / "Will Atletico Madrid win...?" / ... (20 markets) |
| Minnesota Senate | "Will the Democrats win the Minnesota Senate race in 2026?" / "Will the Republicans win...?" / "Will Person A win...?" / ... |

**Key feature:** Question stems are nearly identical except for the subject entity. High Jaccard similarity, but NOT subset -- these are independent exclusive outcomes.

[VERIFIED: gamma-api.polymarket.com/events live data]

### Pattern Category 3: Threshold Variants
Same question with different numeric thresholds. Higher threshold is subset of lower threshold for "beat by more than X" patterns.

| Event | Market Questions |
|-------|-----------------|
| Sports spreads | "Will the Mavericks beat the Grizzlies by more than 5.5 points...?" (implied: "by more than 3.5 points" would be a parent) |

[VERIFIED: gamma-api.polymarket.com/events live data]

### Implications for Signal Design

1. **Time relation (DEP-05) is the highest-value signal** for Polymarket. The majority of multi-market events are deadline variants. The regex must handle all four observed date formats.

2. **Jaccard alone is misleading** for candidate-style events. "Will Real Madrid win..." and "Will Barcelona win..." have high Jaccard overlap but are independent outcomes, not subsets. The classifier needs the combination of Jaccard + implication + event_bonus to distinguish.

3. **Numeric relation (DEP-04)** applies to sports spread markets ("by more than 5.5 points") but these are less common in multi-market events than deadline variants.

4. **Event bonus (DEP-06) is critical for disambiguation.** Same-event markets with high Jaccard but different subjects are "related" (not "subset"). Without event_bonus, high Jaccard + no implication/temporal signal = ambiguous.

## Common Pitfalls

### Pitfall 1: Jaccard Overweighting on Candidate-Style Events
**What goes wrong:** "Will Real Madrid win the La Liga?" and "Will Barcelona win the La Liga?" have Jaccard ~0.83 (only 1 token differs in 6-7 token questions). Without other signals, the scorer would classify this as "subset" when it should be "related" or "independent".
**Why it happens:** Jaccard measures overlap but not directionality. It cannot distinguish "same question, different subject" from "same question, narrower scope".
**How to avoid:** Implication signal (DEP-03) must return 0.0 for this case (no subset relationship detected). Thresholds must be calibrated so high Jaccard alone does not reach `subset_threshold`.
**Warning signs:** Validation set shows candidate-style pairs classified as "subset".

### Pitfall 2: Date Format Inconsistency
**What goes wrong:** Polymarket uses at least 4 date formats. A regex that only handles "by Month Day, Year" misses "in 2025?" and "by December 31?" (no year).
**Why it happens:** Incomplete pattern coverage from not examining real data.
**How to avoid:** Test against all four observed formats. Handle missing year as "current year" or "unresolved" (still allows ordering within same stem).
**Warning signs:** Time relation signal returns 0.0 for pairs that clearly have deadline relationships.

### Pitfall 3: Stopword Over-Stripping
**What goes wrong:** Removing "by", "in", "more", "than" strips signal-bearing tokens from questions like "win by 5%" or "more than 3.5 points". The numeric/implication signals lose context.
**Why it happens:** Stopword lists designed for general English remove prepositions that carry meaning in Polymarket questions.
**How to avoid:** Signal extraction (DEP-03, DEP-04, DEP-05) should operate on the ORIGINAL question string, NOT the preprocessed tokens. Only the Jaccard signal (DEP-02) uses preprocessed tokens. Preprocessing is for Jaccard's benefit.
**Warning signs:** Implication and numeric signals fail on questions containing "by X%", "more than X".

### Pitfall 4: Weight Sum Not Equaling 1.0
**What goes wrong:** If weights sum to more or less than 1.0, the composite score's scale is unpredictable, making thresholds unreliable.
**Why it happens:** Weights are chosen independently for each signal without checking total.
**How to avoid:** Either normalize weights to sum to 1.0, or document that the threshold values are calibrated for a specific weight sum. Recommend normalization for simplicity.
**Warning signs:** Threshold tuning in Phase 4 produces counterintuitive results.

### Pitfall 5: Empty Token Sets from Short Questions
**What goes wrong:** Very short questions like "Kraken IPO in 2025?" after stopword removal become `{"kraken", "ipo"}` -- 2 tokens. Jaccard between this and "Kraken IPO by March 31, 2026?" (tokens: `{"kraken", "ipo", "march", "31", "2026"}`) gives a misleadingly low score (2/5 = 0.4) despite being essentially the same question with different deadlines.
**Why it happens:** Short questions have high stopword-to-content ratios, and date tokens dilute Jaccard.
**How to avoid:** This is expected behavior -- the temporal signal (DEP-05) compensates. Weights must ensure temporal signal contributes enough to override low Jaccard for deadline-variant pairs.
**Warning signs:** Deadline-variant pairs classified as "independent" despite obvious relationship.

## Code Examples

Verified patterns from the existing codebase:

### Preprocessing (DEP-01)
```python
# Source: fee_model.py line 55 pattern + Decision D-04
import re

_STOPWORDS = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "will", "be", "been",
    "do", "does", "did", "have", "has", "had", "of", "in", "to", "for",
    "on", "at", "by", "from", "with", "as", "or", "and", "but", "if",
    "it", "its", "this", "that", "than", "any", "more", "not", "no",
])

def _preprocess(question: str) -> frozenset[str]:
    """Tokenize, lowercase, strip stopwords. Returns frozenset for set ops."""
    tokens = re.findall(r'\w+', question.lower())
    return frozenset(t for t in tokens if t not in _STOPWORDS)
```

### Jaccard Similarity (DEP-02)
```python
# Source: Standard set similarity formula
def _jaccard_similarity(tokens_a: frozenset[str], tokens_b: frozenset[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)
```

### Time Relation Regex (DEP-05) -- All Four Polymarket Formats
```python
# Source: Gamma API live data analysis (2026-04-25)
import re
import calendar

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}

# Pattern 1: "by Month Day, Year" (e.g., "by March 31, 2026")
# Pattern 2: "by Month Day" no year (e.g., "by December 31")
# Pattern 3: "in Year" (e.g., "in 2025")
# Pattern 4: "by Month Day, Year?" at end (same as 1 but with trailing ?)
_DATE_PATTERN = re.compile(
    r'(?:by|in|before)\s+'
    r'(?:'
    r'(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?'  # Month Day[, Year]
    r'|'
    r'(\d{4})'  # standalone year
    r')',
    re.IGNORECASE,
)
```

### Result Dataclass (DEP-08)
```python
# Source: Follows opportunity.py + filters.py patterns
from dataclasses import dataclass

@dataclass(frozen=True)
class DependencyResult:
    """Classification result for a market question pair."""
    label: str          # "subset" | "related" | "independent"
    score: float        # weighted composite [0.0, 1.0]
    jaccard: float      # DEP-02
    implication: float  # DEP-03
    numeric: float      # DEP-04
    temporal: float     # DEP-05
    event_bonus: float  # DEP-06
```

### Test Structure (follows test_filters.py pattern)
```python
# Source: test_filters.py pattern -- grouped by requirement ID
import pytest

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# DEP-01: Preprocessing
# ---------------------------------------------------------------------------

def test_preprocess_lowercase_and_tokenize():
    from bot.detection.dependency import _preprocess
    tokens = _preprocess("Will Bitcoin REACH $100k?")
    assert "bitcoin" in tokens
    assert "reach" in tokens
    assert "100k" in tokens

def test_preprocess_strips_stopwords():
    from bot.detection.dependency import _preprocess
    tokens = _preprocess("Will the price of Bitcoin be higher?")
    assert "the" not in tokens
    assert "will" not in tokens
    assert "bitcoin" in tokens
```

## Validation Set Design

The test suite needs a validation set of known market pairs with expected classifications. Based on real Polymarket data:

### Subset Pairs (earlier deadline implies later deadline)
| Question A | Question B | Expected | Why |
|-----------|-----------|----------|-----|
| "MicroStrategy sells any Bitcoin in 2025?" | "MicroStrategy sells any Bitcoin by December 31, 2026?" | subset | 2025 < Dec 2026 |
| "Kraken IPO by March 31, 2026?" | "Kraken IPO by December 31, 2026?" | subset | Mar < Dec same year |
| "Macron out by October 31, 2025?" | "Macron out by June 30, 2026?" | subset | Oct 2025 < Jun 2026 |

### Related Pairs (same event, different outcomes -- NOT subset)
| Question A | Question B | Expected | Why |
|-----------|-----------|----------|-----|
| "Will Real Madrid win the 2025-26 La Liga?" | "Will Barcelona win the 2025-26 La Liga?" | related | Same event, different subject |
| "Will the Democrats win the Minnesota Senate race in 2026?" | "Will the Republicans win the Minnesota Senate race in 2026?" | related | Same event, different subject |

### Independent Pairs (completely different markets)
| Question A | Question B | Expected | Why |
|-----------|-----------|----------|-----|
| "MicroStrategy sells any Bitcoin in 2025?" | "Will Real Madrid win the 2025-26 La Liga?" | independent | Different domains |
| "Macron out in 2025?" | "Kraken IPO in 2025?" | independent | Different subjects |

[VERIFIED: All question strings from gamma-api.polymarket.com/events live data]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v1.1 BFS keyword heuristic | v1.1 Gamma API event grouping | 2026-04-19 | Eliminated false-positive cross-market grouping |
| No dependency detection | Phase 3 weighted scoring | v1.2 (current) | Validates mutual exclusivity within event groups |
| LLM mutual exclusivity check (considered) | Stdlib weighted scoring | v1.2 requirements | Eliminated latency/cost overhead per REQUIREMENTS.md |

**Deprecated/outdated:**
- BFS keyword heuristic for market grouping: replaced by Gamma API event-level grouping in v1.1
- LLM-based validation: explicitly out of scope per REQUIREMENTS.md

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Default weights (jaccard=0.30, implication=0.25, numeric=0.15, temporal=0.15, event_bonus=0.15) produce reasonable initial classifications | Architecture Patterns | LOW -- Phase 4 audit mode (DEP-10) exists specifically for tuning. Initial values just need to be directionally correct |
| A2 | 30-50 hardcoded stopwords cover Polymarket question patterns adequately | Architecture Patterns | LOW -- easy to expand the frozenset if edge cases emerge |
| A3 | Four observed date formats cover >95% of Polymarket deadline-style questions | Real-World Patterns | MEDIUM -- new date formats may appear. Regex is extensible but untested on full corpus |
| A4 | `re.findall(r'\w+', text)` tokenization handles all Polymarket question characters correctly (including $, %, hyphens in "2025-26") | Code Examples | LOW -- `\w+` splits on non-word characters. "$100k" becomes "100k", "2025-26" becomes "2025" and "26". This is acceptable behavior |
| A5 | Signal functions operating on original strings (not preprocessed tokens) for implication/numeric/temporal extraction is the right design | Pitfalls | LOW -- preprocessing is explicitly for Jaccard only per D-04 |

**All other claims verified via codebase inspection or Gamma API live data.**

## Open Questions

1. **Optimal default weight distribution**
   - What we know: Five signals with different value densities. Temporal is highest-value for Polymarket (most multi-market events are deadline variants)
   - What's unclear: Exact optimal weight ratios without production data
   - Recommendation: Use A1 weights as starting point. Phase 4 audit mode (DEP-10) will tune from real data

2. **"in 2025" vs "by December 31, 2025" -- are these subset or equal?**
   - What we know: "in 2025" logically means "before end of 2025". "by December 31, 2025" means the same thing
   - What's unclear: Whether to classify as subset (one direction) or treat as equivalent
   - Recommendation: Treat "in YEAR" as equivalent to "by December 31, YEAR" for temporal comparison purposes. Both map to the same deadline

3. **Implication rules -- how many do we need?**
   - What we know: Decision D-09 specifies curated `(pattern, parent_pattern)` tuples. Real data shows "win by X%" implies "win", "reach $X" where X > Y implies "reach $Y"
   - What's unclear: Full enumeration of Polymarket-specific implication patterns
   - Recommendation: Start with 3-5 core rules (win/beat/reach + threshold patterns). Expand in Phase 4 based on audit mode findings

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pytest.ini` (exists, `asyncio_mode = auto`) |
| Quick run command | `python3 -m pytest tests/test_dependency.py -x -q` |
| Full suite command | `python3 -m pytest tests/ -x -q --tb=short` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEP-01 | Preprocessing normalizes, tokenizes, strips stopwords | unit | `python3 -m pytest tests/test_dependency.py -k "preprocess" -x` | Wave 0 |
| DEP-02 | Jaccard similarity on token sets | unit | `python3 -m pytest tests/test_dependency.py -k "jaccard" -x` | Wave 0 |
| DEP-03 | Keyword implication signal extraction | unit | `python3 -m pytest tests/test_dependency.py -k "implication" -x` | Wave 0 |
| DEP-04 | Numeric relation signal extraction | unit | `python3 -m pytest tests/test_dependency.py -k "numeric" -x` | Wave 0 |
| DEP-05 | Time relation signal extraction | unit | `python3 -m pytest tests/test_dependency.py -k "temporal" -x` | Wave 0 |
| DEP-06 | Event bonus binary signal | unit | `python3 -m pytest tests/test_dependency.py -k "event_bonus" -x` | Wave 0 |
| DEP-07 | Weighted scorer combines signals | unit | `python3 -m pytest tests/test_dependency.py -k "score" -x` | Wave 0 |
| DEP-08 | Classifier labels pairs correctly on validation set | unit | `python3 -m pytest tests/test_dependency.py -k "classify" -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_dependency.py -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -x -q --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_dependency.py` -- covers DEP-01 through DEP-08 (must be created)
- No framework install needed -- pytest 9.0.2 already available
- No conftest changes needed -- `bot_config` fixture not required (module is pure, no config dependency)

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `src/bot/detection/filters.py` -- pure function pattern, `FilterDiagnostics` dataclass template
- Codebase analysis: `src/bot/detection/fee_model.py` -- frozenset keyword matching, `question` field access pattern
- Codebase analysis: `src/bot/detection/opportunity.py` -- frozen dataclass result pattern
- Codebase analysis: `src/bot/detection/cross_market.py` -- `_event_groups` mapping, event-level grouping architecture
- Codebase analysis: `src/bot/config.py` -- `BotConfig` frozen dataclass, field naming conventions
- Codebase analysis: `tests/test_filters.py` -- test organization pattern (grouped by requirement ID, `pytestmark = pytest.mark.unit`)

### Secondary (MEDIUM confidence)
- Gamma API live data: `https://gamma-api.polymarket.com/events?limit=50&closed=false` -- real market question text patterns, date format enumeration
- Gamma API live data: `https://gamma-api.polymarket.com/events?limit=50&closed=false&offset=100` -- deadline-variant and sports spread patterns
- Gamma API live data: `https://gamma-api.polymarket.com/events?limit=50&closed=false&offset=200` -- election/candidate-style patterns

### Tertiary (LOW confidence)
- None -- all claims verified via codebase or live API data

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- stdlib-only, no external dependencies, fully verified against codebase
- Architecture: HIGH -- all patterns directly derived from existing codebase modules
- Pitfalls: HIGH -- derived from analysis of real Polymarket question data against proposed signal design

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (stable -- stdlib-only module, no version sensitivity)
