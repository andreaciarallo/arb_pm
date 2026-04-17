"""
CLOB WebSocket client for real-time order book data.

Subscribes to order book updates for liquid markets. Automatically reconnects
on disconnect with exponential backoff (1→2→4→8→30s cap).

Prices are always parsed from "sells" (ask side) per D-05.
Data is written to the shared PriceCache.
"""
import asyncio
import json
import math
import time

import websockets
from loguru import logger

from bot.config import BotConfig
from bot.scanner.price_cache import MarketPrice, PriceCache

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
_BACKOFF_INITIAL = 1
_BACKOFF_MAX = 30


class WebSocketClient:
    """
    Async WebSocket client that subscribes to Polymarket CLOB order book updates.

    Usage:
        client = WebSocketClient(token_ids=market_token_ids, cache=price_cache, config=config)
        asyncio.create_task(client.run())
    """

    def __init__(
        self,
        token_ids: list[str],
        cache: PriceCache,
        config: BotConfig,
    ) -> None:
        self._token_ids = token_ids
        self._cache = cache
        self._config = config
        self._max_reconnects: int | None = None  # None = run forever

    def _handle_message(self, raw: str) -> None:
        """Parse a WebSocket message and update the price cache."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON WebSocket message: {raw[:80]}")
            return

        event_type = data.get("event_type")
        if event_type != "book":
            return  # ignore price_change and other event types for now

        token_id = data.get("asset_id")
        if not token_id:
            return

        sells = data.get("sells", [])
        buys = data.get("buys", [])

        if not sells:
            return  # no ask data — skip

        try:
            # Sort ascending by price so sells[0] is the best (lowest) ask.
            # Polymarket CLOB WebSocket returns sells sorted descending (highest first).
            best_sell = min(sells, key=lambda s: float(s["price"]))
            yes_ask = float(best_sell["price"])
            yes_depth = float(best_sell["size"])
            yes_bid = float(buys[0]["price"]) if buys else yes_ask - 0.02
        except (KeyError, ValueError, IndexError) as e:
            logger.debug(f"Failed to parse book event for {token_id}: {e}")
            return

        # T-09: reject NaN/Inf prices — float() accepts them silently but they
        # corrupt downstream arithmetic and can pass comparison gates unexpectedly.
        if not math.isfinite(yes_ask) or not math.isfinite(yes_depth):
            logger.debug(f"Non-finite price/depth for {token_id}: ask={yes_ask} depth={yes_depth}")
            return

        # For YES/NO pairs, we receive separate events per token_id.
        # The cache stores each token independently; the detection engine
        # pairs YES+NO tokens by market condition_id.
        price = MarketPrice(
            token_id=token_id,
            yes_ask=yes_ask,
            no_ask=0.0,       # populated by the paired NO token event
            yes_bid=yes_bid,
            no_bid=0.0,
            yes_depth=yes_depth,
            no_depth=0.0,
            timestamp=time.time(),
            source="websocket",
        )
        self._cache.update(token_id, price)

    async def _connect_once(self, ws) -> None:
        """Send subscribe message and read messages until connection closes."""
        subscribe_msg = {
            "type": "market",
            "assets_ids": self._token_ids,
        }
        await ws.send(json.dumps(subscribe_msg))
        logger.info(f"WebSocket subscribed to {len(self._token_ids)} tokens")

        async for raw_message in ws:
            self._handle_message(raw_message)

    async def run(self) -> None:
        """
        Run the WebSocket client indefinitely with exponential backoff reconnection.

        This coroutine is designed to run as an asyncio task for the lifetime
        of the bot. It never raises — all exceptions trigger reconnection.
        """
        backoff = _BACKOFF_INITIAL
        reconnect_count = 0

        while True:
            if self._max_reconnects is not None and reconnect_count >= self._max_reconnects:
                logger.info("WebSocket max reconnects reached — stopping")
                return

            try:
                async with websockets.connect(WS_URL) as ws:
                    backoff = _BACKOFF_INITIAL  # reset on successful connect
                    logger.info(f"WebSocket connected: {WS_URL}")
                    await self._connect_once(ws)
            except (websockets.ConnectionClosed, OSError) as e:
                reconnect_count += 1
                logger.warning(
                    f"WebSocket disconnected: {e}. "
                    f"Reconnecting in {backoff}s (attempt {reconnect_count})"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)
            except Exception as e:
                reconnect_count += 1
                logger.error(f"Unexpected WebSocket error: {e}. Reconnecting in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)
