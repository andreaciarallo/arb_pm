"""
FastAPI monitoring dashboard for the Polymarket arbitrage bot (OBS-03).

Serves:
  GET /          — Single-page HTML dashboard (auto-refresh every 10s via JS)
  GET /api/status — JSON metrics snapshot consumed by dashboard JS

Runs as asyncio background task in same event loop as scan loop (D-07).
No auth in Phase 4 — VPS firewall provides access control (D-18).
Port 8080 (D-09).
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger


@dataclass
class AppState:
    """
    Shared mutable state between the scan loop and the FastAPI handlers.

    NOT frozen — the scan loop updates daily_pnl_usd, total_trades, cycle_count,
    last_scan_utc after each cycle. FastAPI handlers read these values.

    CPython asyncio is single-threaded — reads/writes from the same event loop
    are safe without locks (uvicorn workers=1 enforced by programmatic Server.serve()).
    """
    conn: sqlite3.Connection
    risk_gate: Any                       # RiskGate instance from live_run.py
    total_capital_usd: float
    daily_pnl_usd: float = 0.0          # Updated by scan loop
    total_trades: int = 0                # Updated by scan loop
    cycle_count: int = 0                 # Updated by scan loop
    last_scan_utc: str = ""              # Updated by scan loop ("HH:MM:SS" UTC)


def _query_recent_trades(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Query last N trades ordered newest first."""
    try:
        cursor = conn.execute(
            "SELECT trade_id, market_question, leg, size, price, fees_usd, net_pnl, status, submitted_at "
            "FROM trades ORDER BY submitted_at DESC LIMIT ?",
            (limit,)
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f"Dashboard: recent_trades query failed: {e}")
        return []


