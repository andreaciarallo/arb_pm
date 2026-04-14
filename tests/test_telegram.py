"""Unit tests for TelegramAlerter — OBS-02."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_alerter_noop_when_no_token():
    from bot.notifications.telegram import TelegramAlerter
    alerter = TelegramAlerter(token=None, chat_id=None)
    await alerter.send("test message")  # must not raise


@pytest.mark.asyncio
async def test_alerter_noop_when_no_chat_id():
    from bot.notifications.telegram import TelegramAlerter
    alerter = TelegramAlerter(token="tok123", chat_id=None)
    await alerter.send("test message")  # must not raise


@pytest.mark.asyncio
async def test_alerter_swallows_telegram_error():
    from telegram.error import TelegramError
    from bot.notifications.telegram import TelegramAlerter
    alerter = TelegramAlerter(token="tok", chat_id="123")
    with patch("bot.notifications.telegram.Bot") as mock_bot_cls:
        mock_bot = AsyncMock()
        mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
        mock_bot.__aexit__ = AsyncMock(return_value=False)
        mock_bot.send_message = AsyncMock(side_effect=TelegramError("timeout"))
        mock_bot_cls.return_value = mock_bot
        await alerter.send("test")  # must NOT raise


@pytest.mark.asyncio
async def test_alerter_swallows_generic_exception():
    from bot.notifications.telegram import TelegramAlerter
    alerter = TelegramAlerter(token="tok", chat_id="123")
    with patch("bot.notifications.telegram.Bot") as mock_bot_cls:
        mock_bot = AsyncMock()
        mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
        mock_bot.__aexit__ = AsyncMock(return_value=False)
        mock_bot.send_message = AsyncMock(side_effect=RuntimeError("network error"))
        mock_bot_cls.return_value = mock_bot
        await alerter.send("test")  # must NOT raise


@pytest.mark.asyncio
async def test_alerter_calls_send_message_with_html_parse_mode():
    from bot.notifications.telegram import TelegramAlerter
    alerter = TelegramAlerter(token="tok", chat_id="456")
    with patch("bot.notifications.telegram.Bot") as mock_bot_cls:
        mock_bot = AsyncMock()
        mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
        mock_bot.__aexit__ = AsyncMock(return_value=False)
        mock_bot.send_message = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        await alerter.send("<b>Alert</b>")
        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs.get("parse_mode") == "HTML"
