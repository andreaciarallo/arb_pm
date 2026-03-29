import pytest
from bot.execution.kelly import kelly_size


def test_normal_case_returns_positive_size():
    size = kelly_size(net_spread=0.03, depth=200.0, target_size=100.0, total_capital=1000.0)
    assert size > 0
    assert size <= 50.0   # 5% capital cap
    assert size >= 5.0    # above floor


def test_zero_spread_returns_zero():
    assert kelly_size(0.0, 200.0, 100.0, 1000.0) == 0.0


def test_negative_spread_returns_zero():
    assert kelly_size(-0.01, 200.0, 100.0, 1000.0) == 0.0


def test_zero_depth_returns_zero():
    assert kelly_size(0.03, 0.0, 100.0, 1000.0) == 0.0


def test_thin_market_negative_numerator_returns_zero():
    # p = min(1.0, 5/1000) = 0.005; q=0.995; b*p=0.00015 < q -> numerator negative
    assert kelly_size(0.03, 5.0, 1000.0, 1000.0) == 0.0


def test_depth_cap_fifty_pct():
    size = kelly_size(0.10, 1000.0, 100.0, 100000.0)
    assert size <= 500.0  # max 50% of depth=1000


def test_capital_pct_cap_five_pct():
    size = kelly_size(0.10, 100000.0, 100.0, 1000.0)
    assert size <= 50.0   # max 5% of capital=1000


def test_below_floor_returns_zero():
    # Force formula result to be tiny: very small capital
    size = kelly_size(0.03, 10.0, 10.0, 50.0)
    # 5% of 50 = $2.50 -- below $5 floor
    assert size == 0.0


def test_result_rounded_to_two_decimals():
    size = kelly_size(0.03, 200.0, 100.0, 1000.0)
    if size > 0:
        assert round(size, 2) == size
