import asyncio
import sqlite3
import tempfile
import os
from datetime import datetime
import pytest

# ---------------------------------------------------------------------------
# Phase 4: arb_pairs table tests (TDD — written before implementation)
# ---------------------------------------------------------------------------


def _make_arb_pair(**kwargs):
    defaults = dict(
        arb_id="arb-001",
        yes_trade_id="trade-yes-001",
        no_trade_id="trade-no-001",
        market_id="0xabc",
        market_question="Will X happen?",
        yes_entry_price=0.40,
        no_entry_price=0.60,
        size_usd=100.0,
        gross_pnl=2.50,
        fees_usd=0.80,
        net_pnl=1.70,
        entry_time="2026-04-15T10:00:00",
        exit_time="2026-04-15T10:05:00",
        hold_seconds=300.0,
    )
    defaults.update(kwargs)
    return defaults


def test_init_arb_pairs_table_creates_table():
    """init_arb_pairs_table() creates the arb_pairs table."""
    from bot.storage.schema import init_arb_pairs_table

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_arb_pairs_table(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='arb_pairs'"
        )
        assert cursor.fetchone() is not None
    finally:
        conn.close()
        os.unlink(db_path)


def test_init_arb_pairs_table_idempotent():
    """Calling init_arb_pairs_table() twice does not raise."""
    from bot.storage.schema import init_arb_pairs_table

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_arb_pairs_table(conn)
        init_arb_pairs_table(conn)  # Must not raise
    finally:
        conn.close()
        os.unlink(db_path)


def test_init_arb_pairs_table_creates_market_id_index():
    """init_arb_pairs_table() creates idx_arb_pairs_market_id index."""
    from bot.storage.schema import init_arb_pairs_table

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_arb_pairs_table(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_arb_pairs_market_id'"
        )
        assert cursor.fetchone() is not None
    finally:
        conn.close()
        os.unlink(db_path)


def test_init_arb_pairs_table_creates_entry_time_index():
    """init_arb_pairs_table() creates idx_arb_pairs_entry_time index."""
    from bot.storage.schema import init_arb_pairs_table

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_arb_pairs_table(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_arb_pairs_entry_time'"
        )
        assert cursor.fetchone() is not None
    finally:
        conn.close()
        os.unlink(db_path)


def test_insert_arb_pair_inserts_row():
    """insert_arb_pair() inserts a row with all 14 fields."""
    from bot.storage.schema import init_arb_pairs_table, insert_arb_pair

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_arb_pairs_table(conn)
        pair = _make_arb_pair()
        insert_arb_pair(conn, pair)
        cursor = conn.execute("SELECT COUNT(*) FROM arb_pairs")
        assert cursor.fetchone()[0] == 1
    finally:
        conn.close()
        os.unlink(db_path)


def test_insert_arb_pair_values_stored_correctly():
    """insert_arb_pair() stores all fields with correct values."""
    from bot.storage.schema import init_arb_pairs_table, insert_arb_pair

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_arb_pairs_table(conn)
        pair = _make_arb_pair()
        insert_arb_pair(conn, pair)
        cursor = conn.execute(
            "SELECT arb_id, yes_trade_id, no_trade_id, market_id, market_question, "
            "yes_entry_price, no_entry_price, size_usd, gross_pnl, fees_usd, "
            "net_pnl, entry_time, exit_time, hold_seconds FROM arb_pairs"
        )
        row = cursor.fetchone()
        assert row[0] == "arb-001"
        assert row[1] == "trade-yes-001"
        assert row[2] == "trade-no-001"
        assert row[3] == "0xabc"
        assert row[4] == "Will X happen?"
        assert abs(row[5] - 0.40) < 0.0001   # yes_entry_price
        assert abs(row[6] - 0.60) < 0.0001   # no_entry_price
        assert abs(row[7] - 100.0) < 0.0001  # size_usd
        assert abs(row[8] - 2.50) < 0.0001   # gross_pnl
        assert abs(row[9] - 0.80) < 0.0001   # fees_usd
        assert abs(row[10] - 1.70) < 0.0001  # net_pnl
        assert row[11] == "2026-04-15T10:00:00"
        assert row[12] == "2026-04-15T10:05:00"
        assert abs(row[13] - 300.0) < 0.0001  # hold_seconds
    finally:
        conn.close()
        os.unlink(db_path)


def test_insert_arb_pair_ignore_duplicate():
    """INSERT OR IGNORE: inserting same arb_id twice does not raise."""
    from bot.storage.schema import init_arb_pairs_table, insert_arb_pair

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_arb_pairs_table(conn)
        pair = _make_arb_pair()
        insert_arb_pair(conn, pair)
        insert_arb_pair(conn, pair)  # Same arb_id — must not raise
        cursor = conn.execute("SELECT COUNT(*) FROM arb_pairs")
        assert cursor.fetchone()[0] == 1  # Still only 1 row
    finally:
        conn.close()
        os.unlink(db_path)


