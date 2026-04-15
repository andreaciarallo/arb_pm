# Dashboard Guide

The bot serves a live monitoring dashboard at **port 8080** on whatever machine (VPS or local) is running Docker. No login required — access is restricted by VPS firewall rules only.

---

## Accessing the Dashboard

### From the VPS

```
http://<VPS_IP>:8080
```

Replace `<VPS_IP>` with your server's public IP address (e.g. `http://1.2.3.4:8080`).

### From Another Computer

Open a browser on the other computer and navigate to the same URL. The dashboard works in any modern browser — no installation needed.

> **Firewall note:** Port 8080 must be open in your VPS firewall for incoming TCP connections from your IP. If the page doesn't load, check that the firewall allows your current IP to reach port 8080. The `docker-compose.yml` comment says: *"Restrict in VPS firewall: only allow trusted IPs to reach port 8080"* — by default the port may only be reachable from whitelisted IPs.

### Checking the firewall (DigitalOcean / UFW example)

```bash
# Allow your own IP only
sudo ufw allow from <YOUR_IP> to any port 8080

# Or allow all (less secure — only do this on a trusted network)
sudo ufw allow 8080
```

---

## Dashboard Layout

The page auto-refreshes every **10 seconds**. A countdown in the top-right corner shows when the next refresh fires.

