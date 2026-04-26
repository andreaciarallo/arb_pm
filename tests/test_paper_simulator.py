"""
Tests for the paper trade simulator: PaperTrade dataclass, simulate_yes_no(),
and simulate_cross_market().

Covers PAPER-01 (VWAP + Kelly from cached prices) and PAPER-03 (all 20 fields).
Plan 05-02 adds cross-market simulation tests.
"""
import time
from datetime import datetime

from bot.detection.opportunity import ArbitrageOpportunity
from bot.scanner.price_cache import MarketPrice, PriceCache
from bot.paper.simulator import PaperTrade, simulate_yes_no, simulate_cross_market


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_opp(
    yes_ask: float = 0.45,
    no_ask: float = 0.45,
    net_spread: float = 0.10,
    depth: float = 100.0,
    category: str = "politics",
    yes_token_id: str = "tok_yes",
    no_token_id: str = "tok_no",
    market_id: str = "mkt_1",
    market_question: str = "Will it happen?",
    opportunity_type: str = "yes_no",
) -> ArbitrageOpportunity:
    """Build an ArbitrageOpportunity with sensible defaults."""
    gross_spread = 1.0 - yes_ask - no_ask
    estimated_fees = gross_spread - net_spread
    return ArbitrageOpportunity(
        market_id=market_id,
        market_question=market_question,
        opportunity_type=opportunity_type,
        category=category,
        yes_ask=yes_ask,
        no_ask=no_ask,
        gross_spread=gross_spread,
        estimated_fees=estimated_fees,
        net_spread=net_spread,
        depth=depth,
        vwap_yes=yes_ask,
        vwap_no=no_ask,
        confidence_score=0.9,
        detected_at=datetime.utcnow(),
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
    )


def _make_cache(
    entries: list[dict] | None = None,
) -> PriceCache:
    """Build a PriceCache with MarketPrice entries.

    entries: list of dicts with keys: token_id, yes_ask, yes_depth.
    Defaults build cache for tok_yes and tok_no at 0.45 / depth 100.
    """
    cache = PriceCache()
    if entries is None:
        entries = [
            {"token_id": "tok_yes", "yes_ask": 0.45, "yes_depth": 100.0},
            {"token_id": "tok_no", "yes_ask": 0.45, "yes_depth": 100.0},
        ]
    for e in entries:
        mp = MarketPrice(
            token_id=e["token_id"],
            yes_ask=e["yes_ask"],
            no_ask=1.0 - e["yes_ask"],
            yes_bid=e["yes_ask"] - 0.01,
            no_bid=(1.0 - e["yes_ask"]) - 0.01,
            yes_depth=e["yes_depth"],
            no_depth=e.get("no_depth", 50.0),
            timestamp=time.time(),
            source="test",
        )
        cache.update(e["token_id"], mp)
    return cache


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_paper_trade_has_all_fields():
    """PaperTrade dataclass has all 20 fields per D-06."""
    pt = PaperTrade(
        paper_trade_id="pt1",
        paper_arb_id="arb1",
        market_id="mkt",
        market_question="Q?",
        opportunity_type="yes_no",
        category="politics",
        leg="yes",
        side="BUY",
        token_id="tok",
        ask_price=0.45,
        simulated_size_usd=50.0,
        size_filled_usd=50.0,
        vwap_price=0.45,
        kelly_fraction=0.05,
        estimated_fees_usd=0.50,
        net_pnl_usd=1.0,
        depth_available=100.0,
        fill_ratio=1.0,
        simulated_at="2026-01-01T00:00:00",
        status="filled",
    )
    expected_fields = [
        "paper_trade_id", "paper_arb_id", "market_id", "market_question",
        "opportunity_type", "category", "leg", "side", "token_id",
        "ask_price", "simulated_size_usd", "size_filled_usd", "vwap_price",
        "kelly_fraction", "estimated_fees_usd", "net_pnl_usd",
        "depth_available", "fill_ratio", "simulated_at", "status",
    ]
    for field_name in expected_fields:
        assert hasattr(pt, field_name), f"Missing field: {field_name}"
    # Verify mutability (NOT frozen -- needed for cross-market P&L distribution per A1)
    pt.net_pnl_usd = 99.9
    assert pt.net_pnl_usd == 99.9


