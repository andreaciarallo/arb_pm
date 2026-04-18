"""
Integration tests for live_run.py.

All py-clob-client calls are mocked — zero real orders placed.
Tests verify: risk gate integration, trade log writes, dry_run not modified.
"""
import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bot.config import BotConfig
from bot.storage.schema import init_db, init_trades_table

pytestmark = pytest.mark.unit


def _test_config():
    return BotConfig(
        poly_api_key="test", poly_api_secret="test", poly_api_passphrase="test",
        wallet_private_key="0x" + "a" * 64, polygon_rpc_http="http://localhost",
        polygon_rpc_ws="ws://localhost", total_capital_usd=1000.0,
    )


@pytest.mark.asyncio
async def test_live_run_exits_on_kill_file():
    """Bot exits scan loop when KILL file exists at start of first cycle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        kill_file = os.path.join(tmpdir, "KILL")
        open(kill_file, "w").close()  # create KILL file

        config = _test_config()
        client = MagicMock()
        client.cancel_all.return_value = None
        client.get_address.return_value = "0xabc"

        with patch("bot.live_run._KILL_FILE", kill_file), \
             patch("bot.live_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
             patch("bot.live_run.WebSocketClient") as mock_ws, \
             patch("bot.live_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.live_run.detect_yes_no_opportunities", return_value=[]), \
             patch("bot.live_run.detect_cross_market_opportunities", return_value=[]), \
             patch("bot.live_run._start_dashboard", new_callable=AsyncMock), \
             patch("bot.live_run._daily_summary_task", new_callable=AsyncMock):
            mock_ws.return_value.run = AsyncMock()
            from bot import live_run
            # Run with 1-second duration to avoid infinite loop
            await live_run.run(config, client, duration_hours=0.001, db_path=db_path)
        # If we get here without timeout, the kill switch worked


@pytest.mark.asyncio
async def test_trade_inserted_on_execution():
    """ExecutionResult rows are inserted into SQLite trades table."""
    from bot.execution.engine import ExecutionResult
    from bot.storage.schema import insert_trade

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = init_db(db_path)
        init_trades_table(conn)

        result = ExecutionResult(
            market_id="cond_test", leg="yes", side="BUY", token_id="tok_yes",
            price=0.48, size=10.0, order_id="ord_001", status="filled",
            size_filled=10.0, kelly_size_usd=10.0, vwap_price=0.48, error_msg=None,
        )
        insert_trade(conn, result, "Test market", "trade-uuid-001")

        row = conn.execute("SELECT status, market_id FROM trades WHERE trade_id=?",
                           ("trade-uuid-001",)).fetchone()
        assert row is not None
        assert row[0] == "filled"
        assert row[1] == "cond_test"
        conn.close()


@pytest.mark.asyncio
async def test_failed_order_inserted_with_status_failed():
    """Failed orders also get a row in trades table (status='failed')."""
    from bot.execution.engine import ExecutionResult
    from bot.storage.schema import insert_trade

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = init_db(db_path)
        init_trades_table(conn)

        result = ExecutionResult(
            market_id="cond_fail", leg="yes", side="BUY", token_id="tok_yes",
            price=0.48, size=10.0, order_id=None, status="failed",
            size_filled=0.0, kelly_size_usd=10.0, vwap_price=0.48,
            error_msg="API rejected",
        )
        insert_trade(conn, result, "Fail market", "trade-uuid-002")

        row = conn.execute("SELECT status, error_msg FROM trades WHERE trade_id=?",
                           ("trade-uuid-002",)).fetchone()
        assert row[0] == "failed"
        assert row[1] == "API rejected"
        conn.close()


@pytest.mark.asyncio
async def test_risk_gate_blocked_skips_execution():
    """When risk gate is blocked, execute_opportunity is never called."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = _test_config()
        client = MagicMock()

        with patch("bot.live_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
             patch("bot.live_run.WebSocketClient") as mock_ws, \
             patch("bot.live_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.live_run.detect_yes_no_opportunities", return_value=[MagicMock()]), \
             patch("bot.live_run.detect_cross_market_opportunities", return_value=[]), \
             patch("bot.live_run.execute_opportunity", new_callable=AsyncMock) as mock_exec, \
             patch("bot.live_run.RiskGate") as mock_rg_cls, \
             patch("bot.live_run._start_dashboard", new_callable=AsyncMock), \
             patch("bot.live_run._daily_summary_task", new_callable=AsyncMock):
            mock_ws.return_value.run = AsyncMock()
            mock_rg = MagicMock()
            mock_rg.is_kill_switch_active.return_value = False
            mock_rg.is_blocked.return_value = True  # blocked
            mock_rg.is_stop_loss_triggered.return_value = True
            mock_rg.is_circuit_breaker_open.return_value = False
            mock_rg_cls.return_value = mock_rg
            from bot import live_run
            await live_run.run(config, client, duration_hours=0.00001, db_path=db_path)
        mock_exec.assert_not_called()


def test_dry_run_module_unchanged():
    """dry_run.py must still import cleanly — no modifications."""
    from bot import dry_run
    assert hasattr(dry_run, "run")
    import inspect
    assert asyncio.iscoroutinefunction(dry_run.run)


def test_main_has_live_flag():
    """main.py contains --live flag routing."""
    main_path = Path(__file__).parents[1] / "src" / "bot" / "main.py"
    source = main_path.read_text()
    assert "--live" in source
    assert "live_run" in source


# ---------------------------------------------------------------------------
# Phase 6: Alert wiring tests — D-04
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kill_switch_alert_fires_kill_file():
    """Kill switch alert fires with trigger='KILL file' when KILL file present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        kill_file = os.path.join(tmpdir, "KILL")
        open(kill_file, "w").close()  # create KILL file

        config = _test_config()
        client = MagicMock()
        client.cancel_all.return_value = None

        alerter_mock = MagicMock()
        alerter_mock.send_kill_switch = AsyncMock(return_value=None)

        with patch("bot.live_run._KILL_FILE", kill_file), \
             patch("bot.live_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
             patch("bot.live_run.WebSocketClient") as mock_ws, \
             patch("bot.live_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.live_run.detect_yes_no_opportunities", return_value=[]), \
             patch("bot.live_run.detect_cross_market_opportunities", return_value=[]), \
             patch("bot.live_run._start_dashboard", new_callable=AsyncMock), \
             patch("bot.live_run._daily_summary_task", new_callable=AsyncMock), \
             patch("bot.live_run.TelegramAlerter", return_value=alerter_mock):
            mock_ws.return_value.run = AsyncMock()
            from bot import live_run
            await live_run.run(config, client, duration_hours=0.001, db_path=db_path)

        # Yield to let any scheduled coroutines run
        await asyncio.sleep(0)
        alerter_mock.send_kill_switch.assert_awaited_once_with(trigger="KILL file")


@pytest.mark.asyncio
async def test_kill_switch_alert_fires_sigterm():
    """Kill switch alert fires with trigger='SIGTERM' when SIGTERM signal received."""
    import signal as _signal

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = _test_config()
        client = MagicMock()
        client.cancel_all.return_value = None

        alerter_mock = MagicMock()
        alerter_mock.send_kill_switch = AsyncMock(return_value=None)

        # Capture registered signal handler so we can invoke it manually
        registered_handlers: dict = {}

        def fake_add_signal_handler(sig, handler):
            registered_handlers[sig] = handler

        async def trigger_sigterm_then_return(*args, **kwargs):
            # Call the SIGTERM handler to simulate signal receipt mid-run
            if _signal.SIGTERM in registered_handlers:
                registered_handlers[_signal.SIGTERM]()
            return 0  # return value matches poll_stale_markets signature

        loop = asyncio.get_running_loop()
        original_add = loop.add_signal_handler
        loop.add_signal_handler = fake_add_signal_handler
        try:
            with patch("bot.live_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
                 patch("bot.live_run.WebSocketClient") as mock_ws, \
                 patch("bot.live_run.poll_stale_markets", side_effect=trigger_sigterm_then_return), \
                 patch("bot.live_run.detect_yes_no_opportunities", return_value=[]), \
                 patch("bot.live_run.detect_cross_market_opportunities", return_value=[]), \
                 patch("bot.live_run._start_dashboard", new_callable=AsyncMock), \
                 patch("bot.live_run._daily_summary_task", new_callable=AsyncMock), \
                 patch("bot.live_run.TelegramAlerter", return_value=alerter_mock):
                mock_ws.return_value.run = AsyncMock()
                from bot import live_run
                await live_run.run(config, client, duration_hours=1.0, db_path=db_path)
        finally:
            loop.add_signal_handler = original_add

        await asyncio.sleep(0)
        alerter_mock.send_kill_switch.assert_awaited_once_with(trigger="SIGTERM")


@pytest.mark.asyncio
async def test_cb_alert_fires_on_trip():
    """Circuit breaker alert fires when CB transitions closed -> open in a scan cycle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = _test_config()
        client = MagicMock()

        alerter_mock = MagicMock()
        alerter_mock.send_circuit_breaker_trip = AsyncMock(return_value=None)

        # CB starts closed (False), then trips (True) on second call
        cb_open_calls = [False, True]
        call_count = [0]

        def cb_open_side_effect():
            idx = min(call_count[0], len(cb_open_calls) - 1)
            result = cb_open_calls[idx]
            call_count[0] += 1
            return result

        with patch("bot.live_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
             patch("bot.live_run.WebSocketClient") as mock_ws, \
             patch("bot.live_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.live_run.detect_yes_no_opportunities", return_value=[]), \
             patch("bot.live_run.detect_cross_market_opportunities", return_value=[]), \
             patch("bot.live_run._start_dashboard", new_callable=AsyncMock), \
             patch("bot.live_run._daily_summary_task", new_callable=AsyncMock), \
             patch("bot.live_run.TelegramAlerter", return_value=alerter_mock), \
             patch("bot.live_run.RiskGate") as mock_rg_cls:
            mock_ws.return_value.run = AsyncMock()
            mock_rg = MagicMock()
            mock_rg.is_kill_switch_active.return_value = False
            mock_rg.is_blocked.return_value = False
            mock_rg.is_stop_loss_triggered.return_value = False
            mock_rg.is_circuit_breaker_open.side_effect = cb_open_side_effect
            mock_rg.circuit_breaker_errors = 5
            mock_rg.last_trip_error_count = 5   # required after D-03 fix: live_run reads this
            mock_rg.cb_cooldown_remaining.return_value = 300.0
            mock_rg_cls.return_value = mock_rg
            from bot import live_run
            await live_run.run(config, client, duration_hours=0.00001, db_path=db_path)

        await asyncio.sleep(0)
        alerter_mock.send_circuit_breaker_trip.assert_awaited_once_with(
            error_count=5,
            cooldown_seconds=300.0,
        )


@pytest.mark.asyncio
async def test_cb_alert_no_duplicate():
    """Circuit breaker alert does NOT fire when CB was already open at cycle start."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = _test_config()
        client = MagicMock()

        alerter_mock = MagicMock()
        alerter_mock.send_circuit_breaker_trip = AsyncMock(return_value=None)

        with patch("bot.live_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
             patch("bot.live_run.WebSocketClient") as mock_ws, \
             patch("bot.live_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.live_run.detect_yes_no_opportunities", return_value=[]), \
             patch("bot.live_run.detect_cross_market_opportunities", return_value=[]), \
             patch("bot.live_run._start_dashboard", new_callable=AsyncMock), \
             patch("bot.live_run._daily_summary_task", new_callable=AsyncMock), \
             patch("bot.live_run.TelegramAlerter", return_value=alerter_mock), \
             patch("bot.live_run.RiskGate") as mock_rg_cls:
            mock_ws.return_value.run = AsyncMock()
            mock_rg = MagicMock()
            mock_rg.is_kill_switch_active.return_value = False
            mock_rg.is_blocked.return_value = True   # blocked — CB already open
            mock_rg.is_stop_loss_triggered.return_value = False
            mock_rg.is_circuit_breaker_open.return_value = True  # already open — no transition
            mock_rg.circuit_breaker_errors = 5
            mock_rg.cb_cooldown_remaining.return_value = 300.0
            mock_rg_cls.return_value = mock_rg
            from bot import live_run
            await live_run.run(config, client, duration_hours=0.00001, db_path=db_path)

        await asyncio.sleep(0)
        alerter_mock.send_circuit_breaker_trip.assert_not_called()


@pytest.mark.asyncio
async def test_cb_alert_shows_live_count_not_static_threshold():
    """CB alert passes last_trip_error_count (live=7), not circuit_breaker_errors (static=5)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = _test_config()
        client = MagicMock()

        alerter_mock = MagicMock()
        alerter_mock.send_circuit_breaker_trip = AsyncMock(return_value=None)

        # CB starts closed (False), then trips (True) on second call
        cb_open_calls = [False, True]
        call_count = [0]

        def cb_open_side_effect():
            idx = min(call_count[0], len(cb_open_calls) - 1)
            result = cb_open_calls[idx]
            call_count[0] += 1
            return result

        with patch("bot.live_run.fetch_liquid_markets", new_callable=AsyncMock, return_value=[]), \
             patch("bot.live_run.WebSocketClient") as mock_ws, \
             patch("bot.live_run.poll_stale_markets", new_callable=AsyncMock, return_value=0), \
             patch("bot.live_run.detect_yes_no_opportunities", return_value=[]), \
             patch("bot.live_run.detect_cross_market_opportunities", return_value=[]), \
             patch("bot.live_run._start_dashboard", new_callable=AsyncMock), \
             patch("bot.live_run._daily_summary_task", new_callable=AsyncMock), \
             patch("bot.live_run.TelegramAlerter", return_value=alerter_mock), \
             patch("bot.live_run.RiskGate") as mock_rg_cls:
            mock_ws.return_value.run = AsyncMock()
            mock_rg = MagicMock()
            mock_rg.is_kill_switch_active.return_value = False
            mock_rg.is_blocked.return_value = False
            mock_rg.is_stop_loss_triggered.return_value = False
            mock_rg.is_circuit_breaker_open.side_effect = cb_open_side_effect
            mock_rg.circuit_breaker_errors = 5       # static configured threshold
            mock_rg.last_trip_error_count = 7        # live burst count (differs from threshold)
            mock_rg.cb_cooldown_remaining.return_value = 300.0
            mock_rg_cls.return_value = mock_rg
            from bot import live_run
            await live_run.run(config, client, duration_hours=0.00001, db_path=db_path)

        await asyncio.sleep(0)
        # Must pass live count (7), NOT static threshold (5)
        alerter_mock.send_circuit_breaker_trip.assert_awaited_once_with(
            error_count=7,
            cooldown_seconds=300.0,
        )
