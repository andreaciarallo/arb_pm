"""
Cross-market arbitrage detection using Polymarket event-level grouping.

Groups binary prediction markets by their shared Polymarket event (fetched once
from the Gamma API at startup) and detects when the sum of YES asks across a
mutually exclusive group is < $1.00 after fees.

Example: "Will Alice win?" + "Will Bob win?" + "Will Carol win?" all belong to
the same event. If exactly one candidate must win, buy all YES tokens when
total < $1.00.

Event-level grouping catches ALL mutually exclusive market groups on Polymarket
— both NegRisk-enabled events and standard multi-outcome events (e.g., elections
with N candidates) — unlike the old keyword heuristic which only found groups
with overlapping question text.

Gamma API is called ONCE at startup via load_event_groups(). The detection loop
(detect_cross_market_opportunities) is hot-path and never makes network calls.
"""
import httpx
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

_MAX_GROUP_SIZE = 20        # cap: groups > 20 markets are likely noise
_MIN_GROUP_SIZE = 2         # single-market groups are handled by yes_no_arb

_GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"

# Module-level cache: condition_id -> event_id
# Populated once at startup by load_event_groups(); never written during detection.
_event_groups: dict[str, str] = {}


def load_event_groups(condition_ids: list[str] | None = None) -> None:
    """
    Fetch event->market mappings from the Gamma API and populate _event_groups.

    Call this once when markets are loaded (at scanner startup), NOT on every
    detection cycle. The mapping is stable — events don't change mid-session.

    condition_ids: optional filter; if None, fetches all active events.
    """
    global _event_groups
    try:
        params: dict = {"active": "true", "limit": 500}
        resp = httpx.get(_GAMMA_EVENTS_URL, params=params, timeout=10.0)
        resp.raise_for_status()
        count = 0
        for event in resp.json():
            event_id = str(event.get("id", ""))
            if not event_id:
                continue
            for market in event.get("markets", []):
                cid = market.get("conditionId") or market.get("condition_id", "")
                if cid:
                    _event_groups[cid] = event_id
                    count += 1
        logger.info(
            f"load_event_groups: loaded {len(_event_groups)} condition_id->event_id "
            f"mappings ({count} from gamma API)"
        )
    except Exception as exc:
        logger.warning(f"load_event_groups: gamma API fetch failed: {exc}")


def _group_by_event(markets: list[dict]) -> list[list[dict]]:
    """
    Group markets by Polymarket event ID (from Gamma API) with neg_risk_market_id fallback.

    All markets in the same event are mutually exclusive — exactly one will
    resolve YES. This covers both NegRisk-enabled and standard multi-outcome
    events (e.g., election with N candidates).

    Markets without any event ID (standalone binary markets) are silently ignored.

    Requires load_event_groups() to have been called at startup for full coverage.
    The neg_risk_market_id fallback ensures NegRisk-enabled events are still
    detected even if the Gamma API call failed.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for market in markets:
        cid = market.get("condition_id", "")
        event_id = (
            _event_groups.get(cid)                  # Gamma API event (primary)
            or market.get("neg_risk_market_id")      # NegRisk fallback
            or market.get("neg_risk_id")             # alt field name
        )
        if event_id:
            groups[event_id].append(market)
    return [
        group for group in groups.values()
        if _MIN_GROUP_SIZE <= len(group) <= _MAX_GROUP_SIZE
    ]


def detect_cross_market_opportunities(
    markets: list[dict],
    cache: PriceCache,
    config: BotConfig,
) -> list[ArbitrageOpportunity]:
    """
    Detect cross-market arbitrage via event-level grouping + exclusivity constraint.

    Groups markets by their shared Polymarket event (using _event_groups populated
    by load_event_groups() at startup) and detects when the sum of YES asks is
    < $1.00 after fees (mutual exclusivity arbitrage).

    Returns list of ArbitrageOpportunity with opportunity_type='cross_market'.
    """
    groups = _group_by_event(markets)
    opportunities: list[ArbitrageOpportunity] = []

    for group in groups:
        # Collect YES ask prices and depths for all markets in group
        yes_asks: list[float] = []
        depths: list[float] = []
        categories: list[str] = []
        legs_data: list[dict] = []

        # Capture group[0]'s YES token ID before the loop overwrites yes_token_id (D-01)
        first_market_tokens = group[0].get("tokens", [])
        group0_yes_token_id = next(
            (t["token_id"] for t in first_market_tokens if t.get("outcome", "").lower() == "yes"),
            ""
        )

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
            legs_data.append({
                "token_id": yes_token_id,
                "ask": price.yes_ask,
                "depth": price.yes_depth,
            })

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

        # Entry fees: taker fee on all N YES token buys.
        # Exit fee: one additional taker fee on the winning token sell at resolution.
        # Approximate exit as average cost of one token position.
        entry_fees = total_yes * taker_fee
        exit_fee = (total_yes / len(group)) * taker_fee
        estimated_fees = entry_fees + exit_fee
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
            yes_token_id=group0_yes_token_id,
            no_token_id="",   # D-01: cross-market has no NO token
            legs=legs_data,   # all YES token legs for cross-market execution
        )
        opportunities.append(opp)

        logger.info(
            f"Cross-market arb | {len(group)} markets | "
            f"cat={dominant_category} gross={gross_spread:.3f} net={net_spread:.3f}"
        )

    return opportunities
