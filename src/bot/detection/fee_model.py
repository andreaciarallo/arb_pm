"""
Category-aware fee model for Polymarket arbitrage detection.

Polymarket fees are variable by market category (2026 structure, D-18):
  - Crypto:       1.8% per side taker fee (highest)
  - Politics/Finance/Tech: 1.0% per side
  - Sports:       0.75% per side
  - Geopolitics:  0% fee-free (strategic priority — D-12)

Category detection uses official market tags first, then keyword fallback
on the market question text.
"""
from bot.config import BotConfig

# Category keyword mapping for question-text fallback
_CRYPTO_KEYWORDS = frozenset([
    "bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol",
    "defi", "nft", "blockchain", "token", "coin", "altcoin",
])
_GEO_KEYWORDS = frozenset([
    "nato", "un ", "united nations", "war", "treaty", "sanction",
    "ceasefire", "invasion", "territory", "military", "troops",
])
_SPORTS_KEYWORDS = frozenset([
    "nfl", "nba", "mlb", "nhl", "mls", "fifa", "tennis", "golf",
    "olympics", "championship", "super bowl", "world cup", "match",
    "soccer", "football", "basketball", "baseball", "hockey",
])

# Canonical Polymarket tag names
_CRYPTO_TAGS = frozenset(["crypto", "cryptocurrency", "bitcoin", "ethereum", "defi"])
_GEO_TAGS = frozenset(["geopolitics", "international", "nato", "war", "conflict"])
_SPORTS_TAGS = frozenset(["sports", "nfl", "nba", "mlb", "soccer", "tennis", "golf"])
_POLITICS_TAGS = frozenset(["politics", "election", "government", "policy", "finance", "tech"])


def get_market_category(market: dict) -> str:
    """
    Detect market category from official tags, falling back to question keywords.

    Returns: 'crypto' | 'geopolitics' | 'sports' | 'politics' | 'other'
    """
    tags = {t.lower() for t in market.get("tags", [])}

    if tags & _CRYPTO_TAGS:
        return "crypto"
    if tags & _GEO_TAGS:
        return "geopolitics"
    if tags & _SPORTS_TAGS:
        return "sports"
    if tags & _POLITICS_TAGS:
        return "politics"

    # Keyword fallback on question text
    question = market.get("question", "").lower()
    if any(kw in question for kw in _CRYPTO_KEYWORDS):
        return "crypto"
    if any(kw in question for kw in _GEO_KEYWORDS):
        return "geopolitics"
    if any(kw in question for kw in _SPORTS_KEYWORDS):
        return "sports"

    return "other"


def get_taker_fee(category: str, config: BotConfig) -> float:
    """Return per-side taker fee rate for the given market category."""
    if category == "crypto":
        return config.fee_pct_crypto
    if category == "geopolitics":
        return config.fee_pct_geopolitics
    if category == "sports":
        return config.fee_pct_sports
    if category == "politics":
        return config.fee_pct_politics
    return config.fee_pct_default


def get_min_profit_threshold(category: str, config: BotConfig) -> float:
    """Return minimum net profit % threshold for the given market category."""
    if category == "crypto":
        return config.min_net_profit_pct_crypto
    if category == "geopolitics":
        return config.min_net_profit_pct_geopolitics
    # Sports, politics, and other use base threshold
    return config.min_net_profit_pct
