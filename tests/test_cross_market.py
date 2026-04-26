import time
import pytest

pytestmark = pytest.mark.unit

# Field name used by _group_by_event() to look up event membership.
# PATH B (Gamma API): _event_groups maps condition_id -> EventInfo at module level.
# In tests we bypass the Gamma API by injecting the event_id directly into the
# market dict via the "_test_event_id" helper key, then patching _event_groups.
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
                 tags: list[str] = None, event_id: str = None,
                 neg_risk: bool = False) -> dict:
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
    if neg_risk:
        m["_test_neg_risk"] = True
    return m


def _patch_event_groups(markets: list[dict]) -> dict:
    """
    Build a condition_id -> EventInfo mapping from markets that have
    _test_event_id set, and inject it into the module-level _event_groups dict.
    Returns the original _event_groups so callers can restore it.
    """
    import bot.detection.cross_market as cm
    original = dict(cm._event_groups)
    cm._event_groups.clear()
    # Count markets per event for market_count
    event_counts: dict[str, int] = {}
    for m in markets:
        eid = m.get("_test_event_id")
        if eid:
            event_counts[eid] = event_counts.get(eid, 0) + 1
    for m in markets:
        eid = m.get("_test_event_id")
        if eid:
            cm._event_groups[m["condition_id"]] = cm.EventInfo(
                event_id=eid,
                neg_risk=m.get("_test_neg_risk", False),
                market_count=event_counts.get(eid, 1),
            )
    return original


def _restore_event_groups(original: dict) -> None:
    import bot.detection.cross_market as cm
    cm._event_groups.clear()
    cm._event_groups.update(original)


def _patch_valid_groups(markets: list[dict]) -> set:
    """
    Populate group_validator._valid_groups with all event IDs from test markets.
    Returns original _valid_groups for restoration.
    """
    import bot.detection.group_validator as gv
    original = set(gv._valid_groups)
    gv._valid_groups.clear()
    event_ids = {m.get("_test_event_id") for m in markets if m.get("_test_event_id")}
    gv._valid_groups.update(event_ids)
    return original


def _restore_valid_groups(original: set) -> None:
    import bot.detection.group_validator as gv
    gv._valid_groups.clear()
    gv._valid_groups.update(original)


def _populate_cache(cache, token_id: str, ask: float, depth: float = 200.0):
    from bot.scanner.price_cache import MarketPrice
    cache.update(token_id, MarketPrice(
        token_id=token_id, yes_ask=ask, no_ask=0.0,
        yes_bid=ask - 0.02, no_bid=0.0,
        yes_depth=depth, no_depth=0.0,
        timestamp=time.time(), source="websocket",
    ))


