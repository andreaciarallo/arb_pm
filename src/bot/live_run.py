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

import uvicorn
from loguru import logger

from bot.config import BotConfig
from bot.dashboard.app import AppState, create_app
from bot.detection.cross_market import detect_cross_market_opportunities
from bot.detection.fee_model import get_taker_fee
from bot.detection.yes_no_arb import detect_yes_no_opportunities
from bot.execution.engine import execute_opportunity
from bot.notifications.telegram import TelegramAlerter
from bot.risk.gate import RiskGate
from bot.scanner.http_poller import poll_stale_markets
from bot.scanner.market_filter import fetch_liquid_markets
from bot.scanner.price_cache import PriceCache
from bot.scanner.ws_client import WebSocketClient
from bot.storage.schema import init_arb_pairs_table, init_db, init_trades_table, insert_arb_pair, insert_trade
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


def _derive_status_label(risk_gate) -> tuple[str, str]:
    """Return (status_label, description) from risk gate state for daily summary."""
    if risk_gate.is_kill_switch_active():
        return "stopped", "Kill switch active"
    if risk_gate.is_circuit_breaker_open():
        return "blocked", "Circuit breaker open"
    if risk_gate.is_stop_loss_triggered():
        return "paused", "Stop-loss triggered"
    return "running", "Active"


async def _start_dashboard(app_state: AppState, port: int = 8080) -> None:
    """Start the FastAPI dashboard as a background task (D-07, D-09)."""
    app = create_app(app_state)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        loop="none",
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info(f"Dashboard starting on port {port}")
    await server.serve()


