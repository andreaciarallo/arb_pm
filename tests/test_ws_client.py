import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

pytestmark = pytest.mark.unit


def _make_config():
    from bot.config import BotConfig
    return BotConfig(
        poly_api_key="k", poly_api_secret="s", poly_api_passphrase="p",
        wallet_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        polygon_rpc_http="https://polygon.example.com",
        polygon_rpc_ws="wss://polygon.example.com",
    )


def _make_book_event(token_id: str, ask: float = 0.45, bid: float = 0.43,
                     ask_size: float = 200.0) -> dict:
    return {
        "event_type": "book",
        "asset_id": token_id,
        "market": "0xcondition_id",
        "buys": [{"price": str(bid), "size": "100.00"}],
        "sells": [{"price": str(ask), "size": str(ask_size)}],
    }


@pytest.mark.asyncio
async def test_subscribe_message_sent_on_connect():
    """WebSocketClient sends subscribe message with all token_ids on connect."""
    from bot.scanner.price_cache import PriceCache
    from bot.scanner.ws_client import WebSocketClient

    token_ids = ["tok_yes_1", "tok_no_1"]
    cache = PriceCache()
    config = _make_config()
    client = WebSocketClient(token_ids=token_ids, cache=cache, config=config)

    # Build a mock WebSocket that supports `async for` and records send() calls
    messages = [json.dumps(_make_book_event("tok_yes_1"))]
    sent_messages = []

    class _FakeWS:
        async def send(self, data):
            sent_messages.append(data)

        def __aiter__(self):
            return self._gen()

        async def _gen(self):
            for msg in messages:
                yield msg

    mock_ws = _FakeWS()

    with patch("websockets.connect") as mock_connect:
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)

        await client._connect_once(mock_ws)

    assert len(sent_messages) == 1
    sent = json.loads(sent_messages[0])
    assert sent["type"] == "market"
    assert set(sent["assets_ids"]) == set(token_ids)


@pytest.mark.asyncio
async def test_book_event_updates_cache():
    """Book event parsed correctly — ask price from 'sells', updates cache."""
    from bot.scanner.price_cache import PriceCache
    from bot.scanner.ws_client import WebSocketClient

    cache = PriceCache()
    config = _make_config()
    client = WebSocketClient(token_ids=["tok_yes"], cache=cache, config=config)

    event = _make_book_event("tok_yes", ask=0.45, bid=0.43, ask_size=200.0)
    client._handle_message(json.dumps(event))

    price = cache.get("tok_yes")
    assert price is not None
    assert price.yes_ask == pytest.approx(0.45)
    assert price.source == "websocket"


@pytest.mark.asyncio
async def test_reconnects_on_disconnect():
    """WebSocketClient reconnects automatically after ConnectionClosed."""
    import websockets
    from bot.scanner.price_cache import PriceCache
    from bot.scanner.ws_client import WebSocketClient

    cache = PriceCache()
    config = _make_config()
    client = WebSocketClient(token_ids=["tok"], cache=cache, config=config)
    client._max_reconnects = 2  # stop after 2 reconnect attempts for test

    connect_calls = []

    class _FailingCM:
        """Async context manager that raises ConnectionClosed on __aenter__."""

        async def __aenter__(self):
            connect_calls.append(1)
            raise websockets.ConnectionClosed(None, None)

        async def __aexit__(self, *args):
            return False

    def fake_connect(*args, **kwargs):
        return _FailingCM()

    with patch("bot.scanner.ws_client.websockets.connect", side_effect=fake_connect):
        with patch("asyncio.sleep", new_callable=AsyncMock):  # skip actual sleep
            try:
                await asyncio.wait_for(client.run(), timeout=1.0)
            except (asyncio.TimeoutError, StopIteration):
                pass

    assert len(connect_calls) >= 2  # confirmed reconnect attempt
