"""
Execution engine: orchestrates VWAP gate → Kelly sizing → FAK orders → retry-then-hedge.

Behavioral contracts (D-01, D-03, D-05, EXEC-03, EXEC-04):

  1. VWAP gate (D-05): Compute vwap_spread = 1.0 - vwap_yes - vwap_no before ordering.
     If vwap_spread < config.min_net_profit_pct → skip, return [ExecutionResult(skipped)].

  2. Kelly gate (D-01): Call kelly_size(). If 0.0 returned → skip.

  3. YES leg: place_fak_order(BUY). If None → failed, return early (no NO exposure).

  4. YES verification (EXEC-04, REST-only, intentional for Phase 3):
     verify_fill_rest() polls get_order() every 500ms × 10 (5s timeout). REST-only.
     User WebSocket fill channel deferred to Phase 4 — message format undocumented
     (RESEARCH.md Pattern 3: LOW confidence on field names). If False → failed, return early.

  5. NO leg with retry-then-hedge (D-03, EXEC-03):
     Attempt place_fak_order(BUY) for NO up to 3 times with 500ms between retries.
     Check is_kill_switch_active() before each retry. On exhaustion → hedge SELL
     of YES at price=0.01 (market-aggressive, hits best bid).

Returns list[ExecutionResult] for trade logging.
"""
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from bot.detection.opportunity import ArbitrageOpportunity
from bot.execution.kelly import kelly_size
from bot.execution.order_client import place_fak_order, verify_fill_rest

_NO_RETRY_COUNT = 3          # D-03: 3 NO leg attempts before hedge
_NO_RETRY_DELAY = 0.5        # D-03: 500ms between NO retry attempts
_HEDGE_PRICE = 0.01          # D-03: market-aggressive hedge SELL price (hits best bid)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    market_id: str
    leg: str                   # "yes" | "no" | "hedge" | "skip"
    side: str                  # "BUY" | "SELL" | ""
    token_id: str
    price: float
    size: float
    order_id: str | None       # None on failure or skip
    status: str                # "filled" | "partial" | "failed" | "hedged" | "skipped"
    size_filled: float         # 0.0 on failure
    kelly_size_usd: float      # kelly_size() output for this trade
    vwap_price: float          # VWAP simulation price used
    error_msg: str | None = None  # detail if status="failed"


# ---------------------------------------------------------------------------
# VWAP simulation (D-05)
# ---------------------------------------------------------------------------

def simulate_vwap(asks: list, target_size_usd: float) -> float:
    """
    Calculate VWAP fill price for buying target_size_usd against an ask book.

    Args:
        asks: List of objects with .price (str|float) and .size (str|float) attributes,
              OR dicts with "price" and "size" keys. Sorted ascending (best ask first).
        target_size_usd: Target order size in USD.

    Returns:
        VWAP price as float. Returns 1.0 if insufficient depth (worst case — will
        fail the VWAP gate and cause a skip).
    """
    if not asks or target_size_usd <= 0:
        return 1.0

    total_cost = 0.0
    total_filled = 0.0
    remaining = target_size_usd

    for level in asks:
        # Support both dict and object-style access
        if isinstance(level, dict):
            price = float(level.get("price", 1.0))
            size = float(level.get("size", 0))
        else:
            price = float(getattr(level, "price", 1.0))
            size = float(getattr(level, "size", 0))

        if size <= 0:
            continue

        fill = min(remaining, size)
        total_cost += fill * price
        total_filled += fill
        remaining -= fill

        if remaining <= 0:
            break

    if total_filled <= 0:
        return 1.0

    return total_cost / total_filled


# ---------------------------------------------------------------------------
# Main execution coroutine
# ---------------------------------------------------------------------------

