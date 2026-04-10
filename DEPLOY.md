# DEPLOY.md — VPS Migration Guide

**Target:** Hetzner HEL1 (Helsinki, Finland) — geoblocking fix + latency optimization
**From:** Hetzner CPX31 Ashburn VA (US, geoblocked, 92ms RTT)
**To:** Hetzner CPX31 HEL1 (Finland, allowed, ~35ms RTT expected)

This document is self-contained. A remote Claude or human operator can follow it end-to-end
without any additional context. Run every step in order. Do **not** decommission the old VPS
until UAT Step 3 passes on the new one.

---

## Prerequisites

Before starting, you need:

1. **New VPS provisioned** — Hetzner CPX31, HEL1 (Helsinki), Ubuntu 22.04 LTS
   - Root SSH access confirmed
   - Public IP noted (referred to as `NEW_VPS_IP` throughout)
2. **Old VPS still running** — `/opt/arbbot/secrets.env` accessible via SSH
   - Old VPS IP referred to as `OLD_VPS_IP` throughout
3. **Local machine** with SSH access to both VPS instances

---

## Phase 1: Bootstrap New VPS

### Step 1.1 — SSH into new VPS

```bash
ssh root@NEW_VPS_IP
```

### Step 1.2 — Run the automated setup script

The setup script is committed to the repo. Run it via curl (no git needed yet):

```bash
curl -fsSL https://raw.githubusercontent.com/andreaciarallo/arb_pm/master/scripts/setup_vps.sh | bash
```

This script:
- Updates apt and installs `git`, `curl`, `ca-certificates`
- Installs Docker CE (official docker.com method)
- Adds root to the `docker` group
- Clones the repo to `/opt/arbbot`

**Expected output (last lines):**
```
[setup] Docker installed: Docker version 27.x.x
[setup] Repo cloned to /opt/arbbot
[setup] Setup complete. Next steps:
  1. cd /opt/arbbot
  2. Copy secrets.env from old VPS (see DEPLOY.md)
  3. docker compose up -d
```

If the script fails, run it manually — see `scripts/setup_vps.sh` for individual commands.

### Step 1.3 — Verify Docker is working

```bash
docker run --rm hello-world
```

Must print `Hello from Docker!`. If it fails with permission denied, run:

```bash
newgrp docker
# then retry
docker run --rm hello-world
```

---

## Phase 2: Transfer Secrets

**Never transmit secrets via git, email, or chat.** Use `scp` between VPS instances directly.

### Step 2.1 — Copy secrets.env from old VPS to new VPS

Run this **from your local machine** (not from either VPS):

```bash
# Pull secrets from old VPS to local temp file
scp root@OLD_VPS_IP:/opt/arbbot/secrets.env /tmp/arbbot_secrets.env

# Push secrets to new VPS
scp /tmp/arbbot_secrets.env root@NEW_VPS_IP:/opt/arbbot/secrets.env

# Delete local temp copy immediately
rm /tmp/arbbot_secrets.env
```

### Step 2.2 — Lock down secrets file on new VPS

```bash
# On new VPS
chmod 600 /opt/arbbot/secrets.env
ls -la /opt/arbbot/secrets.env
# Must show: -rw------- 1 root root ... secrets.env
```

### Step 2.3 — Sanity check secrets content

```bash
# On new VPS — verify all 6 required keys are present (values not shown)
grep -E "^(POLY_API_KEY|POLY_API_SECRET|POLY_API_PASSPHRASE|WALLET_PRIVATE_KEY|POLYGON_RPC_HTTP|POLYGON_RPC_WS)=" /opt/arbbot/secrets.env | cut -d= -f1
```

Expected output (order may vary):
```
POLY_API_KEY
POLY_API_SECRET
POLY_API_PASSPHRASE
WALLET_PRIVATE_KEY
POLYGON_RPC_HTTP
POLYGON_RPC_WS
```

If any key is missing, copy it from the old VPS manually.

---

## Phase 3: Build and Start the Bot

### Step 3.1 — Build the Docker image