async def _daily_summary_task(alerter: TelegramAlerter, app_state: AppState) -> None:
    """Fire daily P&L summary at midnight UTC (D-05 event 5)."""
    while True:
        now = datetime.utcnow()
        tomorrow_midnight = datetime.combine(
            now.date() + timedelta(days=1),
            datetime.min.time()
        )
        sleep_seconds = (tomorrow_midnight - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
        try:
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            conn = app_state.conn
            cursor = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE submitted_at >= ?",
                (today_str,)
            )
            trade_count = cursor.fetchone()[0] or 0
            cursor = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE submitted_at >= ? AND net_pnl > 0",
                (today_str,)
            )
            win_count = cursor.fetchone()[0] or 0
            loss_count = max(0, trade_count - win_count)
            cursor = conn.execute(
                "SELECT COUNT(*), SUM(net_pnl), SUM(fees_usd) FROM arb_pairs WHERE entry_time >= ?",
                (today_str,)
            )
            row = cursor.fetchone()
            arb_count = row[0] or 0
            pnl_usd = row[1] or 0.0
            fees_usd = row[2] or 0.0
            eff_pct = (pnl_usd / app_state.total_capital_usd * 100.0) if app_state.total_capital_usd > 0 else None
            status_label, _ = _derive_status_label(app_state.risk_gate)
            await alerter.send_daily_summary(
                date_str=today_str + " UTC",
                pnl_usd=pnl_usd,
                trade_count=trade_count,
                win_count=win_count,
                loss_count=loss_count,
                arb_count=arb_count,
                fees_usd=fees_usd,
                efficiency_pct=eff_pct,
                bot_status=status_label,
            )
        except Exception as e:
            logger.warning(f"Daily summary task error: {e}")


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
    init_arb_pairs_table(conn)
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

    # Phase 4: Initialize alerter and dashboard
    alerter = TelegramAlerter(
        token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
    )
    app_state = AppState(
        conn=conn,
        risk_gate=risk_gate,
        total_capital_usd=config.total_capital_usd,
    )
    dashboard_task = asyncio.create_task(_start_dashboard(app_state))
    summary_task = asyncio.create_task(_daily_summary_task(alerter, app_state))

    # Register SIGTERM and SIGINT to activate kill switch immediately
    loop = asyncio.get_running_loop()
    _stop_event = asyncio.Event()

    def _handle_signal():
        logger.warning("Shutdown signal received — activating kill switch")
        risk_gate.activate_kill_switch()
        _stop_event.set()  # interrupt any in-progress sleep immediately

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
                    arb_id, results = await execute_opportunity(client, opp, config, risk_gate)
                    yes_trade_id: str | None = None
                    no_trade_id: str | None = None
                    yes_result = None
                    no_result = None
                    entry_time = datetime.utcnow().isoformat()

                    for result in results:
                        trade_id = str(uuid.uuid4())
                        # Compute real fees_usd at fill time (D-13)
                        fees_usd = 0.0
                        if result.status in ("filled", "partial") and result.size_filled > 0:
                            fees_usd = result.size_filled * get_taker_fee(opp.category, config)
                        insert_trade(conn, result, opp.market_question, trade_id, fees_usd=fees_usd)
                        total_executed += 1

                        # Track YES and NO legs for arb_pairs write (D-12)
                        if result.leg == "yes" and result.status == "filled":
                            yes_trade_id = trade_id
                            yes_result = result
                        elif result.leg == "no" and result.status == "filled":
                            no_trade_id = trade_id
                            no_result = result

                    # Write arb_pairs ONLY if BOTH legs confirmed filled (D-12)
                    # Hedge path (no_result is None) does NOT write arb_pairs (D-19)
                    if yes_result and no_result and yes_trade_id and no_trade_id:
                        exit_time = datetime.utcnow().isoformat()  # Pitfall 6: compute at write time
                        hold_secs = (
                            datetime.fromisoformat(exit_time) - datetime.fromisoformat(entry_time)
                        ).total_seconds()
                        yes_fees = yes_result.size_filled * get_taker_fee(opp.category, config)
                        no_fees = no_result.size_filled * get_taker_fee(opp.category, config)
                        total_fees = yes_fees + no_fees
                        n_contracts = yes_result.size_filled / yes_result.price  # USD / price = contracts
                        gross_pnl = (1.0 - yes_result.price - no_result.price) * n_contracts
                        net_pnl = gross_pnl - total_fees
                        arb_pair = {
                            "arb_id": arb_id,
                            "yes_trade_id": yes_trade_id,
                            "no_trade_id": no_trade_id,
                            "market_id": opp.market_id,
                            "market_question": opp.market_question,
                            "yes_entry_price": yes_result.price,
                            "no_entry_price": no_result.price,
                            "size_usd": yes_result.size_filled,
                            "gross_pnl": gross_pnl,
                            "fees_usd": total_fees,
                            "net_pnl": net_pnl,
                            "entry_time": entry_time,
                            "exit_time": exit_time,
                            "hold_seconds": hold_secs,
                        }
                        insert_arb_pair(conn, arb_pair)
                        app_state.daily_pnl_usd += net_pnl
                        # Fire-and-forget Telegram alert (D-05 event 1)
                        asyncio.create_task(alerter.send_arb_complete(
                            market_question=opp.market_question,
                            yes_entry_price=yes_result.price,
                            no_entry_price=no_result.price,
                            size_usd=yes_result.size_filled,
                            hold_seconds=hold_secs,
                            gross_pnl=gross_pnl,
                            fees_usd=total_fees,
                            net_pnl=net_pnl,
                        ))

                    # Update dashboard state counters
                    app_state.total_trades += len(results)
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
            app_state.cycle_count = cycle
            app_state.last_scan_utc = datetime.utcnow().strftime("%H:%M:%S")

            # Wait for next scan cycle — but wake immediately on SIGTERM
            sleep_time = max(0, config.scan_interval_seconds - cycle_duration)
            if sleep_time > 0:
                try:
                    await asyncio.wait_for(_stop_event.wait(), timeout=sleep_time)
                except asyncio.TimeoutError:
                    pass  # normal cycle end — continue scanning

    except asyncio.CancelledError:
        logger.info("Live run cancelled")
    finally:
        dashboard_task.cancel()
        summary_task.cancel()
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass

        for t in (dashboard_task, summary_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

        await writer.stop()
        conn.close()

        logger.info(
            f"Live run complete | {cycle} cycles | "
            f"{total_logged} total opportunities logged | "
            f"{total_executed} trade attempts"
        )
