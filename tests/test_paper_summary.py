"""
Tests for paper trade summary query functions.

Covers PAPER-05 (paper trade summary analytics). All aggregation is by
paper_arb_id (D-14) to count complete arb attempts, not individual legs.
"""
import sqlite3

from bot.paper.simulator import PaperTrade
from bot.storage.schema import init_paper_trades_table, insert_paper_trade
from bot.storage.paper_summary import (
    get_total_pnl,
    get_win_rate,
    get_avg_spread,
    get_category_breakdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COUNTER = 0


def _make_pt(**overrides) -> PaperTrade:
    """Build a PaperTrade with sensible defaults. Auto-increments paper_trade_id."""
    global _COUNTER
    _COUNTER += 1
    defaults = dict(
        paper_trade_id=f"pt-{_COUNTER:04d}",
        paper_arb_id="arb-default",
        market_id="mkt_1",
        market_question="Will it happen?",
        opportunity_type="yes_no",
        category="politics",
        leg="yes",
        side="BUY",
        token_id="tok_yes",
        ask_price=0.45,
        simulated_size_usd=50.0,
        size_filled_usd=50.0,
        vwap_price=0.45,
        kelly_fraction=0.05,
        estimated_fees_usd=0.01,
        net_pnl_usd=0.0,
        depth_available=100.0,
        fill_ratio=1.0,
        simulated_at="2026-01-01T00:00:00",
        status="filled",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


def _seed_paper_trades(conn: sqlite3.Connection, trades_data: list[PaperTrade]) -> None:
    """Insert test PaperTrade rows via insert_paper_trade()."""
    for pt in trades_data:
        insert_paper_trade(conn, pt)


def _seed_standard(conn: sqlite3.Connection) -> None:
    """
    Seed A1-A4 test data.

    A1 (yes_no, politics): 2 rows, net_pnl = +0.05 each = +0.10 total. Win.
    A2 (yes_no, crypto):   2 rows, net_pnl = -0.03 each = -0.06 total. Loss.
    A3 (cross_market, politics): 3 rows, net_pnl = +0.02 each = +0.06 total. Win.
    A4 (cross_market, politics): 5 rows (2 filled + 1 partial + 2 hedge),
        net_pnl = -0.04, -0.04, -0.02, -0.03, -0.02 = -0.15 total. Loss.
    """
    trades = [
        # --- A1: yes_no, politics, WIN ---
        _make_pt(paper_arb_id="A1", opportunity_type="yes_no", category="politics",
                 leg="yes", net_pnl_usd=0.05, estimated_fees_usd=0.01),
        _make_pt(paper_arb_id="A1", opportunity_type="yes_no", category="politics",
                 leg="no", net_pnl_usd=0.05, estimated_fees_usd=0.01),
        # --- A2: yes_no, crypto, LOSS ---
        _make_pt(paper_arb_id="A2", opportunity_type="yes_no", category="crypto",
                 leg="yes", net_pnl_usd=-0.03, estimated_fees_usd=0.01),
        _make_pt(paper_arb_id="A2", opportunity_type="yes_no", category="crypto",
                 leg="no", net_pnl_usd=-0.03, estimated_fees_usd=0.01),
        # --- A3: cross_market, politics, WIN ---
        _make_pt(paper_arb_id="A3", opportunity_type="cross_market", category="politics",
                 leg="leg_1", net_pnl_usd=0.02, estimated_fees_usd=0.01),
        _make_pt(paper_arb_id="A3", opportunity_type="cross_market", category="politics",
                 leg="leg_2", net_pnl_usd=0.02, estimated_fees_usd=0.01),
        _make_pt(paper_arb_id="A3", opportunity_type="cross_market", category="politics",
                 leg="leg_3", net_pnl_usd=0.02, estimated_fees_usd=0.01),
        # --- A4: cross_market, politics, LOSS ---
        _make_pt(paper_arb_id="A4", opportunity_type="cross_market", category="politics",
                 leg="leg_1", status="filled", net_pnl_usd=-0.04, estimated_fees_usd=0.01),
        _make_pt(paper_arb_id="A4", opportunity_type="cross_market", category="politics",
                 leg="leg_2", status="filled", net_pnl_usd=-0.04, estimated_fees_usd=0.01),
        _make_pt(paper_arb_id="A4", opportunity_type="cross_market", category="politics",
                 leg="leg_3", status="partial", net_pnl_usd=-0.02, estimated_fees_usd=0.01),
        _make_pt(paper_arb_id="A4", opportunity_type="cross_market", category="politics",
                 leg="hedge", side="SELL", status="hedged", net_pnl_usd=-0.03, estimated_fees_usd=0.01),
        _make_pt(paper_arb_id="A4", opportunity_type="cross_market", category="politics",
                 leg="hedge", side="SELL", status="hedged", net_pnl_usd=-0.02, estimated_fees_usd=0.01),
    ]
    _seed_paper_trades(conn, trades)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_total_pnl():
    """get_total_pnl aggregates across all paper trades."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)
    _seed_standard(conn)

    result = get_total_pnl(conn)

    assert result["trade_count"] == 4, f"Expected 4 distinct arbs, got {result['trade_count']}"

    # total_net_pnl = sum of ALL net_pnl_usd across all 12 rows
    # A1: +0.10, A2: -0.06, A3: +0.06, A4: -0.15 = -0.05
    expected_net = round(0.05 + 0.05 - 0.03 - 0.03 + 0.02 + 0.02 + 0.02
                         - 0.04 - 0.04 - 0.02 - 0.03 - 0.02, 4)
    assert result["total_net_pnl"] == expected_net, (
        f"Expected total_net_pnl={expected_net}, got {result['total_net_pnl']}"
    )

    # total_fees = sum of ALL estimated_fees_usd (0.01 * 12 = 0.12)
    expected_fees = round(0.01 * 12, 4)
    assert result["total_fees"] == expected_fees, (
        f"Expected total_fees={expected_fees}, got {result['total_fees']}"
    )

    # total_gross_pnl = total_net_pnl + total_fees
    expected_gross = round(expected_net + expected_fees, 4)
    assert result["total_gross_pnl"] == expected_gross, (
        f"Expected total_gross_pnl={expected_gross}, got {result['total_gross_pnl']}"
    )
    conn.close()


def test_get_total_pnl_empty():
    """get_total_pnl returns zeroes on empty table."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    result = get_total_pnl(conn)

    assert result["trade_count"] == 0
    assert result["total_net_pnl"] == 0.0
    assert result["total_fees"] == 0.0
    assert result["total_gross_pnl"] == 0.0
    conn.close()


def test_get_win_rate():
    """get_win_rate groups by opportunity_type and counts wins (arb pnl > 0)."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)
    _seed_standard(conn)

    result = get_win_rate(conn)

    # yes_no: A1 wins, A2 loses -> 1/2
    assert "yes_no" in result
    assert result["yes_no"]["total"] == 2
    assert result["yes_no"]["wins"] == 1
    assert result["yes_no"]["win_rate"] == 0.5

    # cross_market: A3 wins, A4 loses -> 1/2
    assert "cross_market" in result
    assert result["cross_market"]["total"] == 2
    assert result["cross_market"]["wins"] == 1
    assert result["cross_market"]["win_rate"] == 0.5
    conn.close()


def test_get_win_rate_empty():
    """get_win_rate returns empty dict on empty table."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    result = get_win_rate(conn)
    assert result == {}
    conn.close()


def test_get_avg_spread():
    """get_avg_spread computes per-arb net P&L average by category."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)
    _seed_standard(conn)

    result = get_avg_spread(conn)

    # politics: A1=+0.10, A3=+0.06, A4=-0.15 -> avg = 0.01/3 > 0
    assert "politics" in result
    assert result["politics"]["avg_spread"] > 0, (
        f"Expected politics avg_spread > 0, got {result['politics']['avg_spread']}"
    )
    assert result["politics"]["arb_count"] == 3

    # crypto: A2=-0.06 -> avg = -0.06 < 0
    assert "crypto" in result
    assert result["crypto"]["avg_spread"] < 0, (
        f"Expected crypto avg_spread < 0, got {result['crypto']['avg_spread']}"
    )
    assert result["crypto"]["arb_count"] == 1
    conn.close()


def test_get_avg_spread_empty():
    """get_avg_spread returns empty dict on empty table."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    result = get_avg_spread(conn)
    assert result == {}
    conn.close()


def test_get_category_breakdown():
    """get_category_breakdown returns per-category stats sorted by total_pnl DESC."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)
    _seed_standard(conn)

    result = get_category_breakdown(conn)

    assert len(result) == 2, f"Expected 2 categories, got {len(result)}"

    # Find politics and crypto entries
    by_cat = {r["category"]: r for r in result}

    # politics: A1=+0.10, A3=+0.06, A4=-0.15 -> 3 arbs, total=+0.01
    pol = by_cat["politics"]
    assert pol["arb_count"] == 3
    assert pol["total_pnl"] == round(0.10 + 0.06 - 0.15, 4)  # 0.01
    assert abs(pol["avg_pnl"] - round(0.01 / 3, 6)) < 1e-6
    # A1 and A3 win, A4 loses -> win_rate = 2/3
    assert abs(pol["win_rate"] - round(2 / 3, 4)) < 1e-4

    # crypto: A2=-0.06 -> 1 arb, total=-0.06, win_rate=0.0
    cry = by_cat["crypto"]
    assert cry["arb_count"] == 1
    assert cry["total_pnl"] == -0.06
    assert cry["avg_pnl"] == -0.06
    assert cry["win_rate"] == 0.0

    # Sorted by total_pnl DESC: politics (+0.01) before crypto (-0.06)
    assert result[0]["category"] == "politics"
    assert result[1]["category"] == "crypto"
    conn.close()


def test_get_category_breakdown_empty():
    """get_category_breakdown returns empty list on empty table."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    result = get_category_breakdown(conn)
    assert result == []
    conn.close()


def test_aggregation_by_arb_id_not_legs():
    """Summary functions aggregate by paper_arb_id, not individual leg rows."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    # Single arb with 5 legs, each contributing +0.01 net_pnl
    trades = [
        _make_pt(paper_arb_id="MULTI", opportunity_type="cross_market",
                 category="sports", leg=f"leg_{i}", net_pnl_usd=0.01,
                 estimated_fees_usd=0.005)
        for i in range(1, 6)
    ]
    _seed_paper_trades(conn, trades)

    # get_total_pnl: trade_count should be 1 (one arb), not 5 (five legs)
    pnl = get_total_pnl(conn)
    assert pnl["trade_count"] == 1, f"Expected 1 arb, got {pnl['trade_count']}"

    # get_win_rate: total should be 1 (one arb), not 5
    wr = get_win_rate(conn)
    assert wr["cross_market"]["total"] == 1, (
        f"Expected 1 arb in win_rate, got {wr['cross_market']['total']}"
    )
    # Sum of net_pnl = 5 * 0.01 = +0.05 > 0, so it's a win
    assert wr["cross_market"]["wins"] == 1

    # get_avg_spread: arb_count should be 1
    spread = get_avg_spread(conn)
    assert spread["sports"]["arb_count"] == 1

    # get_category_breakdown: arb_count should be 1
    breakdown = get_category_breakdown(conn)
    assert len(breakdown) == 1
    assert breakdown[0]["arb_count"] == 1
    conn.close()
