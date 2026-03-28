"""
In-memory price cache for Polymarket order book data.

Stores MarketPrice snapshots keyed by token_id. Provides staleness detection
to trigger HTTP polling fallback when WebSocket data is >5s old (D-09).

All prices are CLOB ask prices — never Gamma bid prices (D-05).
"""
import time
from dataclasses import dataclass


@dataclass
class MarketPrice:
    """
    Price snapshot for a single YES or NO token.

    yes_ask / no_ask: CLOB ask prices (what you pay to go long). Always use
    these for arbitrage detection — never bid prices (D-05, critical lesson).

    source: "websocket" (primary) or "http" (fallback polling).
    """
    token_id: str
    yes_ask: float
    no_ask: float
    yes_bid: float
    no_bid: float
    yes_depth: float    # USD depth at best ask level
    no_depth: float     # USD depth at best ask level
    timestamp: float    # Unix epoch seconds (time.time())
    source: str         # "websocket" | "http"


class PriceCache:
    """
    Thread-safe in-memory cache of MarketPrice snapshots.

    All operations are O(1) dict lookups. No background threads — the async
    WebSocket client calls update() directly.
    """

    def __init__(self) -> None:
        self._data: dict[str, MarketPrice] = {}

    def update(self, token_id: str, price: MarketPrice) -> None:
        """Store or overwrite the price for token_id."""
        self._data[token_id] = price

    def get(self, token_id: str) -> MarketPrice | None:
        """Return the cached price for token_id, or None if not cached."""
        return self._data.get(token_id)

    def is_stale(self, token_id: str, threshold_seconds: int) -> bool:
        """
        Return True if the cached price is older than threshold_seconds,
        or if token_id has never been cached (treat missing as stale).
        """
        price = self._data.get(token_id)
        if price is None:
            return True
        return (time.time() - price.timestamp) > threshold_seconds

    def get_all_fresh(self, threshold_seconds: int) -> dict[str, MarketPrice]:
        """Return all non-stale cache entries as a {token_id: MarketPrice} dict."""
        now = time.time()
        return {
            token_id: price
            for token_id, price in self._data.items()
            if (now - price.timestamp) <= threshold_seconds
        }

    def __len__(self) -> int:
        return len(self._data)
