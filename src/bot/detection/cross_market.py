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
import itertools
import json

import httpx
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from loguru import logger


@dataclass(frozen=True)
class EventInfo:
    """Enriched event metadata for partition validation (D-04)."""
    event_id: str
    neg_risk: bool       # True if enableNegRisk=True in Gamma API
    market_count: int    # Number of markets in this event

from bot.config import BotConfig
from bot.detection.fee_model import (
    get_market_category,
    get_min_profit_threshold,
    get_taker_fee,
)
from bot.detection.filters import (
    DedupTracker,
    FilterDiagnostics,
    has_dead_leg,
    is_total_yes_reject,
)
from bot.detection.dependency import classify_pair
from bot.detection.opportunity import ArbitrageOpportunity
from bot.scanner.price_cache import PriceCache

_MAX_GROUP_SIZE = 20        # cap: groups > 20 markets are likely noise
_MIN_GROUP_SIZE = 2         # single-market groups are handled by yes_no_arb

_GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"

# Module-level cache: condition_id -> EventInfo (enriched from Gamma API)
# Populated once at startup by load_event_groups(); never written during detection.
_event_groups: dict[str, EventInfo] = {}

# Secondary cache: condition_id -> {question, outcomePrices} from Gamma (for validator)
_gamma_market_data: dict[str, dict] = {}


