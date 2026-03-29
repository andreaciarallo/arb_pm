"""
TDD tests for bot.execution.order_client.

Tests cover:
  - place_fak_order: success, FAK enforcement, exception handling
  - verify_fill_rest: success, timeout, zero size_matched
  - async function signatures
  - forbidden pattern (create_and_post_order never called)

EXEC-01, EXEC-02, EXEC-04 (D-02, D-04)
"""
import asyncio
import inspect
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from py_clob_client.clob_types import OrderType
from py_clob_client.exceptions import PolyApiException

from bot.execution.order_client import place_fak_order, verify_fill_rest

pytestmark = pytest.mark.unit


def _make_client(
    create_order_result=None,
    post_order_result=None,
    create_order_raises=None,
    get_order_result=None,
):
    client = MagicMock()
    if create_order_raises:
        client.create_order.side_effect = create_order_raises
    else:
        client.create_order.return_value = create_order_result or MagicMock(name="signed_order")
    client.post_order.return_value = post_order_result or {"orderID": "abc123", "status": "matched"}
    client.get_order.return_value = get_order_result or {"status": "matched", "size_matched": "10.0"}
    return client


async def test_place_fak_order_success():
    """place_fak_order returns the response dict from post_order on success."""
    client = _make_client(post_order_result={"orderID": "abc123", "status": "matched"})
    result = await place_fak_order(client, "token_yes", 0.41, 10.0, "BUY")
    assert result == {"orderID": "abc123", "status": "matched"}


async def test_place_fak_order_uses_fak_not_gtc():
    """place_fak_order must call post_order with orderType=OrderType.FAK (never GTC)."""
    client = _make_client()
    await place_fak_order(client, "token_yes", 0.41, 10.0, "BUY")
    # Verify post_order was called with FAK
    args, kwargs = client.post_order.call_args
    assert kwargs.get("orderType") == OrderType.FAK or (len(args) >= 2 and args[1] == OrderType.FAK)


async def test_place_fak_order_poly_exception_returns_none():
    """PolyApiException during create_order must return None (never raise)."""
    # PolyApiException(error_msg=...) — status_code kwarg not supported by actual SDK (0.34.6)
    client = _make_client(create_order_raises=PolyApiException(error_msg="rejected"))
    result = await place_fak_order(client, "token_yes", 0.41, 10.0, "BUY")
    assert result is None


async def test_place_fak_order_generic_exception_returns_none():
    """Generic exception during create_order must return None (never raise)."""
    client = _make_client(create_order_raises=RuntimeError("network error"))
    result = await place_fak_order(client, "token_yes", 0.41, 10.0, "BUY")
    assert result is None


async def test_verify_fill_rest_success_first_poll():
    """verify_fill_rest returns True immediately when size_matched > 0 on first poll."""
    client = _make_client(get_order_result={"status": "matched", "size_matched": "10.0"})
    result = await verify_fill_rest(client, "order_abc", timeout_seconds=5)
    assert result is True


async def test_verify_fill_rest_timeout_all_unmatched():
    """verify_fill_rest returns False after exhausting all polls when always unmatched."""
    client = _make_client(get_order_result={"status": "unmatched", "size_matched": "0.0"})
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await verify_fill_rest(client, "order_abc", timeout_seconds=5)
    assert result is False
    # Must have polled multiple times (up to 10)
    assert client.get_order.call_count >= 2


async def test_verify_fill_rest_false_on_zero_size_matched():
    """verify_fill_rest returns False when size_matched is 0 even if status is matched."""
    client = _make_client(get_order_result={"status": "matched", "size_matched": "0.0"})
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await verify_fill_rest(client, "order_abc", timeout_seconds=5)
    assert result is False


async def test_place_fak_order_is_async():
    """place_fak_order must be an async coroutine function."""
    assert inspect.iscoroutinefunction(place_fak_order)


async def test_place_fak_order_never_calls_create_and_post_order():
    """place_fak_order must never call create_and_post_order (GTC forbidden, D-02)."""
    client = _make_client()
    await place_fak_order(client, "token_yes", 0.41, 10.0, "BUY")
    client.create_and_post_order.assert_not_called()
