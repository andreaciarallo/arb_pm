"""
Live execution scan loop.

Mirrors dry_run.py structure with Phase 3 additions:
- RiskGate checked before every execution attempt
- execute_opportunity() called for each detected opportunity
- insert_trade() records every order attempt (success and failure)
- SIGTERM and SIGINT handlers activate kill switch immediately
- KILL file checked at start of every scan cycle (max 30s detection lag)
- _execute_kill_switch() cancels all open orders and sells held positions

Phase 3 gate: trades are placed only when --live flag is passed to main.py.
dry_run.py is completely unchanged — Phase 2 tests continue to pass.
"""
import asyncio
import os
import signal
import time
import uuid
from datetime import datetime, timedelta

from loguru import logger

from bot.config import BotConfig
from bot.detection.cross_market import detect_cross_market_opportunities
from bot.detection.yes_no_arb import detect_yes_no_opportunities
from bot.execution.engine import execute_opportunity
from bot.risk.gate import RiskGate
from bot.scanner.http_poller import poll_stale_markets
from bot.scanner.market_filter import fetch_liquid_markets
from bot.scanner.price_cache import PriceCache
from bot.scanner.ws_client import WebSocketClient
from bot.storage.schema import init_db, init_trades_table, insert_trade
from bot.storage.writer import AsyncWriter

_KILL_FILE = "/app/data/KILL"
_DEFAULT_DURATION_HOURS = 24 * 365  # "infinite" for live mode
_MARKET_REFRESH_CYCLES = 10  # re-fetch market list every 10 scan cycles
_DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
_DB_PATH = os.path.join(_DATA_DIR, "bot.db")


async def _execute_kill_switch(
    client, conn, writer: AsyncWriter
) -> None:
    """
    Active kill switch (D-08): cancel all open orders, sell all held positions, flush writer.

    Steps:
    1. cancel_all() — sync, wrapped in run_in_executor to avoid blocking the event loop
    2. Query trades table for status IN ('filled', 'partial') to find open positions
    3. Place FAK SELL for each open position at price=0.01 (market-aggressive)
    4. Flush the async writer queue to ensure all rows are persisted
    """
    logger.warning("Kill switch executing — cancelling all pending orders")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, client.cancel_all)
        logger.info("cancel_all() completed")
    except Exception as exc:
        logger.error(f"cancel_all() failed: {exc}")

    # Sell open positions: query trades table for status IN ('filled', 'partial')
    try:
        cursor = conn.execute(
            "SELECT token_id, size FROM trades WHERE status IN ('filled', 'partial')"
        )
        rows = cursor.fetchall()
        for token_id, size in rows:
            if size and size > 0:
                from bot.execution.order_client import place_fak_order
                sell_resp = await place_fak_order(client, token_id, 0.01, size, "SELL")
                logger.info(f"Kill switch: sold {size} of {token_id} -> {sell_resp}")
    except Exception as exc:
        logger.error(f"Kill switch position close failed: {exc}")

    await writer.flush()
    logger.warning("Kill switch complete — scan loop exiting")


