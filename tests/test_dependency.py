"""
Tests for dependency detection signals (DEP-01 through DEP-06) and DependencyResult.

Covers preprocessing, five signal extractors, and the result dataclass.
Uses real Polymarket question strings from Gamma API validation set.
"""
import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# DEP-01: Preprocessing (_preprocess)
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
    assert "will" not in tokens
    assert "the" not in tokens
    assert "of" not in tokens
    assert "be" not in tokens
    assert "bitcoin" in tokens
    assert "price" in tokens
    assert "higher" in tokens


def test_preprocess_returns_frozenset():
    from bot.detection.dependency import _preprocess
    result = _preprocess("Will Bitcoin REACH $100k?")
    assert isinstance(result, frozenset)


def test_preprocess_empty_string():
    from bot.detection.dependency import _preprocess
    result = _preprocess("")
    assert result == frozenset()


# ---------------------------------------------------------------------------
# DEP-02: Jaccard similarity (_jaccard_similarity)
# ---------------------------------------------------------------------------

def test_jaccard_identical_sets():
    from bot.detection.dependency import _jaccard_similarity
    assert _jaccard_similarity(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0


def test_jaccard_disjoint_sets():
    from bot.detection.dependency import _jaccard_similarity
    assert _jaccard_similarity(frozenset({"a"}), frozenset({"b"})) == 0.0


def test_jaccard_partial_overlap():
    from bot.detection.dependency import _jaccard_similarity
    score = _jaccard_similarity(frozenset({"a", "b", "c"}), frozenset({"b", "c", "d"}))
    assert score == pytest.approx(0.5)  # 2 shared / 4 total


def test_jaccard_empty_set():
    from bot.detection.dependency import _jaccard_similarity
    assert _jaccard_similarity(frozenset(), frozenset({"a"})) == 0.0


# ---------------------------------------------------------------------------
# DEP-03: Keyword implication (_keyword_implication)
# ---------------------------------------------------------------------------

def test_implication_win_by_x_implies_win():
    from bot.detection.dependency import _keyword_implication
    score = _keyword_implication("Will team X win by 5%?", "Will team X win?")
    assert score > 0.0


def test_implication_no_relationship():
    from bot.detection.dependency import _keyword_implication
    score = _keyword_implication("Kraken IPO?", "Bitcoin reaches $100k?")
    assert score == 0.0


def test_implication_reach_higher_implies_lower():
    from bot.detection.dependency import _keyword_implication
    score = _keyword_implication("Bitcoin reaches $150k?", "Bitcoin reaches $100k?")
    assert score > 0.0


# ---------------------------------------------------------------------------
# DEP-04: Numeric relation (_numeric_relation)
# ---------------------------------------------------------------------------

def test_numeric_subset_percentage():
    from bot.detection.dependency import _numeric_relation
    score = _numeric_relation("win by 10%?", "win by 5%?")
    assert score > 0.0


def test_numeric_no_numbers():
    from bot.detection.dependency import _numeric_relation
    score = _numeric_relation("Will it rain?", "Will it snow?")
    assert score == 0.0


def test_numeric_dollar_amounts():
    from bot.detection.dependency import _numeric_relation
    score = _numeric_relation("reach $150k?", "reach $100k?")
    assert score > 0.0


# ---------------------------------------------------------------------------
# DEP-05: Time relation (_time_relation)
# ---------------------------------------------------------------------------

def test_time_in_year_vs_by_date():
    from bot.detection.dependency import _time_relation
    score = _time_relation("Kraken IPO in 2025?", "Kraken IPO by December 31, 2026?")
    assert score > 0.0


def test_time_earlier_by_date():
    from bot.detection.dependency import _time_relation
    score = _time_relation(
        "Macron out by October 31, 2025?",
        "Macron out by June 30, 2026?",
    )
    assert score > 0.0


def test_time_no_dates():
    from bot.detection.dependency import _time_relation
    score = _time_relation("Will it rain?", "Will it snow?")
    assert score == 0.0


def test_time_same_date():
    from bot.detection.dependency import _time_relation
    score = _time_relation("IPO by March 31, 2026?", "IPO by March 31, 2026?")
    assert score == 0.0  # same date = not subset


def test_time_by_month_day_no_year():
    from bot.detection.dependency import _time_relation
    score = _time_relation("out by October 31?", "out by December 31?")
    assert score > 0.0


# ---------------------------------------------------------------------------
# DEP-06: Event bonus (_event_bonus)
# ---------------------------------------------------------------------------

def test_event_bonus_same_id():
    from bot.detection.dependency import _event_bonus
    assert _event_bonus("evt-1", "evt-1") == 1.0


def test_event_bonus_different_id():
    from bot.detection.dependency import _event_bonus
    assert _event_bonus("evt-1", "evt-2") == 0.0


def test_event_bonus_none_ids():
    from bot.detection.dependency import _event_bonus
    assert _event_bonus(None, None) == 0.0


def test_event_bonus_one_none():
    from bot.detection.dependency import _event_bonus
    assert _event_bonus("evt-1", None) == 0.0


# ---------------------------------------------------------------------------
# DependencyResult dataclass
# ---------------------------------------------------------------------------

def test_dependency_result_frozen():
    from bot.detection.dependency import DependencyResult
    result = DependencyResult(
        label="independent",
        score=0.0,
        jaccard=0.0,
        implication=0.0,
        numeric=0.0,
        temporal=0.0,
        event_bonus=0.0,
    )
    with pytest.raises(AttributeError):
        result.label = "subset"


def test_dependency_result_fields():
    from bot.detection.dependency import DependencyResult
    result = DependencyResult(
        label="subset",
        score=0.85,
        jaccard=0.6,
        implication=1.0,
        numeric=0.0,
        temporal=1.0,
        event_bonus=1.0,
    )
    assert result.label == "subset"
    assert result.score == 0.85
    assert result.jaccard == 0.6
    assert result.implication == 1.0
    assert result.numeric == 0.0
    assert result.temporal == 1.0
    assert result.event_bonus == 1.0


# ---------------------------------------------------------------------------
# DEP-07: Weighted scorer
# ---------------------------------------------------------------------------

def test_scorer_all_zeros():
    """Two completely unrelated questions with different events produce score ~0.0."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "Will it rain tomorrow?",
        "Is the moon made of cheese?",
        event_id_a="evt-rain",
        event_id_b="evt-moon",
    )
    assert result.score == pytest.approx(0.0, abs=0.05)


def test_scorer_weights_sum_to_one():
    """DEFAULT_WEIGHTS values must sum to 1.0 (Pitfall 4)."""
    from bot.detection.dependency import DEFAULT_WEIGHTS
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_scorer_max_score():
    """Identical questions with same event_id produce score close to 1.0."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "Bitcoin reaches $100k in 2025?",
        "Bitcoin reaches $100k in 2025?",
        event_id_a="evt-btc",
        event_id_b="evt-btc",
    )
    # Identical text -> jaccard=1.0, event_bonus=1.0; temporal/numeric may be 0.0
    # since same values -> no containment relationship
    assert result.score >= 0.40


