"""
Tests for group_validator.py -- partition validation for Polymarket event groups.

Covers GV-01 through GV-04:
- NegRisk auto-pass (GV-01)
- Duplicate detection via Jaccard (GV-02)
- Subset/implication detection (GV-03)
- Completeness heuristic (GV-04)
- Cache accessor (get_valid_groups)
- GV-REJECT log format
"""
import sys
import pytest

pytestmark = pytest.mark.unit


def _setup_test_data(event_id, markets, neg_risk=False):
    """Populate _event_groups and _gamma_market_data for testing."""
    import bot.detection.cross_market as cm
    import bot.detection.group_validator as gv

    cm._event_groups.clear()
    cm._gamma_market_data.clear()
    gv._valid_groups.clear()
    for m in markets:
        cid = m["cid"]
        cm._event_groups[cid] = cm.EventInfo(
            event_id=event_id, neg_risk=neg_risk, market_count=len(markets)
        )
        cm._gamma_market_data[cid] = {
            "question": m["question"],
            "outcomePrices": m.get("outcomePrices", "[0.5, 0.5]"),
        }


def _cleanup():
    """Restore module-level caches to empty state."""
    import bot.detection.cross_market as cm
    import bot.detection.group_validator as gv

    cm._event_groups.clear()
    cm._gamma_market_data.clear()
    gv._valid_groups.clear()


# ---- GV-01: NegRisk auto-pass ----

def test_negrisk_auto_pass():
    """GV-01: NegRisk group is in returned valid set without any pairwise checks."""
    from bot.detection.group_validator import validate_groups

    _setup_test_data("event_nr", [
        {"cid": "c1", "question": "Will Alice win?"},
        {"cid": "c2", "question": "Will Bob win?"},
        {"cid": "c3", "question": "Will Carol win?"},
    ], neg_risk=True)
    try:
        valid = validate_groups()
        assert "event_nr" in valid
    finally:
        _cleanup()


def test_non_negrisk_validated():
    """GV-01 (negative): Non-NegRisk group with all distinct questions passes."""
    from bot.detection.group_validator import validate_groups

    _setup_test_data("event_std", [
        {"cid": "c1", "question": "Will Alice win the race?",
         "outcomePrices": "[0.4, 0.6]"},
        {"cid": "c2", "question": "Will Bob win the contest?",
         "outcomePrices": "[0.3, 0.7]"},
        {"cid": "c3", "question": "Will Carol take the prize?",
         "outcomePrices": "[0.25, 0.75]"},
    ], neg_risk=False)
    try:
        valid = validate_groups()
        assert "event_std" in valid
    finally:
        _cleanup()


# ---- GV-02: Duplicate detection ----

def test_duplicate_detected():
    """GV-02: Duplicate pair (Jaccard > 0.9) causes group rejection."""
    from bot.detection.group_validator import validate_groups

    # Near-identical questions: after stopword removal, both reduce to
    # the same token set -> Jaccard ~1.0
    _setup_test_data("event_dup", [
        {"cid": "c1", "question": "Will Biden win the 2026 presidential election?",
         "outcomePrices": "[0.5, 0.5]"},
        {"cid": "c2", "question": "Biden will win the presidential election 2026?",
         "outcomePrices": "[0.5, 0.5]"},
    ], neg_risk=False)
    try:
        valid = validate_groups()
        assert "event_dup" not in valid
    finally:
        _cleanup()


def test_non_duplicate_passes():
    """GV-02 (negative): Distinct pair (Jaccard < 0.9) passes."""
    from bot.detection.group_validator import validate_groups

    _setup_test_data("event_distinct", [
        {"cid": "c1", "question": "Will Alice win?",
         "outcomePrices": "[0.5, 0.5]"},
        {"cid": "c2", "question": "Will Bob win?",
         "outcomePrices": "[0.5, 0.5]"},
    ], neg_risk=False)
    try:
        valid = validate_groups()
        assert "event_distinct" in valid
    finally:
        _cleanup()


# ---- GV-03: Subset detection ----

def test_subset_detected():
    """GV-03: Keyword implication pair causes group rejection."""
    from bot.detection.group_validator import validate_groups

    _setup_test_data("event_sub", [
        {"cid": "c1", "question": "Team wins by 5 points",
         "outcomePrices": "[0.5, 0.5]"},
        {"cid": "c2", "question": "Team wins",
         "outcomePrices": "[0.5, 0.5]"},
    ], neg_risk=False)
    try:
        valid = validate_groups()
        assert "event_sub" not in valid
    finally:
        _cleanup()