async def execute_opportunity(
    client,
    opp: ArbitrageOpportunity,
    config,
    risk_gate,
) -> tuple[str, list[ExecutionResult]]:
    """
    Execute a detected ArbitrageOpportunity through the full order lifecycle.

    Args:
        client: Authenticated ClobClient instance.
        opp: Detected ArbitrageOpportunity from detection engine.
        config: BotConfig (or compatible MagicMock with required attributes).
        risk_gate: Risk gate object with is_kill_switch_active() method.

    Token IDs are read from opp.yes_token_id and opp.no_token_id (D-02).
    Empty token IDs → Gate 0 skip.

    Returns:
        Tuple of (arb_id, results) where arb_id is a UUID and results is the list
        of ExecutionResult entries (one per order attempt, including hedge).
    """
    arb_id = str(uuid.uuid4())
    results: list[ExecutionResult] = []

    # Read token IDs from opportunity dataclass (D-02 — no longer passed as params)
    yes_token_id = opp.yes_token_id
    no_token_id = opp.no_token_id

    # ------------------------------------------------------------------
    # Gate 0: Token ID presence check
    # ------------------------------------------------------------------
    if not yes_token_id or not no_token_id:
        logger.warning(
            f"execute_opportunity: missing token IDs for market={opp.market_id} — skipping"
        )
        results.append(ExecutionResult(
            market_id=opp.market_id,
            leg="skip",
            side="",
            token_id="",
            price=0.0,
            size=0.0,
            order_id=None,
            status="skipped",
            size_filled=0.0,
            kelly_size_usd=0.0,
            vwap_price=0.0,
            error_msg="missing token IDs",
        ))
        return arb_id, results

    # ------------------------------------------------------------------
    # Gate 1: VWAP gate (D-05, D-03) — fetch fresh order books and simulate
    # multi-level VWAP. Reject if VWAP-adjusted spread is below threshold.
    # ------------------------------------------------------------------
    # After Gate 0 — fetch fresh order books for VWAP simulation (D-03, resolves WR-07)
    loop = asyncio.get_running_loop()
    yes_book = None
    no_book = None
    try:
        yes_book = await loop.run_in_executor(None, client.get_order_book, yes_token_id)
        no_book = await loop.run_in_executor(None, client.get_order_book, no_token_id)
    except Exception as exc:
        logger.warning(
            f"Order book fetch failed for VWAP gate | market={opp.market_id}: {exc} — skipping"
        )
        results.append(ExecutionResult(
            market_id=opp.market_id, leg="skip", side="", token_id="",
            price=0.0, size=0.0, order_id=None, status="skipped",
            size_filled=0.0, kelly_size_usd=0.0, vwap_price=0.0,
            error_msg="order book fetch failed for VWAP",
        ))
        return arb_id, results

    # Extract asks — sort ascending (best ask first); CLOB returns descending (MEMORY.md critical finding)
    yes_asks = sorted(
        getattr(yes_book, "asks", []),
        key=lambda a: float(getattr(a, "price", 1.0) if not isinstance(a, dict) else a.get("price", 1.0))
    )
    no_asks = sorted(
        getattr(no_book, "asks", []),
        key=lambda a: float(getattr(a, "price", 1.0) if not isinstance(a, dict) else a.get("price", 1.0))
    )

    target_size = config.total_capital_usd * config.kelly_max_capital_pct
    vwap_yes = simulate_vwap(yes_asks, target_size)
    vwap_no = simulate_vwap(no_asks, target_size)
    vwap_spread = 1.0 - vwap_yes - vwap_no

    if vwap_spread < config.min_net_profit_pct:
        logger.info(
            f"VWAP gate skip | market={opp.market_id} "
            f"vwap_spread={vwap_spread:.4f} < threshold={config.min_net_profit_pct}"
        )
        results.append(ExecutionResult(
            market_id=opp.market_id,
            leg="skip", side="", token_id="",
            price=0.0, size=0.0, order_id=None, status="skipped",
            size_filled=0.0, kelly_size_usd=0.0, vwap_price=vwap_spread,
            error_msg="vwap_spread below threshold",
        ))
        return arb_id, results

    # ------------------------------------------------------------------
    # Gate 2: Kelly sizing (D-01)
    # ------------------------------------------------------------------
    target_size = config.total_capital_usd * config.kelly_max_capital_pct
    kelly_usd = kelly_size(
        net_spread=opp.net_spread,
        depth=opp.depth,
        target_size=target_size,
        total_capital=config.total_capital_usd,
        min_order_usd=config.kelly_min_order_usd,
        max_capital_pct=config.kelly_max_capital_pct,
    )

    if kelly_usd == 0.0:
        logger.info(
            f"Kelly gate skip | market={opp.market_id} "
            f"net_spread={opp.net_spread:.4f} depth={opp.depth}"
        )
        results.append(ExecutionResult(
            market_id=opp.market_id,
            leg="skip",
            side="",
            token_id="",
            price=0.0,
            size=0.0,
            order_id=None,
            status="skipped",
            size_filled=0.0,
            kelly_size_usd=0.0,
            vwap_price=vwap_spread,
            error_msg="kelly_size returned 0.0",
        ))
        return arb_id, results

    logger.info(
        f"Executing opportunity | market={opp.market_id} "
        f"net_spread={opp.net_spread:.4f} kelly_usd={kelly_usd} "
        f"vwap_spread={vwap_spread:.4f}"
    )

    # ------------------------------------------------------------------
    # YES leg (D-02: FAK BUY)
    # ------------------------------------------------------------------
    yes_resp = None
    try:
        yes_resp = await place_fak_order(
            client, yes_token_id, opp.yes_ask, kelly_usd, "BUY"
        )
    except Exception as exc:
        logger.error(f"YES leg exception for market={opp.market_id}: {exc}")

    if not yes_resp:
        logger.warning(f"YES leg failed | market={opp.market_id}")
        results.append(ExecutionResult(
            market_id=opp.market_id,
            leg="yes",
            side="BUY",
            token_id=yes_token_id,
            price=opp.yes_ask,
            size=kelly_usd,
            order_id=None,
            status="failed",
            size_filled=0.0,
            kelly_size_usd=kelly_usd,
            vwap_price=opp.vwap_yes,
            error_msg="place_fak_order returned None",
        ))
        return arb_id, results

    yes_order_id = yes_resp.get("orderID")

    # Guard: if the CLOB response is missing an orderID, fail fast rather than
    # passing None into verify_fill_rest (which would waste 10 × 500ms polling None).
    if not yes_order_id:
        logger.error(
            f"YES response missing orderID for market={opp.market_id}: {yes_resp}"
        )
        results.append(ExecutionResult(
            market_id=opp.market_id,
            leg="yes",
            side="BUY",
            token_id=yes_token_id,
            price=opp.yes_ask,
            size=kelly_usd,
            order_id=None,
            status="failed",
            size_filled=0.0,
            kelly_size_usd=kelly_usd,
            vwap_price=opp.vwap_yes,
            error_msg="missing orderID in YES response",
        ))
        return arb_id, results

    # ------------------------------------------------------------------
    # YES verification (EXEC-04, REST-only — intentional Phase 3 design)
    # verify_fill_rest polls get_order() every 500ms × 10 = 5s timeout.
    # WebSocket fill channel deferred to Phase 4 (undocumented format).
    # ------------------------------------------------------------------
    yes_verified = False
    try:
        yes_verified = await verify_fill_rest(client, yes_order_id)
    except Exception as exc:
        logger.error(f"YES verify exception for market={opp.market_id}: {exc}")

    if not yes_verified:
        logger.warning(
            f"YES REST verification failed | market={opp.market_id} order={yes_order_id}"
        )
        if hasattr(risk_gate, "record_order_error"):
            risk_gate.record_order_error()
        results.append(ExecutionResult(
            market_id=opp.market_id,
            leg="yes",
            side="BUY",
            token_id=yes_token_id,
            price=opp.yes_ask,
            size=kelly_usd,
            order_id=yes_order_id,
            status="failed",
            size_filled=0.0,
            kelly_size_usd=kelly_usd,
            vwap_price=opp.vwap_yes,
            error_msg="verify_fill_rest returned False",
        ))
        return arb_id, results

    # YES confirmed filled
    results.append(ExecutionResult(
        market_id=opp.market_id,
        leg="yes",
        side="BUY",
        token_id=yes_token_id,
        price=opp.yes_ask,
        size=kelly_usd,
        order_id=yes_order_id,
        status="filled",
        size_filled=kelly_usd,
        kelly_size_usd=kelly_usd,
        vwap_price=opp.vwap_yes,
    ))
    logger.info(f"YES leg filled | market={opp.market_id} order={yes_order_id}")

    # ------------------------------------------------------------------
    # NO leg — retry-then-hedge (D-03, EXEC-03)
    # 3 retries × 500ms delay; check kill switch before each attempt.
    # On exhaustion: hedge SELL YES at price=0.01 (market-aggressive).
    # ------------------------------------------------------------------
    no_resp = None
    no_filled = False

    for attempt in range(_NO_RETRY_COUNT):
        # Kill switch check before each NO attempt (D-03)
        if risk_gate.is_kill_switch_active():
            logger.warning(
                f"Kill switch active — aborting NO retries at attempt {attempt + 1} "
                f"for market={opp.market_id}"
            )
            break

        try:
            no_resp = await place_fak_order(
                client, no_token_id, opp.no_ask, kelly_usd, "BUY"
            )
        except Exception as exc:
            logger.error(
                f"NO leg attempt {attempt + 1} exception for market={opp.market_id}: {exc}"
            )
            no_resp = None

        if no_resp and no_resp.get("status") != "unmatched":
            no_filled = True
            no_order_id = no_resp.get("orderID")
            results.append(ExecutionResult(
                market_id=opp.market_id,
                leg="no",
                side="BUY",
                token_id=no_token_id,
                price=opp.no_ask,
                size=kelly_usd,
                order_id=no_order_id,
                status="filled",
                size_filled=kelly_usd,
                kelly_size_usd=kelly_usd,
                vwap_price=opp.vwap_no,
            ))
            logger.info(
                f"NO leg filled on attempt {attempt + 1} | "
                f"market={opp.market_id} order={no_order_id}"
            )
            break

        logger.warning(
            f"NO leg attempt {attempt + 1}/{_NO_RETRY_COUNT} failed | "
            f"market={opp.market_id}"
        )
        if attempt < _NO_RETRY_COUNT - 1:
            await asyncio.sleep(_NO_RETRY_DELAY)

    # ------------------------------------------------------------------
    # Hedge: if NO never filled, SELL YES at market-aggressive price=0.01
    # ------------------------------------------------------------------
    if not no_filled:
        if hasattr(risk_gate, "record_order_error"):
            risk_gate.record_order_error()
        logger.warning(
            f"NO leg exhausted all retries — triggering hedge SELL | "
            f"market={opp.market_id} price={_HEDGE_PRICE}"
        )
        hedge_resp = None
        try:
            hedge_resp = await place_fak_order(
                client, yes_token_id, _HEDGE_PRICE, kelly_usd, "SELL"
            )
        except Exception as exc:
            logger.error(f"Hedge SELL exception for market={opp.market_id}: {exc}")

        hedge_order_id = hedge_resp.get("orderID") if hedge_resp else None
        results.append(ExecutionResult(
            market_id=opp.market_id,
            leg="hedge",
            side="SELL",
            token_id=yes_token_id,
            price=_HEDGE_PRICE,
            size=kelly_usd,
            order_id=hedge_order_id,
            status="hedged" if hedge_resp else "failed",
            size_filled=kelly_usd if hedge_resp else 0.0,
            kelly_size_usd=kelly_usd,
            vwap_price=opp.vwap_yes,
            error_msg=None if hedge_resp else "hedge SELL failed",
        ))
        if hedge_resp:
            logger.info(
                f"Hedge SELL placed | market={opp.market_id} order={hedge_order_id}"
            )
        else:
            logger.error(
                f"Hedge SELL FAILED — manual intervention required for market={opp.market_id}"
            )

    return arb_id, results
