"""
Polymarket Arbitrage Bot — entrypoint.

Loads configuration, validates CLOB connectivity, and starts the dry-run scanner.
All trade execution is deferred to Phase 3 — Phase 2 detects and logs only.

Run via Docker:
    docker compose up -d

Run locally (development):
    PYTHONPATH=src python -m bot.main
"""
import asyncio
import sys

from loguru import logger

from bot import dry_run
from bot.client import build_client
from bot.config import load_config
from bot.health import check_health


def main() -> None:
    """
    Bot startup sequence:
    1. Load and validate all secrets (fail fast if any missing — D-06)
    2. Verify CLOB API connectivity
    3. Build authenticated client and confirm wallet address
    4. Start Phase 2 dry-run scanner (detection only, no trades)
    """
    logger.info("Polymarket Arbitrage Bot starting...")

    # Step 1: Load secrets — raises RuntimeError immediately if any missing (D-06)
    try:
        config = load_config()
    except RuntimeError as exc:
        logger.error("Startup failed — missing required secrets: {}", exc)
        sys.exit(1)

    logger.info("Secrets loaded successfully ({} required, {} optional)",
                6, 2 - [config.telegram_bot_token, config.discord_webhook_url].count(None))

    # Step 2: Verify CLOB API is reachable before doing anything else
    logger.info("Checking Polymarket CLOB connectivity...")
    if not check_health():
        logger.error("Startup failed — Polymarket CLOB is not reachable")
        sys.exit(1)

    # Step 3: Build authenticated client and confirm wallet address
    client = build_client(config)
    wallet_address = client.get_address()
    logger.info("Wallet address: {}", wallet_address)
    # Log RPC availability without exposing the URL (Pitfall 5 avoidance)
    logger.info("Polygon RPC HTTP: configured")
    logger.info("Polygon RPC WS: configured")

    # Step 4: Start Phase 2 dry-run scanner (detection only, no trades placed)
    logger.info("Starting Phase 2 dry-run scanner (detection only, no trades)")
    asyncio.run(dry_run.run(config, client))


if __name__ == "__main__":
    main()
