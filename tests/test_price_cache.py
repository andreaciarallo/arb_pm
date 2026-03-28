import time
import pytest

pytestmark = pytest.mark.unit


def _make_price(token_id: str, yes_ask: float = 0.45, no_ask: float = 0.57,
                timestamp: float | None = None, source: str = "websocket"):
    from bot.scanner.price_cache import MarketPrice
    return MarketPrice(
        token_id=token_id,
        yes_ask=yes_ask,
        no_ask=no_ask,
        yes_bid=yes_ask - 0.02,
        no_bid=no_ask - 0.02,
        yes_depth=100.0,
        no_depth=100.0,
        timestamp=timestamp if timestamp is not None else time.time(),
        source=source,
    )


def test_cache_stores_and_retrieves():
    """update() stores MarketPrice; get() retrieves it by token_id."""
    from bot.scanner.price_cache import PriceCache

    cache = PriceCache()
    price = _make_price("token_yes_123")
    cache.update("token_yes_123", price)

    retrieved = cache.get("token_yes_123")
    assert retrieved is not None
    assert retrieved.yes_ask == 0.45
    assert retrieved.source == "websocket"


def test_cache_get_returns_none_for_missing():
    """get() returns None for unknown token_id."""
    from bot.scanner.price_cache import PriceCache

    cache = PriceCache()
    assert cache.get("nonexistent") is None


def test_is_stale_fresh_data():
    """is_stale() returns False for data within threshold."""
    from bot.scanner.price_cache import PriceCache

    cache = PriceCache()
    cache.update("tok", _make_price("tok", timestamp=time.time()))
    assert cache.is_stale("tok", threshold_seconds=5) is False


def test_is_stale_old_data():
    """is_stale() returns True for data older than threshold."""
    from bot.scanner.price_cache import PriceCache

    cache = PriceCache()
    old_timestamp = time.time() - 10  # 10 seconds ago
    cache.update("tok", _make_price("tok", timestamp=old_timestamp))
    assert cache.is_stale("tok", threshold_seconds=5) is True


def test_is_stale_unknown_token():
    """is_stale() returns True for unknown token_id (treat as stale)."""
    from bot.scanner.price_cache import PriceCache

    cache = PriceCache()
    assert cache.is_stale("unknown_token", threshold_seconds=5) is True


def test_get_all_fresh_filters_stale():
    """get_all_fresh() returns only non-stale entries."""
    from bot.scanner.price_cache import PriceCache

    cache = PriceCache()
    cache.update("fresh", _make_price("fresh", timestamp=time.time()))
    cache.update("stale", _make_price("stale", timestamp=time.time() - 10))

    fresh = cache.get_all_fresh(threshold_seconds=5)
    assert "fresh" in fresh
    assert "stale" not in fresh


def test_market_price_source_field():
    """MarketPrice tracks whether data came from websocket or http."""
    from bot.scanner.price_cache import MarketPrice

    ws_price = _make_price("tok", source="websocket")
    http_price = _make_price("tok", source="http")

    assert ws_price.source == "websocket"
    assert http_price.source == "http"
