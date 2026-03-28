import time
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


def _make_config():
    from bot.config import BotConfig
    return BotConfig(
        poly_api_key="k", poly_api_secret="s", poly_api_passphrase="p",
        wallet_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        polygon_rpc_http="https://polygon.example.com",
        polygon_rpc_ws="wss://polygon.example.com",
    )


def _make_cache_with_stale(stale_token: str, fresh_token: str):
    from bot.scanner.price_cache import PriceCache, MarketPrice

    cache = PriceCache()
    # Add fresh entry
    cache.update(fresh_token, MarketPrice(
        token_id=fresh_token, yes_ask=0.45, no_ask=0.57,
        yes_bid=0.43, no_bid=0.55, yes_depth=200.0, no_depth=200.0,
        timestamp=time.time(), source="websocket",
    ))
    # Add stale entry (10 seconds old)
    cache.update(stale_token, MarketPrice(
        token_id=stale_token, yes_ask=0.45, no_ask=0.57,
        yes_bid=0.43, no_bid=0.55, yes_depth=200.0, no_depth=200.0,
        timestamp=time.time() - 10, source="websocket",
    ))
    return cache


@pytest.mark.asyncio
async def test_poll_stale_markets_refreshes_stale():
    """Stale market is polled; fresh market is skipped."""
    from bot.scanner.http_poller import poll_stale_markets

    stale_token = "tok_stale"
    fresh_token = "tok_fresh"
    cache = _make_cache_with_stale(stale_token, fresh_token)
    config = _make_config()

    mock_client = MagicMock()
    mock_client.get_order_book.return_value = {
        "asset_id": stale_token,
        "asks": [{"price": "0.46", "size": "150.00"}],
        "bids": [{"price": "0.44", "size": "100.00"}],
    }

    markets = [
        {"token_ids": [stale_token]},
        {"token_ids": [fresh_token]},
    ]

    count = await poll_stale_markets(mock_client, cache, markets, config)

    assert count == 1  # only stale_token was polled
    mock_client.get_order_book.assert_called_once_with(stale_token)

    # Cache should be updated with http source
    refreshed = cache.get(stale_token)
    assert refreshed is not None
    assert refreshed.source == "http"
    assert refreshed.yes_ask == pytest.approx(0.46)


@pytest.mark.asyncio
async def test_poll_returns_count_of_refreshed():
    """Returns count of successfully refreshed markets, not total stale."""
    from bot.scanner.http_poller import poll_stale_markets

    # Two stale tokens, one will fail normalization
    from bot.scanner.price_cache import PriceCache, MarketPrice
    cache = PriceCache()
    cache.update("tok_a", MarketPrice(
        token_id="tok_a", yes_ask=0.45, no_ask=0.0,
        yes_bid=0.43, no_bid=0.0, yes_depth=100.0, no_depth=0.0,
        timestamp=time.time() - 10, source="websocket",
    ))
    cache.update("tok_b", MarketPrice(
        token_id="tok_b", yes_ask=0.45, no_ask=0.0,
        yes_bid=0.43, no_bid=0.0, yes_depth=100.0, no_depth=0.0,
        timestamp=time.time() - 10, source="websocket",
    ))

    config = _make_config()
    mock_client = MagicMock()
    mock_client.get_order_book.side_effect = [
        {"asset_id": "tok_a", "asks": [{"price": "0.45", "size": "100"}], "bids": []},
        {"asset_id": "tok_b", "asks": [], "bids": []},  # empty asks -> normalize returns None
    ]

    markets = [{"token_ids": ["tok_a"]}, {"token_ids": ["tok_b"]}]
    count = await poll_stale_markets(mock_client, cache, markets, config)

    assert count == 1  # only tok_a succeeded (tok_b had empty asks)


@pytest.mark.asyncio
async def test_poll_http_error_does_not_stop_others():
    """HTTP fetch failure for one token is logged but does not stop polling others."""
    from bot.scanner.http_poller import poll_stale_markets
    from bot.scanner.price_cache import PriceCache, MarketPrice

    cache = PriceCache()
    for tok in ["tok_a", "tok_b"]:
        cache.update(tok, MarketPrice(
            token_id=tok, yes_ask=0.45, no_ask=0.0,
            yes_bid=0.43, no_bid=0.0, yes_depth=100.0, no_depth=0.0,
            timestamp=time.time() - 10, source="websocket",
        ))

    config = _make_config()
    mock_client = MagicMock()
    mock_client.get_order_book.side_effect = [
        Exception("Connection timeout"),
        {"asset_id": "tok_b", "asks": [{"price": "0.45", "size": "100"}], "bids": []},
    ]

    markets = [{"token_ids": ["tok_a"]}, {"token_ids": ["tok_b"]}]
    count = await poll_stale_markets(mock_client, cache, markets, config)

    assert count == 1  # tok_b succeeded despite tok_a failing
