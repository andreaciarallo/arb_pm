import time
import pytest

pytestmark = pytest.mark.unit


def _make_config():
    from bot.config import BotConfig
    return BotConfig(
        poly_api_key="k", poly_api_secret="s", poly_api_passphrase="p",
        wallet_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        polygon_rpc_http="https://polygon.example.com",
        polygon_rpc_ws="wss://polygon.example.com",
    )


def _make_market(condition_id: str, question: str, yes_tok: str,
                 tags: list[str] = None) -> dict:
    return {
        "condition_id": condition_id,
        "question": question,
        "tags": tags or ["politics"],
        "tokens": [{"token_id": yes_tok, "outcome": "Yes"},
                   {"token_id": f"no_{yes_tok}", "outcome": "No"}],
        "token_ids": [yes_tok, f"no_{yes_tok}"],
    }


def _populate_cache(cache, token_id: str, ask: float, depth: float = 200.0):
    from bot.scanner.price_cache import MarketPrice
    cache.update(token_id, MarketPrice(
        token_id=token_id, yes_ask=ask, no_ask=0.0,
        yes_bid=ask - 0.02, no_bid=0.0,
        yes_depth=depth, no_depth=0.0,
        timestamp=time.time(), source="websocket",
    ))


def test_exclusivity_constraint_detected():
    """3 mutually exclusive markets with sum(YES) < 1.0 → cross_market opportunity."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win the 2026 election?", "tok_a"),
        _make_market("0x2", "Will Bob win the 2026 election?", "tok_b"),
        _make_market("0x3", "Will Carol win the 2026 election?", "tok_c"),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.20)

    config = _make_config()
    opps = detect_cross_market_opportunities(markets, cache, config)

    assert len(opps) == 1
    assert opps[0].opportunity_type == "cross_market"
    assert opps[0].gross_spread == pytest.approx(0.25)  # 1.0 - 0.75


def test_unrelated_markets_not_grouped():
    """Markets with no shared keywords are not grouped."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will bitcoin reach $200k by 2027?", "tok_a", ["crypto"]),
        _make_market("0x2", "Will Super Bowl be played in Las Vegas?", "tok_b", ["sports"]),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.30)

    config = _make_config()
    opps = detect_cross_market_opportunities(markets, cache, config)

    assert len(opps) == 0


def test_insufficient_depth_skips_group():
    """One market in the group has insufficient depth → whole group not returned."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win the 2026 election?", "tok_a"),
        _make_market("0x2", "Will Bob win the 2026 election?", "tok_b"),
    ]
    _populate_cache(cache, "tok_a", 0.30, depth=200.0)
    _populate_cache(cache, "tok_b", 0.25, depth=10.0)  # below $50 threshold

    config = _make_config()
    opps = detect_cross_market_opportunities(markets, cache, config)

    assert len(opps) == 0


def test_no_arb_when_sum_at_or_above_one():
    """Sum(YES asks) >= 1.0 → no arbitrage."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win the 2026 election?", "tok_a"),
        _make_market("0x2", "Will Bob win the 2026 election?", "tok_b"),
    ]
    _populate_cache(cache, "tok_a", 0.55)  # sum = 1.05 > 1.0
    _populate_cache(cache, "tok_b", 0.50)

    config = _make_config()
    opps = detect_cross_market_opportunities(markets, cache, config)

    assert len(opps) == 0


def test_single_market_group_not_returned():
    """A group of 1 market is not a cross-market opportunity."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [_make_market("0x1", "Will Alice win the election?", "tok_a")]
    _populate_cache(cache, "tok_a", 0.30)

    config = _make_config()
    opps = detect_cross_market_opportunities(markets, cache, config)

    assert len(opps) == 0
