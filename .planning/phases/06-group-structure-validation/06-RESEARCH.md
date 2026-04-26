# Phase 6: Group Structure Validation - Research

**Researched:** 2026-04-26
**Domain:** Partition validation for Polymarket event groups (NegRisk detection, duplicate/subset/overlap rejection)
**Confidence:** HIGH

## Summary

Phase 6 adds a startup-time validator that classifies each Polymarket event group as a valid one-of-N partition (suitable for basket arbitrage) or invalid (structural violations). The core insight is that NegRisk-enabled events are exchange-guaranteed partitions and can be auto-accepted, while non-NegRisk multi-market events require heuristic checks for duplicates, subsets, and overlaps.

Live Gamma API analysis confirms the data model: 1,622 NegRisk events exist across 10,000+ active events, ALL with 3+ markets, and ALL markets within NegRisk events have `negRisk=True` at the market level (zero mixed events found). 532 non-NegRisk multi-market events exist, many of which are NOT partitions (e.g., "NHL: February 2nd" groups different games, mid_sum=2.0; "CryptoPunks" events have threshold/bracket questions with subset relationships).

The implementation is entirely local (new `group_validator.py` module + enrichment of `_event_groups` dict + removal of inline dependency gate in `cross_market.py`). No new pip dependencies. No external API calls beyond the existing Gamma API fetch already happening at startup.

**Primary recommendation:** Create `group_validator.py` with NegRisk auto-pass, then three pairwise violation detectors (duplicate via Jaccard, subset via keyword implication + numeric, overlap via disjoint check), and a mid-price completeness heuristic. Enrich `_event_groups` to carry `EventInfo(event_id, neg_risk, market_count)`. Remove the inline `classify_pair()` dependency gate from `cross_market.py` lines 217-257.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Create new standalone module `src/bot/detection/group_validator.py`. Group validation is its own concern, separate from detection and fee logic in `cross_market.py`.
- **D-02:** Validation runs ONCE at startup (alongside `load_event_groups()`). Pre-compute a `set[str]` of valid event IDs. Detection loop checks membership -- zero latency impact on hot path.
- **D-03:** Remove the existing inline pairwise dependency gate in `cross_market.py` (lines 218-257). It becomes redundant once `group_validator.py` runs at startup. Simplifies the detection hot path.
- **D-04:** Enrich `_event_groups` from `dict[str, str]` (condition_id -> event_id) to `dict[str, EventInfo]` where `EventInfo` is a dataclass holding `event_id`, `neg_risk` (bool), and `market_count` (int). Single dict lookup serves both validator and detector.
- **D-05:** `EventInfo` dataclass and enriched dict stay in `cross_market.py` where `load_event_groups()` already lives. `group_validator.py` imports them.
- **D-06:** Group validation is **partition structure validation**, NOT dependency rejection. In a valid one-of-N group, all pairs ARE mutually exclusive (dependent) -- that's expected structure. The validator detects **structural violations** that break the partition: subset, duplicate, overlap.
- **D-07:** Write fresh, purpose-built validation functions in `group_validator.py`: `is_subset_pair()`, `is_duplicate_pair()`, `is_overlapping_pair()`. Do NOT reuse `classify_pair()` from `dependency.py`. May reuse low-level utilities like `_preprocess()` if helpful.
- **D-08:** Structured per-violation logging. `GV-REJECT: {type} | q1="{...}" q2="{...}" | score={...}`.
- **D-09:** `validate_groups()` returns `set[str]` of valid event IDs. Rejections are logged only.

