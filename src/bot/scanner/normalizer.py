"""
Order book normalization for CLOB HTTP API responses.

Converts raw CLOB order book dicts to MarketPrice objects.
Handles edge cases: resolved markets, empty books, malformed data.

This is a pure-function module — no side effects, no I/O.
"""
import time

from loguru import logger

from bot.scanner.price_cache import MarketPrice


def normalize_order_book(book: dict) -> MarketPrice | None:
    """
    Convert a CLOB HTTP order book response to a MarketPrice.

    Returns None (with warning log) for any error condition:
    - Missing asset_id
    - Empty asks list (no ask price available)
    - Non-numeric price strings

    Note: A resolved market (asks[0].price == "1.0") returns a valid
    MarketPrice with yes_ask=1.0. The detection engine skips markets
    where yes_ask == 1.0 as a separate step.
    """
    token_id = book.get("asset_id")
    if not token_id:
        logger.warning("normalize_order_book: missing asset_id in response")
        return None

    asks = book.get("asks", [])
    if not asks:
        logger.debug(f"normalize_order_book: empty asks for {token_id}")
        return None

    bids = book.get("bids", [])

    try:
        yes_ask = float(asks[0]["price"])
        yes_depth = float(asks[0].get("size", 0.0))
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"normalize_order_book: malformed ask for {token_id}: {e}")
        return None

    try:
        yes_bid = float(bids[0]["price"]) if bids else 0.0
    except (KeyError, ValueError, TypeError):
        yes_bid = 0.0

    return MarketPrice(
        token_id=token_id,
        yes_ask=yes_ask,
        no_ask=0.0,       # populated by paired NO token normalization
        yes_bid=yes_bid,
        no_bid=0.0,
        yes_depth=yes_depth,
        no_depth=0.0,
        timestamp=time.time(),
        source="http",
    )