def test_scorer_individual_signals_in_result():
    """DependencyResult contains correct individual signal values matching
    what the signal functions would return independently."""
    from bot.detection.dependency import (
        classify_pair, _preprocess, _jaccard_similarity,
        _keyword_implication, _numeric_relation, _time_relation, _event_bonus,
    )
    q_a = "Kraken IPO in 2025?"
    q_b = "Kraken IPO by December 31, 2026?"
    eid = "evt-kraken"

    result = classify_pair(q_a, q_b, event_id_a=eid, event_id_b=eid)

    tokens_a = _preprocess(q_a)
    tokens_b = _preprocess(q_b)
    assert result.jaccard == pytest.approx(_jaccard_similarity(tokens_a, tokens_b))
    assert result.implication == pytest.approx(_keyword_implication(q_a, q_b))
    assert result.numeric == pytest.approx(_numeric_relation(q_a, q_b))
    assert result.temporal == pytest.approx(_time_relation(q_a, q_b))
    assert result.event_bonus == pytest.approx(_event_bonus(eid, eid))


# ---------------------------------------------------------------------------
# DEP-08: Classifier (three-way classification + validation set)
# ---------------------------------------------------------------------------

def test_classify_independent_unrelated():
    """Completely unrelated markets with different event_ids -> independent."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "MicroStrategy sells any Bitcoin in 2025?",
        "Will Real Madrid win the 2025-26 La Liga?",
        event_id_a="evt-microstrategy",
        event_id_b="evt-laliga",
    )
    assert result.label == "independent"


def test_classify_independent_different_subjects():
    """Different subjects but same year -> independent."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "Macron out in 2025?",
        "Kraken IPO in 2025?",
        event_id_a="evt-macron",
        event_id_b="evt-kraken",
    )
    assert result.label == "independent"