```bash
cd /opt/arbbot
docker compose build bot
```

Expected: build completes without errors. Takes 3–5 minutes first time (pip install).

**If build fails with dependency conflict:** Check `requirements.txt` — known fix is
`pytest==8.3.4` (not 9.x). The committed version should already have this pinned.

### Step 3.2 — Start the bot

```bash
docker compose up -d
```

### Step 3.3 — Verify bot is healthy

```bash
docker compose ps
```

Expected output:
```
NAME      IMAGE         COMMAND               SERVICE   CREATED         STATUS                   PORTS
arbbot    arbbot-bot    "python -m bot.main"  bot       X seconds ago   Up X seconds (healthy)
```

Status must be `(healthy)` — not `(health: starting)` or `(unhealthy)`.
The healthcheck runs every 30s with a 10s timeout and 3 retries. Wait up to 2 minutes.

If status stays `(unhealthy)`:
```bash
docker compose logs --tail=50
# Look for: "ERROR" or "ModuleNotFoundError" or secret validation failures
```

### Step 3.4 — Check startup logs

```bash
docker compose logs --tail=30
```

Expected healthy startup sequence:
```
INFO | bot.main:main - Config loaded: 6 secrets validated
INFO | bot.health:check - CLOB reachable: clob.polymarket.com responded in Xms
INFO | bot.main:main - Mode: live_run
INFO | bot.live_run:run - Live run started. Scanning for opportunities...
```

---

## Phase 4: Verification

### Step 4.1 — Geoblock check

```bash
curl -s https://polymarket.com/api/geoblock | python3 -m json.tool
```

**Must return:**
```json
{
    "blocked": false,
    "country": "FI",
    "region": "..."
}
```

If `"blocked": true` — the new VPS IP is also geoblocked. Do not proceed.
Check that Hetzner assigned a Finnish IP (not a shared/anycast US address):
```bash
curl -s https://ipinfo.io/json | python3 -m json.tool
# "country" must be "FI"
```

### Step 4.2 — Latency benchmark

```bash
docker compose exec bot python scripts/benchmark_latency.py
```

Expected output for HEL1 → CLOB:
```
Samples: 20
Mean:    35.0 ms
Median:  34.5 ms
P95:     48.2 ms
Min:     30.1 ms
Max:     62.4 ms

Median < 100ms: PASS
```

**Gate:** Median must be `< 100ms`. Expect ~30–40ms for HEL1. If median is above 60ms,
something is wrong with routing — investigate before proceeding.

### Step 4.2.5 — Get wallet address for funding

The FAK order test requires ~$2 USDC in the wallet. Get your wallet address:

```bash
# Run locally (reads secrets.env from repo)
python scripts/get_wallet_address.py

# Or on the VPS
ssh root@NEW_VPS_IP "cd /opt/arbbot && docker compose exec bot python scripts/get_wallet_address.py"
```

Send ~$2 USDC (Polygon network only) to the printed address before running Step 4.3.

---

### Step 4.3 — UAT Step 3: FAK order placement

This is the definitive test. Places a non-crossing FAK BUY at price=0.01 (will never fill).
Uses a live market from the sampling pool — dynamically fetched to avoid stale token IDs.

**Note:** Wallet must have ~$2 USDC balance for the order to be accepted.

```bash
docker compose exec bot python -c "
from bot.config import load_config
from bot.client import build_client
from bot.execution.order_client import place_fak_order
import asyncio

async def test():
    cfg = load_config()
    client = build_client(cfg)
    # Fetch an active market dynamically (avoids stale token IDs)
    markets = client.get_sampling_markets()
    if not markets or 'data' not in markets or len(markets['data']) == 0:
        print('FAIL — no active markets available')
        return
    token_id = markets['data'][0]['tokens'][0]['token_id']
    print(f'Testing with token: {token_id}')
    # place_fak_order signature: (client, token_id, price, size_usd, side)
    result = await place_fak_order(client, token_id, 0.01, 2.0, 'BUY')
    print('Result:', result)
    if result is not None:
        print('PASS — order accepted by CLOB (not filled, price too low)')
    elif 'not enough balance' in str(result):
        print('FAIL — wallet needs ~\$2 USDC for test')
    else:
        print('FAIL — order rejected, check logs')

asyncio.run(test())
"
```

