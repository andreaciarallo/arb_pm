"""
RiskGate: independent risk control state layer.

Tracks stop-loss (RISK-02), circuit breaker (RISK-03), and kill switch (RISK-04).
In-memory only — state does not persist across restarts.

Usage:
    risk_gate = RiskGate(
        total_capital_usd=config.total_capital_usd,
        daily_stop_loss_pct=config.daily_stop_loss_pct,
        circuit_breaker_errors=config.circuit_breaker_error_count,
        circuit_breaker_window_seconds=config.circuit_breaker_window_seconds,
        circuit_breaker_cooldown_seconds=config.circuit_breaker_cooldown_seconds,
    )

    # In scan loop:
    if risk_gate.is_kill_switch_active():
        await execute_kill_switch(client, risk_gate, writer)
        break  # exit scan loop

    if risk_gate.is_blocked():
        continue  # skip opportunity, wait for next cycle

    # After a confirmed realized loss:
    risk_gate.record_loss(realized_loss_usd)

    # After an order rejection or timeout during execution:
    risk_gate.record_order_error()
"""
import datetime
import time

from loguru import logger


class RiskGate:
    """
    Mutable risk control state machine.

    NOT a frozen dataclass — state updated via methods.
    NOT thread-safe — single asyncio event loop assumed.

    Attributes
    ----------
    total_capital_usd : float
        Total capital deployed. Used to compute stop-loss threshold.
    daily_stop_loss_pct : float
        Fraction of total_capital_usd that constitutes the daily stop-loss.
        Default 0.05 (5%) → $50 at $1k capital (D-06).
    circuit_breaker_errors : int
        Number of order errors within the window required to trip (D-07).
    circuit_breaker_window_seconds : int
        Sliding window for counting errors (D-07).
    circuit_breaker_cooldown_seconds : int
        Base cooldown duration in seconds. Doubles on repeat trips (D-07).
    """

    def __init__(
        self,
        total_capital_usd: float,
        daily_stop_loss_pct: float = 0.05,
        circuit_breaker_errors: int = 5,
        circuit_breaker_window_seconds: int = 60,
        circuit_breaker_cooldown_seconds: int = 300,
    ) -> None:
        # Config (immutable after init)
        self.total_capital_usd = total_capital_usd
        self.daily_stop_loss_pct = daily_stop_loss_pct
        self.circuit_breaker_errors = circuit_breaker_errors
        self.circuit_breaker_window_seconds = circuit_breaker_window_seconds
        self.circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds

        # Mutable state
        self._daily_loss_usd: float = 0.0
        self._day_reset_timestamp: float = time.time()
        self._error_timestamps: list[float] = []
        self._cb_cooldown_until: float = 0.0
        self._cb_cooldown_multiplier: int = 1   # doubles on each trip, caps at 4 (→ 20m max)
        self._kill_switch_active: bool = False

    # ------------------------------------------------------------------
    # Mutators — called from execution path
    # ------------------------------------------------------------------

    def record_loss(self, loss_usd: float) -> None:
        """
        Add a realized loss to the daily accumulator.

        Only call this after a confirmed fill that results in a loss.
        Unrealized losses (open positions) are excluded.

        Parameters
        ----------
        loss_usd : float
            Positive USD amount lost on a filled trade.
        """
        self._check_day_reset()
        self._daily_loss_usd += loss_usd
        logger.debug(
            f"Loss recorded: ${loss_usd:.2f} | daily_total=${self._daily_loss_usd:.2f} "
            f"| limit=${self.total_capital_usd * self.daily_stop_loss_pct:.2f}"
        )

    def record_order_error(self) -> None:
        """
        Record an order-phase error for the circuit breaker sliding window.

        Only call from the execution path — order rejection, timeout, auth failure.
        Do NOT call for connection errors during idle scanning (D-07).
        """
        now = time.time()
        self._error_timestamps.append(now)
        # Trim to sliding window
        cutoff = now - self.circuit_breaker_window_seconds
        self._error_timestamps = [t for t in self._error_timestamps if t >= cutoff]
        logger.debug(f"Order error recorded — {len(self._error_timestamps)} in window")

        if len(self._error_timestamps) >= self.circuit_breaker_errors:
            cooldown = self.circuit_breaker_cooldown_seconds * self._cb_cooldown_multiplier
            self._cb_cooldown_until = now + cooldown
            self._cb_cooldown_multiplier = min(self._cb_cooldown_multiplier * 2, 4)
            self._error_timestamps.clear()
            logger.warning(
                f"Circuit breaker tripped — cooldown {cooldown}s "
                f"(next multiplier={self._cb_cooldown_multiplier}x)"
            )

    def record_clean_cycle(self) -> None:
        """
        No-op — error window trims naturally on time expiry.

        Kept for interface clarity; callers may call this after a successful
        execution cycle without effect.
        """
        pass

    def activate_kill_switch(self) -> None:
        """
        Activate the kill switch immediately.

        Once active, kill switch cannot be deactivated without restart.
        Triggered by:
        - SIGTERM signal (loop.add_signal_handler in live_run.py)
        - /app/data/KILL file presence (checked every scan cycle in live_run.py)
        """
        self._kill_switch_active = True
        logger.warning("Kill switch ACTIVATED — all trading halted, position closure required")

    # ------------------------------------------------------------------
    # Predicates — called before each execution cycle
    # ------------------------------------------------------------------

    def is_kill_switch_active(self) -> bool:
        """Return True if kill switch has been activated."""
        return self._kill_switch_active

    def is_stop_loss_triggered(self) -> bool:
        """
        Return True if cumulative realized daily loss has reached the threshold.

        Automatically resets at midnight UTC (checked each call).
        Threshold: daily_stop_loss_pct × total_capital_usd (D-06).
        """
        self._check_day_reset()
        limit = self.total_capital_usd * self.daily_stop_loss_pct
        triggered = self._daily_loss_usd >= limit
        if triggered:
            logger.debug(
                f"Stop-loss triggered: ${self._daily_loss_usd:.2f} >= ${limit:.2f}"
            )
        return triggered

    def is_circuit_breaker_open(self) -> bool:
        """
        Return True if circuit breaker cooldown is currently active.

        Cooldown expires at _cb_cooldown_until timestamp (D-07).
        """
        return time.time() < self._cb_cooldown_until

    def is_blocked(self) -> bool:
        """
        Return True if any risk control prevents new order submission.

        Kill switch overrides all other states — is_blocked() returns True
        even when circuit breaker cooldown has expired, if kill switch is active.

        Order of checks:
        1. Kill switch (override — never unblocked without restart)
        2. Stop-loss (daily threshold reached)
        3. Circuit breaker (cooldown active)
        """
        return (
            self.is_kill_switch_active()
            or self.is_stop_loss_triggered()
            or self.is_circuit_breaker_open()
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_day_reset(self) -> None:
        """
        Reset daily loss accumulator at midnight UTC.

        Compares _day_reset_timestamp against today's midnight UTC.
        If reset timestamp is before midnight, loss is cleared and
        timestamp is updated to now.
        """
        now_utc = datetime.datetime.utcnow()
        midnight = datetime.datetime.combine(now_utc.date(), datetime.time.min)
        if self._day_reset_timestamp < midnight.timestamp():
            prev_loss = self._daily_loss_usd
            self._daily_loss_usd = 0.0
            self._day_reset_timestamp = time.time()
            logger.info(
                f"Daily loss reset at midnight UTC — "
                f"previous daily loss was ${prev_loss:.2f}"
            )