def test_simulate_yes_no_basic(bot_config):
    """simulate_yes_no returns exactly 2 PaperTrade rows for a valid opportunity."""
    opp = _make_opp(
        yes_ask=0.45,
        no_ask=0.45,
        net_spread=0.10,
        depth=100.0,
        category="politics",
        yes_token_id="tok_yes",
        no_token_id="tok_no",
    )
    cache = _make_cache()
    result = simulate_yes_no(opp, cache, bot_config)

    assert len(result) == 2, f"Expected 2 trades, got {len(result)}"

    # Both should share the same paper_arb_id
    arb_ids = {t.paper_arb_id for t in result}
    assert len(arb_ids) == 1, "All trades in one arb should share paper_arb_id"

    legs = {t.leg for t in result}
    assert legs == {"yes", "no"}

    for t in result:
        assert t.opportunity_type == "yes_no"
        assert t.side == "BUY"
        # depth=100 and kelly output ~29.56 for this config, so depth > kelly => filled
        assert t.status == "filled"


def test_simulate_yes_no_kelly_skip(bot_config):
    """When net_spread is too small for kelly, simulate_yes_no returns []."""
    opp = _make_opp(
        yes_ask=0.49,
        no_ask=0.49,
        net_spread=0.001,
        depth=1.0,
    )
    cache = _make_cache([
        {"token_id": "tok_yes", "yes_ask": 0.49, "yes_depth": 1.0},
        {"token_id": "tok_no", "yes_ask": 0.49, "yes_depth": 1.0},
    ])
    result = simulate_yes_no(opp, cache, bot_config)
    assert result == [], f"Expected empty list, got {len(result)} trades"


def test_simulate_yes_no_missing_cache(bot_config):
    """If token IDs not in cache, simulate_yes_no returns []."""
    opp = _make_opp(
        yes_token_id="missing_yes",
        no_token_id="missing_no",
    )
    cache = PriceCache()  # empty cache
    result = simulate_yes_no(opp, cache, bot_config)
    assert result == []


def test_simulate_yes_no_partial_fill(bot_config):
    """When depth < kelly output, at least one leg has fill_ratio < 1.0 and status='partial'."""
    opp = _make_opp(
        yes_ask=0.45,
        no_ask=0.45,
        net_spread=0.10,
        depth=100.0,  # detection depth is high enough for kelly to produce a trade
    )
    # But cache depth is very low, so fill will be partial
    cache = _make_cache([
        {"token_id": "tok_yes", "yes_ask": 0.45, "yes_depth": 3.0},
        {"token_id": "tok_no", "yes_ask": 0.45, "yes_depth": 3.0},
    ])
    result = simulate_yes_no(opp, cache, bot_config)
    assert len(result) == 2, f"Expected 2 trades, got {len(result)}"

    # At least one leg should have partial status
    statuses = {t.status for t in result}
    assert "partial" in statuses, f"Expected at least one 'partial' status, got {statuses}"
    for t in result:
        if t.status == "partial":
            assert t.fill_ratio < 1.0


def test_simulate_yes_no_pnl_formula(bot_config):
    """Verify P&L uses shares, not dollars (D-09)."""
    opp = _make_opp(
        yes_ask=0.40,
        no_ask=0.40,
        net_spread=0.20,
        depth=200.0,
    )
    cache = _make_cache([
        {"token_id": "tok_yes", "yes_ask": 0.40, "yes_depth": 200.0},
        {"token_id": "tok_no", "yes_ask": 0.40, "yes_depth": 200.0},
    ])
    result = simulate_yes_no(opp, cache, bot_config)
    assert len(result) == 2

    # Reconstruct expected values
    from bot.execution.kelly import kelly_size

    target_size = bot_config.total_capital_usd * bot_config.kelly_max_capital_pct
    kelly_usd = kelly_size(
        net_spread=0.20,
        depth=200.0,
        target_size=target_size,
        total_capital=bot_config.total_capital_usd,
        min_order_usd=bot_config.kelly_min_order_usd,
        max_capital_pct=bot_config.kelly_max_capital_pct,
    )
    assert kelly_usd > 0

    # With depth=200 >> kelly_usd, both legs are fully filled at VWAP = best ask
    vwap_yes = 0.40
    vwap_no = 0.40
    yes_filled = kelly_usd  # depth >> kelly
    no_filled = kelly_usd

    effective_shares = min(yes_filled / vwap_yes, no_filled / vwap_no)
    gross_pnl = (1.0 - vwap_yes - vwap_no) * effective_shares

    fee_rate = bot_config.fee_pct_politics  # 0.010
    total_fees = fee_rate * yes_filled + fee_rate * no_filled
    expected_net_pnl = gross_pnl - total_fees

    # Sum net_pnl across both legs
    actual_net_pnl = sum(t.net_pnl_usd for t in result)
    assert abs(actual_net_pnl - expected_net_pnl) < 0.01, (
        f"Expected net_pnl={expected_net_pnl:.4f}, got {actual_net_pnl:.4f}"
    )


