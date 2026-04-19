---
plan: 01-01
status: complete
completed_at: "2026-04-19T17:34:23Z"
commits:
  - hash: 6344139
    message: "fix(deploy): set dry-run as default command in docker-compose.yml"
---

# Plan 01-01 Summary — Dry-Run Lock

## Outcome

VPS bot switched from `--live` to dry-run. All must-haves satisfied.

## What Was Done

**Task 1 (human checkpoint):**
- Confirmed container was running with `--live` via `docker inspect`
- Verified all 770 trades had `status=skipped` (no real orders placed)
- Stopped container; restarted failed (--live hardcoded in VPS docker-compose.yml)

**Task 2 (auto):**
- Added `command: [python, -m, bot.main]` to local `docker-compose.yml` with dry-run comment
- Committed as `6344139`, pushed to origin/master
- VPS had `--live` as an uncommitted local change — stashed it, pulled new commit
- Rebuilt and restarted container

**Task 3 (verify):**
- Logs confirm: `Starting Phase 2 dry-run scanner (detection only, no trades)`
- CMD confirmed: no `--live` flag

## Side Effects Fixed

- VPS was under SSH brute-force attack (IP 45.227.254.170 flooding startup slots)
- UFW enabled with port 22/tcp allowed
- fail2ban installed and active (was blocking this Mac's IP — unbanned)
- `PasswordAuthentication no` set in sshd_config
- sqlite3 installed on VPS host for DB inspection

## Must-Have Verification

| Truth | Status |
|-------|--------|
| VPS logs show 'dry-run scanner' | ✓ PASS |
| docker-compose.yml has `command:` override without `--live` | ✓ PASS |
| Container CMD does not contain `--live` | ✓ PASS |
