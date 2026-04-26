"""
Paper trade simulator for the Polymarket arbitrage bot.

Simulates YES/NO arbitrage trades using cached price data, producing PaperTrade
dataclasses for persistence and analytics. No real orders are placed.

Key design decisions:
  - D-02: VWAP uses cached PriceCache data, NOT fresh API calls
  - D-06: PaperTrade has 20 fields
  - D-07: Depth-gated deterministic fill (no stochastic component)
  - D-08: Kelly sizing reuses same parameters as live execution
  - D-09: P&L uses shares not dollars: gross_pnl = (1.0 - vwap_yes - vwap_no) * effective_shares

PaperTrade is NOT frozen (mutable) so net_pnl_usd can be updated for
cross-market P&L distribution after all legs are computed (A1 from RESEARCH.md).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime

from bot.config import BotConfig
from bot.detection.fee_model import get_taker_fee
from bot.detection.opportunity import ArbitrageOpportunity
from bot.execution.engine import simulate_vwap
from bot.execution.kelly import kelly_size
from bot.scanner.price_cache import PriceCache


@dataclass
class PaperTrade:
    """
    A single simulated trade leg for paper trading.

    20 fields per D-06. NOT frozen -- net_pnl_usd is mutable for cross-market
    P&L distribution (Plan 02 needs this).
    """
    paper_trade_id: str       # UUID, unique per leg
    paper_arb_id: str         # UUID, groups multi-leg trades
    market_id: str
    market_question: str
    opportunity_type: str     # "yes_no" | "cross_market"
    category: str
    leg: str                  # "yes" | "no" | "leg_1".."leg_N" | "hedge"
    side: str                 # "BUY" | "SELL"
    token_id: str
    ask_price: float
    simulated_size_usd: float   # kelly output (requested size)
    size_filled_usd: float      # actual fill based on depth
    vwap_price: float
    kelly_fraction: float
    estimated_fees_usd: float
    net_pnl_usd: float
    depth_available: float
    fill_ratio: float           # size_filled / simulated_size
    simulated_at: str           # ISO timestamp
    status: str                 # "filled" | "partial" | "failed" | "hedged"


def simulate_yes_no(
    opp: ArbitrageOpportunity,
    cache: PriceCache,
    config: BotConfig,
) -> list[PaperTrade]:
    """
    Simulate a YES/NO arb paper trade.

    Returns 2 PaperTrade rows (YES + NO legs) on success, or [] if:
      - Either token's price is missing from cache
      - Kelly sizing returns 0.0 (trade too small/risky)

    VWAP uses single-level ask list from PriceCache (Pitfall 1 in RESEARCH.md).
    P&L uses shares not dollars (Pitfall 2 in RESEARCH.md).
    """
    arb_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    # Guard: cached prices must exist for both tokens (D-02)
    yes_price = cache.get(opp.yes_token_id)
    no_price = cache.get(opp.no_token_id)
    if yes_price is None or no_price is None:
        return []

    # Target size for VWAP and Kelly
    target_size = config.total_capital_usd * config.kelly_max_capital_pct

    # Build single-level ask lists from cached prices (Pitfall 1)
    yes_asks = [{"price": yes_price.yes_ask, "size": yes_price.yes_depth}]
    no_asks = [{"price": no_price.yes_ask, "size": no_price.yes_depth}]

    vwap_yes = simulate_vwap(yes_asks, target_size)
    vwap_no = simulate_vwap(no_asks, target_size)

    # Kelly sizing (D-08: reuse same parameters as live execution)
    kelly_usd = kelly_size(
        net_spread=opp.net_spread,
        depth=opp.depth,
        target_size=target_size,
        total_capital=config.total_capital_usd,
        min_order_usd=config.kelly_min_order_usd,
        max_capital_pct=config.kelly_max_capital_pct,
    )
    if kelly_usd == 0.0:
        return []

    kelly_frac = kelly_usd / config.total_capital_usd

    # Depth-gated fill (D-07): deterministic, no stochastic component
    yes_depth = yes_price.yes_depth
    no_depth = no_price.yes_depth
    yes_filled = min(kelly_usd, yes_depth)
    no_filled = min(kelly_usd, no_depth)
    yes_fill_ratio = yes_filled / kelly_usd if kelly_usd > 0 else 0.0
    no_fill_ratio = no_filled / kelly_usd if kelly_usd > 0 else 0.0

    # Fees (D-09): category-aware per-side taker fee
    fee_rate = get_taker_fee(opp.category, config)
    yes_fees = fee_rate * yes_filled
    no_fees = fee_rate * no_filled

    # P&L (D-09): use shares not dollars (Pitfall 2)
    # effective_shares = min(yes_shares, no_shares) since excess shares on
    # one side are not hedged in YES/NO arb
    if vwap_yes > 0 and vwap_no > 0:
        effective_shares = min(yes_filled / vwap_yes, no_filled / vwap_no)
    else:
        effective_shares = 0.0

    gross_pnl = (1.0 - vwap_yes - vwap_no) * effective_shares
    total_fees = yes_fees + no_fees
    net_pnl = gross_pnl - total_fees

    # Split P&L equally across the 2 legs
    yes_pnl = net_pnl / 2.0
    no_pnl = net_pnl / 2.0

    # Build trade rows
    trades = []
    for leg_name, token_id, ask, filled, fill_ratio, vwap, fees, pnl, depth_avail in [
        ("yes", opp.yes_token_id, opp.yes_ask, yes_filled, yes_fill_ratio, vwap_yes, yes_fees, yes_pnl, yes_depth),
        ("no", opp.no_token_id, opp.no_ask, no_filled, no_fill_ratio, vwap_no, no_fees, no_pnl, no_depth),
    ]:
        status = (
            "filled" if fill_ratio >= 1.0
            else ("partial" if fill_ratio > 0 else "failed")
        )
        trades.append(PaperTrade(
            paper_trade_id=str(uuid.uuid4()),
            paper_arb_id=arb_id,
            market_id=opp.market_id,
            market_question=opp.market_question,
            opportunity_type="yes_no",
            category=opp.category,
            leg=leg_name,
            side="BUY",
            token_id=token_id,
            ask_price=ask,
            simulated_size_usd=kelly_usd,
            size_filled_usd=filled,
            vwap_price=vwap,
            kelly_fraction=kelly_frac,
            estimated_fees_usd=fees,
            net_pnl_usd=pnl,
            depth_available=depth_avail,
            fill_ratio=fill_ratio,
            simulated_at=now,
            status=status,
        ))

    return trades
