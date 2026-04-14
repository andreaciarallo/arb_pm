# Phase 4: Observability & Monitoring - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 04-observability-monitoring
**Areas discussed:** Notification channel, Dashboard format, Alert triggers, Per-arb analytics schema

---

## Notification Channel

| Option | Description | Selected |
|--------|-------------|----------|
| Telegram only | python-telegram-bot 21+, one token, highest reliability | ✓ |
| Discord only | Webhook-based, no library, simpler setup | |
| Both Telegram + Discord | Parallel delivery, doubles integration work | |

**User's choice:** Telegram only

---

| Option | Description | Selected |
|--------|-------------|----------|
| Keep discord field, wire as httpx webhook fallback | No discord.py library needed, one extra call | |
| Keep discord field, leave inert (no code) | Field stays as documentation only | |
| Remove it — Telegram only, no Discord config noise | Cleaner codebase | ✓ |

**User's choice:** Remove discord_webhook_url entirely

---

## Dashboard Format

| Option | Description | Selected |
|--------|-------------|----------|
| Terminal stats — Rich table printed each cycle | Zero extra deps, visible in docker logs -f | |
| Browser-based — Flask/FastAPI serving live HTML | Proper GUI, visit in browser | ✓ |
| TUI — Textual live terminal dashboard | Rich ncurses-style, adds complexity | |

**User's choice:** Browser-based web dashboard

---

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI | Asyncio-native, clean integration with bot loop | ✓ |
| Flask | Simpler, synchronous, needs thread workaround | |

**User's choice:** FastAPI

---

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-refresh every 10s via JS polling | Simple, no WebSocket server, ≤10s staleness | ✓ |
| WebSocket push — server pushes updates | Truly live, more complex | |

**User's choice:** Auto-refresh every 10s

---

| Option | Description | Selected |
|--------|-------------|----------|
| Core metrics only — bot status, daily P&L, open positions, last 10 trades | Matches OBS-03 exactly | |
| Core + extended — per-arb analytics, execution cost breakdown, capital efficiency | More useful, covers OBS-04 | ✓ |

**User's choice:** Core + extended metrics

---

## Alert Triggers

| Option | Description | Selected |
|--------|-------------|----------|
| Completed arb pair (both legs filled) | One message with net P&L, includes both legs | ✓ |
| Individual leg fills | Separate message per leg — potentially noisy | |
| Errors — circuit breaker trips, API failures | Alerts on critical failures | ✓ |
| Daily P&L summary | One message at midnight UTC | ✓ |

**User's choice:** Completed arb pair + Errors + Daily P&L summary (not individual leg fills)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — send Telegram alert on kill switch activation | Critical event, fires before position close | ✓ |
| No — kill switch is silent | Rely on Docker logs | |

**User's choice:** Yes — kill switch alert

---

| Option | Description | Selected |
|--------|-------------|----------|
| Log failure, continue bot operation — alerts are non-critical | Telegram never stops trading | ✓ |
| Retry once after 5s, then log and continue | One retry for transient blips | |

**User's choice:** Log and continue — no retry

---

## Per-Arb Analytics Schema

| Option | Description | Selected |
|--------|-------------|----------|
| New arb_pairs table linking YES+NO legs | Clean normalization, easy dashboard queries | ✓ |
| arb_id column on trades table — same UUID on both legs | Simpler migration, slightly denormalized | |

**User's choice:** New arb_pairs table

---

| Option | Description | Selected |
|--------|-------------|----------|
| Compute fees_usd at fill time: size_filled × fee_pct | Exact and immediate | ✓ |
| Compute on read from dashboard/analytics query | Simpler write path, view-level concern | |

**User's choice:** Compute at fill time

---

| Option | Description | Selected |
|--------|-------------|----------|
| Write arb_pairs row after both legs confirm | Atomic and accurate, no partial rows | ✓ |
| Write optimistically after YES, update on NO | Captures one-leg failures, more complex | |

**User's choice:** Write only after both legs confirmed

---

## Claude's Discretion

- FastAPI app structure (single file vs. routers, lifespan vs. startup/shutdown events)
- HTML/JS dashboard design and layout
- Telegram message formatting (Markdown vs HTML parse mode, emoji usage)
- Daily summary cron trigger implementation
- `arb_id` UUID generation strategy

## Deferred Ideas

- WebSocket push to dashboard (real-time) — Phase 5 or V2
- Telegram retry logic — not needed
- Discord support — removed entirely
- Grafana + Prometheus — V2