def test_insert_trade_fees_usd_not_zero():
    """insert_trade() stores the supplied fees_usd value (not the hardcoded 0.0 placeholder)."""
    from bot.storage.schema import init_trades_table, insert_trade
    from bot.execution.engine import ExecutionResult

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_trades_table(conn)
        result = ExecutionResult(
            market_id="cond_fees", leg="yes", side="BUY", token_id="tok_yes",
            price=0.48, size=10.0, order_id="ord_fees", status="filled",
            size_filled=10.0, kelly_size_usd=10.0, vwap_price=0.48, error_msg=None,
        )
        insert_trade(conn, result, "Fees market", "trade-fees-001", fees_usd=0.5)
        row = conn.execute(
            "SELECT fees_usd FROM trades WHERE trade_id='trade-fees-001'"
        ).fetchone()
        assert row is not None
        assert abs(row[0] - 0.5) < 0.0001  # fees_usd stored, not 0.0
    finally:
        conn.close()
        os.unlink(db_path)


def test_insert_trade_fees_usd_default_zero():
    """insert_trade() defaults fees_usd to 0.0 when not provided (backwards compat)."""
    from bot.storage.schema import init_trades_table, insert_trade
    from bot.execution.engine import ExecutionResult

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        init_trades_table(conn)
        result = ExecutionResult(
            market_id="cond_compat", leg="no", side="BUY", token_id="tok_no",
            price=0.52, size=10.0, order_id="ord_compat", status="filled",
            size_filled=10.0, kelly_size_usd=10.0, vwap_price=0.52, error_msg=None,
        )
        insert_trade(conn, result, "Compat market", "trade-compat-001")  # no fees_usd kwarg
        row = conn.execute(
            "SELECT fees_usd FROM trades WHERE trade_id='trade-compat-001'"
        ).fetchone()
        assert row is not None
        assert row[0] == 0.0  # default preserved
    finally:
        conn.close()
        os.unlink(db_path)


pytestmark = pytest.mark.unit


def _make_opportunity(**kwargs):
    from bot.detection.opportunity import ArbitrageOpportunity
    defaults = dict(
        market_id="0xabc",
        market_question="Will X happen?",
        opportunity_type="yes_no",
        category="politics",
        yes_ask=0.40,
        no_ask=0.40,
        gross_spread=0.20,
        estimated_fees=0.008,
        net_spread=0.192,
        depth=200.0,
        vwap_yes=0.40,
        vwap_no=0.40,
        confidence_score=0.95,
        detected_at=datetime(2026, 3, 28, 14, 23, 11),
    )
    defaults.update(kwargs)
    return ArbitrageOpportunity(**defaults)


def test_schema_creates_table():
    """init_db() creates the opportunities table."""
    from bot.storage.schema import init_db

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='opportunities'")
        assert cursor.fetchone() is not None
    finally:
        conn.close()
        os.unlink(db_path)


def test_schema_creates_detected_at_index():
    """init_db() creates idx_detected_at index."""
    from bot.storage.schema import init_db

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_detected_at'")
        assert cursor.fetchone() is not None
    finally:
        conn.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_writer_inserts_opportunity():
    """AsyncWriter.enqueue() followed by flush() inserts row in SQLite."""
    from bot.storage.schema import init_db
    from bot.storage.writer import AsyncWriter

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        writer = AsyncWriter(conn)
        writer.start()

        opp = _make_opportunity()
        writer.enqueue(opp)
        await writer.flush()

        cursor = conn.execute("SELECT COUNT(*) FROM opportunities")
        count = cursor.fetchone()[0]
        assert count == 1

        cursor = conn.execute("SELECT market_id, opportunity_type, net_spread FROM opportunities")
        row = cursor.fetchone()
        assert row[0] == "0xabc"
        assert row[1] == "yes_no"
        assert abs(row[2] - 0.192) < 0.0001
    finally:
        await writer.stop()
        conn.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_detected_at_stored_as_iso_string():
    """detected_at stored as ISO 8601 string."""
    from bot.storage.schema import init_db
    from bot.storage.writer import AsyncWriter

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        writer = AsyncWriter(conn)
        writer.start()

        opp = _make_opportunity(detected_at=datetime(2026, 3, 28, 14, 23, 11))
        writer.enqueue(opp)
        await writer.flush()

        cursor = conn.execute("SELECT detected_at FROM opportunities")
        detected_at_str = cursor.fetchone()[0]
        assert "2026-03-28" in detected_at_str
    finally:
        await writer.stop()
        conn.close()
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# Phase 4 additions — OBS-01 / OBS-04: arb_pairs table and fees_usd fix
# ---------------------------------------------------------------------------

