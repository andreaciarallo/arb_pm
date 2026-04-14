"""Unit tests for FastAPI dashboard — OBS-03."""
import sqlite3
import tempfile
import os
import pytest
from unittest.mock import MagicMock
from starlette.testclient import TestClient

pytestmark = pytest.mark.unit

_REQUIRED_STATUS_KEYS = [
    "bot_status", "bot_status_description", "circuit_breaker_open",
    "circuit_breaker_cooldown_seconds", "kill_switch_active",
    "daily_pnl_usd", "total_capital_usd", "open_positions_count",
    "total_trades", "cycle_count", "last_scan_utc",
    "efficiency_7d_pct", "efficiency_30d_pct",
    "total_fees_paid_usd", "avg_fee_rate_pct",
    "recent_trades", "arb_pairs",
]


def _make_app_state(conn):
    from bot.dashboard.app import AppState
    risk_gate = MagicMock()
    risk_gate.is_blocked.return_value = False
    risk_gate.is_circuit_breaker_open.return_value = False
    risk_gate.is_kill_switch_active.return_value = False
    risk_gate.is_stop_loss_triggered.return_value = False
    risk_gate._cb_cooldown_until = 0.0
    return AppState(
        conn=conn,
        risk_gate=risk_gate,
        total_capital_usd=1000.0,
    )


def _make_client():
    from bot.dashboard.app import create_app
    from bot.storage.schema import init_db, init_trades_table, init_arb_pairs_table
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)
    init_trades_table(conn)
    init_arb_pairs_table(conn)
    app_state = _make_app_state(conn)
    app = create_app(app_state)
    client = TestClient(app)
    return client, conn, db_path


def test_status_endpoint_returns_required_keys():
    client, conn, db_path = _make_client()
    try:
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        for key in _REQUIRED_STATUS_KEYS:
            assert key in data, f"Missing key: {key}"
    finally:
        conn.close()
        os.unlink(db_path)


def test_status_bot_status_running():
    client, conn, db_path = _make_client()
    try:
        resp = client.get("/api/status")
        data = resp.json()
        assert data["bot_status"] == "running"
    finally:
        conn.close()
        os.unlink(db_path)


def test_status_bot_status_blocked():
    from bot.dashboard.app import create_app, AppState
    from bot.storage.schema import init_db, init_trades_table, init_arb_pairs_table
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)
    init_trades_table(conn)
    init_arb_pairs_table(conn)
    risk_gate = MagicMock()
    risk_gate.is_blocked.return_value = True
    risk_gate.is_circuit_breaker_open.return_value = True
    risk_gate.is_kill_switch_active.return_value = False
    risk_gate.is_stop_loss_triggered.return_value = False
    risk_gate._cb_cooldown_until = 0.0
    import time
    risk_gate._cb_cooldown_until = time.time() + 300
    app_state = AppState(conn=conn, risk_gate=risk_gate, total_capital_usd=1000.0)
    app = create_app(app_state)
    client = TestClient(app)
    try:
        resp = client.get("/api/status")
        data = resp.json()
        assert data["bot_status"] == "blocked"
    finally:
        conn.close()
        os.unlink(db_path)


def test_root_returns_html():
    client, conn, db_path = _make_client()
    try:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
    finally:
        conn.close()
        os.unlink(db_path)


def test_root_html_contains_refresh_interval():
    client, conn, db_path = _make_client()
    try:
        resp = client.get("/")
        assert "setInterval(refresh, 10000)" in resp.text
    finally:
        conn.close()
        os.unlink(db_path)
