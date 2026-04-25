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
    raise NotImplementedError


# ---------------------------------------------------------------------------
# DEP-02: Jaccard similarity
# ---------------------------------------------------------------------------

def _jaccard_similarity(tokens_a: frozenset[str], tokens_b: frozenset[str]) -> float:
    """Semantic overlap via Jaccard similarity on preprocessed token sets."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# DEP-03: Keyword implication
# ---------------------------------------------------------------------------

def _keyword_implication(question_a: str, question_b: str) -> float:
    """Pattern matching for subset relationships on original question strings."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# DEP-04: Numeric relation
# ---------------------------------------------------------------------------

def _numeric_relation(question_a: str, question_b: str) -> float:
    """Numeric threshold/range containment on original question strings."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# DEP-05: Time relation
# ---------------------------------------------------------------------------

def _time_relation(question_a: str, question_b: str) -> float:
    """Date/deadline containment on original question strings."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# DEP-06: Event bonus
# ---------------------------------------------------------------------------

def _event_bonus(event_id_a: str | None, event_id_b: str | None) -> float:
    """Binary signal: 1.0 if same event_id, 0.0 otherwise."""
    raise NotImplementedError
