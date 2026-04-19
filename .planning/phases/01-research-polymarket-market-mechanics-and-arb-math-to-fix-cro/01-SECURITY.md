---
phase: 01
slug: research-polymarket-market-mechanics-and-arb-math-to-fix-cro
status: verified
threats_open: 0
asvs_level: 1
created: "2026-04-19"
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| bot process → Gamma API | HTTP GET to external public endpoint at gamma-api.polymarket.com | condition_id → event_id mappings (read-only, public) |
| bot process → Polymarket CLOB | FAK BUY/SELL orders via place_fak_order() | token_id, price, size_usd, side — authenticated via py-clob-client |
| docker-compose.yml → container CMD | command: override controls runtime flags at container start | presence/absence of --live flag |
| VPS SSH | Root access to HEL1 (204.168.164.145) | config files, DB, container state |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-01-01 | Tampering | docker-compose command override | mitigate | `command: ["python", "-m", "bot.main"]` added to docker-compose.yml (commit 6344139); omits --live; future `docker compose up -d` restarts are dry-run by default | closed |
| T-01-02-01 | Tampering | cross-market detection math regression | mitigate | PLAN read_first requires full file review; acceptance criteria verified `total_yes = sum` unchanged (1 occurrence); 8/8 cross-market tests pass | closed |
| T-01-02-02 | Tampering | wrong grouping key (neg_risk_market_id only) | mitigate | Live API discovery (Step 1a/1b in Task 1) confirmed PATH B (Gamma API); neg_risk_market_id retained as fallback; documented in 01-02-SUMMARY.md | closed |
| T-01-02-03 | Denial of Service | Gamma API latency injected into hot detection path | mitigate | load_event_groups() called ONCE at scanner startup; _event_groups is a module-level cache never written during detection cycles; hot path has no network I/O | closed |
| T-01-03-01 | Tampering | cross-market sizing error (equal dollars instead of equal shares) | mitigate | Equal-shares formula enforced: `target_shares = kelly_usd / total_yes`; `test_cross_market_equal_shares` asserts different size_usd per leg proportional to ask prices; test also asserts sizes are NOT equal | closed |
| T-01-03-02 | Tampering | Gate 0 change allows YES+NO opps with missing token IDs to bypass guard | mitigate | Gate 0 routing requires BOTH conditions: `opp.opportunity_type == "cross_market" AND opp.legs`; `test_yes_no_missing_token_still_skips` verifies empty legs → skip path still fires | closed |
| T-01-03-03 | Tampering | unhedged partial fill creates open exposure | mitigate | `_execute_cross_market()` tracks `filled_legs`; on any leg failure triggers FAK SELL at price=0.01 for all previously filled legs; `test_cross_market_partial_hedge` verifies mock_fak called 3×: leg1 BUY fill → leg2 BUY fail → leg1 SELL hedge | closed |
| T-01-04-01 | Tampering | malformed Gamma API JSON response corrupts _event_groups | mitigate | `load_event_groups()` wraps entire fetch+parse in try/except; ValueError/JSONDecodeError caught internally; outer guard in both runners adds belt-and-suspenders second layer | closed |
| T-01-04-02 | Denial of Service | Gamma API slow/unavailable at bot startup | accept | Non-blocking by design: failure logs warning only; scanner starts with empty _event_groups; detection falls back to neg_risk_market_id; scan loop is not delayed | closed |
| T-01-04-03 | Information Disclosure | Gamma API URL or params logged | accept | URL is public (https://gamma-api.polymarket.com/events); no credentials, API keys, or PII in request or response | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-01 | T-01-04-02 | Gamma API downtime at startup is non-fatal — scanner degrades gracefully to neg_risk_market_id fallback grouping. Acceptable for Phase 01 scope. | gsd-security-auditor | 2026-04-19 |
| AR-01-02 | T-01-04-03 | Gamma API URL is publicly documented on docs.polymarket.com. No secrets in request. Logging the URL does not disclose any sensitive information. | gsd-security-auditor | 2026-04-19 |

---

## Out-of-Scope Threats (Noted)

| Item | Notes |
|------|-------|
| VPS SSH brute-force (IP 45.227.254.170) | Discovered during plan 01-01 execution. Mitigated by: UFW enabled (port 22/tcp), fail2ban installed, PasswordAuthentication disabled. Not in PLAN threat model — addressed as side-effect. |
| Manual `docker run ... --live` override | Residual risk acknowledged in 01-01-PLAN.md. The command: override in docker-compose.yml covers the canonical path; operator must explicitly bypass to run live. Acceptable residual risk for internal-only deployment. |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-19 | 10 | 10 | 0 | gsd-security-auditor (automated) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-19
