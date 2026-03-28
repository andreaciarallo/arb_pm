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


def _make_market(tags: list[str] = None, question: str = "Will X happen?") -> dict:
    return {
        "condition_id": "0xabc",
        "question": question,
        "tags": tags or [],
        "tokens": [{"token_id": "y", "outcome": "Yes"}, {"token_id": "n", "outcome": "No"}],
        "token_ids": ["y", "n"],
    }


def test_crypto_category_from_tags():
    """Tags=['crypto'] → category='crypto'."""
    from bot.detection.fee_model import get_market_category
    market = _make_market(tags=["crypto"])
    assert get_market_category(market) == "crypto"


def test_crypto_category_fee():
    """Crypto category → 1.8% per-side fee, 2.0% min profit threshold."""
    from bot.detection.fee_model import get_taker_fee, get_min_profit_threshold
    config = _make_config()
    assert get_taker_fee("crypto", config) == pytest.approx(0.018)
    assert get_min_profit_threshold("crypto", config) == pytest.approx(0.020)


def test_geopolitics_from_tags():
    """Tags=['geopolitics'] → category='geopolitics'."""
    from bot.detection.fee_model import get_market_category
    market = _make_market(tags=["geopolitics"])
    assert get_market_category(market) == "geopolitics"


def test_geopolitics_category_fee():
    """Geopolitics → 0% fee, 0.75% min profit threshold."""
    from bot.detection.fee_model import get_taker_fee, get_min_profit_threshold
    config = _make_config()
    assert get_taker_fee("geopolitics", config) == pytest.approx(0.0)
    assert get_min_profit_threshold("geopolitics", config) == pytest.approx(0.0075)


def test_geopolitics_from_question_keyword():
    """No tags, question contains 'nato' → geopolitics."""
    from bot.detection.fee_model import get_market_category
    market = _make_market(tags=[], question="Will NATO expand by 2027?")
    assert get_market_category(market) == "geopolitics"


def test_sports_from_tags():
    """Tags=['sports'] → category='sports', base min profit (1.5%)."""
    from bot.detection.fee_model import get_market_category, get_taker_fee, get_min_profit_threshold
    config = _make_config()
    market = _make_market(tags=["sports"])
    cat = get_market_category(market)
    assert cat == "sports"
    assert get_taker_fee(cat, config) == pytest.approx(0.0075)
    assert get_min_profit_threshold(cat, config) == pytest.approx(0.015)  # uses base


def test_unknown_category_uses_defaults():
    """Unknown tags + ambiguous question → 'other', default fee=1.0%."""
    from bot.detection.fee_model import get_market_category, get_taker_fee
    config = _make_config()
    market = _make_market(tags=["entertainment"], question="Will movie X gross $1B?")
    cat = get_market_category(market)
    assert cat == "other"
    assert get_taker_fee(cat, config) == pytest.approx(0.010)


def test_bitcoin_keyword_maps_to_crypto():
    """Question containing 'bitcoin' with no tags → crypto."""
    from bot.detection.fee_model import get_market_category
    market = _make_market(tags=[], question="Will bitcoin reach $200k?")
    assert get_market_category(market) == "crypto"