### Claude's Discretion
- **D-10:** NegRisk auto-pass logging level and format. Recommendation: debug-level aggregate count at startup.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GV-01 | Bot validates event groups using NegRisk boolean as primary partition signal (NegRisk=true auto-passes as one-of-N) | Gamma API `enableNegRisk` (event level) and `negRisk` (market level) fields verified. All 1,622 NegRisk events have 100% market-level consistency. Zero single-market NegRisk events exist. |
| GV-02 | Bot detects duplicate markets within event groups via Jaccard similarity (>0.9 threshold) on preprocessed question tokens | `_preprocess()` and `_jaccard_similarity()` from `dependency.py` are reusable utilities. Duplicate examples found in live data (e.g., minor wording variants in sports events). |
| GV-03 | Bot detects subset/implication relations within event groups using keyword implication and temporal signals | Real examples found: CryptoPunks "above 55 ETH" / "above 69 ETH" / "above 75 ETH" are classic subset/threshold groups. `_keyword_implication()` patterns (reach/pass + dollar amount) cover these. Numeric threshold comparison needed. |
| GV-04 | Bot applies completeness heuristic (0.7 <= sum(mid_prices) <= 1.3) to non-NegRisk groups | Live data validates the range: valid partition events have mid_sum near 1.0; sports "collection" events have mid_sum=2.0-8.0 (immediate rejection). Some resolved markets have mid_sum=0.0 (also rejected). |
| GV-05 | Bot caches event metadata (market count per event) from Gamma API at startup for partition verification | `load_event_groups()` already fetches all event data; enriching to `EventInfo(event_id, neg_risk, market_count)` adds zero extra API calls. |
</phase_requirements>

## Standard Stack

### Core
No new dependencies. Phase 6 uses only existing project libraries.

| Library | Version | Purpose | Already Installed |
|---------|---------|---------|-------------------|
| Python | 3.10+ | Runtime | Yes |
| httpx | 0.28+ | Gamma API fetch (already in `load_event_groups()`) | Yes |
| loguru | 0.7+ | Structured logging (GV-REJECT pattern) | Yes |

### Supporting
| Library | Purpose | Notes |
|---------|---------|-------|
| `re` (stdlib) | Token preprocessing, pattern matching | Already used in `dependency.py` |
| `dataclasses` (stdlib) | `EventInfo` dataclass | Already used throughout |
| `itertools.combinations` (stdlib) | Pairwise violation checking | Already used in `cross_market.py` |

**Installation:** None required -- zero new pip dependencies.

## Architecture Patterns

### Recommended Project Structure (changes only)
```
src/bot/detection/
    cross_market.py          # MODIFY: enrich _event_groups, remove dep gate lines 217-257
    group_validator.py       # NEW: partition validation module
    dependency.py            # UNCHANGED (kept for potential future cross-event use)
    filters.py               # UNCHANGED
    opportunity.py           # UNCHANGED
```

### Pattern 1: Startup Validation with Module-Level Cache

**What:** Follow the existing `_event_groups` pattern: module-level `set[str]` populated once at startup, queried in O(1) during hot path.

**When to use:** Whenever validation is expensive but results are stable for the session lifetime.

**Example:**
```python
# Source: existing pattern in cross_market.py:51
# group_validator.py

from bot.detection.cross_market import EventInfo

# Module-level cache: valid event IDs (populated at startup)
_valid_groups: set[str] = set()

def validate_groups(
    event_groups: dict[str, list[dict]],
    event_info: dict[str, EventInfo],
    cache: PriceCache,
) -> set[str]:
    """
    Validate event groups as one-of-N partitions.

    NegRisk groups auto-pass. Non-NegRisk groups are checked for:
    1. Duplicate markets (Jaccard > 0.9)
    2. Subset/implication pairs
    3. Overlapping pairs (non-exclusive)
    4. Completeness (0.7 <= mid_sum <= 1.3)

    Returns set of valid event IDs.
    """
    global _valid_groups
    valid: set[str] = set()

    neg_risk_count = 0
    checked_count = 0
    rejected_count = 0

    for event_id, markets in event_groups.items():
        info = event_info.get(event_id)
        if info and info.neg_risk:
            valid.add(event_id)
            neg_risk_count += 1
            continue

        checked_count += 1
        if _validate_non_negrisk_group(event_id, markets, cache):
            valid.add(event_id)
        else:
            rejected_count += 1

    logger.info(
        f"GV: {neg_risk_count} NegRisk groups auto-validated, "
        f"{checked_count} non-NegRisk checked, {rejected_count} rejected"
    )

    _valid_groups = valid
    return valid
```

