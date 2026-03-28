"""
24-hour dry-run scanner loop.

Orchestrates all Phase 2 modules: market filtering, WebSocket subscription,
HTTP polling fallback, arbitrage detection, and SQLite opportunity logging.

NO orders are placed in dry-run mode. This is enforced architecturally —
there are no order placement calls anywhere in this module or its imports.

Phase 2 gate: run for 24h with zero trades and a non-empty opportunity log.
"""
import asyncio
import os
import time
from datetime import datetime, timedelta

from loguru import logger

from bot.config import BotConfig
from bot.detection.cross_market import detect_cross_market_opportunities
from bot.detection.yes_no_arb import detect_yes_no_opportunities
from bot.scanner.http_poller import poll_stale_markets
from bot.scanner.market_filter import fetch_liquid_markets
from bot.scanner.price_cache import PriceCache
from bot.scanner.ws_client import WebSocketClient
from bot.storage.schema import init_db
from bot.storage.writer import AsyncWriter

_DEFAULT_DURATION_HOURS = 24
_MARKET_REFRESH_CYCLES = 10  # re-fetch market list every 10 scan cycles
_DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
_DB_PATH = os.path.join(_DATA_DIR, "bot.db")


async def run(
    config: BotConfig,
    client,
    duration_hours: float = _DEFAULT_DURATION_HOURS,
    db_path: str = _DB_PATH,
) -> None:
    """
    Run the arbitrage scanner in dry-run mode for duration_hours.

    Scan cycle (every config.scan_interval_seconds):
    1. Poll stale markets via HTTP fallback
    2. Detect YES+NO arbitrage opportunities
    3. Detect cross-market arbitrage opportunities
    4. Enqueue all opportunities to AsyncWriter (SQLite)
    5. Log summary

    Zero orders are placed — no order placement code exists in this module.
    """
    logger.info(f"Starting dry-run scanner for {duration_hours}h | db={db_path}")

    # Initialize SQLite
    conn = init_db(db_path)
    writer = AsyncWriter(conn)
    writer.start()

    # Initialize price cache and fetch initial market list
    cache = PriceCache()
    markets = await fetch_liquid_markets(client, config)
    logger.info(f"Loaded {len(markets)} liquid markets")

    # Start WebSocket client as background task
    all_token_ids = [tid for m in markets for tid in m.get("token_ids", [])]
    ws_client = WebSocketClient(token_ids=all_token_ids, cache=cache, config=config)
    ws_task = asyncio.create_task(ws_client.run())

    stop_at = datetime.utcnow() + timedelta(hours=duration_hours)
    cycle = 0
    total_logged = 0

    try:
        while datetime.utcnow() < stop_at:
            cycle_start = time.monotonic()

            # Refresh market list periodically
            if cycle % _MARKET_REFRESH_CYCLES == 0 and cycle > 0:
                markets = await fetch_liquid_markets(client, config)
                all_token_ids = [tid for m in markets for tid in m.get("token_ids", [])]
                logger.debug(f"Market list refreshed: {len(markets)} markets")

            # HTTP polling fallback for stale markets
            refreshed = await poll_stale_markets(client, cache, markets, config)

            # Detection
            yes_no_opps = detect_yes_no_opportunities(markets, cache, config)
            cross_opps = detect_cross_market_opportunities(markets, cache, config)
            all_opps = yes_no_opps + cross_opps

            # Enqueue to SQLite writer (non-blocking)
            for opp in all_opps:
                writer.enqueue(opp)
            total_logged += len(all_opps)

            cycle_duration = time.monotonic() - cycle_start
            logger.info(
                f"Cycle {cycle + 1} | "
                f"{len(yes_no_opps)} YES/NO + {len(cross_opps)} cross-market opps | "
                f"{refreshed} HTTP polls | "
                f"cycle={cycle_duration:.2f}s | "
                f"total_logged={total_logged}"
            )

            cycle += 1

            # Wait for next scan cycle
            sleep_time = max(0, config.scan_interval_seconds - cycle_duration)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info("Dry-run cancelled")
    finally:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass

        await writer.stop()
        conn.close()

        logger.info(
            f"Dry-run complete | {cycle} cycles | {total_logged} total opportunities logged"
        )
