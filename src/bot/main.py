"""
Polymarket Arbitrage Bot — entrypoint.

Phase 1: Validates secrets and confirms connectivity. The main loop is a
placeholder — subsequent phases (data scanning, execution) replace it.

Run via Docker:
    docker compose up -d

Run locally (development):
    PYTHONPATH=. python -m bot.main
"""
import sys
import time

from loguru import logger

from bot.config import load_config
from bot.client import build_client
from bot.health import check_health


def main() -> None:
    """
    Bot startup sequence:
    1. Load and validate all secrets (fail fast if any missing — D-06)
    2. Verify CLOB API connectivity
    3. Confirm wallet address
    4. Enter main loop (placeholder in Phase 1)
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

    # Step 4: Main loop placeholder (Phase 2 replaces this with market scanning)
    logger.info("Bot ready. Entering idle loop (Phase 2 will replace with market scanning).")
    while True:
        time.sleep(60)
        logger.debug("Bot idle — waiting for Phase 2 market scanning implementation")


if __name__ == "__main__":
    main()
