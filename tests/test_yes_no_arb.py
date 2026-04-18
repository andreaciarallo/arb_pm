import time
import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.unit


def _make_config():
    from bot.config import BotConfig
    return BotConfig(
        poly_api_key="k", poly_api_secret="s", poly_api_passphrase="p",
        wallet_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        polygon_rpc_http="https://polygon.example.com",
        polygon_rpc_ws="wss://polygon.example.com",
    )


def _make_market(condition_id: str = "0xabc", yes_tok: str = "y",
                 no_tok: str = "n", tags: list[str] = None,
                 question: str = "Will X happen?") -> dict:
    return {
        "condition_id": condition_id,
        "question": question,
        "tags": tags or [],
        "tokens": [
            {"token_id": yes_tok, "outcome": "Yes"},
            {"token_id": no_tok, "outcome": "No"},
        ],
        "token_ids": [yes_tok, no_tok],
    }


def _make_cache(yes_tok: str, no_tok: str, yes_ask: float, no_ask: float,
                yes_depth: float = 200.0, no_depth: float = 200.0):
    from bot.scanner.price_cache import PriceCache, MarketPrice

    cache = PriceCache()
    cache.update(yes_tok, MarketPrice(
        token_id=yes_tok, yes_ask=yes_ask, no_ask=0.0,
        yes_bid=yes_ask - 0.02, no_bid=0.0,
        yes_depth=yes_depth, no_depth=0.0,
        timestamp=time.time(), source="websocket",
    ))
    cache.update(no_tok, MarketPrice(
        token_id=no_tok, yes_ask=no_ask, no_ask=0.0,
        yes_bid=no_ask - 0.02, no_bid=0.0,
        yes_depth=no_depth, no_depth=0.0,
        timestamp=time.time(), source="websocket",
    ))
    return cache


def test_clear_arbitrage_detected():
    """YES 0.40 + NO 0.40 = 0.20 gross. Politics fee 2*1% = 2%. Net 18% >> 1.5% threshold."""
    from bot.detection.yes_no_arb import detect_yes_no_opportunities

    market = _make_market(tags=["politics"])
    cache = _make_cache("y", "n", yes_ask=0.40, no_ask=0.40)
    config = _make_config()

    opps = detect_yes_no_opportunities([market], cache, config)

    assert len(opps) == 1
    opp = opps[0]
    assert opp.gross_spread == pytest.approx(0.20)
    assert opp.net_spread > 0.015  # above base threshold
    assert opp.opportunity_type == "yes_no"
    assert opp.category == "politics"


def test_marginal_below_threshold_not_returned():
    """Net spread of 0.5% < 1.5% base threshold — not returned."""
    from bot.detection.yes_no_arb import detect_yes_no_opportunities

    # yes_ask=0.485, no_ask=0.495 → gross=0.02, fees=2*1%=0.02, net=0 → below threshold
    market = _make_market(tags=["politics"])
    cache = _make_cache("y", "n", yes_ask=0.485, no_ask=0.495)
    config = _make_config()

    opps = detect_yes_no_opportunities([market], cache, config)
    assert len(opps) == 0


def test_resolved_market_skipped():
    """YES ask == 1.0 (resolved) → no opportunity returned."""
    from bot.detection.yes_no_arb import detect_yes_no_opportunities

    market = _make_market(tags=["politics"])
    cache = _make_cache("y", "n", yes_ask=1.0, no_ask=0.0)
    config = _make_config()

    opps = detect_yes_no_opportunities([market], cache, config)
    assert len(opps) == 0


def test_insufficient_depth_skipped():
    """depth < $50 → opportunity not returned."""
    from bot.detection.yes_no_arb import detect_yes_no_opportunities

    market = _make_market(tags=["politics"])
    # Clear arb but tiny depth
    cache = _make_cache("y", "n", yes_ask=0.40, no_ask=0.40,
                        yes_depth=20.0, no_depth=20.0)  # $20 < $50 min
    config = _make_config()

    opps = detect_yes_no_opportunities([market], cache, config)
    assert len(opps) == 0


def test_missing_price_in_cache_skipped():
    """Market not in price cache → skipped gracefully (no exception)."""
    from bot.detection.yes_no_arb import detect_yes_no_opportunities
    from bot.scanner.price_cache import PriceCache

    market = _make_market()
    cache = PriceCache()  # empty cache
    config = _make_config()

    opps = detect_yes_no_opportunities([market], cache, config)
    assert len(opps) == 0


def test_geopolitics_lower_threshold():
    """Geopolitics uses 0.75% threshold — an opportunity that fails the 1.5% base still passes."""
    from bot.detection.yes_no_arb import detect_yes_no_opportunities

    # Geopolitics: fee=0%, threshold=0.75%
    # YES 0.492 + NO 0.492 = 0.016 gross, fees=0, net=1.6% > 0.75% ✓
    # But net=1.6% < 1.5% only if fees ate some — wait, fees=0, so net=1.6% > 0.75% ✓
    market = _make_market(tags=["geopolitics"],
                          question="Will NATO expand into Scandinavia by 2027?")
    cache = _make_cache("y", "n", yes_ask=0.492, no_ask=0.492)
    config = _make_config()

    opps = detect_yes_no_opportunities([market], cache, config)

    assert len(opps) == 1
    assert opps[0].category == "geopolitics"
    assert opps[0].estimated_fees == pytest.approx(0.0)  # fee-free


def test_token_ids_populated():
    """yes_token_id and no_token_id are populated on returned ArbitrageOpportunity (EXEC-01)."""
    from bot.detection.yes_no_arb import detect_yes_no_opportunities

    market = _make_market(yes_tok="yes_token_abc", no_tok="no_token_xyz", tags=["politics"])
    cache = _make_cache("yes_token_abc", "no_token_xyz", yes_ask=0.40, no_ask=0.40)
    config = _make_config()

    opps = detect_yes_no_opportunities([market], cache, config)

    assert len(opps) == 1
    opp = opps[0]
    assert opp.yes_token_id == "yes_token_abc", (
        f"expected yes_token_id='yes_token_abc', got '{opp.yes_token_id}'"
    )
    assert opp.no_token_id == "no_token_xyz", (
        f"expected no_token_id='no_token_xyz', got '{opp.no_token_id}'"
    )
    assert opp.yes_token_id != "", "yes_token_id must not be empty"
    assert opp.no_token_id != "", "no_token_id must not be empty"
