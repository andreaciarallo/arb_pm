"""
HTTP polling fallback for stale WebSocket data (DATA-02).

When a market's WebSocket data is >5 seconds old, this module fetches
fresh order book data via the CLOB HTTP API and updates the price cache.

Runs on every scan cycle — cheap because only stale markets are polled.
"""
from loguru import logger
from py_clob_client.client import ClobClient

from bot.config import BotConfig
from bot.scanner.normalizer import normalize_order_book
from bot.scanner.price_cache import PriceCache


async def poll_stale_markets(
    client: ClobClient,
    cache: PriceCache,
    markets: list[dict],
    config: BotConfig,
) -> int:
    """
    Poll the CLOB HTTP API for markets with stale WebSocket data.

    For each market, checks each token_id in the PriceCache. If stale
    (older than config.ws_stale_threshold_seconds), fetches fresh order
    book data and updates the cache with source="http".

    Returns:
        Count of markets successfully refreshed.
    """
    refreshed = 0

    for market in markets:
        for token_id in market.get("token_ids", []):
            if not cache.is_stale(token_id, config.ws_stale_threshold_seconds):
                continue  # fresh — skip

            try:
                raw_book = client.get_order_book(token_id)
                price = normalize_order_book(raw_book)
                if price is None:
                    logger.debug(f"HTTP poll: failed to normalize order book for {token_id}")
                    continue
                cache.update(token_id, price)
                refreshed += 1
                logger.debug(f"HTTP poll: refreshed {token_id} (was stale)")
            except Exception as e:
                logger.warning(f"HTTP poll: failed to fetch {token_id}: {e}")

    if refreshed > 0:
        logger.debug(f"HTTP poll: refreshed {refreshed} stale market tokens")

    return refreshed
