import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.unit


def _make_market(volume: float, closed: bool = False) -> dict:
    return {
        "condition_id": f"0x{volume:.0f}",
        "question": f"Test market volume={volume}",
        "tokens": [
            {"token_id": f"yes_{volume:.0f}", "outcome": "Yes"},
            {"token_id": f"no_{volume:.0f}", "outcome": "No"},
        ],
        "volume": volume,
        "liquidity": volume * 0.5,
        "active": not closed,
        "closed": closed,
        "tags": [],
        "end_date_iso": "2027-01-01T00:00:00Z",
    }


def _make_config(min_volume: float = 1000.0):
    from bot.config import BotConfig
    return BotConfig(
        poly_api_key="k", poly_api_secret="s", poly_api_passphrase="p",
        wallet_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        polygon_rpc_http="https://polygon.example.com",
        polygon_rpc_ws="wss://polygon.example.com",
        min_market_volume=min_volume,
    )


@pytest.mark.asyncio
async def test_fetch_liquid_markets_filters_by_volume():
    """Markets with volume >= threshold are returned; below threshold are excluded."""
    from bot.scanner.market_filter import fetch_liquid_markets

    mock_client = MagicMock()
    mock_client.get_markets.return_value = {
        "data": [
            _make_market(5000.0),   # above threshold — include
            _make_market(999.0),    # below threshold — exclude
            _make_market(1000.0),   # exactly at threshold — include
        ],
        "next_cursor": "end",
        "count": 3,
    }

    config = _make_config(min_volume=1000.0)
    result = await fetch_liquid_markets(mock_client, config)

    assert len(result) == 2
    volumes = {m["volume"] for m in result}
    assert 5000.0 in volumes
    assert 1000.0 in volumes
    assert 999.0 not in volumes


@pytest.mark.asyncio
async def test_fetch_liquid_markets_excludes_closed():
    """Closed markets are excluded regardless of volume."""
    from bot.scanner.market_filter import fetch_liquid_markets

    mock_client = MagicMock()
    mock_client.get_markets.return_value = {
        "data": [
            _make_market(5000.0, closed=False),
            _make_market(5000.0, closed=True),
        ],
        "next_cursor": "end",
        "count": 2,
    }

    config = _make_config(min_volume=1000.0)
    result = await fetch_liquid_markets(mock_client, config)

    assert len(result) == 1
    assert result[0]["closed"] is False


@pytest.mark.asyncio
async def test_fetch_liquid_markets_empty_returns_empty():
    """Empty market list returns empty list without raising."""
    from bot.scanner.market_filter import fetch_liquid_markets

    mock_client = MagicMock()
    mock_client.get_markets.return_value = {
        "data": [],
        "next_cursor": "end",
        "count": 0,
    }

    config = _make_config()
    result = await fetch_liquid_markets(mock_client, config)
    assert result == []


@pytest.mark.asyncio
async def test_fetch_liquid_markets_pagination():
    """Fetches all pages when next_cursor is present."""
    from bot.scanner.market_filter import fetch_liquid_markets

    mock_client = MagicMock()
    page1 = {
        "data": [_make_market(2000.0)],
        "next_cursor": "cursor_abc",
        "count": 1,
    }
    page2 = {
        "data": [_make_market(3000.0)],
        "next_cursor": "end",
        "count": 1,
    }
    mock_client.get_markets.side_effect = [page1, page2]

    config = _make_config()
    result = await fetch_liquid_markets(mock_client, config)

    assert len(result) == 2
    assert mock_client.get_markets.call_count == 2


@pytest.mark.asyncio
async def test_fetch_liquid_markets_token_ids_present():
    """Each returned market has token_ids field for WebSocket subscription."""
    from bot.scanner.market_filter import fetch_liquid_markets

    mock_client = MagicMock()
    mock_client.get_markets.return_value = {
        "data": [_make_market(5000.0)],
        "next_cursor": "end",
        "count": 1,
    }

    config = _make_config()
    result = await fetch_liquid_markets(mock_client, config)

    assert len(result) == 1
    assert "token_ids" in result[0]
    assert len(result[0]["token_ids"]) == 2  # YES and NO token
