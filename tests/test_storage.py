import asyncio
import sqlite3
import tempfile
import os
from datetime import datetime
import pytest

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
    """Minimal trade result object for insert_trade tests."""
    from unittest.mock import MagicMock
    result = MagicMock()
    result.trade_id = "trade-abc-123"
    result.token_id = "0xtoken"
    result.side = "BUY"
    result.size = 10.0
    result.price = 0.40
    result.status = "filled"
    result.submitted_at = "2026-04-15T10:00:00Z"
    result.filled_at = "2026-04-15T10:00:01Z"
    return result


def test_insert_trade_fees_usd_not_zero():
    """insert_trade with fees_usd=0.5 stores 0.5, not the 0.0 placeholder."""
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


def _make_arb_pair():
    """Return a dict with all 14 arb_pairs fields from D-11."""
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
        pair = _make_arb_pair()
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
        pair = _make_arb_pair()
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
        pair = _make_arb_pair()
        insert_arb_pair(conn, pair)
        insert_arb_pair(conn, pair)  # duplicate — must not raise
        cursor = conn.execute("SELECT COUNT(*) FROM arb_pairs WHERE arb_id = 'arb-uuid-0001'")
        assert cursor.fetchone()[0] == 1
    finally:
        conn.close()
        os.unlink(db_path)
