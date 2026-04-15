"""
Telegram alerting for the Polymarket arbitrage bot (OBS-02).

Fire-and-forget non-critical alerts. Telegram failures NEVER affect bot operation.
All public send_*() methods are async — callers MUST use asyncio.create_task().

Locked decisions (D-01 through D-06):
- D-01: Telegram only (no Discord)
- D-03: Fire-and-forget — no retry on failure
- D-04: Optional env vars — if absent, all sends are silent no-ops
- D-05: Alert events: arb complete, circuit breaker trip, critical failure, kill switch, daily summary
- D-06: Individual leg fills do NOT trigger alerts
"""
from __future__ import annotations

import html

from loguru import logger
from telegram import Bot
from telegram.error import TelegramError


class TelegramAlerter:
    """
    Fire-and-forget Telegram alerter.

    Usage (callers MUST use create_task, never await directly):
        alerter = TelegramAlerter(token=config.telegram_bot_token,
                                  chat_id=config.telegram_chat_id)
        asyncio.create_task(alerter.send_arb_complete(...))
        asyncio.create_task(alerter.send_circuit_breaker_trip(...))
    """

    def __init__(self, token: str | None, chat_id: str | None) -> None:
        self._token = token
        self._chat_id = chat_id

    async def send(self, text: str, parse_mode: str | None = "HTML") -> None:
        """
        Send a message to the configured Telegram chat.

        Fire-and-forget: catches ALL exceptions and logs them.
        Never raises — trading must never pause for an alert failure (D-03).

        Args:
            text: Message text. Use HTML for alerts, plain text for daily summary.
            parse_mode: "HTML" (default) or None for plain text.
        """
        if not self._token or not self._chat_id:
            return  # Silent no-op when Telegram not configured (D-04)
        try:
            async with Bot(token=self._token) as bot:
                kwargs: dict = {
                    "chat_id": self._chat_id,
                    "text": text,
                }
                if parse_mode:
                    kwargs["parse_mode"] = parse_mode
                await bot.send_message(**kwargs)
        except TelegramError as e:
            logger.warning(f"Telegram alert failed: {e}")
        except Exception as e:
            # Catch-all: network errors, invalid token, etc.
            # Log and swallow — never propagate (D-03)
            logger.warning(f"Telegram alert failed: {e}")

    async def send_arb_complete(
        self,
        market_question: str,
        yes_entry_price: float,
        no_entry_price: float,
        size_usd: float,
        hold_seconds: float,
        gross_pnl: float,
        fees_usd: float,
        net_pnl: float,
    ) -> None:
        """
        Alert: both YES and NO legs confirmed filled (D-05 event 1).

        HTML parse_mode per UI-SPEC. Market question wrapped in <b> tags.
        All numeric values plain (avoids HTML entity escaping issues on dynamic content).
        """
        # Hold time formatting: Xs or Xm Ys
        if hold_seconds < 60:
            hold_str = f"{hold_seconds:.0f}s"
        else:
            minutes = int(hold_seconds // 60)
            seconds = int(hold_seconds % 60)
            hold_str = f"{minutes}m {seconds}s"

        pnl_sign = "+" if net_pnl >= 0 else ""
        gross_sign = "+" if gross_pnl >= 0 else ""

        escaped_q = html.escape(market_question[:60])
        text = (
            f"<b>Arb complete — {escaped_q}</b>\n\n"
            f"YES: {yes_entry_price:.4f} | NO: {no_entry_price:.4f}\n"
            f"Size: ${size_usd:.2f} | Hold: {hold_str}\n"
            f"Gross: {gross_sign}${gross_pnl:.4f} | Fees: ${fees_usd:.4f}\n"
            f"Net P&L: {pnl_sign}${net_pnl:.4f}"
        )
        await self.send(text, parse_mode="HTML")

    async def send_circuit_breaker_trip(
        self,
        error_count: int,
        cooldown_seconds: float,
    ) -> None:
        """Alert: circuit breaker tripped (D-05 event 2). Plain text."""
        cooldown_minutes = int(cooldown_seconds // 60)
        cooldown_secs = int(cooldown_seconds % 60)
        text = (
            f"Circuit breaker tripped. "
            f"Errors: {error_count}/60s. "
            f"Cooldown: {cooldown_minutes}m {cooldown_secs}s."
        )
        await self.send(text, parse_mode=None)

    async def send_kill_switch(self, trigger: str) -> None:
        """
        Alert: kill switch activated (D-05 event 4).

        Args:
            trigger: "KILL file" or "SIGTERM"
        """
        text = f"Kill switch triggered via {trigger}. Closing positions now."
        await self.send(text, parse_mode=None)

    async def send_daily_summary(
        self,
        date_str: str,
        pnl_usd: float,
        trade_count: int,
        win_count: int,
        loss_count: int,
        arb_count: int,
        fees_usd: float,
        efficiency_pct: float | None,
        bot_status: str,
    ) -> None:
        """
        Daily P&L summary at midnight UTC (D-05 event 5).

        Plain text only — no HTML parse mode to avoid escaping issues with
        dynamic market names in edge cases (UI-SPEC Daily Summary section).
        """
        win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0.0
        pnl_sign = "+" if pnl_usd >= 0 else ""
        if efficiency_pct is None:
            eff_str = "N/A"
        elif efficiency_pct >= 0:
            eff_str = f"+{efficiency_pct:.2f}%"
        else:
            eff_str = f"{efficiency_pct:.2f}%"

        text = (
            f"Daily Summary — {date_str}\n\n"
            f"P&L: {pnl_sign}${pnl_usd:.4f}\n"
            f"Trades: {trade_count} ({win_count} wins, {loss_count} losses, win rate {win_rate:.0f}%)\n"
            f"Arbs completed: {arb_count}\n"
            f"Fees paid: ${fees_usd:.4f}\n"
            f"Capital efficiency (today): {eff_str}\n\n"
            f"Bot status: {bot_status.upper()}"
        )
        await self.send(text, parse_mode=None)