def test_numeric_subset_detected():
    """GV-03: Numeric threshold pair causes group rejection."""
    from bot.detection.group_validator import validate_groups

    # Use longer questions so shared tokens dominate -> Jaccard > 0.6
    # "CryptoPunks floor price above $100k by end of year" vs
    # "CryptoPunks floor price above $150k by end of year"
    # Shared tokens: {cryptopunks, floor, price, above, end, year} = 6
    # Different tokens: {100k} vs {150k} = 2 (one per set)
    # Jaccard = 6/8 = 0.75 > 0.6
    _setup_test_data("event_num", [
        {"cid": "c1", "question": "CryptoPunks floor price above $100k by end of year",
         "outcomePrices": "[0.5, 0.5]"},
        {"cid": "c2", "question": "CryptoPunks floor price above $150k by end of year",
         "outcomePrices": "[0.5, 0.5]"},
    ], neg_risk=False)
    try:
        valid = validate_groups()
        assert "event_num" not in valid
    finally:
        _cleanup()


# ---- GV-04: Completeness check ----

def test_completeness_pass():
    """GV-04: mid_sum=0.95 within [0.7, 1.3] passes."""
    from bot.detection.group_validator import passes_completeness_check

    markets = [
        {"outcomePrices": "[0.35, 0.65]"},
        {"outcomePrices": "[0.30, 0.70]"},
        {"outcomePrices": "[0.30, 0.70]"},
    ]
    passes, mid_sum = passes_completeness_check(markets)
    assert passes is True
    assert abs(mid_sum - 0.95) < 0.01


def test_completeness_reject_high():
    """GV-04: mid_sum=2.0 outside [0.7, 1.3] is rejected."""
    from bot.detection.group_validator import passes_completeness_check

    markets = [
        {"outcomePrices": "[0.50, 0.50]"},
        {"outcomePrices": "[0.50, 0.50]"},
        {"outcomePrices": "[0.50, 0.50]"},
        {"outcomePrices": "[0.50, 0.50]"},
    ]
    passes, mid_sum = passes_completeness_check(markets)
    assert passes is False
    assert abs(mid_sum - 2.0) < 0.01


def test_completeness_reject_low():
    """GV-04: mid_sum=0.5 outside [0.7, 1.3] is rejected."""
    from bot.detection.group_validator import passes_completeness_check

    markets = [
        {"outcomePrices": "[0.25, 0.75]"},
        {"outcomePrices": "[0.25, 0.75]"},
    ]
    passes, mid_sum = passes_completeness_check(markets)
    assert passes is False
    assert abs(mid_sum - 0.50) < 0.01


# ---- Cache accessor ----

def test_get_valid_groups_returns_cache():
    """get_valid_groups() returns the cached set from last validate_groups() call."""
    from bot.detection.group_validator import validate_groups, get_valid_groups

    _setup_test_data("event_cache", [
        {"cid": "c1", "question": "Will Alice win?"},
        {"cid": "c2", "question": "Will Bob win?"},
    ], neg_risk=True)
    try:
        validate_groups()
        cached = get_valid_groups()
        assert "event_cache" in cached
    finally:
        _cleanup()


# ---- GV-REJECT log format ----

def test_gv_reject_log_format(capfd):
    """GV-REJECT log line contains violation type, questions, and score."""
    from loguru import logger as _logger
    from bot.detection.group_validator import validate_groups

    # Near-identical questions that trigger duplicate detection (Jaccard > 0.9)
    _setup_test_data("event_log", [
        {"cid": "c1", "question": "Will Biden win the 2026 presidential election?",
         "outcomePrices": "[0.5, 0.5]"},
        {"cid": "c2", "question": "Biden will win the presidential election 2026?",
         "outcomePrices": "[0.5, 0.5]"},
    ], neg_risk=False)

    sink_id = _logger.add(sys.stderr, format="{message}", level="DEBUG")
    try:
        validate_groups()
        captured = capfd.readouterr()
        assert "GV-REJECT:" in captured.err
        assert "duplicate" in captured.err
        assert "Biden" in captured.err
    finally:
        _cleanup()
        _logger.remove(sink_id)