def test_exclusivity_constraint_detected():
    """3 mutually exclusive markets with sum(YES) < 1.0 -> cross_market opportunity."""
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

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)

        assert len(opps) == 1
        assert opps[0].opportunity_type == "cross_market"
        assert opps[0].gross_spread == pytest.approx(0.25)  # 1.0 - 0.75
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_unrelated_markets_not_grouped():
    """Markets without an event ID are never grouped -- zero opportunities."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will bitcoin reach $200k by 2027?", "tok_a", ["crypto"]),
        _make_market("0x2", "Will Super Bowl be played in Las Vegas?", "tok_b", ["sports"]),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.30)

    # No event_id on either market -> no grouping -> 0 opportunities
    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_insufficient_depth_skips_group():
    """One market in the group has insufficient depth -> whole group not returned."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win the 2026 election?", "tok_a", event_id="event_election_2026"),
        _make_market("0x2", "Will Bob win the 2026 election?", "tok_b", event_id="event_election_2026"),
    ]
    _populate_cache(cache, "tok_a", 0.30, depth=200.0)
    _populate_cache(cache, "tok_b", 0.25, depth=10.0)  # below $50 threshold

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_no_arb_when_sum_at_or_above_one():
    """Sum(YES asks) >= 1.0 -> no arbitrage."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win the 2026 election?", "tok_a", event_id="event_election_2026"),
        _make_market("0x2", "Will Bob win the 2026 election?", "tok_b", event_id="event_election_2026"),
    ]
    _populate_cache(cache, "tok_a", 0.55)  # sum = 1.05 > 1.0
    _populate_cache(cache, "tok_b", 0.50)

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_single_market_group_not_returned():
    """A group of 1 market is not a cross-market opportunity."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [_make_market("0x1", "Will Alice win the election?", "tok_a", event_id="event_election_2026")]
    _populate_cache(cache, "tok_a", 0.30)

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


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

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)

        assert len(opps) == 1
        assert opps[0].opportunity_type == "cross_market"
        assert opps[0].gross_spread == pytest.approx(0.25, abs=1e-4)  # 1.0 - 0.75
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_event_markets_no_id_ignored():
    """Markets without an event ID are not grouped -- zero opportunities."""
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

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


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

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)

        # event_001 has only 1 market -> skipped
        # event_002 has 2 markets: total_yes = 0.55 < 1.0 -> 1 opportunity
        assert len(opps) == 1
        assert opps[0].opportunity_type == "cross_market"
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_dead_leg_rejects_group():
    """DETECT-03: one leg has ask=0.003 (<= 0.005 floor) -> group rejected."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win?", "tok_a", event_id="event_dead"),
        _make_market("0x2", "Will Bob win?", "tok_b", event_id="event_dead"),
        _make_market("0x3", "Will Carol win?", "tok_c", event_id="event_dead"),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.003)  # dead leg <= 0.005

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
        assert diag.leg_floor_rejects == 1
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_total_yes_floor_rejects_degenerate():
    """DETECT-04: total_yes=0.09 (< 0.10 floor) -> group rejected."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win?", "tok_a", event_id="event_degen"),
        _make_market("0x2", "Will Bob win?", "tok_b", event_id="event_degen"),
        _make_market("0x3", "Will Carol win?", "tok_c", event_id="event_degen"),
    ]
    _populate_cache(cache, "tok_a", 0.03)
    _populate_cache(cache, "tok_b", 0.03)
    _populate_cache(cache, "tok_c", 0.03)  # total_yes = 0.09 < 0.10

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)
        assert len(opps) == 0
        assert diag.total_yes_rejects == 1
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_cross_dedup_suppresses_repeat():
    """DETECT-05: same group detected twice within window -> second suppressed."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities
    from bot.detection.filters import DedupTracker

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win?", "tok_a", event_id="event_dedup"),
        _make_market("0x2", "Will Bob win?", "tok_b", event_id="event_dedup"),
        _make_market("0x3", "Will Carol win?", "tok_c", event_id="event_dedup"),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.20)

    dedup = DedupTracker(window_seconds=300)

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)
    try:
        config = _make_config()

        # First call: opportunity detected
        opps1, diag1 = detect_cross_market_opportunities(markets, cache, config, dedup=dedup)
        assert len(opps1) == 1
        assert diag1.dedup_suppressed == 0

        # Second call: same group -> suppressed
        opps2, diag2 = detect_cross_market_opportunities(markets, cache, config, dedup=dedup)
        assert len(opps2) == 0
        assert diag2.dedup_suppressed == 1
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


# ---------------------------------------------------------------------------
# GV gate: group validator integration tests
# ---------------------------------------------------------------------------

def test_gv_valid_group_passes_through():
    """Groups in valid_groups pass through the GV gate."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win?", "tok_a", event_id="event_valid"),
        _make_market("0x2", "Will Bob win?", "tok_b", event_id="event_valid"),
        _make_market("0x3", "Will Carol win?", "tok_c", event_id="event_valid"),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.20)

    orig_eg = _patch_event_groups(markets)
    orig_vg = _patch_valid_groups(markets)  # event_valid is in valid_groups
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)

        assert len(opps) == 1
        assert opps[0].opportunity_type == "cross_market"
        assert diag.gv_rejects == 0
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_gv_invalid_group_rejected():
    """Groups NOT in valid_groups are rejected with gv_rejects counter."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities
    import bot.detection.group_validator as gv

    cache = PriceCache()
    markets = [
        _make_market("0x1", "Will Alice win?", "tok_a", event_id="event_invalid"),
        _make_market("0x2", "Will Bob win?", "tok_b", event_id="event_invalid"),
        _make_market("0x3", "Will Carol win?", "tok_c", event_id="event_invalid"),
    ]
    _populate_cache(cache, "tok_a", 0.30)
    _populate_cache(cache, "tok_b", 0.25)
    _populate_cache(cache, "tok_c", 0.20)

    orig_eg = _patch_event_groups(markets)
    # Explicitly set valid_groups to NOT include event_invalid
    orig_vg = set(gv._valid_groups)
    gv._valid_groups.clear()
    gv._valid_groups.add("some_other_event")  # different event, not event_invalid
    try:
        config = _make_config()
        opps, diag = detect_cross_market_opportunities(markets, cache, config)

        assert len(opps) == 0
        assert diag.gv_rejects == 1
    finally:
        _restore_event_groups(orig_eg)
        _restore_valid_groups(orig_vg)


def test_gv_rejects_counter_in_diagnostics():
    """FilterDiagnostics gv_rejects starts at 0 and increments on rejection."""
    from bot.scanner.price_cache import PriceCache
    from bot.detection.cross_market import detect_cross_market_opportunities

    cache = PriceCache()
    # No markets -> no groups -> gv_rejects stays 0
    config = _make_config()
    opps, diag = detect_cross_market_opportunities([], cache, config)
    assert diag.gv_rejects == 0
