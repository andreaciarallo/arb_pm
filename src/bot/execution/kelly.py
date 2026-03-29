"""
Modified Kelly position sizing for Polymarket arbitrage.

Formula: f = (b x p - q) / (b x sqrt(p))
  b = net_spread (arbitrage profit fraction from detection engine)
  p = min(1.0, depth / target_size)  -- execution probability from order book depth
  q = 1 - p

Source: "Unravelling the Probabilistic Forest" (arxiv 2508.03474), D-01.

Returns 0.0 on any edge case -- caller must skip the trade when 0.0 is returned.
Never force a minimum allocation when Kelly says no.
"""
import math


def kelly_size(
    net_spread: float,
    depth: float,
    target_size: float,
    total_capital: float,
    min_order_usd: float = 5.0,
    max_capital_pct: float = 0.05,
) -> float:
    """
    Compute position size in USD using the Modified Kelly formula.

    Args:
        net_spread: Arbitrage profit fraction (b). E.g. 0.03 for 3%.
        depth: Order book depth in USD at best ask level.
        target_size: Initial target size estimate for p calculation.
        total_capital: Total bot capital in USD.
        min_order_usd: Minimum order size ($5 Polymarket floor).
        max_capital_pct: Safety ceiling as fraction of capital (0.05 = 5%).

    Returns:
        Position size in USD rounded to 2 decimal places, or 0.0 if trade should be skipped.
    """
    b = net_spread
    if b <= 0:
        return 0.0

    if target_size <= 0:
        return 0.0

    p = min(1.0, depth / target_size)
    if p <= 0:
        return 0.0

    q = 1.0 - p

    numerator = b * p - q
    if numerator <= 0:
        return 0.0

    denominator = b * math.sqrt(p)
    if denominator <= 0:
        return 0.0

    kelly_fraction = numerator / denominator
    size = kelly_fraction * total_capital

    # Apply hard constraints (D-01)
    max_by_depth = depth * 0.5                       # Never move the market against yourself
    max_by_capital = total_capital * max_capital_pct  # 5% capital ceiling
    size = min(size, max_by_depth, max_by_capital)

    # Below Polymarket minimum -- skip entirely, do NOT round up
    if size < min_order_usd:
        return 0.0

    return round(size, 2)