```
┌─────────────────────────────────────────────────────────────────┐
│  STATUS BAR  (bot state, circuit breaker, cycle, last scan)     │
├─────────────────────────────────────────────────────────────────┤
│  DAILY P&L  │  TOTAL CAPITAL  │  OPEN POSITIONS                 │
│  TOTAL TRADES  │  7-DAY EFF  │  30-DAY EFF                      │
├─────────────────────────────────────────────────────────────────┤
│  LAST 20 TRADES table                                            │
├─────────────────────────────────────────────────────────────────┤
│  PER-ARB ANALYTICS table                                         │
├─────────────────────────────────────────────────────────────────┤
│  EXECUTION COST BREAKDOWN  │  CAPITAL EFFICIENCY                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Status Bar

The narrow bar at the top tells you the bot's current operating state at a glance.

| Element | Meaning |
|---------|---------|
| **Coloured dot + label** | Bot status (see states below) |
| **Description text** | Human-readable reason for the current state |
| **CB:** | Circuit breaker — `closed` (normal) or `OPEN` (trading paused, cooldown active) |
| **Kill:** | Kill switch — `inactive` (normal) or `ACTIVE` (all trading stopped, positions closing) |
| **Cycle:** | Number of scan cycles completed since the bot started |
| **Last scan:** | UTC time of the most recent completed scan cycle (`HH:MM:SS`) |
| **Refreshing in Xs** | Countdown to the next automatic data refresh |

### Bot Status States

| Status | Colour | Meaning |
|--------|--------|---------|
| `RUNNING` | Green | Normal operation — scan loop active, orders can be placed |
| `PAUSED` | Amber | Daily stop-loss limit reached — trading halted until midnight UTC reset |
| `BLOCKED` | Red | Circuit breaker open — too many order errors in the last 60s, cooling down |
| `STOPPED` | Grey | Kill switch active — all trading permanently halted until restart |

---

## Metric Cards

Six summary cards sit below the status bar.

### Daily P&L
Cumulative realized net profit/loss for today (UTC). Green = positive, red = negative. Resets to $0.00 at midnight UTC regardless of what the bot is doing.

### Total Capital
The configured total capital from `BOT_TOTAL_CAPITAL_USD` in `secrets.env`. Fixed — does not change at runtime.

### Open Positions
Count of YES-leg trades that are filled but whose corresponding NO leg has not yet completed (i.e. the arb is still "in flight"). Hedge-closed positions are excluded.

### Total Trades
Cumulative number of individual trade legs submitted since the database was created (across all restarts).

### 7-Day Efficiency / 30-Day Efficiency
`net_pnl / total_capital_usd × 100` for completed arb pairs in the last 7 or 30 days. Shows `N/A` until at least one arb pair completes. A positive percentage means the capital is generating returns.

---

## Last 20 Trades Table

Shows the 20 most recent individual order legs, newest first.

| Column | Description |
|--------|-------------|
| **Time** | UTC time the order was submitted (`HH:MM:SS`) |
| **Market** | Market question, truncated to 48 characters. Hover to see the full text in the browser tooltip. |
| **Leg** | `YES`, `NO`, or `HEDGE` — which side of the arb this leg represents |
| **Size (USD)** | Dollar size of the order |
| **Price** | Fill price (0–1 scale, e.g. `0.5200` = 52 cents) |
| **Fees (USD)** | Taker fees paid on this leg |
| **Net P&L** | Realized profit/loss on this leg. Green = profit, red = loss, grey = zero |
| **Status** | Order outcome badge (see below) |

### Status Badges

| Badge | Colour | Meaning |
|-------|--------|---------|
| `filled` | Green | Order fully filled |
| `partial` | Amber | Order partially filled — one-leg risk mitigated by hedge |
| `hedged` | Amber | Hedge sell was executed to close a stranded YES position |
| `failed` | Red | Order rejected or timed out |
| `submitted` | Grey | Order submitted but fill not yet confirmed |
| `skipped` | Grey | Order was intentionally not sent (e.g. pre-execution VWAP gate failed) |

---

## Per-Arb Analytics Table

Shows the 20 most recent **completed** arbitrage pairs, newest first. A row only appears here once both the YES leg and NO leg are confirmed filled.

| Column | Description |
|--------|-------------|
| **Arb ID** | First 8 characters of the internal UUID for this arb pair |
| **Market** | Market question, truncated to 48 characters |
| **Entry YES** | Price paid for the YES token (0–1 scale) |
| **Entry NO** | Price paid for the NO token (0–1 scale) |
| **Size (USD)** | Total dollar size of this arb (both legs combined) |
| **Hold** | Time between YES fill and NO fill (`Xs` or `Xm Ys`) |
| **Gross P&L** | Raw profit before fees: `1 - yes_price - no_price` × size |
| **Fees** | Total fees paid across both legs |
| **Net P&L** | `Gross P&L - Fees`. Green = profitable arb captured |

> **What "gross" means:** If YES was bought at 0.42 and NO at 0.51, the gross spread is `1 - 0.42 - 0.51 = 0.07` (7%). Multiply by size to get the gross P&L in dollars.

---

## Bottom Panels

### Execution Cost Breakdown

| Row | Description |
|-----|-------------|
| **Total fees paid** | Sum of all `fees_usd` across every trade in the database |
| **Avg fee rate** | Average `fees_usd / size × 100` — what percentage of each trade's size goes to fees |

### Capital Efficiency

Mirrors the 7-day and 30-day efficiency cards. Shows `N/A` until at least one arb completes. The note below the values is a reminder that the metric requires completed arbs.

---

## Error States

### Red error banner (top of page)
Appears when the browser fails to fetch `/api/status`. This means:
- The bot container crashed or is restarting
- The VPS lost network connectivity
- The firewall blocked the request

The banner reads: *"Data refresh failed — Retrying in 10s — check bot logs if this persists"*

### Stale indicator (status bar)
After **3 consecutive failures** (30 seconds of no data), a red stale notice appears next to the last-scan time showing when the last successful refresh was. The dashboard continues retrying every 10 seconds automatically.

---

## JSON API

The dashboard also exposes a raw JSON endpoint for scripting or external monitoring:

```
GET http://<VPS_IP>:8080/api/status
```

Example response fields:

```json
{
  "bot_status": "running",
  "bot_status_description": "Scan cycle active",
  "circuit_breaker_open": false,
  "circuit_breaker_cooldown_seconds": 0.0,
  "kill_switch_active": false,
  "daily_pnl_usd": 1.23,
  "total_capital_usd": 1000.0,
  "open_positions_count": 0,
  "total_trades": 42,
  "cycle_count": 180,
  "last_scan_utc": "14:22:07",
  "efficiency_7d_pct": 0.45,
  "efficiency_30d_pct": null,
  "total_fees_paid_usd": 0.312,
  "avg_fee_rate_pct": 0.98,
  "recent_trades": [...],
  "arb_pairs": [...]
}
```

---

## Checking Bot Logs

If the dashboard shows `STOPPED` or `BLOCKED`, check the container logs for root cause:

```bash
# On the VPS
docker compose logs -f --tail 100
```

Or for just the last 50 lines without following:

```bash
docker compose logs --tail 50
```

---

## Stopping and Restarting

```bash
# Graceful stop (respects kill switch — positions should already be closed)
docker compose stop

# Start again
docker compose up -d

# Full rebuild after code changes
docker compose up -d --build

# Check container health
docker compose ps
```

---

## Quick Reference

| Task | How |
|------|-----|
| Open dashboard | Browser → `http://<VPS_IP>:8080` |
| Check raw JSON | `curl http://<VPS_IP>:8080/api/status` |
| View bot logs | `docker compose logs -f` (on VPS) |
| Stop the bot | `docker compose stop` (on VPS) |
| Kill switch (emergency) | `touch /path/to/bot_data/KILL` or send SIGTERM to container |
| Refresh rate | Every 10 seconds (automatic) |
| Dashboard port | `8080` (TCP) |
| Data storage | SQLite, persisted in Docker volume `bot_data` |