def _query_arb_pairs(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Query last N completed arb pairs ordered newest first."""
    try:
        cursor = conn.execute(
            "SELECT arb_id, market_question, yes_entry_price, no_entry_price, "
            "size_usd, hold_seconds, gross_pnl, fees_usd, net_pnl, entry_time "
            "FROM arb_pairs ORDER BY entry_time DESC LIMIT ?",
            (limit,)
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f"Dashboard: arb_pairs query failed: {e}")
        return []


def _query_open_positions_count(conn: sqlite3.Connection) -> int:
    """Count YES legs filled with no corresponding arb_pairs row (open positions)."""
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM trades t "
            "LEFT JOIN arb_pairs ap ON ap.yes_trade_id = t.trade_id "
            "WHERE t.leg = 'yes' AND t.status = 'filled' AND ap.arb_id IS NULL"
        )
        return cursor.fetchone()[0] or 0
    except Exception as e:
        logger.warning(f"Dashboard: open_positions query failed: {e}")
        return 0


def _query_capital_efficiency(conn: sqlite3.Connection, days: int, total_capital_usd: float) -> float | None:
    """Compute net_pnl / total_capital_usd for arb pairs in last N days. None if no data."""
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        cursor = conn.execute(
            "SELECT SUM(net_pnl) FROM arb_pairs WHERE entry_time >= ?",
            (cutoff,)
        )
        total_pnl = cursor.fetchone()[0]
        if total_pnl is None or total_capital_usd <= 0:
            return None
        return (total_pnl / total_capital_usd) * 100.0
    except Exception as e:
        logger.warning(f"Dashboard: efficiency_{days}d query failed: {e}")
        return None


def _query_total_fees(conn: sqlite3.Connection) -> float:
    """Sum of all fees_usd from trades table."""
    try:
        cursor = conn.execute("SELECT SUM(fees_usd) FROM trades")
        result = cursor.fetchone()[0]
        return result if result is not None else 0.0
    except Exception as e:
        logger.warning(f"Dashboard: total_fees query failed: {e}")
        return 0.0


def _query_avg_fee_rate(conn: sqlite3.Connection) -> float:
    """Average fee rate as percentage (fees_usd / size * 100)."""
    try:
        cursor = conn.execute("SELECT AVG(fees_usd / size * 100) FROM trades WHERE size > 0")
        result = cursor.fetchone()[0]
        return result if result is not None else 0.0
    except Exception as e:
        logger.warning(f"Dashboard: avg_fee_rate query failed: {e}")
        return 0.0


def _derive_bot_status(risk_gate: Any) -> tuple[str, str]:
    """
    Return (status, description) based on RiskGate state.

    Priority: kill_switch > circuit_breaker > stop_loss > running
    """
    if risk_gate.is_kill_switch_active():
        return "stopped", "Kill switch active — all positions closing"

    if risk_gate.is_circuit_breaker_open():
        cooldown_remaining = max(0.0, risk_gate._cb_cooldown_until - time.time())
        minutes = int(cooldown_remaining // 60)
        seconds = int(cooldown_remaining % 60)
        return "blocked", f"Circuit breaker open — cooldown {minutes}m {seconds}s remaining"

    if risk_gate.is_stop_loss_triggered():
        return "paused", "Stop-loss limit reached — trading halted until midnight UTC"

    return "running", "Scan cycle active"


# ---------------------------------------------------------------------------
# Dashboard HTML (single-page, inline CSS + JS, no external dependencies)
# All CSS variables match UI-SPEC Color table exactly.
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Arb Bot Dashboard</title>
<style>
:root {
  --bg-base: #0f1117;
  --bg-card: #1a1d27;
  --border: #2a2d3a;
  --accent: #6366f1;
  --text-primary: #e2e8f0;
  --text-secondary: #64748b;
  --status-running: #22c55e;
  --status-paused: #f59e0b;
  --status-blocked: #f87171;
  --status-stopped: #94a3b8;
  --bg-row-alt: #141720;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 13px;
  line-height: 1.4;
  padding: 32px;
}
.page { max-width: 1280px; margin: 0 auto; }

/* Status bar */
.status-bar {
  background: var(--bg-card);
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.status-left { display: flex; align-items: center; gap: 16px; }
.status-dot {
  width: 10px; height: 10px; border-radius: 50%;
  display: inline-block; margin-right: 6px;
  background: var(--status-running);
}
.status-label { font-size: 11px; font-weight: 600; }
.status-desc { font-size: 11px; color: var(--text-secondary); }
.status-item { font-size: 11px; color: var(--text-secondary); }
.refresh-indicator { font-size: 11px; font-weight: 600; color: var(--accent); }

/* Cards grid */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px;
}
.card-label { font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; }
.card-value { font-size: 16px; font-weight: 600; color: var(--text-primary); }
.card-value.display { font-size: 24px; }
.pnl-positive { color: #22c55e; }
.pnl-negative { color: #f87171; }
.pnl-zero { color: var(--text-secondary); }

/* Section headings */
.section-heading {
  font-size: 16px; font-weight: 600; margin-bottom: 8px;
  color: var(--text-primary);
}

/* Tables */
.table-wrap { overflow-x: auto; margin-bottom: 24px; }
table { width: 100%; border-collapse: collapse; }
thead tr { background: var(--bg-card); position: sticky; top: 0; }
th {
  font-size: 11px; font-weight: 600; color: var(--text-secondary);
  padding: 8px 16px; text-align: left; border-bottom: 1px solid var(--border);
}
th.right { text-align: right; }
th.center { text-align: center; }
td {
  padding: 8px 16px; font-size: 13px; border-bottom: 1px solid var(--border);
  color: var(--text-primary);
}
td.mono { font-family: "SF Mono","Fira Code","Cascadia Code",Consolas,monospace; font-variant-numeric: tabular-nums; }
td.right { text-align: right; }
td.center { text-align: center; }
tbody tr:nth-child(even) { background: var(--bg-row-alt); }
tbody tr:hover { background: #1e2130; }
.market-cell { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Status badge */
.badge {
  display: inline-block; border-radius: 4px; padding: 4px 8px;
  font-size: 11px; font-weight: 600;
}
.badge-filled { background: rgba(34,197,94,0.15); color: #22c55e; }
.badge-partial { background: rgba(245,158,11,0.15); color: #f59e0b; }
.badge-hedged { background: rgba(245,158,11,0.15); color: #f59e0b; }
.badge-failed { background: rgba(248,113,113,0.15); color: #f87171; }
.badge-submitted { background: rgba(148,163,184,0.15); color: #94a3b8; }
.badge-skipped { background: rgba(148,163,184,0.15); color: #94a3b8; }

/* Empty state */
.empty-state { text-align: center; padding: 24px; color: var(--text-secondary); }

/* Bottom panels */
.bottom-panels { display: flex; gap: 24px; }
.panel {
  flex: 1; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 6px; padding: 16px;
}
.panel-row { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; }
.panel-label { color: var(--text-secondary); font-size: 11px; font-weight: 600; }
.panel-value { color: var(--text-primary); font-family: "SF Mono","Fira Code","Cascadia Code",Consolas,monospace; font-variant-numeric: tabular-nums; }

/* Error banner */
.error-banner {
  display: none;
  background: rgba(248,113,113,0.10);
  border: 1px solid rgba(248,113,113,0.3);
  color: #f87171;
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 16px;
  font-size: 13px;
}
</style>
</head>
<body>
<div class="page">
  <div id="error-banner" class="error-banner"></div>

  <div class="status-bar">
    <div class="status-left">
      <div>
        <span id="status-dot" class="status-dot"></span>
        <span id="status-label" class="status-label" style="color: var(--status-running)">RUNNING</span>
        <span id="status-desc" class="status-desc" style="margin-left:8px">Scan cycle active</span>
      </div>
      <span class="status-item">CB: <span id="cb-state">closed</span></span>
      <span class="status-item">Kill: <span id="kill-state">inactive</span></span>
      <span class="status-item">Cycle: <span id="cycle-count">0</span></span>
      <span class="status-item">Last scan: <span id="last-scan">\u2014</span></span>
      <span id="stale-indicator" style="display:none; color: #f87171; font-size: 11px; font-weight: 600;"></span>
    </div>
    <div class="refresh-indicator">Refreshing in <span id="countdown">10</span>s</div>
  </div>

  <div class="cards-grid">
    <div class="card">
      <div class="card-label">DAILY P&L</div>
      <div id="daily-pnl" class="card-value display">$0.00</div>
    </div>
    <div class="card">
      <div class="card-label">TOTAL CAPITAL</div>
      <div id="total-capital" class="card-value">$0.00</div>
    </div>
    <div class="card">
      <div class="card-label">OPEN POSITIONS</div>
      <div id="open-positions" class="card-value">0</div>
    </div>
    <div class="card">
      <div class="card-label">TOTAL TRADES</div>
      <div id="total-trades" class="card-value">0</div>
    </div>
    <div class="card">
      <div class="card-label">7-DAY EFFICIENCY</div>
      <div id="eff-7d" class="card-value">N/A</div>
    </div>
    <div class="card">
      <div class="card-label">30-DAY EFFICIENCY</div>
      <div id="eff-30d" class="card-value">N/A</div>
    </div>
  </div>

  <div class="section-heading">LAST 20 TRADES</div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th class="center" style="width:72px">Time</th>
          <th style="min-width:200px">Market</th>
          <th class="center" style="width:40px">Leg</th>
          <th class="right" style="width:72px">Size (USD)</th>
          <th class="right" style="width:60px">Price</th>
          <th class="right" style="width:64px">Fees (USD)</th>
          <th class="right" style="width:72px">Net P&L</th>
          <th class="center" style="width:76px">Status</th>
        </tr>
      </thead>
      <tbody id="trades-body">
        <tr><td colspan="8" class="empty-state">No trades recorded<br><span style="font-size:11px">Bot is scanning. Executed trades will appear here.</span></td></tr>
      </tbody>
    </table>
  </div>

  <div class="section-heading">PER-ARB ANALYTICS</div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="width:88px">Arb ID</th>
          <th>Market</th>
          <th class="right" style="width:68px">Entry YES</th>
          <th class="right" style="width:68px">Entry NO</th>
          <th class="right" style="width:72px">Size (USD)</th>
          <th class="right" style="width:64px">Hold</th>
          <th class="right" style="width:72px">Gross P&L</th>
          <th class="right" style="width:64px">Fees</th>
          <th class="right" style="width:72px">Net P&L</th>
        </tr>
      </thead>
      <tbody id="arb-body">
        <tr><td colspan="9" class="empty-state">No completed arbs<br><span style="font-size:11px">Arb pairs appear here after both legs are confirmed filled.</span></td></tr>
      </tbody>
    </table>
  </div>

  <div class="bottom-panels">
    <div class="panel">
      <div class="section-heading" style="margin-bottom:16px">EXECUTION COST BREAKDOWN</div>
      <div class="panel-row">
        <span class="panel-label">Total fees paid</span>
        <span id="total-fees" class="panel-value">$0.0000</span>
      </div>
      <div class="panel-row">
        <span class="panel-label">Avg fee rate</span>
        <span id="avg-fee-rate" class="panel-value">0.00%</span>
      </div>
    </div>
    <div class="panel">
      <div class="section-heading" style="margin-bottom:16px">CAPITAL EFFICIENCY</div>
      <div class="panel-row">
        <span class="panel-label">7-day</span>
        <span id="panel-eff-7d" class="panel-value">N/A</span>
      </div>
      <div class="panel-row">
        <span class="panel-label">30-day</span>
        <span id="panel-eff-30d" class="panel-value">N/A</span>
      </div>
      <div style="font-size:11px; color: var(--text-secondary); margin-top:8px">Need at least one completed arb to compute efficiency.</div>
    </div>
  </div>
</div>

<script>
'use strict';
const STATUS_COLORS = {
  running: '#22c55e',
  paused: '#f59e0b',
  blocked: '#f87171',
  stopped: '#94a3b8',
  degraded: '#f87171',
};

let countdown = 10;
let consecutiveFails = 0;
let lastSuccessTime = null;

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function pnlStr(v, decimals = 4) {
  if (v === null || v === undefined) return '\u2014';
  const abs = Math.abs(v).toFixed(decimals);
  if (v > 0) return '+$' + abs;
  if (v < 0) return '-$' + abs;
  return '$' + abs;
}

function effStr(v) {
  if (v === null || v === undefined) return 'N/A';
  const s = Math.abs(v).toFixed(2) + '%';
  return (v >= 0 ? '+' : '-') + s;
}

function pnlClass(v) {
  if (v === null || v === undefined) return '';
  if (v > 0) return 'pnl-positive';
  if (v < 0) return 'pnl-negative';
  return 'pnl-zero';
}

function badgeClass(status) {
  const map = {filled:'badge-filled',partial:'badge-partial',hedged:'badge-hedged',
                failed:'badge-failed',submitted:'badge-submitted',skipped:'badge-skipped'};
  return map[status] || 'badge-submitted';
}

function formatTime(iso) {
  if (!iso) return '\u2014';
  try { return new Date(iso).toLocaleTimeString('en-GB', {timeZone:'UTC',hour12:false}); }
  catch(e) { return iso; }
}

function holdStr(secs) {
  if (secs === null || secs === undefined) return '\u2014';
  if (secs < 60) return Math.round(secs) + 's';
  const m = Math.floor(secs / 60), s = Math.round(secs % 60);
  return m + 'm ' + s + 's';
}

function setEl(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setElClass(id, cls) {
  const el = document.getElementById(id);
  if (el) { el.className = el.className.replace(/pnl-[a-z]+/g, '').trim(); if (cls) el.classList.add(cls); }
}

function renderTrades(trades) {
  const tbody = document.getElementById('trades-body');
  if (!trades || trades.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No trades recorded<br><span style="font-size:11px">Bot is scanning. Executed trades will appear here.</span></td></tr>';
    return;
  }
  const rows = trades.map(t => {
    const pnlV = t.net_pnl;
    const pnlTxt = pnlStr(pnlV);
    const pnlCls = pnlClass(pnlV);
    const leg = (t.leg || '').toUpperCase();
    return '<tr>' +
      '<td class="mono center" style="font-size:11px">' + formatTime(t.submitted_at) + '</td>' +
      '<td class="market-cell" title="' + esc(t.market_question) + '">' + esc((t.market_question || '').substring(0,48)) + '</td>' +
      '<td class="center" style="font-size:11px;font-weight:600">' + leg + '</td>' +
      '<td class="mono right">$' + (t.size || 0).toFixed(2) + '</td>' +
      '<td class="mono right">' + (t.price || 0).toFixed(4) + '</td>' +
      '<td class="mono right">$' + (t.fees_usd || 0).toFixed(4) + '</td>' +
      '<td class="mono right ' + pnlCls + '">' + pnlTxt + '</td>' +
      '<td class="center"><span class="badge ' + badgeClass(t.status) + '">' + (t.status || '') + '</span></td>' +
      '</tr>';
  });
  tbody.innerHTML = rows.join('');
}

function renderArbs(arbs) {
  const tbody = document.getElementById('arb-body');
  if (!arbs || arbs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No completed arbs<br><span style="font-size:11px">Arb pairs appear here after both legs are confirmed filled.</span></td></tr>';
    return;
  }
  const rows = arbs.map(a => {
    const netCls = pnlClass(a.net_pnl);
    const grossCls = pnlClass(a.gross_pnl);
    return '<tr>' +
      '<td class="mono" style="font-size:11px">' + (a.arb_id || '').substring(0,8) + '</td>' +
      '<td class="market-cell">' + esc((a.market_question || '').substring(0,48)) + '</td>' +
      '<td class="mono right">' + (a.yes_entry_price || 0).toFixed(4) + '</td>' +
      '<td class="mono right">' + (a.no_entry_price || 0).toFixed(4) + '</td>' +
      '<td class="mono right">$' + (a.size_usd || 0).toFixed(2) + '</td>' +
      '<td class="mono right">' + holdStr(a.hold_seconds) + '</td>' +
      '<td class="mono right ' + grossCls + '">' + pnlStr(a.gross_pnl) + '</td>' +
      '<td class="mono right">$' + (a.fees_usd || 0).toFixed(4) + '</td>' +
      '<td class="mono right ' + netCls + '">' + pnlStr(a.net_pnl) + '</td>' +
      '</tr>';
  });
  tbody.innerHTML = rows.join('');
}

async function refresh() {
  try {
    const r = await fetch('/api/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    consecutiveFails = 0;
    lastSuccessTime = new Date();
    document.getElementById('error-banner').style.display = 'none';
    document.getElementById('stale-indicator').style.display = 'none';

    // Status bar
    const color = STATUS_COLORS[d.bot_status] || STATUS_COLORS.degraded;
    const dot = document.getElementById('status-dot');
    if (dot) dot.style.background = color;
    const lbl = document.getElementById('status-label');
    if (lbl) { lbl.textContent = d.bot_status.toUpperCase(); lbl.style.color = color; }
    setEl('status-desc', d.bot_status_description || '');
    setEl('cb-state', d.circuit_breaker_open ? 'OPEN' : 'closed');
    setEl('kill-state', d.kill_switch_active ? 'ACTIVE' : 'inactive');
    setEl('cycle-count', d.cycle_count);
    setEl('last-scan', d.last_scan_utc || '\u2014');

    // Cards
    const pnl = d.daily_pnl_usd || 0;
    const pnlEl = document.getElementById('daily-pnl');
    if (pnlEl) {
      pnlEl.textContent = pnlStr(pnl, 2);
      pnlEl.className = 'card-value display ' + pnlClass(pnl);
    }
    setEl('total-capital', '$' + (d.total_capital_usd || 0).toFixed(2));
    setEl('open-positions', d.open_positions_count || 0);
    setEl('total-trades', d.total_trades || 0);
    setEl('eff-7d', effStr(d.efficiency_7d_pct));
    setEl('eff-30d', effStr(d.efficiency_30d_pct));

    // Tables
    renderTrades(d.recent_trades || []);
    renderArbs(d.arb_pairs || []);

    // Bottom panels
    setEl('total-fees', '$' + (d.total_fees_paid_usd || 0).toFixed(4));
    setEl('avg-fee-rate', (d.avg_fee_rate_pct || 0).toFixed(2) + '%');
    setEl('panel-eff-7d', effStr(d.efficiency_7d_pct));
    setEl('panel-eff-30d', effStr(d.efficiency_30d_pct));

  } catch(e) {
    consecutiveFails++;
    const banner = document.getElementById('error-banner');
    if (banner) {
      banner.style.display = 'block';
      banner.textContent = 'Data refresh failed \u2014 Retrying in 10s \u2014 check bot logs if this persists';
    }
    if (consecutiveFails >= 3 && lastSuccessTime) {
      const staleEl = document.getElementById('stale-indicator');
      if (staleEl) {
        staleEl.style.display = 'inline';
        staleEl.textContent = '(stale \u2014 last update ' + lastSuccessTime.toLocaleTimeString('en-GB', {timeZone:'UTC',hour12:false}) + ' UTC)';
      }
    }
  }
  countdown = 10;
}

setInterval(refresh, 10000);
setInterval(function() {
  countdown = Math.max(0, countdown - 1);
  setEl('countdown', countdown);
}, 1000);
refresh();
</script>
</body>
</html>"""


def create_app(app_state: AppState) -> FastAPI:
    """
    Create and configure the FastAPI dashboard application.

    Args:
        app_state: Shared state object populated by the scan loop.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(title="Arb Bot Dashboard", docs_url=None, redoc_url=None)
    app.state.obs = app_state

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        return HTMLResponse(content=_DASHBOARD_HTML)

    @app.get("/api/status")
    async def status(request: Request) -> dict:
        state: AppState = request.app.state.obs
        rg = state.risk_gate

        bot_status, bot_status_description = _derive_bot_status(rg)

        cooldown_remaining = max(0.0, getattr(rg, "_cb_cooldown_until", 0.0) - time.time())

        return {
            "bot_status": bot_status,
            "bot_status_description": bot_status_description,
            "circuit_breaker_open": bool(rg.is_circuit_breaker_open()),
            "circuit_breaker_cooldown_seconds": round(cooldown_remaining, 1),
            "kill_switch_active": bool(rg.is_kill_switch_active()),
            "daily_pnl_usd": state.daily_pnl_usd,
            "total_capital_usd": state.total_capital_usd,
            "open_positions_count": _query_open_positions_count(state.conn),
            "total_trades": state.total_trades,
            "cycle_count": state.cycle_count,
            "last_scan_utc": state.last_scan_utc,
            "efficiency_7d_pct": _query_capital_efficiency(state.conn, 7, state.total_capital_usd),
            "efficiency_30d_pct": _query_capital_efficiency(state.conn, 30, state.total_capital_usd),
            "total_fees_paid_usd": _query_total_fees(state.conn),
            "avg_fee_rate_pct": _query_avg_fee_rate(state.conn),
            "recent_trades": _query_recent_trades(state.conn, limit=20),
            "arb_pairs": _query_arb_pairs(state.conn, limit=20),
        }

    return app