**PASS:** `result` is a dict/object with order details (not None, not 403)
**FAIL:** `result` is None → check `docker compose logs --tail=20` for error details

---

## Phase 5: Decommission Old VPS

**Only proceed after UAT Step 4.3 returns PASS.**

### Step 5.1 — Stop the old bot gracefully

```bash
# On OLD VPS
cd /opt/arbbot
docker compose stop       # respects SIGTERM, gives 30s for graceful shutdown
docker compose ps         # verify status is "Exited"
```

### Step 5.2 — Optional: Export SQLite trade history

The Phase 2 dry-run logs live in Docker volume `arbbot_bot_data`. If you want to preserve
them (e.g. for analysis), export before deleting the VPS:

```bash
# On OLD VPS — create backup tarball in /tmp
docker run --rm \
  -v arbbot_bot_data:/data \
  -v /tmp:/backup \
  alpine tar czf /backup/bot_data_backup.tar.gz /data

# From LOCAL machine — copy to new VPS
scp root@OLD_VPS_IP:/tmp/bot_data_backup.tar.gz root@NEW_VPS_IP:/tmp/

# On NEW VPS — restore into new volume (do this BEFORE docker compose up if not done yet)
# WARNING: only restore if bot has not yet written any data on the new VPS
docker volume create arbbot_bot_data
docker run --rm \
  -v arbbot_bot_data:/data \
  -v /tmp:/backup \
  alpine tar xzf /backup/bot_data_backup.tar.gz -C /
```

If a clean start is acceptable (Phase 3 is live trading, not dry-run continuation), skip
this step entirely — the new VPS will initialize a fresh `bot.db` on first start.

### Step 5.3 — Delete old VPS

1. Log into [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Navigate to **Servers** → select the **CPX31 Ashburn** server
3. Click **Delete** (permanent, stops billing immediately)
4. Confirm deletion

**Do NOT delete until:**
- UAT Step 4.3 passed (PASS printed)
- Bot on new VPS shows `(healthy)` for at least 10 minutes
- `docker compose logs` on new VPS shows normal scan cycles

---

## Troubleshooting

### Bot stays unhealthy after startup

```bash
docker compose logs --tail=100
```

Common causes:
- **Missing secret:** `Config error: POLY_API_KEY is required` → re-check secrets.env
- **Import error:** `ModuleNotFoundError` → rebuild image: `docker compose build --no-cache bot`
- **CLOB unreachable:** `health check failed` → check firewall rules (port 443 outbound must be open)

### Geoblock check still returns blocked=true

```bash
curl -s https://ipinfo.io/json
```

If `country` is not `FI`, Hetzner may have assigned a non-Finnish IP to the server.
Contact Hetzner support or create a new server in a different HEL1 zone.

### Latency benchmark shows > 60ms median

```bash
# Traceroute to CLOB
traceroute clob.polymarket.com
```

Look for unexpected routing through US or Asian hops. If routing looks correct but latency
is still high, run the benchmark 3 times and take the best run — occasional spikes happen.

### FAK order returns None but no 403 in logs

```bash
docker compose logs --tail=50 | grep -E "(ERROR|WARNING|place_fak)"
```

Other possible causes:
- Market token no longer valid (near-resolved markets can close) → find a new test token
- API key expired (rotate via `scripts/create_api_key.py` on the new VPS)
- Insufficient balance (check wallet via Polygon RPC)

---

## Post-Migration Checklist

- [ ] Geoblock check returns `blocked: false, country: FI`
- [ ] Latency benchmark median < 100ms (expected ~35ms)
- [ ] Bot status is `(healthy)` for 10+ minutes
- [ ] UAT Step 3 FAK order returns non-None result
- [ ] Old VPS stopped and deleted
- [ ] `current-infrastructure.md` updated with new VPS details (gitignored, update locally)