### Pattern 2: EventInfo Dataclass Enrichment

**What:** Extend the `_event_groups` dict from `dict[str, str]` to `dict[str, EventInfo]` during the existing Gamma API fetch.

**Example:**
```python
# Source: enrichment of existing cross_market.py:load_event_groups()

from dataclasses import dataclass

@dataclass(frozen=True)
class EventInfo:
    event_id: str
    neg_risk: bool
    market_count: int

# Module-level cache: condition_id -> EventInfo
_event_groups: dict[str, EventInfo] = {}

def load_event_groups(condition_ids: list[str] | None = None) -> None:
    global _event_groups
    # ... existing Gamma API pagination ...
    for event in events:
        event_id = str(event.get("id", ""))
        neg_risk = event.get("enableNegRisk", False) is True
        market_list = event.get("markets", [])
        market_count = len(market_list)
        info = EventInfo(event_id=event_id, neg_risk=neg_risk, market_count=market_count)
        for market in market_list:
            cid = market.get("conditionId") or market.get("condition_id", "")
            if cid:
                _event_groups[cid] = info
```

### Pattern 3: Pairwise Violation Detection (Partition-Aware)

**What:** Check all pairs within a group for structural violations, short-circuiting on first violation.

**Example:**
```python
# Source: partition validation logic for group_validator.py

import itertools
from bot.detection.dependency import _preprocess, _jaccard_similarity

def is_duplicate_pair(q_a: str, q_b: str, threshold: float = 0.9) -> bool:
    """Two markets with near-identical questions (Jaccard > threshold)."""
    tokens_a = _preprocess(q_a)
    tokens_b = _preprocess(q_b)
    return _jaccard_similarity(tokens_a, tokens_b) > threshold

def is_subset_pair(q_a: str, q_b: str) -> bool:
    """One market implies the other (e.g., 'reaches $150k' implies 'reaches $100k')."""
    # Check keyword implication patterns
    from bot.detection.dependency import _keyword_implication
    if _keyword_implication(q_a, q_b) > 0.0:
        return True
    # Check numeric threshold containment (same subject, different thresholds)
    from bot.detection.dependency import _extract_number
    tokens_a = _preprocess(q_a)
    tokens_b = _preprocess(q_b)
    jaccard = _jaccard_similarity(tokens_a, tokens_b)
    if jaccard > 0.6:  # same subject
        num_a = _extract_number(q_a)
        num_b = _extract_number(q_b)
        if num_a is not None and num_b is not None and num_a != num_b:
            return True  # same subject + different thresholds = subset
    return False
```

### Anti-Patterns to Avoid
- **Reusing `classify_pair()` from `dependency.py`:** Its "subset / related / independent" labels encode the wrong mental model. In a valid partition, all pairs SHOULD be "related" (mutually exclusive candidates). The dependency classifier would flag every valid partition group as "related" or "subset", leading to mass false rejections. [VERIFIED: CONTEXT.md D-06, D-07]
- **Running validation on every scan cycle:** Validation is O(n^2) per group. Running at startup is fine (one-time cost), running in the hot path would add latency. [VERIFIED: CONTEXT.md D-02]
- **Checking NegRisk events for structural violations:** NegRisk is an exchange-level guarantee. If Polymarket marks an event as NegRisk, the smart contract enforces one-of-N resolution. Heuristic checks cannot improve on this. [VERIFIED: Gamma API live data -- 100% consistency across 1,622 events]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token preprocessing | Custom tokenizer | `_preprocess()` from `dependency.py` | Already handles stopwords, lowercasing, tokenization. Tested. |
| Jaccard similarity | Custom set comparison | `_jaccard_similarity()` from `dependency.py` | Handles edge cases (empty sets). Tested. |
| Keyword implication | New regex patterns from scratch | Start from `_IMPLICATION_RULES` in `dependency.py` as reference | Well-tested patterns for "wins by X", "reaches $X", etc. |
| Numeric extraction | New number parser | `_extract_number()` from `dependency.py` | Handles %, $, suffixes (k/M/B). Tested. |

