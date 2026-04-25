"""
Tests for detection quality filters (DETECT-01 through DETECT-05).

Covers stateless threshold filters, DedupTracker, and FilterDiagnostics.
"""
import time
import pytest

pytestmark = pytest.mark.unit


def _make_config():
    from bot.config import BotConfig
    return BotConfig(
        poly_api_key="k", poly_api_secret="s", poly_api_passphrase="p",
        wallet_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        polygon_rpc_http="https://polygon.example.com",
        polygon_rpc_ws="wss://polygon.example.com",
    )


# ---------------------------------------------------------------------------
# BotConfig threshold field defaults
# ---------------------------------------------------------------------------

def test_config_min_ask_floor_default():
    cfg = _make_config()
    assert cfg.min_ask_floor == 0.03


def test_config_max_ask_sum_default():
    cfg = _make_config()
    assert cfg.max_ask_sum == 0.99


def test_config_min_cross_leg_ask_default():
    cfg = _make_config()
    assert cfg.min_cross_leg_ask == 0.005


def test_config_min_cross_total_yes_default():
    cfg = _make_config()
    assert cfg.min_cross_total_yes == 0.10


def test_config_dedup_window_seconds_default():
    cfg = _make_config()
    assert cfg.dedup_window_seconds == 300


# ---------------------------------------------------------------------------
# DETECT-01: is_ask_floor_reject (operator: <=, boundary 0.03 IS rejected)
# ---------------------------------------------------------------------------

def test_ask_floor_reject_yes_at_boundary():
    """0.03 <= 0.03 -> rejected (boundary: 0.03 IS rejected)."""
    from bot.detection.filters import is_ask_floor_reject
    assert is_ask_floor_reject(0.03, 0.50, 0.03) is True


def test_ask_floor_reject_above_floor():
    """0.031 > 0.03 -> not rejected."""
    from bot.detection.filters import is_ask_floor_reject
    assert is_ask_floor_reject(0.031, 0.50, 0.03) is False


def test_ask_floor_reject_no_below_floor():
    """no_ask 0.02 <= 0.03 -> rejected."""
    from bot.detection.filters import is_ask_floor_reject
    assert is_ask_floor_reject(0.50, 0.02, 0.03) is True


# ---------------------------------------------------------------------------
# DETECT-02: is_sum_cap_reject (operator: >, boundary 0.99 is NOT rejected)
# ---------------------------------------------------------------------------

def test_sum_cap_reject_above():
    """0.50 + 0.50 = 1.00 > 0.99 -> rejected."""
    from bot.detection.filters import is_sum_cap_reject
    assert is_sum_cap_reject(0.50, 0.50, 0.99) is True


def test_sum_cap_reject_at_boundary():
    """0.50 + 0.49 = 0.99. 0.99 is NOT > 0.99 -> not rejected."""
    from bot.detection.filters import is_sum_cap_reject
    assert is_sum_cap_reject(0.50, 0.49, 0.99) is False


def test_sum_cap_reject_just_above():
    """0.50 + 0.491 = 0.991 > 0.99 -> rejected."""
    from bot.detection.filters import is_sum_cap_reject
    assert is_sum_cap_reject(0.50, 0.491, 0.99) is True


# ---------------------------------------------------------------------------
# DETECT-03: has_dead_leg (operator: <=, boundary 0.005 IS rejected)
# ---------------------------------------------------------------------------

def test_dead_leg_at_boundary():
    """One leg at 0.005 <= 0.005 -> has dead leg."""
    from bot.detection.filters import has_dead_leg
    assert has_dead_leg([0.30, 0.005, 0.20], 0.005) is True


def test_dead_leg_all_above():
    """All legs above 0.005 -> no dead leg."""
    from bot.detection.filters import has_dead_leg
    assert has_dead_leg([0.30, 0.006, 0.20], 0.005) is False


def test_dead_leg_single_dead():
    """Single leg at 0.001 <= 0.005 -> has dead leg."""
    from bot.detection.filters import has_dead_leg
    assert has_dead_leg([0.001], 0.005) is True


# ---------------------------------------------------------------------------
# DETECT-04: is_total_yes_reject (operator: <, boundary 0.10 is NOT rejected)
# ---------------------------------------------------------------------------

def test_total_yes_reject_below():
    """0.099 < 0.10 -> rejected."""
    from bot.detection.filters import is_total_yes_reject
    assert is_total_yes_reject(0.099, 0.10) is True


def test_total_yes_reject_at_boundary():
    """0.10 is NOT < 0.10 -> not rejected."""
    from bot.detection.filters import is_total_yes_reject
    assert is_total_yes_reject(0.10, 0.10) is False


def test_total_yes_reject_well_above():
    """0.50 is NOT < 0.10 -> not rejected."""
    from bot.detection.filters import is_total_yes_reject
    assert is_total_yes_reject(0.50, 0.10) is False


# ---------------------------------------------------------------------------
# DETECT-05: DedupTracker
# ---------------------------------------------------------------------------

def test_dedup_first_call_not_duplicate():
    """First call for a key returns False (not a duplicate)."""
    from bot.detection.filters import DedupTracker
    tracker = DedupTracker(window_seconds=300)
    assert tracker.is_duplicate("m1", "yes_no") is False


def test_dedup_immediate_second_call_duplicate():
    """Immediate second call for same key returns True (duplicate)."""
    from bot.detection.filters import DedupTracker
    tracker = DedupTracker(window_seconds=300)
    tracker.is_duplicate("m1", "yes_no")
    assert tracker.is_duplicate("m1", "yes_no") is True


def test_dedup_expired_window_allows_redetection():
    """Window=0 means entries expire immediately, allowing re-detection."""
    from bot.detection.filters import DedupTracker
    tracker = DedupTracker(window_seconds=0)
    tracker.is_duplicate("m1", "yes_no")
    # With window=0, the entry is already expired
    assert tracker.is_duplicate("m1", "yes_no") is False


def test_dedup_different_opp_type_independent():
    """Same market_id but different opp_type are independent (per D-01)."""
    from bot.detection.filters import DedupTracker
    tracker = DedupTracker(window_seconds=300)
    tracker.is_duplicate("m1", "yes_no")
    assert tracker.is_duplicate("m1", "cross_market") is False


def test_dedup_prune_removes_expired():
    """prune() removes expired entries and returns count pruned."""
    from bot.detection.filters import DedupTracker
    tracker = DedupTracker(window_seconds=0)
    tracker.is_duplicate("m1", "yes_no")
    tracker.is_duplicate("m2", "cross_market")
    pruned = tracker.prune()
    assert pruned == 2


# ---------------------------------------------------------------------------
# FilterDiagnostics
# ---------------------------------------------------------------------------

def test_filter_diagnostics_defaults():
    """All FilterDiagnostics counters default to 0."""
    from bot.detection.filters import FilterDiagnostics
    diag = FilterDiagnostics()
    assert diag.ask_floor_rejects == 0
    assert diag.sum_cap_rejects == 0
    assert diag.leg_floor_rejects == 0
    assert diag.total_yes_rejects == 0
    assert diag.dedup_suppressed == 0
