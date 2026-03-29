"""
Liquid market fetching and filtering.

Fetches all markets from the CLOB API (paginated), filters to markets that
are active and accepting orders.

Note: The CLOB markets endpoint does not return volume data. Filtering is
done via active=True and accepting_orders=True flags instead.
"""
import asyncio
import time

from loguru import logger
from py_clob_client.client import ClobClient

from bot.config import BotConfig

_PAGINATION_END = "LTE="  # Polymarket CLOB API end-of-pagination cursor (base64 for "-1")
_PAGE_DELAY = 0.2         # 200ms between pages → 5 req/s, safely under 60/10s limit
_RETRY_BACKOFF_START = 5  # seconds to wait on first 429
_MAX_RETRIES = 5


def _get_markets_page(client: ClobClient, **kwargs) -> dict:
    """
    Fetch one page of markets with retry on 429.

    Retries up to _MAX_RETRIES times with exponential backoff starting at
    _RETRY_BACKOFF_START seconds. Raises on non-429 errors or exhausted retries.
    """
    backoff = _RETRY_BACKOFF_START
    for attempt in range(_MAX_RETRIES):
        try:
            return client.get_markets(**kwargs)
        except Exception as e:
            if "429" in str(e) and attempt < _MAX_RETRIES - 1:
                logger.warning(
                    f"Rate limited (429) fetching markets page — "
                    f"waiting {backoff}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
            else:
                raise


async def fetch_liquid_markets(client: ClobClient, config: BotConfig) -> list[dict]:
    """
    Fetch all active markets and filter to those meeting the volume threshold.

    Returns a list of market dicts with an added `token_ids` field for
    WebSocket subscription. Markets are fetched via paginated CLOB API calls
    with 200ms inter-page delay to stay within the 60 req/10s rate limit.

    Filters:
    - volume >= config.min_market_volume (D-19)
    - closed == False (active markets only)
    """
    all_markets: list[dict] = []
    cursor: str | None = None
    page = 0

    while True:
        kwargs = {}
        if cursor:
            kwargs["next_cursor"] = cursor

        response = _get_markets_page(client, **kwargs)
        page_markets = response.get("data", [])
        all_markets.extend(page_markets)
        page += 1

        next_cursor = response.get("next_cursor", _PAGINATION_END)
        if next_cursor in (_PAGINATION_END, "end") or not next_cursor:
            break
        cursor = next_cursor

        # Rate limit: yield to event loop and pause between pages
        await asyncio.sleep(_PAGE_DELAY)

    logger.debug(f"Fetched {len(all_markets)} total markets from CLOB API ({page} pages)")

    liquid = []
    for market in all_markets:
        if not market.get("active", False):
            continue
        if not market.get("enable_order_book", False):
            continue
        if not market.get("accepting_orders", False):
            continue

        # Extract token IDs for WebSocket subscription
        token_ids = [t["token_id"] for t in market.get("tokens", [])]
        if not token_ids:
            continue
        enriched = {**market, "token_ids": token_ids}
        liquid.append(enriched)

    logger.info(
        f"Market filter: {len(liquid)} CLOB markets "
        f"(active=True, enable_order_book=True, accepting_orders=True) "
        f"from {len(all_markets)} total"
    )
    return liquid