def test_simulate_yes_no_fees_use_category(bot_config):
    """Category='crypto' should use 0.018 fee rate, not default."""
    opp = _make_opp(
        yes_ask=0.40,
        no_ask=0.40,
        net_spread=0.20,
        depth=200.0,
        category="crypto",
    )
    cache = _make_cache([
        {"token_id": "tok_yes", "yes_ask": 0.40, "yes_depth": 200.0},
        {"token_id": "tok_no", "yes_ask": 0.40, "yes_depth": 200.0},
    ])
    result = simulate_yes_no(opp, cache, bot_config)
    assert len(result) == 2

    # Verify crypto fee rate (0.018) is used
    from bot.execution.kelly import kelly_size

    target_size = bot_config.total_capital_usd * bot_config.kelly_max_capital_pct
    kelly_usd = kelly_size(
        net_spread=0.20,
        depth=200.0,
        target_size=target_size,
        total_capital=bot_config.total_capital_usd,
        min_order_usd=bot_config.kelly_min_order_usd,
        max_capital_pct=bot_config.kelly_max_capital_pct,
    )

    # With full fill, fees should be fee_rate * filled per leg
    expected_fee_per_leg = bot_config.fee_pct_crypto * kelly_usd
    for t in result:
        assert abs(t.estimated_fees_usd - expected_fee_per_leg) < 0.01, (
            f"Expected fee {expected_fee_per_leg:.4f}, got {t.estimated_fees_usd:.4f}"
        )


# ---------------------------------------------------------------------------
# Cross-market helper
# ---------------------------------------------------------------------------


def _make_cross_opp(
    legs: list[dict] | None = None,
    net_spread: float = 0.10,
    depth: float = 100.0,
    category: str = "politics",
    market_id: str = "mkt_cross",
    market_question: str = "Cross-market arb",
) -> ArbitrageOpportunity:
    """Build a cross-market ArbitrageOpportunity with configurable legs."""
    if legs is None:
        legs = [
            {"token_id": "t1", "ask": 0.30, "depth": 50.0},
            {"token_id": "t2", "ask": 0.25, "depth": 50.0},
            {"token_id": "t3", "ask": 0.35, "depth": 50.0},
        ]
    total_yes = sum(leg["ask"] for leg in legs)
    gross_spread = 1.0 - total_yes
    estimated_fees = gross_spread - net_spread
    return ArbitrageOpportunity(
        market_id=market_id,
        market_question=market_question,
        opportunity_type="cross_market",
        category=category,
        yes_ask=total_yes,
        no_ask=0.0,
        gross_spread=gross_spread,
        estimated_fees=estimated_fees,
        net_spread=net_spread,
        depth=depth,
        vwap_yes=total_yes,
        vwap_no=0.0,
        confidence_score=0.9,
        detected_at=datetime.utcnow(),
        yes_token_id=legs[0]["token_id"] if legs else "",
        no_token_id="",
        legs=legs,
    )


# ---------------------------------------------------------------------------
# Cross-market tests
# ---------------------------------------------------------------------------


def test_simulate_cross_market_full_fill(bot_config):
    """3-leg cross-market opp with sufficient depth fills all legs."""
    opp = _make_cross_opp()
    cache = _make_cache([
        {"token_id": "t1", "yes_ask": 0.30, "yes_depth": 50.0},
        {"token_id": "t2", "yes_ask": 0.25, "yes_depth": 50.0},
        {"token_id": "t3", "yes_ask": 0.35, "yes_depth": 50.0},
    ])
    result = simulate_cross_market(opp, cache, bot_config)

    assert len(result) == 3, f"Expected 3 trades, got {len(result)}"
    for t in result:
        assert t.status == "filled"
        assert t.opportunity_type == "cross_market"
    legs = [t.leg for t in result]
    assert legs == ["leg_1", "leg_2", "leg_3"]
    # All share the same paper_arb_id
    arb_ids = {t.paper_arb_id for t in result}
    assert len(arb_ids) == 1, "All trades in one arb should share paper_arb_id"


