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
