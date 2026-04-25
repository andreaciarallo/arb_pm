"""
Dependency detection signals for market question pair classification.

Classifies pairs of Polymarket market questions as subset, related, or
independent using five weighted signals: semantic overlap (Jaccard),
keyword implication, numeric relation, time relation, and event bonus.

Pure module -- zero imports from scanner, execution, or network modules.
All inputs passed as function parameters (D-03).
"""
import re
import calendar
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "will", "be", "been",
    "do", "does", "did", "have", "has", "had", "of", "in", "to", "for",
    "on", "at", "by", "from", "with", "as", "or", "and", "but", "if",
    "it", "its", "this", "that", "than", "any", "more", "not", "no",
])

DEFAULT_WEIGHTS = {
    "jaccard": 0.20,
    "implication": 0.15,
    "numeric": 0.10,
    "temporal": 0.30,
    "event_bonus": 0.25,
}
# Weights tuned against validation set of real Polymarket question pairs:
# - Temporal signal gets highest weight (0.30) because most multi-market events
#   are deadline variants where date ordering is the primary discriminator.
# - Event bonus gets second highest (0.25) because same-event pairs are the main
#   signal for "related" classification of candidate-variant markets.
# - Jaccard reduced to 0.20 to avoid Pitfall 1 (overweighting on candidate-style
#   events where only the subject differs).

DEFAULT_THRESHOLDS = {
    "subset": 0.50,
    "related": 0.30,
}
# Thresholds calibrated for DEFAULT_WEIGHTS against validation set:
# - subset >= 0.50: deadline variants (jaccard + temporal + event_bonus) score 0.58-0.68
# - related >= 0.30: candidate variants (jaccard + event_bonus only) score 0.34-0.39
# - independent < 0.30: cross-domain pairs score 0.02-0.04

# Month name -> month number mapping (lowercase keys)
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}

# Implication rules: (child_pattern, parent_pattern) regex tuples
# If question_a matches child AND question_b matches parent (or vice versa),
# there is an implication relationship.
_IMPLICATION_RULES = [
    (re.compile(r'wins?\s+by\s+\d', re.IGNORECASE),
     re.compile(r'\bwins?\b', re.IGNORECASE)),
    (re.compile(r'beats?\s+.*\s+by\s+\d', re.IGNORECASE),
     re.compile(r'\bbeats?\b', re.IGNORECASE)),
    (re.compile(r'reach(?:es)?\s+\$[\d,]+[kKmMbB]?', re.IGNORECASE),
     re.compile(r'\breach(?:es)?\b', re.IGNORECASE)),
    (re.compile(r'pass(?:es)?\s+\$[\d,]+[kKmMbB]?', re.IGNORECASE),
     re.compile(r'\bpass(?:es)?\b', re.IGNORECASE)),
    (re.compile(r'more\s+than\s+\d', re.IGNORECASE),
     re.compile(r'\bmore\b', re.IGNORECASE)),
]

# Date extraction pattern covering all 4 Polymarket formats:
#   "by Month Day, Year" | "by Month Day" | "in Year" | year-only
# Uses \b word boundary to prevent matching "in" suffix of words like "Bitcoin"
_DATE_PATTERN = re.compile(
    r'\b(?:by|in|before)\s+'
    r'(?:'
    r'(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?'  # Month Day[, Year]
    r'|'
    r'(\d{4})'  # standalone year
    r')',
    re.IGNORECASE,
)

# Numeric extraction patterns (applied in priority order)
_PCT_PATTERN = re.compile(r'(\d+\.?\d*)%')
_DOLLAR_PATTERN = re.compile(r'\$([\d,]+\.?\d*)([kKmMbB])?')
_PLAIN_NUM_PATTERN = re.compile(r'\b(\d+\.\d+)\b')

