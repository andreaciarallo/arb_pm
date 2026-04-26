"""
Tests for paper_trades SQLite table and insert_paper_trade().

Covers PAPER-02 (paper_trades table isolated from trades/opportunities).
"""
import sqlite3

from bot.paper.simulator import PaperTrade
from bot.storage.schema import (
    init_db,
    init_paper_trades_table,
    init_trades_table,
    insert_paper_trade,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paper_trade(**overrides) -> PaperTrade:
    """Build a PaperTrade with sensible defaults."""
    defaults = dict(
        paper_trade_id="pt-001",
        paper_arb_id="arb-001",
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
        estimated_fees_usd=0.50,
        net_pnl_usd=4.50,
        depth_available=100.0,
        fill_ratio=1.0,
        simulated_at="2026-01-01T00:00:00",
        status="filled",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_init_paper_trades_table():
    """init_paper_trades_table creates the paper_trades table in SQLite."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    # Query sqlite_master for table
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'"
    ).fetchone()
    assert row is not None, "paper_trades table not found"
    assert row[0] == "paper_trades"
    conn.close()


def test_init_paper_trades_indexes():
    """init_paper_trades_table creates all 5 indexes."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_paper_trades_%'"
    ).fetchall()
    index_names = {row[0] for row in indexes}

    expected = {
        "idx_paper_trades_arb_id",
        "idx_paper_trades_simulated_at",
        "idx_paper_trades_opp_type",
        "idx_paper_trades_category",
        "idx_paper_trades_status",
    }
    assert expected.issubset(index_names), (
        f"Missing indexes: {expected - index_names}"
    )
    conn.close()


def test_insert_paper_trade():
    """insert_paper_trade correctly inserts a PaperTrade row."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    pt = _make_paper_trade()
    insert_paper_trade(conn, pt)

    row = conn.execute("SELECT * FROM paper_trades").fetchone()
    assert row is not None, "No row found in paper_trades"

    # Row layout: id(0), paper_trade_id(1), paper_arb_id(2), market_id(3), ...
    assert row[1] == "pt-001"
    assert row[2] == "arb-001"
    assert row[3] == "mkt_1"
    assert row[4] == "Will it happen?"
    assert row[5] == "yes_no"
    assert row[6] == "politics"
    assert row[7] == "yes"
    assert row[8] == "BUY"
    assert row[9] == "tok_yes"
    assert row[10] == 0.45        # ask_price
    assert row[11] == 50.0        # simulated_size_usd
    assert row[12] == 50.0        # size_filled_usd
    assert row[13] == 0.45        # vwap_price
    assert row[14] == 0.05        # kelly_fraction
    assert row[15] == 0.50        # estimated_fees_usd
    assert row[16] == 4.50        # net_pnl_usd
    assert row[17] == 100.0       # depth_available
    assert row[18] == 1.0         # fill_ratio
    assert row[19] == "2026-01-01T00:00:00"  # simulated_at
    assert row[20] == "filled"    # status
    conn.close()


def test_insert_paper_trade_duplicate_id():
    """INSERT OR IGNORE prevents duplicate paper_trade_id rows."""
    conn = sqlite3.connect(":memory:")
    init_paper_trades_table(conn)

    pt1 = _make_paper_trade(paper_trade_id="dupe-001", net_pnl_usd=1.0)
    pt2 = _make_paper_trade(paper_trade_id="dupe-001", net_pnl_usd=99.0)

    insert_paper_trade(conn, pt1)
    insert_paper_trade(conn, pt2)

    count = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
    assert count == 1, f"Expected 1 row (INSERT OR IGNORE), got {count}"

    # Verify the first insertion's value was kept
    pnl = conn.execute("SELECT net_pnl_usd FROM paper_trades").fetchone()[0]
    assert pnl == 1.0, f"Expected first insert's PnL=1.0, got {pnl}"
    conn.close()


def test_table_isolation():
    """paper_trades table is completely isolated from opportunities and trades tables."""
    conn = init_db(":memory:")
    init_trades_table(conn)
    init_paper_trades_table(conn)

    # Insert into opportunities (existing table via init_db)
    conn.execute(
        "INSERT INTO opportunities "
        "(market_id, market_question, opportunity_type, category, "
        "gross_spread, estimated_fees, net_spread, depth, detected_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("mkt_1", "Q?", "yes_no", "politics", 0.10, 0.02, 0.08, 100.0, "2026-01-01"),
    )
    conn.commit()

    # Insert into paper_trades
    pt = _make_paper_trade()
    insert_paper_trade(conn, pt)

    # Verify each table has exactly 1 row
    opp_count = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    paper_count = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
    trades_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    assert opp_count == 1, f"opportunities should have 1 row, got {opp_count}"
    assert paper_count == 1, f"paper_trades should have 1 row, got {paper_count}"
    assert trades_count == 0, f"trades should have 0 rows, got {trades_count}"
    conn.close()