def _make_trade_result():
    """Minimal trade result object for insert_trade tests (all 12 required fields)."""
    from unittest.mock import MagicMock
    result = MagicMock()
    result.market_id = "cond-p4-test"
    result.leg = "yes"
    result.side = "BUY"
    result.token_id = "0xtoken"
    result.price = 0.40
    result.size = 10.0
    result.size_filled = 10.0
    result.order_id = "ord-p4-001"
    result.status = "filled"
    result.kelly_size_usd = 10.0
    result.vwap_price = 0.40
    result.error_msg = None
    return result


def test_insert_trade_fees_usd_not_zero_p4():
    """insert_trade with fees_usd=0.5 stores 0.5, not the 0.0 placeholder (P4 stub)."""
    from bot.storage.schema import init_db, init_trades_table, insert_trade
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        init_trades_table(conn)
        result = _make_trade_result()
        insert_trade(conn, result, "Will X happen?", "trade-abc-123", fees_usd=0.5)
        cursor = conn.execute("SELECT fees_usd FROM trades WHERE trade_id = 'trade-abc-123'")
        row = cursor.fetchone()
        assert row is not None
        assert abs(row[0] - 0.5) < 0.0001
    finally:
        conn.close()
        os.unlink(db_path)


def test_arb_pairs_table_exists():
    """init_arb_pairs_table() creates the arb_pairs table in sqlite_master."""
    from bot.storage.schema import init_db, init_arb_pairs_table
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        init_arb_pairs_table(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='arb_pairs'"
        )
        assert cursor.fetchone() is not None
    finally:
        conn.close()
        os.unlink(db_path)


def _make_arb_pair_p4():
    """Return a dict with all 14 arb_pairs fields from D-11 (Phase 4 tests)."""
    return {
        "arb_id": "arb-uuid-0001",
        "yes_trade_id": "trade-yes-001",
        "no_trade_id": "trade-no-001",
        "market_id": "0xmarket123",
        "market_question": "Will candidate X win the election?",
        "yes_entry_price": 0.40,
        "no_entry_price": 0.55,
        "size_usd": 10.0,
        "gross_pnl": 0.05,
        "fees_usd": 0.015,
        "net_pnl": 0.035,
        "entry_time": "2026-04-15T10:00:00Z",
        "exit_time": "2026-04-15T10:00:05Z",
        "hold_seconds": 5.0,
    }


def test_insert_arb_pair_creates_row():
    """insert_arb_pair() inserts a row with correct arb_id."""
    from bot.storage.schema import init_db, init_arb_pairs_table, insert_arb_pair
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        init_arb_pairs_table(conn)
        pair = _make_arb_pair_p4()
        insert_arb_pair(conn, pair)
        cursor = conn.execute(
            "SELECT arb_id FROM arb_pairs WHERE arb_id = 'arb-uuid-0001'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "arb-uuid-0001"
    finally:
        conn.close()
        os.unlink(db_path)


def test_insert_arb_pair_all_columns():
    """arb_pairs row contains correct values for all 14 D-11 fields."""
    from bot.storage.schema import init_db, init_arb_pairs_table, insert_arb_pair
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        init_arb_pairs_table(conn)
        pair = _make_arb_pair_p4()
        insert_arb_pair(conn, pair)
        cursor = conn.execute("SELECT * FROM arb_pairs WHERE arb_id = 'arb-uuid-0001'")
        row = cursor.fetchone()
        col_names = [desc[0] for desc in cursor.description]
        data = dict(zip(col_names, row))
        assert data["arb_id"] == "arb-uuid-0001"
        assert data["yes_trade_id"] == "trade-yes-001"
        assert data["no_trade_id"] == "trade-no-001"
        assert data["market_id"] == "0xmarket123"
        assert data["market_question"] == "Will candidate X win the election?"
        assert abs(data["yes_entry_price"] - 0.40) < 0.0001
        assert abs(data["no_entry_price"] - 0.55) < 0.0001
        assert abs(data["size_usd"] - 10.0) < 0.0001
        assert abs(data["gross_pnl"] - 0.05) < 0.0001
        assert abs(data["fees_usd"] - 0.015) < 0.0001
        assert abs(data["net_pnl"] - 0.035) < 0.0001
        assert data["entry_time"] == "2026-04-15T10:00:00Z"
        assert data["exit_time"] == "2026-04-15T10:00:05Z"
        assert abs(data["hold_seconds"] - 5.0) < 0.0001
    finally:
        conn.close()
        os.unlink(db_path)


def test_insert_arb_pair_idempotent():
    """INSERT OR IGNORE — inserting same arb_id twice does not raise; row count stays at 1."""
    from bot.storage.schema import init_db, init_arb_pairs_table, insert_arb_pair
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = init_db(db_path)
        init_arb_pairs_table(conn)
        pair = _make_arb_pair_p4()
        insert_arb_pair(conn, pair)
        insert_arb_pair(conn, pair)  # duplicate — must not raise
        cursor = conn.execute("SELECT COUNT(*) FROM arb_pairs WHERE arb_id = 'arb-uuid-0001'")
        assert cursor.fetchone()[0] == 1
    finally:
        conn.close()
        os.unlink(db_path)
