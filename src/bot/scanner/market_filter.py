"""
Liquid market fetching and filtering.

Fetches all markets from the CLOB API (paginated), filters to markets that
are active and accepting orders.

Note: The CLOB markets endpoint does not return volume data. Filtering is
done via active=True and accepting_orders=True flags instead.
"""
from loguru import logger
from py_clob_client.client import ClobClient

from bot.config import BotConfig

_PAGINATION_END = "LTE="  # Polymarket CLOB API end-of-pagination cursor (base64 for "-1")


async def fetch_liquid_markets(client: ClobClient, config: BotConfig) -> list[dict]:
    """
    Fetch all active markets and filter to those meeting the volume threshold.

    Returns a list of market dicts with an added `token_ids` field for
    WebSocket subscription. Markets are fetched via paginated CLOB API calls.

    Filters:
    - volume >= config.min_market_volume (D-19)
    - closed == False (active markets only)
    """
    all_markets: list[dict] = []
    cursor: str | None = None

    while True:
        kwargs = {}
        if cursor:
            kwargs["next_cursor"] = cursor

        response = client.get_markets(**kwargs)
        page_markets = response.get("data", [])
        all_markets.extend(page_markets)

        next_cursor = response.get("next_cursor", _PAGINATION_END)
        if next_cursor in (_PAGINATION_END, "end") or not next_cursor:
            break
        cursor = next_cursor

    logger.debug(f"Fetched {len(all_markets)} total markets from CLOB API")

    liquid = []
    for market in all_markets:
        if not market.get("active", False):
            continue
        if not market.get("accepting_orders", False):
            continue

        # Extract token IDs for WebSocket subscription
        token_ids = [t["token_id"] for t in market.get("tokens", [])]
        enriched = {**market, "token_ids": token_ids}
        liquid.append(enriched)

    logger.info(
        f"Market filter: {len(liquid)} active markets "
        f"(active=True, accepting_orders=True) "
        f"from {len(all_markets)} total"
    )
    return liquid
