---
phase: 01-infrastructure-foundation
asvs_level: 1
audited: 2026-04-17
auditor: gsd-security-auditor (claude-sonnet-4-6)
block_on: critical
result: OPEN_THREATS
threats_total: 9
threats_closed: 7
threats_open: 2
unregistered_flags: 2
---

# Phase 01 — Security Audit Report

**Phase:** 01 — infrastructure-foundation
**ASVS Level:** 1
**Closed:** 7/9 | **Open:** 2/9
**Unregistered flags:** 2

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| SEC-01 | Secret Management | mitigate | CLOSED | `.gitignore` line 2: `secrets.env`; line 3: `.env` — both on own lines |
| SEC-02 | Credential Leakage via Logs | mitigate | CLOSED | `src/bot/config.py` lines 7-8 doc comment prohibits raw RPC URL logging; `src/bot/main.py` lines 57-58 log "configured" string only; `scripts/get_wallet_address.py` lines 34-35 suppress exception messages that could embed key material |
| SEC-03 | Insecure Base Image (Alpine musl) | mitigate | CLOSED | `Dockerfile` line 3: `FROM python:3.12-slim`; no `alpine` string present in Dockerfile |
| SEC-04 | Secrets Baked into Docker Image Layers | mitigate | CLOSED | `Dockerfile` contains no `ENV` or `ARG` instructions carrying secret values; only `ENV PYTHONPATH=/app/src`; `docker-compose.yml` lines 29-30 use `env_file: secrets.env` for runtime injection |
| SEC-05 | Container Running as Root | accept | OPEN | `Dockerfile` has no `USER` instruction — container runs as uid 0 by default. No plan formally accepted or documented this risk. See Accepted Risks log below. |
| SEC-06 | Dashboard Port 8080 Publicly Exposed | accept | OPEN | `docker-compose.yml` lines 19-20 bind `0.0.0.0:8080:8080`. Plan 01-03 explicitly required no dashboard port (D-10: "no Phase 4 dashboard service yet"). Port was added during Phase 4 implementation without a registered acceptance. See Unregistered Flags below. |
| SEC-07 | VPS Bootstrap via Pipe-to-Bash | accept | CLOSED | `scripts/setup_vps.sh` line 5 documents the pipe-to-bash pattern in the header comment. Operator explicitly reads and invokes this script — risk is operationally accepted. |
| INFRA-04 | Silent Startup on Missing Secrets | mitigate | CLOSED | `src/bot/config.py` lines 73-78: all REQUIRED_SECRETS checked via list comprehension; `raise RuntimeError` lists missing variable names |
| INFRA-05 | Wrong EOA Auth Type in ClobClient | mitigate | CLOSED | `src/bot/client.py` line 28: `signature_type=0`; present in both `build_client()` and `scripts/create_api_key.py` line 38 |

---

## Open Threats

### SEC-05 — Container Running as Root

**Category:** Container Security
**Disposition declared in plan:** Not registered
**Mitigation expected:** `USER` instruction in Dockerfile creating non-root user
**Files searched:** `Dockerfile`
**Finding:** No `USER` instruction found. The container runs as uid 0. If an attacker achieves remote code execution inside the container, they have root access to the container filesystem and mounted volumes (including `/app/data` containing the SQLite trade database and any cached key material). The `bot_data` volume would be readable and writable as root.

**Severity:** LOW (ASVS Level 1) — mitigated in part by Docker namespace isolation and the absence of `--privileged`. Escalates to MEDIUM if secrets or key material are ever written to `/app/data`.

**Resolution options:**
1. Add `RUN adduser --disabled-password --gecos '' botuser` and `USER botuser` to Dockerfile, then re-verify volume permissions.
2. Formally document as accepted risk in this file if the threat is judged acceptable for this capital level.

---

### SEC-06 — Dashboard Port 8080 Bound to All Interfaces

**Category:** Network Exposure
**Disposition declared in plan:** Not registered (D-10 in Plan 03 prohibited this port in Phase 1)
**Mitigation expected:** No port binding in Phase 1; or if bound, VPS firewall rule restricting access
**Files searched:** `docker-compose.yml`
**Finding:** `ports: - "8080:8080"` binds the FastAPI dashboard to `0.0.0.0:8080` on the host. The comment says "Restrict in VPS firewall: only allow trusted IPs to reach port 8080" but no firewall configuration file or `iptables`/`ufw` rule exists in the repository. The dashboard has no authentication layer (not part of Phase 1 scope). Any actor that can reach the VPS IP on port 8080 can access the dashboard.

