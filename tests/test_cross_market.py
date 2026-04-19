import time
import pytest

pytestmark = pytest.mark.unit

# Field name used by _group_by_event() to look up event membership.
# PATH B (Gamma API): _event_groups maps condition_id -> event_id at module level.
# In tests we bypass the Gamma API by injecting the event_id directly into the
# market dict via the "event_id" helper key, then patching _event_groups.
_EVENT_FIELD = "condition_id"   # used in _group_by_event via _event_groups lookup


def _make_config():
    from bot.config import BotConfig
    return BotConfig(
        poly_api_key="k", poly_api_secret="s", poly_api_passphrase="p",
        wallet_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        polygon_rpc_http="https://polygon.example.com",
        polygon_rpc_ws="wss://polygon.example.com",
    )


def _make_market(condition_id: str, question: str, yes_tok: str,
                 tags: list[str] = None, event_id: str = None) -> dict:
    m = {
        "condition_id": condition_id,
        "question": question,
        "tags": tags or ["politics"],
        "tokens": [{"token_id": yes_tok, "outcome": "Yes"},
                   {"token_id": f"no_{yes_tok}", "outcome": "No"}],
        "token_ids": [yes_tok, f"no_{yes_tok}"],
    }
    if event_id is not None:
        # Store the event_id in the market dict; _patch_event_groups() will
        # use it to populate bot.detection.cross_market._event_groups.
        m["_test_event_id"] = event_id
    return m


def _patch_event_groups(markets: list[dict]) -> dict:
    """
    Build a condition_id -> event_id mapping from markets that have
    _test_event_id set, and inject it into the module-level _event_groups dict.
    Returns the original _event_groups so callers can restore it.
    """
    import bot.detection.cross_market as cm
    original = dict(cm._event_groups)
    cm._event_groups.clear()
    for m in markets:
        eid = m.get("_test_event_id")
        if eid:
            cm._event_groups[m["condition_id"]] = eid
    return original


def _restore_event_groups(original: dict) -> None:
    import bot.detection.cross_market as cm
    cm._event_groups.clear()
    cm._event_groups.update(original)


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
        _make_market("0x1", "Will Alice win the 2026 election?", "tok_a", event_id="event_election_2026"),
        _make_market("0x2", "Will Bob win the 2026 election?", "tok_b", event_id="event_election_2026"),
        _make_market("0x3", "Will Carol win the 2026 election?", "tok_c", event_id="event_election_2026"),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.20)

    original = _patch_event_groups(markets)
    try:
        config = _make_config()
        opps = detect_cross_market_opportunities(markets, cache, config)

        assert len(opps) == 1
        assert opps[0].opportunity_type == "cross_market"
        assert opps[0].gross_spread == pytest.approx(0.25)  # 1.0 - 0.75
    finally:
        _restore_event_groups(original)


def test_unrelated_markets_not_grouped():
    """Markets without an event ID are never grouped — zero opportunities."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will bitcoin reach $200k by 2027?", "tok_a", ["crypto"]),
        _make_market("0x2", "Will Super Bowl be played in Las Vegas?", "tok_b", ["sports"]),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.30)

    # No event_id on either market → no grouping → 0 opportunities
    original = _patch_event_groups(markets)
    try:
        config = _make_config()
        opps = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(original)


def test_insufficient_depth_skips_group():
    """One market in the group has insufficient depth → whole group not returned."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win the 2026 election?", "tok_a", event_id="event_election_2026"),
        _make_market("0x2", "Will Bob win the 2026 election?", "tok_b", event_id="event_election_2026"),
    ]
    _populate_cache(cache, "tok_a", 0.30, depth=200.0)
    _populate_cache(cache, "tok_b", 0.25, depth=10.0)  # below $50 threshold

    original = _patch_event_groups(markets)
    try:
        config = _make_config()
        opps = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(original)


def test_no_arb_when_sum_at_or_above_one():
    """Sum(YES asks) >= 1.0 → no arbitrage."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win the 2026 election?", "tok_a", event_id="event_election_2026"),
        _make_market("0x2", "Will Bob win the 2026 election?", "tok_b", event_id="event_election_2026"),
    ]
    _populate_cache(cache, "tok_a", 0.55)  # sum = 1.05 > 1.0
    _populate_cache(cache, "tok_b", 0.50)

    original = _patch_event_groups(markets)
    try:
        config = _make_config()
        opps = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(original)


def test_single_market_group_not_returned():
    """A group of 1 market is not a cross-market opportunity."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [_make_market("0x1", "Will Alice win the election?", "tok_a", event_id="event_election_2026")]
    _populate_cache(cache, "tok_a", 0.30)

    original = _patch_event_groups(markets)
    try:
        config = _make_config()
        opps = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(original)


def test_event_grouping():
    """Markets sharing an event ID are grouped and produce a cross_market opportunity."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win?", "tok_a", event_id="event_001"),
        _make_market("0x2", "Will Bob win?", "tok_b", event_id="event_001"),
        _make_market("0x3", "Will Carol win?", "tok_c", event_id="event_001"),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.20)

    original = _patch_event_groups(markets)
    try:
        config = _make_config()
        opps = detect_cross_market_opportunities(markets, cache, config)

        assert len(opps) == 1
        assert opps[0].opportunity_type == "cross_market"
        assert opps[0].gross_spread == pytest.approx(0.25, abs=1e-4)  # 1.0 - 0.75
    finally:
        _restore_event_groups(original)


def test_event_markets_no_id_ignored():
    """Markets without an event ID are not grouped — zero opportunities."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win?", "tok_a"),   # no event_id
        _make_market("0x2", "Will Bob win?", "tok_b"),     # no event_id
        _make_market("0x3", "Will Carol win?", "tok_c"),   # no event_id
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.20)

    original = _patch_event_groups(markets)
    try:
        config = _make_config()
        opps = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(original)


def test_event_different_ids_not_grouped():
    """Markets with different event IDs form separate groups, not one merged group."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    # event_001: only 1 market -> below _MIN_GROUP_SIZE=2 -> no opp
    # event_002: 2 markets with total YES = 0.55 < 1.0 -> 1 opp
    markets = [
        _make_market("0x1", "Will Alice win?", "tok_a", event_id="event_001"),
        _make_market("0x2", "Will Bob win?", "tok_b", event_id="event_002"),
        _make_market("0x3", "Will Carol win?", "tok_c", event_id="event_002"),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.30)

    original = _patch_event_groups(markets)
    try:
        config = _make_config()
        opps = detect_cross_market_opportunities(markets, cache, config)

        # event_001 has only 1 market -> skipped
        # event_002 has 2 markets: total_yes = 0.55 < 1.0 -> 1 opportunity
        assert len(opps) == 1
        assert opps[0].opportunity_type == "cross_market"
    finally:
        _restore_event_groups(original)