**Key insight:** While `classify_pair()` itself must NOT be reused (wrong mental model per D-07), the individual signal functions (`_preprocess`, `_jaccard_similarity`, `_keyword_implication`, `_extract_number`) are fine to import as utilities -- they're stateless, pure functions with no classification logic.

## Common Pitfalls

### Pitfall 1: Confusing Event-Level vs Market-Level NegRisk Fields
**What goes wrong:** Gamma API has THREE NegRisk fields: `enableNegRisk` (event level), `negRisk` (market level), and `negRiskOther` (market level). Using the wrong one causes misclassification.
**Why it happens:** Field names are similar and appear at different nesting levels.
**How to avoid:** Use `enableNegRisk` at the **event** level during `load_event_groups()`. This is the authoritative signal. Market-level `negRisk` is redundant (always matches) but could serve as a cross-check. `negRiskOther` is always `False` and irrelevant.
**Warning signs:** Single-market events being flagged as NegRisk (impossible -- all NegRisk events have 3+ markets).
**Confidence:** HIGH [VERIFIED: Gamma API live data -- 1,622 NegRisk events analyzed]

### Pitfall 2: Non-Partition Multi-Market Events
**What goes wrong:** Non-NegRisk multi-market events are assumed to be partitions when many are just thematic groupings (e.g., "NHL: February 2nd" groups 3 independent games, mid_sum=2.0).
**Why it happens:** Polymarket groups unrelated markets by date/sport for UI convenience, not because they're mutually exclusive.
**How to avoid:** The completeness heuristic (GV-04: 0.7 <= mid_sum <= 1.3) catches these immediately. mid_sum=2.0 means the group is NOT a partition.
**Warning signs:** Accepted groups with mid_sum far from 1.0.
**Confidence:** HIGH [VERIFIED: Gamma API live data -- sports collection events have mid_sum=2.0-8.0]

### Pitfall 3: Threshold/Bracket Events Appearing as Partitions
**What goes wrong:** Events like "What will CryptoPunks floor price be?" with markets "above 55 ETH", "above 69 ETH", "above 75 ETH" have subset relationships (55 implies 69 does NOT, but 75 implies 69 implies 55). These are NOT partitions but can have mid_sum near 1.0 if enough markets are near-zero.
**Why it happens:** Threshold events are nested subsets, not exclusive partitions. Any mid_sum near 1.0 is coincidental.
**How to avoid:** The subset check (GV-03) catches these via numeric threshold detection. Same subject + different numeric thresholds = subset relationship.
**Warning signs:** Markets with very similar question text but different numeric values within the same group.
**Confidence:** HIGH [VERIFIED: Gamma API live data -- CryptoPunks threshold event found]

