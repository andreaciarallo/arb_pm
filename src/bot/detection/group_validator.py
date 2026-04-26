"""
Group structure validation for Polymarket event groups (D-01).

Validates event groups as one-of-N partitions suitable for basket arbitrage.
NegRisk groups auto-pass (exchange-guaranteed). Non-NegRisk groups are checked
for structural violations: duplicates, subsets, overlaps.

Runs ONCE at startup (D-02). Detection loop checks membership via get_valid_groups().
"""
import json
import itertools
from collections import defaultdict

from loguru import logger

from bot.detection.cross_market import EventInfo, _event_groups, _gamma_market_data
from bot.detection.dependency import (
    _preprocess,
    _jaccard_similarity,
    _keyword_implication,
    _extract_number,
)

# Module-level cache: valid event IDs (populated at startup by validate_groups)
_valid_groups: set[str] = set()

# Constants
_DUPLICATE_THRESHOLD = 0.9   # Jaccard similarity for duplicate detection (GV-02)
_SUBSET_JACCARD_MIN = 0.6    # Minimum Jaccard for numeric threshold check (GV-03)
_COMPLETENESS_LOW = 0.7      # Mid-price sum lower bound (GV-04)
_COMPLETENESS_HIGH = 1.3     # Mid-price sum upper bound (GV-04)


def is_duplicate_pair(question_a: str, question_b: str) -> tuple[bool, float]:
    """
    Detect if two market questions are near-duplicates (GV-02).

    Uses preprocessed token Jaccard similarity from dependency.py.

    Returns (is_duplicate, jaccard_score).
    """
    tokens_a = _preprocess(question_a)
    tokens_b = _preprocess(question_b)
    score = _jaccard_similarity(tokens_a, tokens_b)
    return score > _DUPLICATE_THRESHOLD, score


def is_subset_pair(question_a: str, question_b: str) -> tuple[bool, str]:
    """
    Detect if one market implies the other -- subset relationship (GV-03).

    Signal 1: Keyword implication (e.g., "wins by 5 points" implies "wins")
    Signal 2: Numeric threshold containment (same subject + different numbers,
              e.g., "BTC reaches $150k" implies "BTC reaches $100k")

    Returns (is_subset, signal_name).
    """
    # Signal 1: Keyword implication
    if _keyword_implication(question_a, question_b) > 0.0:
        return True, "keyword_implication"

    # Signal 2: Numeric threshold (same subject + different numbers)
    tokens_a = _preprocess(question_a)
    tokens_b = _preprocess(question_b)
    jaccard = _jaccard_similarity(tokens_a, tokens_b)
    if jaccard > _SUBSET_JACCARD_MIN:
        num_a = _extract_number(question_a)
        num_b = _extract_number(question_b)
        if num_a is not None and num_b is not None and num_a != num_b:
            return True, "numeric_threshold"

    return False, ""


def passes_completeness_check(
    markets: list[dict],
    low: float = _COMPLETENESS_LOW,
    high: float = _COMPLETENESS_HIGH,
) -> tuple[bool, float]:
    """
    Check if sum of YES prices is within [low, high] range (GV-04).

    Uses outcomePrices from Gamma API (available at startup).
    Parses with json.loads() -- never eval() (T-06-02 mitigation).

    Returns (passes, mid_sum).
    """
    mid_sum = 0.0
    for market in markets:
        outcome_prices_raw = market.get("outcomePrices", "[]")
        if isinstance(outcome_prices_raw, str):
            try:
                prices = json.loads(outcome_prices_raw)
            except (json.JSONDecodeError, ValueError):
                continue
        else:
            prices = outcome_prices_raw
        if prices:
            yes_price = float(prices[0])
            mid_sum += yes_price

    return low <= mid_sum <= high, mid_sum


def _validate_non_negrisk_group(event_id: str, cids: list[str]) -> bool:
    """
    Validate a non-NegRisk group for structural violations.

    Checks all pairs for duplicates and subsets, then runs completeness check.
    Returns True if group is valid (no violations).
    """
    # Get questions from _gamma_market_data for each cid
    questions: dict[str, str] = {}
    for cid in cids:
        data = _gamma_market_data.get(cid, {})
        questions[cid] = data.get("question", "")

    # Pairwise checks using itertools.combinations
    for cid_a, cid_b in itertools.combinations(cids, 2):
        q_a = questions.get(cid_a, "")
        q_b = questions.get(cid_b, "")

        # GV-02: Duplicate check
        is_dup, dup_score = is_duplicate_pair(q_a, q_b)
        if is_dup:
            logger.debug(
                f'GV-REJECT: duplicate | q1="{q_a[:50]}" q2="{q_b[:50]}" '
                f'| score={dup_score:.2f}'
            )
            return False

        # GV-03: Subset check
        is_sub, signal = is_subset_pair(q_a, q_b)
        if is_sub:
            logger.debug(
                f'GV-REJECT: subset | q1="{q_a[:50]}" q2="{q_b[:50]}" '
                f'| signal={signal}'
            )
            return False

    # GV-04: Completeness check
    market_dicts = []
    for cid in cids:
        data = _gamma_market_data.get(cid, {})
        market_dicts.append({"outcomePrices": data.get("outcomePrices", "[]")})

    passes, mid_sum = passes_completeness_check(market_dicts)
    if not passes:
        logger.debug(
            f'GV-REJECT: completeness | event={event_id} | mid_sum={mid_sum:.2f}'
        )
        return False

    return True


def validate_groups() -> set[str]:
    """
    Validate all event groups as one-of-N partitions (D-09).

    NegRisk groups auto-pass (exchange-guaranteed).
    Non-NegRisk groups are checked for structural violations.

    Returns set of valid event IDs. Updates module-level _valid_groups cache.
    """
    global _valid_groups

    # Build event_id -> list[condition_id] mapping from _event_groups
    event_cids: dict[str, list[str]] = defaultdict(list)
    for cid, info in _event_groups.items():
        event_cids[info.event_id].append(cid)

    valid: set[str] = set()
    neg_risk_count = 0
    checked_count = 0
    rejected_count = 0

    for event_id, cids in event_cids.items():
        # Get EventInfo from any cid in the group
        info = _event_groups.get(cids[0])
        if info is None:
            continue

        if info.neg_risk:
            # GV-01: NegRisk auto-pass
            valid.add(event_id)
            neg_risk_count += 1
        else:
            # Non-NegRisk: validate structure
            checked_count += 1
            if _validate_non_negrisk_group(event_id, cids):
                valid.add(event_id)
            else:
                rejected_count += 1

    logger.info(
        f"GV: {neg_risk_count} NegRisk groups auto-validated, "
        f"{checked_count} non-NegRisk checked, {rejected_count} rejected"
    )

    _valid_groups = valid
    return valid


def get_valid_groups() -> set[str]:
    """Return the cached set of valid event IDs from last validate_groups() call."""
    return _valid_groups
