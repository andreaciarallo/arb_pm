"""
Basic cross-market arbitrage detection using keyword grouping.

Groups binary prediction markets by shared question keywords and detects
when the sum of YES asks across a mutually exclusive group is < $1.00 after fees.

Example: "Will Alice win?" + "Will Bob win?" + "Will Carol win?"
If one candidate must win, buy all YES tokens if total < $1.00.

LLM-based market dependency detection is deferred to Phase 3 (D-03).
This module uses keyword overlap only — a fast, deterministic heuristic.
"""
from collections import Counter, defaultdict
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

_MIN_WORD_LENGTH = 4        # ignore short words (articles, prepositions)
_MIN_SHARED_WORDS = 2       # minimum shared words to consider markets related
_MAX_GROUP_SIZE = 20        # cap: groups > 20 markets are likely noise
_MIN_GROUP_SIZE = 2         # single-market groups are handled by yes_no_arb


def _extract_keywords(question: str) -> frozenset[str]:
    """Extract significant words from a market question."""
    words = question.lower().split()
    return frozenset(
        w.strip("?.,!") for w in words
        if len(w.strip("?.,!")) >= _MIN_WORD_LENGTH
        and w.strip("?.,!").isalpha()
    )


def _group_markets(markets: list[dict]) -> list[list[dict]]:
    """
    Group markets by keyword overlap.

    Uses a BFS connected-components approach: for each pair of markets,
    check if they share >= _MIN_SHARED_WORDS significant keywords.
    Groups are sets of markets with sufficient overlap.
    """
    if len(markets) < 2:
        return []

    keywords = {m["condition_id"]: _extract_keywords(m.get("question", "")) for m in markets}
    market_by_id = {m["condition_id"]: m for m in markets}

    # Build adjacency: which markets share enough keywords?
    adj: dict[str, set[str]] = defaultdict(set)
    cids = [m["condition_id"] for m in markets]

    for i, cid_a in enumerate(cids):
        for cid_b in cids[i + 1:]:
            shared = keywords[cid_a] & keywords[cid_b]
            if len(shared) >= _MIN_SHARED_WORDS:
                adj[cid_a].add(cid_b)
                adj[cid_b].add(cid_a)

    # Find connected components (groups) via BFS
    visited: set[str] = set()
    groups: list[list[dict]] = []

    for cid in cids:
        if cid in visited or cid not in adj:
            continue
        # BFS from cid
        group_cids: list[str] = []
        queue = [cid]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            group_cids.append(current)
            queue.extend(adj[current] - visited)

        if _MIN_GROUP_SIZE <= len(group_cids) <= _MAX_GROUP_SIZE:
            groups.append([market_by_id[c] for c in group_cids])

    return groups


def detect_cross_market_opportunities(
    markets: list[dict],
    cache: PriceCache,
    config: BotConfig,
) -> list[ArbitrageOpportunity]:
    """
    Detect cross-market arbitrage via keyword grouping + exclusivity constraint.

    Groups markets with shared question keywords and detects when the sum of
    YES asks is < $1.00 after fees (mutual exclusivity arbitrage).

    Returns list of ArbitrageOpportunity with opportunity_type='cross_market'.
    """
    groups = _group_markets(markets)
    opportunities: list[ArbitrageOpportunity] = []

    for group in groups:
        # Collect YES ask prices and depths for all markets in group
        yes_asks: list[float] = []
        depths: list[float] = []
        categories: list[str] = []

        all_prices_available = True
        for market in group:
            tokens = market.get("tokens", [])
            yes_token_id = next(
                (t["token_id"] for t in tokens if t.get("outcome", "").lower() == "yes"),
                None
            )
            if not yes_token_id:
                all_prices_available = False
                break

            price = cache.get(yes_token_id)
            if price is None:
                all_prices_available = False
                break

            yes_asks.append(price.yes_ask)
            depths.append(price.yes_depth)
            categories.append(get_market_category(market))

        if not all_prices_available:
            continue

        # Depth gate: weakest link in the group
        min_depth = min(depths)
        if min_depth < config.min_order_book_depth:
            continue

        # Exclusivity check
        total_yes = sum(yes_asks)
        if total_yes >= 1.0:
            continue  # no arbitrage — total >= $1.00

        gross_spread = 1.0 - total_yes

        # Use most common category for fee/threshold calculation
        dominant_category = Counter(categories).most_common(1)[0][0]
        taker_fee = get_taker_fee(dominant_category, config)
        threshold = get_min_profit_threshold(dominant_category, config)

        estimated_fees = total_yes * taker_fee
        net_spread = gross_spread - estimated_fees

        if net_spread < threshold:
            continue

        confidence = net_spread / (net_spread + 0.01)

        # Build combined question summary
        questions = [m.get("question", "")[:40] for m in group]
        summary = " | ".join(questions[:3])

        opp = ArbitrageOpportunity(
            market_id=group[0].get("condition_id", ""),
            market_question=f"[{len(group)}-way cross] {summary}",
            opportunity_type="cross_market",
            category=dominant_category,
            yes_ask=yes_asks[0],
            no_ask=0.0,
            gross_spread=round(gross_spread, 6),
            estimated_fees=round(estimated_fees, 6),
            net_spread=round(net_spread, 6),
            depth=round(min_depth, 2),
            vwap_yes=yes_asks[0],
            vwap_no=0.0,
            confidence_score=round(confidence, 4),
            detected_at=datetime.utcnow(),
        )
        opportunities.append(opp)

        logger.info(
            f"Cross-market arb | {len(group)} markets | "
            f"cat={dominant_category} gross={gross_spread:.3f} net={net_spread:.3f}"
        )

    return opportunities
