"""
Low-level order placement and fill verification for Polymarket CLOB.

CRITICAL: All orders use FAK (Fill-And-Kill) via create_order() + post_order(FAK).
Using create_and_post_order() is FORBIDDEN — it defaults to GTC which leaves
naked arb exposure after the opportunity disappears (verified in py-clob-client 0.34.6).

All py-clob-client calls are synchronous (httpx.Client internally). Every call
is wrapped in asyncio.run_in_executor() to avoid blocking the event loop.

EXEC-01, EXEC-02, EXEC-04 (D-02, D-04)
"""
import asyncio

from loguru import logger
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.exceptions import PolyApiException

_VERIFY_POLL_INTERVAL_SECONDS = 0.5
_VERIFY_MAX_POLLS = 10  # 10 × 500ms = 5s max (matches ws_stale_threshold_seconds, D-04)


async def place_fak_order(
    client,
    token_id: str,
    price: float,
    size_usd: float,
    side: str,
) -> dict | None:
    """
    Place a FAK (Fill-And-Kill / IOC) order on Polymarket CLOB.

    Uses the two-step pattern: create_order() -> post_order(FAK).
    Never uses create_and_post_order() which silently defaults to GTC.

    Args:
        client: Authenticated ClobClient instance (from build_client()).
        token_id: YES or NO conditional token asset ID.
        price: Limit price (e.g., 0.41). Must be valid for market tick_size.
        size_usd: Order size in USDC. Converted internally to token count
                  via size_tokens = size_usd / price before sending to CLOB.
        side: "BUY" or "SELL".

    Returns:
        Response dict with "orderID" and "status", or None on any failure.
    """
    loop = asyncio.get_running_loop()
    # CLOB interprets size as number of outcome tokens, not USDC.
    # Total USDC spent = size_tokens × price. Convert here so callers
    # always reason in USD (EXEC-SIZE-001 fix).
    size_tokens = size_usd / price
    order_args = OrderArgs(
        token_id=token_id,
        price=price,
        size=size_tokens,
        side=side,
    )

    try:
        # create_order: local EIP-712 signing + one sync call to resolve tick_size/neg_risk
        signed = await loop.run_in_executor(None, client.create_order, order_args)
        # post_order: REST submission — MUST specify FAK, never GTC
        response = await loop.run_in_executor(
            None,
            lambda: client.post_order(signed, orderType=OrderType.FAK),
        )
        logger.debug(
            f"FAK order submitted | token={token_id} side={side} price={price} "
            f"size_usd={size_usd} size_tokens={size_tokens:.4f} "
            f"status={response.get('status')} id={response.get('orderID')}"
        )
        return response
    except PolyApiException as exc:
        logger.error(f"Order rejected by CLOB: {exc.status_code} — {exc.error_msg}")
        return None
    except Exception as exc:
        logger.error(f"Order placement failed: {exc}")
        return None


async def verify_fill_rest(
    client,
    order_id: str,
    timeout_seconds: float = 5.0,
) -> bool:
    """
    Verify a fill via REST polling (dual verification per D-04, EXEC-04).

    Polls client.get_order() every 500ms for up to 10 iterations (5s total).
    Returns True only when REST confirms size_matched > 0.

    WebSocket fill confirmation is the primary signal; this REST check is the
    secondary verification. Disagreement (REST says 0 after timeout) -> treat as
    unfilled, log discrepancy, do not proceed with second leg.

    Args:
        client: Authenticated ClobClient instance.
        order_id: Polymarket order ID from place_fak_order() response.
        timeout_seconds: Maximum wait time. Default 5s matches ws_stale_threshold.

    Returns:
        True if REST confirms size_matched > 0, False otherwise.
    """
    loop = asyncio.get_running_loop()
    polls = int(timeout_seconds / _VERIFY_POLL_INTERVAL_SECONDS)

    for attempt in range(polls):
        try:
            data = await loop.run_in_executor(None, client.get_order, order_id)
            size_matched = float(data.get("size_matched", 0) or 0)
            if size_matched > 0:
                logger.debug(
                    f"REST verified fill | order={order_id} size_matched={size_matched}"
                )
                return True
        except Exception as exc:
            logger.warning(f"REST verification poll {attempt + 1} failed for {order_id}: {exc}")

        if attempt < polls - 1:
            await asyncio.sleep(_VERIFY_POLL_INTERVAL_SECONDS)

    logger.warning(
        f"REST verification timeout after {polls} polls for order={order_id} — treating as unfilled"
    )
    return False