_DOLLAR_SUFFIX_MULTIPLIER = {
    'k': 1_000, 'K': 1_000,
    'm': 1_000_000, 'M': 1_000_000,
    'b': 1_000_000_000, 'B': 1_000_000_000,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# DEP-01: Preprocessing
# ---------------------------------------------------------------------------

def _preprocess(question: str) -> frozenset[str]:
    """Tokenize, lowercase, strip stopwords. Returns frozenset for set ops."""
    tokens = re.findall(r'\w+', question.lower())
    return frozenset(t for t in tokens if t not in _STOPWORDS)


# ---------------------------------------------------------------------------
# DEP-02: Jaccard similarity
# ---------------------------------------------------------------------------

def _jaccard_similarity(tokens_a: frozenset[str], tokens_b: frozenset[str]) -> float:
    """Semantic overlap via Jaccard similarity on preprocessed token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# DEP-03: Keyword implication
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# DEP-04: Numeric relation
# ---------------------------------------------------------------------------

def _extract_number(question: str) -> float | None:
    """Extract a single numeric value from a question string.

    Priority: percentages > dollar amounts > plain decimals.
    Returns None if no number found.
    """
    # Try percentage first
    match = _PCT_PATTERN.search(question)
    if match:
        return float(match.group(1))

    # Try dollar amount
    match = _DOLLAR_PATTERN.search(question)
    if match:
        raw = match.group(1).replace(",", "")
        value = float(raw)
        suffix = match.group(2)
        if suffix:
            value *= _DOLLAR_SUFFIX_MULTIPLIER.get(suffix, 1)
        return value

    # Try plain decimal
    match = _PLAIN_NUM_PATTERN.search(question)
    if match:
        return float(match.group(1))

    return None


def _numeric_relation(question_a: str, question_b: str) -> float:
    """Numeric threshold/range containment on original question strings."""
    num_a = _extract_number(question_a)
    num_b = _extract_number(question_b)

    if num_a is None or num_b is None:
        return 0.0

    # One must be strictly greater than the other for containment
    if num_a != num_b:
        return 1.0

    return 0.0


# ---------------------------------------------------------------------------
# DEP-05: Time relation
# ---------------------------------------------------------------------------

def _extract_date(question: str) -> tuple[int, int, int] | None:
    """Extract a date tuple (year, month, day) from a question string.

    Handles all 4 Polymarket formats:
      - "in 2025"           -> (2025, 12, 31)
      - "by December 31"    -> (current_year, 12, 31)
      - "by March 31, 2026" -> (2026, 3, 31)
      - "by June 30, 2026?" -> (2026, 6, 30)
    """
    match = _DATE_PATTERN.search(question)
    if not match:
        return None

    month_str, day_str, year_str, standalone_year = match.groups()

    if standalone_year:
        # Format: "in 2025" -> treat as end of year
        return (int(standalone_year), 12, 31)

    if month_str:
        month_lower = month_str.lower()
        if month_lower not in _MONTHS:
            return None
        month = _MONTHS[month_lower]
        day = int(day_str)
        if year_str:
            year = int(year_str)
        else:
            # No year specified -- use a reference year (2025 as current)
            # For relative ordering, this is fine as long as both dateless
            # questions use the same reference year
            import datetime
            year = datetime.datetime.now().year
        return (year, month, day)

    return None


def _time_relation(question_a: str, question_b: str) -> float:
    """Date/deadline containment on original question strings."""
    date_a = _extract_date(question_a)
    date_b = _extract_date(question_b)

    if date_a is None or date_b is None:
        return 0.0

    # Same date -> not a subset relationship
    if date_a == date_b:
        return 0.0

    # Different dates -> one is earlier, indicating subset relationship
    # Bidirectional: we detect relationship, not direction
    return 1.0


# ---------------------------------------------------------------------------
# DEP-06: Event bonus
# ---------------------------------------------------------------------------

def _event_bonus(event_id_a: str | None, event_id_b: str | None) -> float:
    """Binary signal: 1.0 if same event_id, 0.0 otherwise."""
    if event_id_a is not None and event_id_b is not None and event_id_a == event_id_b:
        return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# DEP-07 / DEP-08: Weighted scorer and classifier (public API)
# ---------------------------------------------------------------------------

def classify_pair(
    question_a: str,
    question_b: str,
    event_id_a: str | None = None,
    event_id_b: str | None = None,
    weights: dict[str, float] | None = None,
    thresholds: dict[str, float] | None = None,
) -> DependencyResult:
    """Classify a pair of market questions as subset, related, or independent.

    Combines five weighted signals into a composite score and applies
    two-threshold classification (D-13, D-15, D-17).

    This is the single public function of the dependency detection module.
    Phase 4 imports this to validate mutual exclusivity of cross-market groups.

    Args:
        question_a: First market question string.
        question_b: Second market question string.
        event_id_a: Optional Gamma API event ID for first market.
        event_id_b: Optional Gamma API event ID for second market.
        weights: Optional signal weight overrides (default: DEFAULT_WEIGHTS).
        thresholds: Optional classification threshold overrides (default: DEFAULT_THRESHOLDS).

    Returns:
        DependencyResult with label, composite score, and individual signal scores.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    else:
        weights = {**DEFAULT_WEIGHTS, **weights}
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS
    else:
        thresholds = {**DEFAULT_THRESHOLDS, **thresholds}

    # DEP-01: Preprocess for Jaccard (only Jaccard uses preprocessed tokens)
    tokens_a = _preprocess(question_a)
    tokens_b = _preprocess(question_b)

    # DEP-02 through DEP-06: Compute all 5 signals
    jaccard = _jaccard_similarity(tokens_a, tokens_b)
    implication = _keyword_implication(question_a, question_b)  # original strings (Pitfall 3)
    numeric = _numeric_relation(question_a, question_b)         # original strings
    temporal = _time_relation(question_a, question_b)           # original strings
    event_bonus_val = _event_bonus(event_id_a, event_id_b)

    # DEP-07: Weighted linear combination (D-13)
    score = (
        weights["jaccard"] * jaccard
        + weights["implication"] * implication
        + weights["numeric"] * numeric
        + weights["temporal"] * temporal
        + weights["event_bonus"] * event_bonus_val
    )

    # DEP-08: Three-way classification (D-15)
    if score >= thresholds["subset"]:
        label = "subset"
    elif score >= thresholds["related"]:
        label = "related"
    else:
        label = "independent"

    return DependencyResult(
        label=label,
        score=score,
        jaccard=jaccard,
        implication=implication,
        numeric=numeric,
        temporal=temporal,
        event_bonus=event_bonus_val,
    )
