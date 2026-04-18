"""
YES+NO structural arbitrage detection engine.

Detects when YES ask + NO ask < $1.00 after category-aware fees.
Uses CLOB ask prices only — never bid prices (D-05).

Detection gates (all must pass):
1. Both YES and NO prices in cache (not missing, not stale)
2. Neither price == 1.0 (resolved market guard)
3. min(yes_depth, no_depth) >= config.min_order_book_depth ($50)
4. net_spread >= category-specific min_net_profit_pct threshold
"""
from datetime import datetime

from loguru import logger

from bot.config import BotConfig
from bot.detection.fee_model import (
    get_market_category,
    get_min_profit_threshold,
    get_taker_fee,
)
from bot.detection.opportunity import ArbitrageOpportunity
from bot.scanner.price_cache import PriceCache


def detect_yes_no_opportunities(
    markets: list[dict],
    cache: PriceCache,
    config: BotConfig,
) -> list[ArbitrageOpportunity]:
    """
    Scan liquid markets for YES+NO structural arbitrage opportunities.

    For each market:
    1. Fetch YES and NO token prices from cache
    2. Skip resolved markets (ask == 1.0)
    3. Compute gross_spread = 1.0 - yes_ask - no_ask
    4. Apply category-aware taker fee: fees = (yes_ask + no_ask) * fee_rate
    5. Compute net_spread = gross_spread - fees
    6. Gate on min_order_book_depth and category profit threshold
    7. Yield ArbitrageOpportunity if all gates pass

    Returns list of detected opportunities (may be empty).
    """
    opportunities: list[ArbitrageOpportunity] = []

    # Diagnostic counters
    both_cached = 0
    depth_fails = 0
    spread_fails = 0
    best_sum = 2.0  # track lowest YES_ask + NO_ask seen

    for market in markets:
        tokens = market.get("tokens", [])
        if len(tokens) < 2:
            continue

        # Find YES and NO token IDs
        yes_token_id = None
        no_token_id = None
        for token in tokens:
            outcome = token.get("outcome", "").lower()
            if outcome == "yes":
                yes_token_id = token["token_id"]
            elif outcome == "no":
                no_token_id = token["token_id"]

        if not yes_token_id or not no_token_id:
            continue

        # Fetch prices from cache
        yes_price = cache.get(yes_token_id)
        no_price = cache.get(no_token_id)

        if yes_price is None or no_price is None:
            continue  # not yet in cache — wait for WebSocket data

        both_cached += 1
        yes_ask = yes_price.yes_ask
        no_ask = no_price.yes_ask  # NO token's ask price is stored in yes_ask field

        # Gate 1: Skip resolved markets
        if yes_ask >= 1.0 or no_ask >= 1.0:
            continue

        pair_sum = yes_ask + no_ask
        if pair_sum < best_sum:
            best_sum = pair_sum

        # Gate 2: Depth check
        depth = min(yes_price.yes_depth, no_price.yes_depth)
        if depth < config.min_order_book_depth:
            depth_fails += 1
            continue

        # Category-aware fee model
        category = get_market_category(market)
        taker_fee = get_taker_fee(category, config)
        threshold = get_min_profit_threshold(category, config)

        # Compute spreads
        gross_spread = 1.0 - yes_ask - no_ask
        estimated_fees = (yes_ask + no_ask) * taker_fee
        net_spread = gross_spread - estimated_fees

        # Gate 3: Profit threshold
        if net_spread < threshold:
            spread_fails += 1
            continue

        # Compute confidence score (simple proxy — refined in Phase 3)
        confidence = net_spread / (net_spread + 0.01)

        opportunity = ArbitrageOpportunity(
            market_id=market.get("condition_id", ""),
            market_question=market.get("question", ""),
            opportunity_type="yes_no",
            category=category,
            yes_ask=yes_ask,
            no_ask=no_ask,
            gross_spread=round(gross_spread, 6),
            estimated_fees=round(estimated_fees, 6),
            net_spread=round(net_spread, 6),
            depth=round(depth, 2),
            vwap_yes=yes_ask,   # VWAP = best ask for now (Phase 3 adds multi-level VWAP)
            vwap_no=no_ask,
            confidence_score=round(confidence, 4),
            detected_at=datetime.utcnow(),
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
        )
        opportunities.append(opportunity)

        logger.info(
            f"YES/NO arb | {market.get('question', '')[:60]} | "
            f"cat={category} gross={gross_spread:.3f} net={net_spread:.3f} "
            f"depth=${depth:.0f}"
        )

    best_sum_str = f"{best_sum:.4f}" if best_sum < 2.0 else "n/a"
    logger.info(
        f"YES/NO scan: {both_cached} pairs cached | best_sum={best_sum_str} | "
        f"depth_fails={depth_fails} spread_fails={spread_fails} | "
        f"{len(opportunities)} opps"
    )

    return opportunities
