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
