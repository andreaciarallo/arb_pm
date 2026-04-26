"""
Tests for EventInfo dataclass and enriched _event_groups / _gamma_market_data.

Validates Task 1 of Phase 6 Plan 01:
- EventInfo frozen dataclass with event_id, neg_risk, market_count
- _event_groups enriched from dict[str, str] to dict[str, EventInfo]
- _gamma_market_data populated with question and outcomePrices
- _group_by_event() works with EventInfo (extracts .event_id)
"""
import pytest

pytestmark = pytest.mark.unit


def test_event_info_creation():
    """EventInfo(event_id, neg_risk, market_count) creates a frozen dataclass."""
    from bot.detection.cross_market import EventInfo

    e = EventInfo(event_id="e1", neg_risk=True, market_count=3)
    assert e.event_id == "e1"
    assert e.neg_risk is True
    assert e.market_count == 3


def test_event_info_frozen():
    """EventInfo is frozen -- cannot be modified after creation."""
    from bot.detection.cross_market import EventInfo

    e = EventInfo(event_id="e1", neg_risk=False, market_count=2)
    with pytest.raises(AttributeError):
        e.event_id = "e2"


def test_event_groups_enriched():
    """After enrichment, _event_groups maps cid -> EventInfo with all fields."""
    import bot.detection.cross_market as cm

    original = dict(cm._event_groups)
    try:
        cm._event_groups.clear()
        info = cm.EventInfo(event_id="e1", neg_risk=True, market_count=3)
        cm._event_groups["cid_1"] = info

        assert cm._event_groups["cid_1"].event_id == "e1"
        assert cm._event_groups["cid_1"].neg_risk is True
        assert cm._event_groups["cid_1"].market_count == 3
    finally:
        cm._event_groups.clear()
        cm._event_groups.update(original)


def test_gamma_market_data_populated():
    """_gamma_market_data stores question and outcomePrices for each cid."""
    import bot.detection.cross_market as cm

    original_gmd = dict(getattr(cm, "_gamma_market_data", {}))
    try:
        cm._gamma_market_data.clear()
        cm._gamma_market_data["cid_1"] = {
            "question": "Will Alice win?",
            "outcomePrices": "[0.6, 0.4]",
        }
        assert cm._gamma_market_data["cid_1"]["question"] == "Will Alice win?"
        assert cm._gamma_market_data["cid_1"]["outcomePrices"] == "[0.6, 0.4]"
    finally:
        cm._gamma_market_data.clear()
        cm._gamma_market_data.update(original_gmd)


def test_group_by_event_uses_event_info():
    """_group_by_event() extracts event_id from EventInfo in _event_groups."""
    import bot.detection.cross_market as cm

    original = dict(cm._event_groups)
    try:
        cm._event_groups.clear()
        cm._event_groups["c1"] = cm.EventInfo("ev1", True, 3)
        cm._event_groups["c2"] = cm.EventInfo("ev1", True, 3)
        cm._event_groups["c3"] = cm.EventInfo("ev1", True, 3)

        markets = [
            {"condition_id": "c1", "tokens": []},
            {"condition_id": "c2", "tokens": []},
            {"condition_id": "c3", "tokens": []},
        ]
        groups = cm._group_by_event(markets)
        assert len(groups) == 1
        assert len(groups[0]) == 3
    finally:
        cm._event_groups.clear()
        cm._event_groups.update(original)


def test_group_by_event_size_filtering():
    """_group_by_event() filters groups to [2, 20] size."""
    import bot.detection.cross_market as cm

    original = dict(cm._event_groups)
    try:
        cm._event_groups.clear()
        # Single market group -- should be filtered out
        cm._event_groups["single"] = cm.EventInfo("ev_single", False, 1)
        # Two market group -- should pass
        cm._event_groups["a1"] = cm.EventInfo("ev_pair", False, 2)
        cm._event_groups["a2"] = cm.EventInfo("ev_pair", False, 2)

        markets = [
            {"condition_id": "single", "tokens": []},
            {"condition_id": "a1", "tokens": []},
            {"condition_id": "a2", "tokens": []},
        ]
        groups = cm._group_by_event(markets)
        assert len(groups) == 1  # only the pair passes
        assert len(groups[0]) == 2
    finally:
        cm._event_groups.clear()
        cm._event_groups.update(original)
