"""
TDD suite for RiskGate — stop-loss, circuit breaker, kill switch.

All tests are synchronous (RiskGate is fully sync, no async needed).
"""
import time
import pytest
from bot.risk.gate import RiskGate


def _gate(capital=1000.0, stop_pct=0.05, cb_errors=5, cb_window=60, cb_cooldown=300):
    return RiskGate(
        total_capital_usd=capital,
        daily_stop_loss_pct=stop_pct,
        circuit_breaker_errors=cb_errors,
        circuit_breaker_window_seconds=cb_window,
        circuit_breaker_cooldown_seconds=cb_cooldown,
    )


def test_stop_loss_not_triggered_below_threshold():
    g = _gate()
    g.record_loss(49.0)
    assert g.is_stop_loss_triggered() is False


def test_stop_loss_triggered_at_threshold():
    g = _gate()
    g.record_loss(50.0)  # 5% of 1000 = 50
    assert g.is_stop_loss_triggered() is True


def test_stop_loss_triggered_above_threshold():
    g = _gate()
    g.record_loss(60.0)
    assert g.is_stop_loss_triggered() is True


def test_midnight_reset_clears_daily_loss():
    g = _gate()
    g.record_loss(50.0)
    assert g.is_stop_loss_triggered() is True
    # Force the reset timestamp to yesterday
    yesterday = time.time() - 86400
    g._day_reset_timestamp = yesterday
    # Trigger _check_day_reset by calling is_stop_loss_triggered again
    assert g.is_stop_loss_triggered() is False  # reset fired, loss cleared


def test_circuit_breaker_not_tripped_below_count():
    g = _gate()
    for _ in range(4):
        g.record_order_error()
    assert g.is_circuit_breaker_open() is False


def test_circuit_breaker_trips_at_count():
    g = _gate()
    for _ in range(5):
        g.record_order_error()
    assert g.is_circuit_breaker_open() is True


def test_circuit_breaker_expires_after_cooldown():
    g = _gate()
    for _ in range(5):
        g.record_order_error()
    assert g.is_circuit_breaker_open() is True
    # Set cooldown to the past
    g._cb_cooldown_until = time.time() - 1
    assert g.is_circuit_breaker_open() is False


def test_circuit_breaker_exponential_backoff_doubles():
    g = _gate(cb_cooldown=300)
    # First trip
    for _ in range(5):
        g.record_order_error()
    first_cooldown_until = g._cb_cooldown_until
    first_remaining = first_cooldown_until - time.time()
    assert 280 < first_remaining <= 310  # ~300s first trip

    # Force expiry so second trip is counted
    g._cb_cooldown_until = time.time() - 1
    g._error_timestamps.clear()
    # Second trip
    for _ in range(5):
        g.record_order_error()
    second_remaining = g._cb_cooldown_until - time.time()
    assert 580 < second_remaining <= 620  # ~600s = 2× 300s


def test_kill_switch_not_active_by_default():
    g = _gate()
    assert g.is_kill_switch_active() is False


def test_activate_kill_switch():
    g = _gate()
    g.activate_kill_switch()
    assert g.is_kill_switch_active() is True


def test_is_blocked_true_on_kill_switch():
    g = _gate()
    g.activate_kill_switch()
    assert g.is_blocked() is True


def test_is_blocked_true_on_stop_loss():
    g = _gate()
    g.record_loss(50.0)
    assert g.is_blocked() is True


def test_is_blocked_true_on_circuit_breaker():
    g = _gate()
    for _ in range(5):
        g.record_order_error()
    assert g.is_blocked() is True


def test_is_blocked_false_when_clear():
    g = _gate()
    assert g.is_blocked() is False


def test_kill_switch_overrides_expired_circuit_breaker():
    g = _gate()
    for _ in range(5):
        g.record_order_error()
    g._cb_cooldown_until = time.time() - 1  # CB expired
    g.activate_kill_switch()
    assert g.is_blocked() is True  # kill switch keeps blocked
