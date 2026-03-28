import pytest

pytestmark = pytest.mark.unit


def _make_order_book(token_id: str = "tok_123", ask: str = "0.45",
                     ask_size: str = "200.00", bid: str = "0.43",
                     bid_size: str = "150.00") -> dict:
    return {
        "asset_id": token_id,
        "asks": [{"price": ask, "size": ask_size}],
        "bids": [{"price": bid, "size": bid_size}],
    }


def test_normalize_normal_order_book():
    """Normal order book -> MarketPrice with correct ask/bid from HTTP response."""
    from bot.scanner.normalizer import normalize_order_book

    book = _make_order_book(ask="0.45", bid="0.43")
    result = normalize_order_book(book)

    assert result is not None
    assert result.token_id == "tok_123"
    assert result.yes_ask == pytest.approx(0.45)
    assert result.yes_bid == pytest.approx(0.43)
    assert result.source == "http"


def test_normalize_resolved_market():
    """Resolved market (ask=1.0) -> returns valid MarketPrice, not None.
    Detection engine handles yes_ask==1.0 as skip condition separately."""
    from bot.scanner.normalizer import normalize_order_book

    book = _make_order_book(ask="1.0", ask_size="0.0")
    result = normalize_order_book(book)

    assert result is not None
    assert result.yes_ask == pytest.approx(1.0)


def test_normalize_empty_asks_returns_none():
    """Empty asks list -> None (cannot determine ask price)."""
    from bot.scanner.normalizer import normalize_order_book

    book = {"asset_id": "tok", "asks": [], "bids": [{"price": "0.43", "size": "100"}]}
    assert normalize_order_book(book) is None


def test_normalize_empty_bids_returns_price_with_zero_bid():
    """Empty bids -> returns MarketPrice with yes_bid=0.0 (bid not critical for detection)."""
    from bot.scanner.normalizer import normalize_order_book

    book = {"asset_id": "tok", "asks": [{"price": "0.45", "size": "100"}], "bids": []}
    result = normalize_order_book(book)

    assert result is not None
    assert result.yes_bid == pytest.approx(0.0)


def test_normalize_malformed_price_returns_none():
    """Non-numeric price string -> None."""
    from bot.scanner.normalizer import normalize_order_book

    book = _make_order_book(ask="not_a_number")
    assert normalize_order_book(book) is None


def test_normalize_missing_asset_id_returns_none():
    """Missing asset_id -> None."""
    from bot.scanner.normalizer import normalize_order_book

    book = {"asks": [{"price": "0.45", "size": "100"}], "bids": []}
    assert normalize_order_book(book) is None


def test_normalize_depth_from_ask_size():
    """yes_depth populated from asks[0].size."""
    from bot.scanner.normalizer import normalize_order_book

    book = _make_order_book(ask="0.45", ask_size="500.00")
    result = normalize_order_book(book)

    assert result is not None
    assert result.yes_depth == pytest.approx(500.0)