def load_event_groups(condition_ids: list[str] | None = None) -> None:
    """
    Fetch event->market mappings from the Gamma API and populate _event_groups.

    Call this once when markets are loaded (at scanner startup), NOT on every
    detection cycle. The mapping is stable — events don't change mid-session.

    condition_ids: optional filter; if None, fetches all active events.
    """
    global _event_groups, _gamma_market_data
    try:
        offset = 0
        page_size = 500
        count = 0
        neg_risk_events: set[str] = set()
        all_events: set[str] = set()
        while True:
            params: dict = {"active": "true", "limit": page_size, "offset": offset}
            resp = httpx.get(_GAMMA_EVENTS_URL, params=params, timeout=10.0)
            resp.raise_for_status()
            events = resp.json()
            if not events:
                break
            for event in events:
                event_id = str(event.get("id", ""))
                if not event_id:
                    continue
                neg_risk = event.get("enableNegRisk", False) is True
                market_list = event.get("markets", [])
                market_count = len(market_list)
                all_events.add(event_id)
                if neg_risk:
                    neg_risk_events.add(event_id)
                for market in market_list:
                    cid = market.get("conditionId") or market.get("condition_id", "")
                    if cid:
                        _event_groups[cid] = EventInfo(
                            event_id=event_id,
                            neg_risk=neg_risk,
                            market_count=market_count,
                        )
                        _gamma_market_data[cid] = {
                            "question": market.get("question", ""),
                            "outcomePrices": market.get("outcomePrices", "[]"),
                        }
                        count += 1
            offset += page_size
            if len(events) < page_size:
                break
        logger.info(
            f"load_event_groups: loaded {len(_event_groups)} condition_id->EventInfo "
            f"mappings ({count} from gamma API, "
            f"{len(neg_risk_events)} NegRisk / {len(all_events)} total events)"
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
        info = _event_groups.get(cid)
        event_id = (
            (info.event_id if info else None)        # Gamma API event (primary)
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
    dedup: DedupTracker | None = None,
) -> tuple[list[ArbitrageOpportunity], FilterDiagnostics]:
    """
    Detect cross-market arbitrage via event-level grouping + exclusivity constraint.

    Groups markets by their shared Polymarket event (using _event_groups populated
    by load_event_groups() at startup) and detects when the sum of YES asks is
    < $1.00 after fees (mutual exclusivity arbitrage).

    Returns (opportunities, diagnostics) tuple. Diagnostics track filter rejection counts.
    """
    groups = _group_by_event(markets)
    opportunities: list[ArbitrageOpportunity] = []
    diag = FilterDiagnostics()

    # Build dependency weight/threshold dicts from BotConfig (D-12)
    dep_weights = {
        "jaccard": config.dep_weight_jaccard,
        "implication": config.dep_weight_implication,
        "numeric": config.dep_weight_numeric,
        "temporal": config.dep_weight_temporal,
        "event_bonus": config.dep_weight_event_bonus,
    }
    dep_thresholds = {
        "subset": config.dep_threshold_subset,
        "related": config.dep_threshold_related,
    }

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

        # NEW Gate: DETECT-03 dead legs (per D-11: filter before leaving detector)
        leg_ask_values = [leg["ask"] for leg in legs_data]
        if has_dead_leg(leg_ask_values, config.min_cross_leg_ask):
            diag.leg_floor_rejects += 1
            logger.debug(
                f"DETECT-03 reject: dead leg | min_ask={min(leg_ask_values):.4f}"
            )
            continue

        # NEW Gate: DETECT-04 total_yes floor
        total_yes = sum(yes_asks)
        if is_total_yes_reject(total_yes, config.min_cross_total_yes):
            diag.total_yes_rejects += 1
            logger.debug(
                f"DETECT-04 reject: total_yes floor | total_yes={total_yes:.4f}"
            )
            continue

        # DEP-09/10/11: Dependency gate — pair generation + classify + audit/reject
        _dep_info = _event_groups.get(group[0].get("condition_id", ""))
        event_id = _dep_info.event_id if _dep_info else None
        group_flagged = False
        for m_a, m_b in itertools.combinations(group, 2):
            result = classify_pair(
                m_a.get("question", ""),
                m_b.get("question", ""),
                event_id_a=event_id,
                event_id_b=event_id,
                weights=dep_weights,
                thresholds=dep_thresholds,
            )
            if result.label != "independent":
                if config.dependency_audit_mode:
                    logger.info(
                        f'DEP-AUDIT: {result.label} | score={result.score:.3f} | '
                        f'jaccard={result.jaccard:.2f} impl={result.implication:.2f} '
                        f'num={result.numeric:.2f} temp={result.temporal:.2f} '
                        f'evt={result.event_bonus:.2f} | '
                        f'q1="{m_a.get("question", "")[:50]}" '
                        f'q2="{m_b.get("question", "")[:50]}"'
                    )
                else:
                    logger.debug(
                        f'DEP-REJECT: {result.label} | score={result.score:.3f} | '
                        f'jaccard={result.jaccard:.2f} impl={result.implication:.2f} '
                        f'num={result.numeric:.2f} temp={result.temporal:.2f} '
                        f'evt={result.event_bonus:.2f} | '
                        f'q1="{m_a.get("question", "")[:50]}" '
                        f'q2="{m_b.get("question", "")[:50]}"'
                    )
                group_flagged = True
                break  # D-07: one non-independent pair is enough

        if group_flagged:
            if config.dependency_audit_mode:
                diag.dep_audit_flags += 1
                # Audit mode: DON'T continue — let group proceed through remaining gates
            else:
                diag.dep_rejects += 1
                continue  # Rejection mode: skip this group entirely

        # Depth gate: weakest link in the group
        min_depth = min(depths)
        if min_depth < config.min_order_book_depth:
            continue

        # Exclusivity check
        if total_yes >= 1.0:
            continue  # no arbitrage — total >= $1.00

        gross_spread = 1.0 - total_yes

        # Use most common category for fee/threshold calculation
        dominant_category = Counter(categories).most_common(1)[0][0]
        taker_fee = get_taker_fee(dominant_category, config)
        threshold = get_min_profit_threshold(dominant_category, config)

        # Entry fees: taker fee on all N YES token buys.
        # No exit fee — Polymarket charges fees at match time only, not on resolution
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
            yes_token_id=group0_yes_token_id,
            no_token_id="",   # D-01: cross-market has no NO token
            legs=legs_data,   # all YES token legs for cross-market execution
        )
        # NEW Gate: DETECT-05 dedup (LAST)
        if dedup is not None and dedup.is_duplicate(
            group[0].get("condition_id", ""), "cross_market"
        ):
            diag.dedup_suppressed += 1
            logger.debug(
                f"DETECT-05 suppress: dedup | {group[0].get('question', '')[:40]}"
            )
            continue

        opportunities.append(opp)

        logger.info(
            f"Cross-market arb | {len(group)} markets | "
            f"cat={dominant_category} gross={gross_spread:.3f} net={net_spread:.3f}"
        )

    return opportunities, diag