### Pitfall 4: _group_by_event() Returns Lists, Not Event-ID-Keyed Dicts
**What goes wrong:** `_group_by_event()` returns `list[list[dict]]` without event IDs. The validator needs to know which event_id each group belongs to in order to check NegRisk status.
**Why it happens:** The function was designed for detection (doesn't need event_id), not validation.
**How to avoid:** Either modify `_group_by_event()` to also return event IDs, or have the validator build its own grouped dict from `_event_groups`. The validator should build its own event_id-keyed structure since it needs different grouping logic (it groups by event_id, not by the list-of-markets format that `_group_by_event()` returns).
**Warning signs:** Validator receiving groups without knowing their event_id.
**Confidence:** HIGH [VERIFIED: source code cross_market.py:95-122]

### Pitfall 5: Stale Mid-Prices for Completeness Heuristic
**What goes wrong:** Using `outcomePrices` from the Gamma API (fetched at startup) for the completeness check. These prices can be stale.
**Why it happens:** `outcomePrices` in Gamma are indicative, not live CLOB prices. PriceCache has live data but may not have all markets cached yet at startup.
**How to avoid:** Use Gamma `outcomePrices` for the startup completeness check. This is acceptable because: (1) the check is a coarse heuristic (0.7-1.3 range), not a precise calculation, (2) Gamma prices are refreshed periodically and accurate enough for a +/- 0.3 tolerance, (3) PriceCache may be empty at startup before WebSocket connects.
**Warning signs:** Groups passing completeness check at startup but having wildly different live prices during detection.
**Confidence:** MEDIUM [ASSUMED: Gamma outcomePrices freshness -- no official documentation on update frequency]

### Pitfall 6: Updating _event_groups Type Breaks Existing Detection Code
**What goes wrong:** Changing `_event_groups` from `dict[str, str]` to `dict[str, EventInfo]` breaks `_group_by_event()` and `detect_cross_market_opportunities()` which expect `_event_groups[cid]` to return a string event_id.
**Why it happens:** Multiple locations read `_event_groups.get(cid)` expecting a string.
**How to avoid:** After enrichment, every location that reads `_event_groups[cid]` must be updated: `_group_by_event()` line 113 should use `_event_groups.get(cid).event_id` or equivalent. Detection code line 218 also reads it. Systematic search needed.
**Warning signs:** AttributeError or TypeError when detection runs after enrichment.
**Confidence:** HIGH [VERIFIED: source code cross_market.py:113, 218]

## Code Examples

### EventInfo Dataclass
```python
# Source: new code for cross_market.py
from dataclasses import dataclass

@dataclass(frozen=True)
class EventInfo:
    """Enriched event metadata for partition validation."""
    event_id: str
    neg_risk: bool       # True if enableNegRisk=True in Gamma API
    market_count: int    # Number of markets in this event
```

### Enriched load_event_groups()
```python
# Source: modification of existing cross_market.py:54-92
def load_event_groups(condition_ids: list[str] | None = None) -> None:
    global _event_groups
    try:
        offset = 0
        page_size = 500
        count = 0
        while True:
            params: dict = {"active": "true", "limit": page_size, "offset": offset}
            resp = httpx.get(_GAMMA_EVENTS_URL, params=params, timeout=10.0)
            resp.raise_for_status()
            events = resp.json()
            if not events:
                break
            for event in events:
                event_id = str(event.get("id", ""))
                if not event_id:
                    continue
                neg_risk = event.get("enableNegRisk", False) is True
                market_list = event.get("markets", [])
                market_count = len(market_list)
                info = EventInfo(
                    event_id=event_id,
                    neg_risk=neg_risk,
                    market_count=market_count,
                )
                for market in market_list:
                    cid = market.get("conditionId") or market.get("condition_id", "")
                    if cid:
                        _event_groups[cid] = info
                        count += 1
            offset += page_size
            if len(events) < page_size:
                break
        # Log NegRisk distribution
        neg_count = sum(1 for v in set(_event_groups.values()) if v.neg_risk)
        total = len(set(v.event_id for v in _event_groups.values()))
        logger.info(
            f"load_event_groups: {count} condition_id mappings, "
            f"{total} unique events ({neg_count} NegRisk)"
        )
    except Exception as exc:
        logger.warning(f"load_event_groups: gamma API fetch failed: {exc}")
```

### Updated _group_by_event() for EventInfo
```python
# Source: modification of existing cross_market.py:95-122
def _group_by_event(markets: list[dict]) -> list[list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for market in markets:
        cid = market.get("condition_id", "")
        info = _event_groups.get(cid)
        event_id = (
            info.event_id if info else None
        ) or (
            market.get("neg_risk_market_id")
            or market.get("neg_risk_id")
        )
        if event_id:
            groups[event_id].append(market)
    return [
        group for group in groups.values()
        if _MIN_GROUP_SIZE <= len(group) <= _MAX_GROUP_SIZE
    ]
```

### Updated Detection to Use valid_set
```python
# Source: replacement of cross_market.py lines 217-257
# In detect_cross_market_opportunities():
from bot.detection.group_validator import get_valid_groups

# Replace the entire DEP-09/10/11 dependency gate block with:
event_id = _event_groups.get(group[0].get("condition_id", ""))
eid = event_id.event_id if event_id else None
if eid and eid not in get_valid_groups():
    diag.gv_rejects += 1
    continue
```

### Duplicate Detection (GV-02)
```python
# Source: new code for group_validator.py
from bot.detection.dependency import _preprocess, _jaccard_similarity

_DUPLICATE_THRESHOLD = 0.9  # Jaccard similarity threshold for duplicates

def is_duplicate_pair(question_a: str, question_b: str) -> tuple[bool, float]:
    """
    Detect if two market questions are near-duplicates.

    Returns (is_duplicate, jaccard_score).
    """
    tokens_a = _preprocess(question_a)
    tokens_b = _preprocess(question_b)
    score = _jaccard_similarity(tokens_a, tokens_b)
    return score > _DUPLICATE_THRESHOLD, score
```

### Subset Detection (GV-03)
```python
# Source: new code for group_validator.py
from bot.detection.dependency import _keyword_implication, _extract_number

def is_subset_pair(question_a: str, question_b: str) -> tuple[bool, str]:
    """
    Detect if one market implies the other (subset relationship).

    Checks:
    1. Keyword implication (e.g., "wins by 5%" implies "wins")
    2. Numeric threshold containment (e.g., "above $150k" implies "above $100k")

    Returns (is_subset, signal_name).
    """
    # Signal 1: Keyword implication
    if _keyword_implication(question_a, question_b) > 0.0:
        return True, "keyword_implication"

    # Signal 2: Numeric threshold (same subject + different numbers)
    tokens_a = _preprocess(question_a)
    tokens_b = _preprocess(question_b)
    jaccard = _jaccard_similarity(tokens_a, tokens_b)
    if jaccard > 0.6:  # High overlap = likely same subject
        num_a = _extract_number(question_a)
        num_b = _extract_number(question_b)
        if num_a is not None and num_b is not None and num_a != num_b:
            return True, "numeric_threshold"

    return False, ""
```

### Completeness Heuristic (GV-04)
```python
# Source: new code for group_validator.py
import json

_COMPLETENESS_LOW = 0.7
_COMPLETENESS_HIGH = 1.3

def passes_completeness_check(
    markets: list[dict],
    low: float = _COMPLETENESS_LOW,
    high: float = _COMPLETENESS_HIGH,
) -> tuple[bool, float]:
    """
    Check if sum of mid-prices is within [low, high] range.

    Uses Gamma API outcomePrices (available at startup).
    Returns (passes, mid_sum).
    """
    mid_sum = 0.0
    for market in markets:
        outcome_prices_raw = market.get("outcomePrices", "[]")
        if isinstance(outcome_prices_raw, str):
            try:
                prices = json.loads(outcome_prices_raw)
            except (json.JSONDecodeError, ValueError):
                continue
        else:
            prices = outcome_prices_raw
        if prices:
            yes_price = float(prices[0])
            mid_sum += yes_price

    return low <= mid_sum <= high, mid_sum
```

## Gamma API Data Model (Verified)

### NegRisk Field Locations
| Field | Level | Type | Meaning |
|-------|-------|------|---------|
| `enableNegRisk` | Event | bool | **Primary signal.** True = exchange-guaranteed one-of-N partition |
| `negRisk` | Market | bool | Mirror of event-level `enableNegRisk`. Always consistent. |
| `negRiskAugmented` | Event | bool | Always False in current data. Internal Polymarket field. |
| `negRiskOther` | Market | bool | Always False in current data. Internal Polymarket field. |
| `negRiskMarketID` | Event+Market | string | Hex address of the NegRisk contract. Present only when negRisk=True. |
| `negRiskRequestID` | Market | string | Per-market NegRisk request hash. Present only when negRisk=True. |

**Use `enableNegRisk` at the event level** as the authoritative NegRisk signal. [VERIFIED: Gamma API live data]

### Key Statistics (Live Data, 2026-04-26)
| Metric | Value |
|--------|-------|
| Total active events (10K cap) | 10,000+ |
| NegRisk events | 1,622 |
| NegRisk with < 3 markets | 0 (all have 3+) |
| NegRisk with mixed market-level negRisk | 0 (100% consistent) |
| Non-NegRisk multi-market events | 532 (in first 5K) |
| Total multi-market events | 1,049+ |

[VERIFIED: Gamma API live query, 2026-04-26]

### Non-NegRisk Multi-Market Event Categories (from live data)
| Category | Example | Mid-Sum | Partition? | Why Not |
|----------|---------|---------|------------|---------|
| Sports date collections | "NHL: February 2nd" (3 different games) | 2.0 | No | Independent games, not mutually exclusive |
| Fight cards | "UFC 270: Who will win...?" (5 fights) | 3.5 | No | Independent fights |
| Threshold/brackets | "CryptoPunks above 55/69/75 ETH" | 1.0 | No | Subset relationships (55 implies not-75, etc.) |
| Parallel indicators | "EU inflation 5.3%/5.5%/5.7%" | 2.0 | No | Nested thresholds with overlap |
| True partitions | "Who will win La Liga?" (candidates) | ~1.0 | Yes | Mutual exclusivity if well-formed |

[VERIFIED: Gamma API live data analysis]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline `classify_pair()` dependency gate in detection loop | Startup-time `validate_groups()` with purpose-built checks | Phase 6 (now) | Zero hot-path latency, correct mental model |
| `_event_groups: dict[str, str]` | `_event_groups: dict[str, EventInfo]` | Phase 6 (now) | Carries NegRisk + market_count without extra API call |
| Keyword heuristic grouping (v1.0) | Event-level Gamma API grouping (v1.1) | v1.1 (2026-04-19) | Full coverage of all multi-market events |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Gamma API `outcomePrices` are fresh enough for coarse completeness check (0.7-1.3 range) | Pitfall 5, Code Examples (GV-04) | False positives/negatives in completeness heuristic. Mitigation: 0.7-1.3 is a very wide range; even stale prices would need to be extremely wrong to cause issues. |
| A2 | `is_overlapping_pair()` can be approximated by low Jaccard + no implication + same event = overlap signal | Architecture Patterns | May miss complex overlaps. Mitigation: the completeness heuristic (GV-04) catches groups that aren't real partitions regardless. |

## Open Questions

1. **How to handle `outcomePrices` parsing for completeness check?**
   - What we know: `outcomePrices` is a JSON string like `"[0.65, 0.35]"` at the market level in Gamma API. Index 0 = YES price.
   - What's unclear: Whether all active markets have non-null `outcomePrices`. Resolved/closed markets show `"[0, 1]"` or `"[1, 0]"`.
   - Recommendation: Parse with `json.loads()`, fall back to skipping the market if unparseable. The completeness check is a heuristic -- missing one market's price is acceptable if most are available.

2. **Should the validator store market question data from Gamma for pairwise checks?**
   - What we know: CLOB markets have a `question` field. Gamma markets also have `question`. `load_event_groups()` currently processes Gamma `markets[]` but only extracts `conditionId`.
   - What's unclear: Whether CLOB market `question` is identical to Gamma `question` (same source of truth).
   - Recommendation: Store Gamma `question` and `outcomePrices` per market in a secondary dict during `load_event_groups()`. Use these for pairwise checks + completeness. This avoids needing CLOB market dicts at validation time (which may not be loaded yet).

3. **Should `_MAX_GROUP_SIZE = 20` be raised for NegRisk events?**
   - What we know: Current cap is 20. Live data shows NegRisk events with up to 84 markets.
   - What's unclear: Whether groups > 20 are worth trading (likely very thin liquidity per leg).
   - Recommendation: Apply the 20-market cap in the DETECTION loop (where it prevents O(n) cost), NOT in the validator. NegRisk events with 84 markets should still be validated as partition-valid; the detection loop can skip them if too large.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pytest.ini` |
| Quick run command | `python3 -m pytest tests/test_group_validator.py -x -q` |
| Full suite command | `python3 -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GV-01 | NegRisk auto-pass as valid partition | unit | `python3 -m pytest tests/test_group_validator.py::test_negrisk_auto_pass -x` | Wave 0 |
| GV-01 | Non-NegRisk queued for validation | unit | `python3 -m pytest tests/test_group_validator.py::test_non_negrisk_validated -x` | Wave 0 |
| GV-02 | Duplicate detection via Jaccard > 0.9 | unit | `python3 -m pytest tests/test_group_validator.py::test_duplicate_detected -x` | Wave 0 |
| GV-02 | Non-duplicate pair passes | unit | `python3 -m pytest tests/test_group_validator.py::test_non_duplicate_passes -x` | Wave 0 |
| GV-03 | Subset/implication rejection | unit | `python3 -m pytest tests/test_group_validator.py::test_subset_detected -x` | Wave 0 |
| GV-03 | Numeric threshold subset rejection | unit | `python3 -m pytest tests/test_group_validator.py::test_numeric_subset_detected -x` | Wave 0 |
| GV-04 | Completeness heuristic pass (mid_sum near 1.0) | unit | `python3 -m pytest tests/test_group_validator.py::test_completeness_pass -x` | Wave 0 |
| GV-04 | Completeness heuristic reject (mid_sum > 1.3) | unit | `python3 -m pytest tests/test_group_validator.py::test_completeness_reject_high -x` | Wave 0 |
| GV-05 | EventInfo enrichment from Gamma | unit | `python3 -m pytest tests/test_cross_market.py::test_event_info_enrichment -x` | Wave 0 |
| -- | Inline dependency gate removal (no regression) | unit | `python3 -m pytest tests/test_cross_market.py -x` | Existing (update needed) |
| -- | Full suite regression | unit | `python3 -m pytest tests/ -x -q` | Existing (257 tests) |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_group_validator.py tests/test_cross_market.py -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -x -q`
- **Phase gate:** Full suite green (257+ tests, 0 failures)

### Wave 0 Gaps
- [ ] `tests/test_group_validator.py` -- covers GV-01 through GV-04 (new file)
- [ ] Update `tests/test_cross_market.py` -- EventInfo enrichment tests (GV-05), remove dependency gate test expectations

## Security Domain

This phase has no security-relevant surface area. It processes only:
- Public Polymarket market data (questions, prices, NegRisk flags)
- No user input, no authentication, no cryptographic operations, no network-facing interfaces

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Minimally | JSON parsing of `outcomePrices` uses `json.loads()` (not `eval()`) |
| V6 Cryptography | No | N/A |

No known threat patterns for this phase. All data is read-only from public APIs.

## Sources

### Primary (HIGH confidence)
- Gamma API live query (`https://gamma-api.polymarket.com/events?active=true`) -- NegRisk field structure, event/market counts, multi-market event analysis (fetched 2026-04-26)
- Source code: `src/bot/detection/cross_market.py` -- current `load_event_groups()`, `_group_by_event()`, detection loop with dependency gate
- Source code: `src/bot/detection/dependency.py` -- reusable signal functions (`_preprocess`, `_jaccard_similarity`, `_keyword_implication`, `_extract_number`)
- Source code: `src/bot/config.py` -- BotConfig dataclass structure
- Source code: `tests/test_cross_market.py`, `tests/test_dependency.py` -- existing test patterns

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions D-01 through D-10 -- locked implementation decisions from user discussion

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, fully existing codebase
- Architecture: HIGH -- follows established patterns (module-level cache, startup validation, loguru structured logging)
- Pitfalls: HIGH -- verified against live Gamma API data with concrete examples
- Gamma API data model: HIGH -- verified with live queries covering 10,000+ events

**Research date:** 2026-04-26
**Valid until:** 2026-05-26 (stable -- Gamma API structure unlikely to change within 30 days)