**Severity:** MEDIUM — exposes trade state, profit/loss metrics, and bot configuration to unauthenticated network access. At Hetzner Ashburn the VPS IP is publicly routable.

**Resolution options:**
1. Add a `ufw` rule to the VPS: `ufw allow from <trusted_ip> to any port 8080` and document the command in a deployment runbook.
2. Change docker-compose.yml port binding to `127.0.0.1:8080:8080` to restrict to localhost only (access via SSH tunnel).
3. Add HTTP Basic Auth or token-based auth to the FastAPI dashboard.
4. Formally document as accepted risk with compensating control description.

---

## Closed Threats — Evidence Summary

| Threat ID | Closed By | File | Line(s) |
|-----------|-----------|------|---------|
| SEC-01 | `secrets.env` and `.env` in .gitignore | `.gitignore` | 2, 3 |
| SEC-02 | "configured" log string; doc comments prohibiting raw URL logging; exception message suppression | `src/bot/main.py`, `src/bot/config.py`, `scripts/get_wallet_address.py` | main.py:57-58, config.py:7-8, get_wallet_address.py:34-35 |
| SEC-03 | `FROM python:3.12-slim` (Debian glibc); no Alpine string | `Dockerfile` | 3 |
| SEC-04 | No secret-bearing `ENV`/`ARG`; runtime env_file injection | `Dockerfile`, `docker-compose.yml` | Dockerfile:8, compose:29-30 |
| SEC-07 | Pipe-to-bash usage documented in script header; operator-invoked | `scripts/setup_vps.sh` | 5 |
| INFRA-04 | `raise RuntimeError` listing all missing vars | `src/bot/config.py` | 73-78 |
| INFRA-05 | `signature_type=0` in ClobClient factory and create_api_key | `src/bot/client.py`, `scripts/create_api_key.py` | client.py:28, create_api_key.py:38 |

---

## Unregistered Flags

These items were not declared in any plan's threat model but were detected during code review. They are logged here as informational — they are not counted against `threats_open` unless escalated.

### FLAG-01 — Port 8080 Added Without Phase 1 Plan Authorization

**Source:** Code review of `docker-compose.yml`
**Description:** Plan 01-03 explicitly required no dashboard port in Phase 1 (D-10: "No Phase 4 dashboard service yet — add later"). The final `docker-compose.yml` contains `ports: - "8080:8080"`, which was added during Phase 4 implementation but was never registered as a threat in Phase 1's threat model. This flag is also surfaced as open threat SEC-06 above because the port exposes unauthenticated dashboard access.

### FLAG-02 — `discord_webhook_url` Removed from BotConfig Without Registration

**Source:** Code comparison between Plan 01-01 specification and implemented `src/bot/config.py`
**Description:** Plan 01-01 specified that `secrets.env.example` includes `DISCORD_WEBHOOK_URL` and that `BotConfig` should have a `discord_webhook_url: str | None = None` field. The implemented `config.py` does not include `discord_webhook_url` in `BotConfig` (the field was dropped and `telegram_chat_id` was added instead). The `secrets.env.example` retains `DISCORD_WEBHOOK_URL` as a placeholder. This is a functional deviation, not a security vulnerability, but is logged because a discrepancy between the example file and the config dataclass could confuse operators about which credentials are actually loaded.

---

## Accepted Risks Log

*Threats formally accepted by the team are recorded here. An accepted threat must have a description, rationale, and compensating controls.*

| Threat ID | Description | Rationale | Compensating Controls | Accepted By |
|-----------|-------------|-----------|----------------------|-------------|
| SEC-07 | VPS bootstrap via pipe-to-bash from GitHub | Standard VPS bootstrap pattern for single-operator trading bots; script is in a private/controlled repo; operator reviews before running | Script uses `set -euo pipefail`; operator reads the script header before executing | Implicit — operator invokes manually |

*SEC-05 and SEC-06 are OPEN and require either mitigation or formal acceptance with compensating controls before they can be moved to this table.*

---

## Next Steps

1. **SEC-05 (Container Root):** Either add a non-root `USER` to the Dockerfile, or record formal acceptance in the Accepted Risks Log above with compensating controls.
2. **SEC-06 (Port 8080 exposure):** Either restrict the port binding to `127.0.0.1:8080:8080` in `docker-compose.yml`, add a VPS firewall rule to the deployment runbook, or record formal acceptance with compensating controls.
3. After resolving or formally accepting SEC-05 and SEC-06, re-run `/gsd-secure-phase` to update this file and promote the result to SECURED.
