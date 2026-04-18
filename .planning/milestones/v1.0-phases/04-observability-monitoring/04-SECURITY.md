---
phase: 04-observability-monitoring
security_audit_date: 2026-04-17
asvs_level: 1
block_on: critical
auditor: gsd-security-auditor
threats_total: 11
threats_closed: 11
threats_open: 0
result: SECURED
---

# Phase 04 Security Audit — Observability & Monitoring

## Result: SECURED

**Phase:** 04 — observability-monitoring
**Threats Closed:** 11/11
**ASVS Level:** 1
**Block On:** critical

---

## Threat Verification

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-01-A | Supply chain — PyPI package pinning | mitigate | `requirements.txt:8-10` — fastapi==0.135.3, uvicorn==0.44.0, python-telegram-bot==22.7 pinned to exact versions |
| T-01-B | Test integrity — false green from stubs | mitigate | Wave 0 stubs import from not-yet-existing modules, guaranteeing ImportError (RED) before production code. Pattern confirmed in `04-01-SUMMARY.md`. |
| T-02-A | Schema migration fails silently | mitigate | `schema.py:15,92,189` — all three tables use `CREATE TABLE IF NOT EXISTS`. `init_arb_pairs_table()` present at schema.py:221. |
| T-02-B | discord_webhook_url removal breaks callers | mitigate | `config.py:35-36` — discord_webhook_url absent. telegram_chat_id present. Grep across src/bot returns zero discord matches. |
| T-02-C | insert_trade signature change breaks existing callers | mitigate | `schema.py:150` — `fees_usd: float = 0.0` default preserves backward compatibility. Positional tuple uses the parameter at schema.py:171. |
| T-03-A | Telegram send blocks asyncio event loop | mitigate | `live_run.py:226,361` — both Telegram call sites use `asyncio.create_task()`, not direct await. Fire-and-forget pattern confirmed. |
| T-03-B | TELEGRAM_BOT_TOKEN exposed in Loguru logs | mitigate | `telegram.py:35` — token stored as `self._token` (never logged). `telegram.py:61,65` — only `{e}` (exception repr) written to logger.warning, not the token string. |
| T-03-C | HTML content in TelegramError causes secondary logger failure | mitigate | `telegram.py:60-65` — two-level except: `TelegramError as e` then `Exception as e`; both log only `{e}`. `telegram.py:95` — market_question passed through `html.escape()` before insertion into HTML parse_mode message. |
| T-04-A | Dashboard unauthenticated on port 8080 | accept | Accepted per D-18. VPS firewall is declared access control. `app.py:9` documents: "No auth in Phase 4 — VPS firewall provides access control (D-18)". `docker-compose.yml:18` instructs: "Restrict in VPS firewall: only allow trusted IPs to reach port 8080". See accepted risks log below. |
| T-04-B | SQL injection in dashboard query functions | mitigate | `app.py:48-130` — all six `_query_*` functions use parameterized queries (`conn.execute(sql, (param,))`). No string interpolation used in any SQL statement. `schema.py:46,130,217` — all INSERT statements use `?` positional parameters exclusively. |
| T-04-C | Sensitive data leaked via /api/status response | mitigate | `app.py:631-648` — /api/status response contains only operational metrics (bot_status, pnl, trade counts, efficiency). No private key, API credentials, wallet address, or Telegram token appear in the response payload. `wallet_address` grep returns zero matches in app.py and telegram.py. |

---

## Accepted Risks Log

### T-04-A — Dashboard: No Authentication on Port 8080

**Date accepted:** 2026-04-17
**Decision ID:** D-18
**Risk:** GET /api/status and GET / are publicly accessible to anyone who can reach port 8080 on the VPS. The dashboard exposes operational data (PnL, trade counts, positions, efficiency metrics).
**Transfer mechanism:** N/A
**Compensating control:** VPS network firewall restricts inbound access to port 8080. The docker-compose.yml comment (line 18) explicitly instructs the operator to configure firewall rules allowing only trusted IPs. The dashboard does not expose private keys, API credentials, or trade execution data that could be used to attack the bot. The worst-case consequence of unauthorized read access is information disclosure of performance metrics.
**Review condition:** If the bot is deployed to a shared or public VPS without a firewall, this risk must be re-evaluated and authentication (e.g., HTTP Basic Auth via nginx reverse proxy) added before Phase 5.

---

## Unregistered Threat Flags

No `## Threat Flags` entries were present in any 04-0x-SUMMARY.md that lack a corresponding threat ID in the plan threat models. All threat flags from the SUMMARY files map to documented threats above.

---

## Dashboard Docs/Swagger Exposure

FastAPI is instantiated with `docs_url=None, redoc_url=None` (`app.py:615`). This disables the auto-generated OpenAPI docs and the Swagger UI, which would otherwise expose the full API schema at `/docs` and `/redoc` without authentication. This was not a declared threat in the plan threat model but is present as a defense-in-depth measure.

---

## Notes on Implementation Fidelity

- All SQL in schema.py and app.py uses parameterized queries exclusively; no f-string or %-style SQL interpolation found.
- The Telegram token is loaded from `TELEGRAM_BOT_TOKEN` environment variable via `os.environ.get()` (`config.py:86`). It is stored only in `BotConfig.telegram_bot_token` (a frozen dataclass) and in `TelegramAlerter._token`. Neither field is ever passed to a logger call.
- `wallet_address` is logged once at startup (`main.py:55`) — this is a public blockchain address and does not constitute a secret. The private key (`WALLET_PRIVATE_KEY`) is never logged anywhere in the codebase.
- Polygon RPC URLs (containing embedded Alchemy API keys) are explicitly guarded: `config.py:7-8` documents "Never log the raw POLYGON_RPC_HTTP or POLYGON_RPC_WS values". `main.py:57-58` logs only the string `"configured"` for both.
- The `html.escape()` call in `send_arb_complete()` (`telegram.py:95`) prevents Telegram HTML injection via market question text when using parse_mode="HTML". Plain-text alerts (circuit breaker, kill switch, daily summary) use `parse_mode=None`, avoiding any HTML injection risk entirely.

---

## Audit Scope

Files audited:
- `/Users/aciarallo001/Projects/arb/arb_pm/Arbitrage Polymarket/src/bot/dashboard/app.py`
- `/Users/aciarallo001/Projects/arb/arb_pm/Arbitrage Polymarket/src/bot/notifications/telegram.py`
- `/Users/aciarallo001/Projects/arb/arb_pm/Arbitrage Polymarket/src/bot/storage/schema.py`
- `/Users/aciarallo001/Projects/arb/arb_pm/Arbitrage Polymarket/src/bot/storage/writer.py`
- `/Users/aciarallo001/Projects/arb/arb_pm/Arbitrage Polymarket/src/bot/config.py`
- `/Users/aciarallo001/Projects/arb/arb_pm/Arbitrage Polymarket/src/bot/main.py`

Plans reviewed:
- `.planning/phases/04-observability-monitoring/04-01-PLAN.md`
- `.planning/phases/04-observability-monitoring/04-02-PLAN.md`
- `.planning/phases/04-observability-monitoring/04-03-PLAN.md`
- `.planning/phases/04-observability-monitoring/04-04-PLAN.md`

Summaries reviewed:
- `.planning/phases/04-observability-monitoring/04-01-SUMMARY.md`
- `.planning/phases/04-observability-monitoring/04-02-SUMMARY.md`
- `.planning/phases/04-observability-monitoring/04-03-SUMMARY.md`
- `.planning/phases/04-observability-monitoring/04-04-SUMMARY.md`