def test_simulate_cross_market_partial_hedge(bot_config):
    """When one leg has insufficient depth, partial/failed + hedge rows are created."""
    opp = _make_cross_opp()
    cache = _make_cache([
        {"token_id": "t1", "yes_ask": 0.30, "yes_depth": 50.0},
        {"token_id": "t2", "yes_ask": 0.25, "yes_depth": 50.0},
        {"token_id": "t3", "yes_ask": 0.35, "yes_depth": 0.5},  # insufficient depth
    ])
    result = simulate_cross_market(opp, cache, bot_config)

    assert len(result) > 0
    # The last non-hedge row should be partial or failed
    non_hedge = [t for t in result if t.leg != "hedge"]
    assert non_hedge[-1].status in ("partial", "failed")
    # Hedge rows exist for previously filled legs
    hedges = [t for t in result if t.leg == "hedge"]
    assert len(hedges) > 0
    for h in hedges:
        assert h.status == "hedged"
        assert h.side == "SELL"


def test_simulate_cross_market_kelly_skip(bot_config):
    """When kelly returns 0 (tiny spread/depth), simulate_cross_market returns []."""
    opp = _make_cross_opp(net_spread=0.001, depth=1.0)
    cache = _make_cache([
        {"token_id": "t1", "yes_ask": 0.30, "yes_depth": 1.0},
        {"token_id": "t2", "yes_ask": 0.25, "yes_depth": 1.0},
        {"token_id": "t3", "yes_ask": 0.35, "yes_depth": 1.0},
    ])
    result = simulate_cross_market(opp, cache, bot_config)
    assert result == [], f"Expected empty list, got {len(result)} trades"


def test_simulate_cross_market_empty_legs(bot_config):
    """Cross-market opp with legs=[] returns []."""
    opp = _make_cross_opp(legs=[])
    cache = _make_cache([])
    result = simulate_cross_market(opp, cache, bot_config)
    assert result == []


def test_simulate_cross_market_hedge_fees_zero(bot_config):
    """Hedge rows in partial scenario have estimated_fees_usd = 0.0."""
    opp = _make_cross_opp()
    cache = _make_cache([
        {"token_id": "t1", "yes_ask": 0.30, "yes_depth": 50.0},
        {"token_id": "t2", "yes_ask": 0.25, "yes_depth": 50.0},
        {"token_id": "t3", "yes_ask": 0.35, "yes_depth": 0.5},  # insufficient
    ])
    result = simulate_cross_market(opp, cache, bot_config)
    hedges = [t for t in result if t.leg == "hedge"]
    assert len(hedges) > 0
    for h in hedges:
        assert h.estimated_fees_usd == 0.0


def test_simulate_cross_market_equal_shares(bot_config):
    """2-leg cross-market opp produces equal shares per leg."""
    legs = [
        {"token_id": "t1", "ask": 0.40, "depth": 100.0},
        {"token_id": "t2", "ask": 0.60, "depth": 100.0},
    ]
    # total_yes=1.0, gross_spread=0.0 → need net_spread > 0 for kelly
    # Use asks that sum < 1.0 so there's a real spread
    legs = [
        {"token_id": "t1", "ask": 0.40, "depth": 100.0},
        {"token_id": "t2", "ask": 0.40, "depth": 100.0},
    ]
    opp = _make_cross_opp(legs=legs, net_spread=0.10, depth=100.0)
    cache = _make_cache([
        {"token_id": "t1", "yes_ask": 0.40, "yes_depth": 100.0},
        {"token_id": "t2", "yes_ask": 0.40, "yes_depth": 100.0},
    ])
    result = simulate_cross_market(opp, cache, bot_config)
    assert len(result) == 2
    # Equal shares: simulated_size_usd / ask_price should be the same for both legs
    shares_1 = result[0].simulated_size_usd / result[0].ask_price
    shares_2 = result[1].simulated_size_usd / result[1].ask_price
    assert abs(shares_1 - shares_2) < 0.01, (
        f"Shares should be equal: leg_1={shares_1:.4f} leg_2={shares_2:.4f}"
    )