async def run(
    config: BotConfig,
    client,
    duration_hours: float = _DEFAULT_DURATION_HOURS,
    db_path: str = _DB_PATH,
) -> None:
    """
    Run the arbitrage scanner in live execution mode for duration_hours.

    Scan cycle (every config.scan_interval_seconds):
    1. Check KILL file and kill switch state — exit immediately if triggered
    2. Skip execution if risk gate is blocked (stop-loss or circuit breaker)
    3. Poll stale markets via HTTP fallback
    4. Detect YES+NO arbitrage opportunities
    5. Detect cross-market arbitrage opportunities
    6. Execute all opportunities via execute_opportunity()
    7. Log every ExecutionResult to trades table via insert_trade()
    8. Enqueue all opportunities to AsyncWriter (SQLite)

    SIGTERM and SIGINT activate kill switch immediately.
    """
    logger.info(f"Starting live execution scanner for {duration_hours}h | db={db_path}")

    # Initialize SQLite (opportunities table + trades table)
    conn = init_db(db_path)
    init_trades_table(conn)
    writer = AsyncWriter(conn)
    writer.start()

    # Initialize RiskGate — single instance for the entire session
    risk_gate = RiskGate(
        total_capital_usd=config.total_capital_usd,
        daily_stop_loss_pct=config.daily_stop_loss_pct,
        circuit_breaker_errors=config.circuit_breaker_error_count,
        circuit_breaker_window_seconds=config.circuit_breaker_window_seconds,
        circuit_breaker_cooldown_seconds=config.circuit_breaker_cooldown_seconds,
    )

    # Register SIGTERM and SIGINT to activate kill switch immediately
    loop = asyncio.get_running_loop()

    def _handle_signal():
        logger.warning("Shutdown signal received — activating kill switch")
        risk_gate.activate_kill_switch()

    loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    loop.add_signal_handler(signal.SIGINT, _handle_signal)

    # Initialize price cache and fetch initial market list
    cache = PriceCache()
    markets = await fetch_liquid_markets(client, config)
    logger.info(f"Loaded {len(markets)} liquid markets")

    # Start WebSocket client as background task
    # Cap at 2000 token IDs — large subscription messages are silently dropped
    # by the Polymarket WebSocket server. HTTP polling covers the rest.
    all_token_ids = [tid for m in markets for tid in m.get("token_ids", [])]
    ws_token_ids = all_token_ids[:2000]
    ws_client = WebSocketClient(token_ids=ws_token_ids, cache=cache, config=config)
    ws_task = asyncio.create_task(ws_client.run())

    stop_at = datetime.utcnow() + timedelta(hours=duration_hours)
    cycle = 0
    total_logged = 0
    total_executed = 0

    try:
        while datetime.utcnow() < stop_at:
            cycle_start = time.monotonic()

            # KILL file check (max 30s detection lag per D-08)
            if os.path.exists(_KILL_FILE):
                logger.warning(f"KILL file detected at {_KILL_FILE} — activating kill switch")
                risk_gate.activate_kill_switch()

            # Kill switch takes absolute priority — execute active close and exit loop
            if risk_gate.is_kill_switch_active():
                await _execute_kill_switch(client, conn, writer)
                break

            # Refresh market list periodically
            if cycle % _MARKET_REFRESH_CYCLES == 0 and cycle > 0:
                markets = await fetch_liquid_markets(client, config)
                all_token_ids = [tid for m in markets for tid in m.get("token_ids", [])]
                logger.debug(f"Market list refreshed: {len(markets)} markets")

            # HTTP polling fallback for stale markets
            refreshed = await poll_stale_markets(client, cache, markets, config)

            # Only run detection on markets with cached price data — avoids
            # O(n²) cross-market scan over 44k markets with no price data yet.
            cached_ids = set(cache.get_all_fresh(config.ws_stale_threshold_seconds * 10))
            priced_markets = [m for m in markets if any(
                tid in cached_ids for tid in m.get("token_ids", [])
            )]

            # Detection
            yes_no_opps = detect_yes_no_opportunities(priced_markets, cache, config)
            # Cap cross-market scan at 100 priced markets to prevent O(n²) blowup
            cross_opps = detect_cross_market_opportunities(priced_markets[:100], cache, config)
            all_opps = yes_no_opps + cross_opps

            # Execute on all opportunities — gated by risk controls
            if not risk_gate.is_blocked():
                for opp in all_opps:
                    results = await execute_opportunity(client, opp, config, risk_gate)
                    for result in results:
                        trade_id = str(uuid.uuid4())
                        insert_trade(conn, result, opp.market_question, trade_id)
                        total_executed += 1
            elif risk_gate.is_stop_loss_triggered():
                logger.warning("Stop-loss active — skipping execution this cycle")
            elif risk_gate.is_circuit_breaker_open():
                logger.warning("Circuit breaker open — skipping execution this cycle")

            # Enqueue to SQLite opportunities writer (non-blocking)
            for opp in all_opps:
                writer.enqueue(opp)
            total_logged += len(all_opps)

            cycle_duration = time.monotonic() - cycle_start
            logger.info(
                f"Cycle {cycle + 1} | "
                f"{len(yes_no_opps)} YES/NO + {len(cross_opps)} cross-market opps | "
                f"{refreshed} HTTP polls | "
                f"cycle={cycle_duration:.2f}s | "
                f"total_logged={total_logged} | "
                f"total_executed={total_executed}"
            )

            cycle += 1

            # Wait for next scan cycle
            sleep_time = max(0, config.scan_interval_seconds - cycle_duration)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info("Live run cancelled")
    finally:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass

        await writer.stop()
        conn.close()

        logger.info(
            f"Live run complete | {cycle} cycles | "
            f"{total_logged} total opportunities logged | "
            f"{total_executed} trade attempts"
        )