def test_classify_subset_deadline_variant_year_only():
    """Deadline variant: year-only vs by-date with same event -> subset."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "MicroStrategy sells any Bitcoin in 2025?",
        "MicroStrategy sells any Bitcoin by December 31, 2026?",
        event_id_a="evt-microstrategy",
        event_id_b="evt-microstrategy",
    )
    assert result.label == "subset"


def test_classify_subset_deadline_variant_month():
    """Deadline variant: earlier month vs later month same year -> subset."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "Kraken IPO by March 31, 2026?",
        "Kraken IPO by December 31, 2026?",
        event_id_a="evt-kraken",
        event_id_b="evt-kraken",
    )
    assert result.label == "subset"


def test_classify_subset_deadline_variant_cross_year():
    """Deadline variant: cross-year deadlines with same event -> subset."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "Macron out by October 31, 2025?",
        "Macron out by June 30, 2026?",
        event_id_a="evt-macron",
        event_id_b="evt-macron",
    )
    assert result.label == "subset"


def test_classify_related_candidate_variant():
    """Candidate variant: same event, different subject -> related NOT subset (Pitfall 1)."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "Will Real Madrid win the 2025-26 La Liga?",
        "Will Barcelona win the 2025-26 La Liga?",
        event_id_a="evt-laliga",
        event_id_b="evt-laliga",
    )
    assert result.label == "related"


def test_classify_related_party_variant():
    """Party variant: same event, different party -> related NOT subset."""
    from bot.detection.dependency import classify_pair
    result = classify_pair(
        "Will the Democrats win the Minnesota Senate race in 2026?",
        "Will the Republicans win the Minnesota Senate race in 2026?",
        event_id_a="evt-mn-senate",
        event_id_b="evt-mn-senate",
    )
    assert result.label == "related"


def test_classify_custom_weights():
    """Custom weights produce different score than default."""
    from bot.detection.dependency import classify_pair, DEFAULT_WEIGHTS
    q_a = "Kraken IPO in 2025?"
    q_b = "Kraken IPO by December 31, 2026?"
    eid = "evt-kraken"

    default_result = classify_pair(q_a, q_b, event_id_a=eid, event_id_b=eid)

    custom_weights = {
        "jaccard": 0.10,
        "implication": 0.10,
        "numeric": 0.10,
        "temporal": 0.60,
        "event_bonus": 0.10,
    }
    custom_result = classify_pair(
        q_a, q_b, event_id_a=eid, event_id_b=eid, weights=custom_weights,
    )
    assert custom_result.score != pytest.approx(default_result.score, abs=0.001)


def test_classify_custom_thresholds():
    """Custom thresholds change classification boundary."""
    from bot.detection.dependency import classify_pair
    q_a = "Will Real Madrid win the 2025-26 La Liga?"
    q_b = "Will Barcelona win the 2025-26 La Liga?"
    eid = "evt-laliga"

    # Default thresholds -> "related" (per test_classify_related_candidate_variant)
    default_result = classify_pair(q_a, q_b, event_id_a=eid, event_id_b=eid)

    # Very low subset threshold -> should now be "subset"
    low_thresholds = {"subset": 0.05, "related": 0.01}
    low_result = classify_pair(
        q_a, q_b, event_id_a=eid, event_id_b=eid, thresholds=low_thresholds,
    )
    assert low_result.label == "subset"
    assert default_result.label != low_result.label


def test_classify_pair_signature():
    """classify_pair accepts the full signature per D-17."""
    from bot.detection.dependency import classify_pair, DependencyResult
    import inspect
    sig = inspect.signature(classify_pair)
    param_names = list(sig.parameters.keys())
    assert "question_a" in param_names
    assert "question_b" in param_names
    assert "event_id_a" in param_names
    assert "event_id_b" in param_names
    assert "weights" in param_names
    assert "thresholds" in param_names
    # Return type annotation
    assert sig.return_annotation is DependencyResult


def test_classify_result_type():
    """classify_pair returns a DependencyResult instance."""
    from bot.detection.dependency import classify_pair, DependencyResult
    result = classify_pair("Some question?", "Another question?")
    assert isinstance(result, DependencyResult)
