import asyncio
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

pytestmark = pytest.mark.unit


def _make_config():
    from bot.config import BotConfig
    return BotConfig(
        poly_api_key="k", poly_api_secret="s", poly_api_passphrase="p",
        wallet_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        polygon_rpc_http="https://polygon.example.com",
        polygon_rpc_ws="wss://polygon.example.com",
        scan_interval_seconds=0,  # 0 for fast test cycles
    )


@pytest.mark.asyncio
async def test_no_orders_placed():
    """dry_run.run() never calls any order placement methods."""
    from bot import dry_run

    config = _make_config()
    mock_client = MagicMock()

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Patch all Phase 2 modules to return quickly
        with patch("bot.dry_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]) as mock_fetch, \
             patch("bot.dry_run.WebSocketClient") as mock_ws_cls, \
             patch("bot.dry_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.dry_run.detect_yes_no_opportunities", return_value=[]), \
             patch("bot.dry_run.detect_cross_market_opportunities", return_value=[]):

            mock_ws = MagicMock()
            mock_ws.run = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            # Run for a very short duration (fraction of a second)
            await asyncio.wait_for(
                dry_run.run(config, mock_client, duration_hours=0.0001, db_path=db_path),
                timeout=2.0
            )
    finally:
        os.unlink(db_path)

    # Verify no order methods called
    assert not mock_client.create_order.called
    assert not mock_client.post_order.called


@pytest.mark.asyncio
async def test_opportunities_enqueued_to_writer():
    """Detected opportunities are enqueued to the SQLite writer."""
    from bot import dry_run
    from bot.detection.opportunity import ArbitrageOpportunity
    from datetime import datetime

    config = _make_config()
    mock_client = MagicMock()

    fake_opp = ArbitrageOpportunity(
        market_id="0xabc", market_question="Test?", opportunity_type="yes_no",
        category="politics", yes_ask=0.40, no_ask=0.40, gross_spread=0.20,
        estimated_fees=0.008, net_spread=0.192, depth=200.0,
        vwap_yes=0.40, vwap_no=0.40, confidence_score=0.95,
        detected_at=datetime.utcnow(),
    )

    with patch("bot.dry_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
         patch("bot.dry_run.WebSocketClient") as mock_ws_cls, \
         patch("bot.dry_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
         patch("bot.dry_run.detect_yes_no_opportunities", return_value=[fake_opp]), \
         patch("bot.dry_run.detect_cross_market_opportunities", return_value=[]), \
         patch("bot.dry_run.init_db") as mock_init_db, \
         patch("bot.dry_run.AsyncWriter") as mock_writer_cls:

        mock_ws = MagicMock()
        mock_ws.run = AsyncMock()
        mock_ws_cls.return_value = mock_ws

        mock_writer = MagicMock()
        mock_writer.start = MagicMock()
        mock_writer.enqueue = MagicMock()
        mock_writer.stop = AsyncMock()
        mock_writer_cls.return_value = mock_writer

        mock_init_db.return_value = MagicMock()

        await asyncio.wait_for(
            dry_run.run(config, mock_client, duration_hours=0.0001),
            timeout=2.0
        )

    assert mock_writer.enqueue.called
    enqueued = mock_writer.enqueue.call_args[0][0]
    assert enqueued.market_id == "0xabc"


@pytest.mark.asyncio
async def test_load_event_groups_called_at_startup():
    """dry_run.run() calls load_event_groups() once before the scan loop."""
    from bot import dry_run

    config = _make_config()
    mock_client = MagicMock()

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        with patch("bot.dry_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
             patch("bot.dry_run.WebSocketClient") as mock_ws_cls, \
             patch("bot.dry_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.dry_run.detect_yes_no_opportunities", return_value=[]), \
             patch("bot.dry_run.detect_cross_market_opportunities", return_value=[]), \
             patch("bot.dry_run.load_event_groups") as mock_leg:

            mock_ws = MagicMock()
            mock_ws.run = AsyncMock()
            mock_ws_cls.return_value = mock_ws

            await asyncio.wait_for(
                dry_run.run(config, mock_client, duration_hours=0.0001, db_path=db_path),
                timeout=2.0
            )

        mock_leg.assert_called_once()
    finally:
        os.unlink(db_path)
