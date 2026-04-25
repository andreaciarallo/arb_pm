"""
Detection quality filters (DETECT-01 through DETECT-05).

Stateless threshold filters for rejecting false-positive arbitrage opportunities,
plus DedupTracker for suppressing repeated detections within a time window,
and FilterDiagnostics for per-cycle rejection counters.

All filter functions are pure: they take values and thresholds, return bool.
No side effects, no imports beyond stdlib.
"""
import time
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Stateless threshold filters
# ---------------------------------------------------------------------------

def is_ask_floor_reject(yes_ask: float, no_ask: float, floor: float) -> bool:
    """DETECT-01: Reject if either ask is at or below the floor."""
    return yes_ask <= floor or no_ask <= floor


def is_sum_cap_reject(yes_ask: float, no_ask: float, cap: float) -> bool:
    """DETECT-02: Reject if YES + NO ask sum exceeds the cap."""
    return (yes_ask + no_ask) > cap


def has_dead_leg(leg_asks: list[float], floor: float) -> bool:
    """DETECT-03: Reject if any leg's ask is at or below the floor."""
    return any(ask <= floor for ask in leg_asks)


def is_total_yes_reject(total_yes: float, floor: float) -> bool:
    """DETECT-04: Reject if total YES ask sum is below the floor."""
    return total_yes < floor


# ---------------------------------------------------------------------------
# Dedup tracker
# ---------------------------------------------------------------------------

class DedupTracker:
    """
    DETECT-05: Suppress duplicate opportunity detections within a time window.

    Key is (market_id, opp_type) per D-01 -- different opportunity types on the
    same market are tracked independently.
    """

    def __init__(self, window_seconds: int = 300) -> None:
        self._window = window_seconds
        self._seen: dict[tuple[str, str], float] = {}

    def is_duplicate(self, market_id: str, opp_type: str) -> bool:
        """
        Return True if this (market_id, opp_type) was seen within the window.

        On first call (or after expiry), records the timestamp and returns False.
        """
        key = (market_id, opp_type)
        now = time.monotonic()

        if key in self._seen:
            elapsed = now - self._seen[key]
            if elapsed < self._window:
                return True

        self._seen[key] = now
        return False

    def prune(self) -> int:
        """Remove expired entries. Returns count of entries pruned."""
        now = time.monotonic()
        expired = [
            key for key, ts in self._seen.items()
            if (now - ts) >= self._window
        ]
        for key in expired:
            del self._seen[key]
        return len(expired)


# ---------------------------------------------------------------------------
# Diagnostics dataclass
# ---------------------------------------------------------------------------

@dataclass
class FilterDiagnostics:
    """Per-cycle rejection counters for filter pipeline observability (D-07, D-12)."""
    ask_floor_rejects: int = 0
    sum_cap_rejects: int = 0
    leg_floor_rejects: int = 0
    total_yes_rejects: int = 0
    dedup_suppressed: int = 0
    dep_rejects: int = 0       # groups rejected by dependency gate (rejection mode)
    dep_audit_flags: int = 0   # groups that WOULD be rejected (audit mode)
