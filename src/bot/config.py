"""
Fail-fast secret validation and BotConfig dataclass.

All required secrets are validated at startup. Missing secrets raise RuntimeError
immediately — no silent fallbacks (D-06).

Alchemy RPC URLs contain the API key embedded in the URL path. Never log the raw
POLYGON_RPC_HTTP or POLYGON_RPC_WS values — log only "configured" (boolean presence).
"""
import os
from dataclasses import dataclass


REQUIRED_SECRETS = [
    "POLY_API_KEY",
    "POLY_API_SECRET",
    "POLY_API_PASSPHRASE",   # Three-part auth — not two
    "WALLET_PRIVATE_KEY",
    "POLYGON_RPC_HTTP",
    "POLYGON_RPC_WS",
]


@dataclass(frozen=True)
class BotConfig:
    # Phase 1: Required secrets
    poly_api_key: str
    poly_api_secret: str
    poly_api_passphrase: str
    wallet_private_key: str
    polygon_rpc_http: str    # Contains Alchemy API key — never log raw value
    polygon_rpc_ws: str      # Contains Alchemy API key — never log raw value

    # Phase 1: Optional notification channels
    telegram_bot_token: str | None = None
    discord_webhook_url: str | None = None

    # Phase 2: Market scanning parameters (D-08, D-09, D-11, D-19)
    min_market_volume: float = 1000.0         # USD 24h volume filter (D-19)
    scan_interval_seconds: int = 30            # Scan cycle frequency (D-08)
    ws_stale_threshold_seconds: int = 5        # WebSocket staleness cutoff (D-09)
    min_order_book_depth: float = 50.0         # USD minimum depth per opportunity (D-11)

    # Phase 2: Profit thresholds by category (D-12)
    min_net_profit_pct: float = 0.015          # 1.5% base
    min_net_profit_pct_crypto: float = 0.020   # 2.0% (crypto fees peak at 1.8%)
    min_net_profit_pct_geopolitics: float = 0.0075  # 0.75% (fee-free markets)

    # Phase 2: Taker fee rates by category, per side (D-18)
    fee_pct_crypto: float = 0.018              # 1.8% per side
    fee_pct_politics: float = 0.010            # 1.0% per side (Politics/Finance/Tech)
    fee_pct_sports: float = 0.0075             # 0.75% per side
    fee_pct_geopolitics: float = 0.0           # 0% fee-free
    fee_pct_default: float = 0.010             # 1.0% fallback for unknown categories


def load_config() -> BotConfig:
    """
    Load and validate all required environment variables.

    Raises RuntimeError listing all missing variables if any required secret
    is absent or empty (D-06: fail fast, no silent fallbacks).
    """
    missing = [k for k in REQUIRED_SECRETS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {missing}. "
            f"Copy secrets.env.example to secrets.env and fill in all values."
        )
    return BotConfig(
        poly_api_key=os.environ["POLY_API_KEY"],
        poly_api_secret=os.environ["POLY_API_SECRET"],
        poly_api_passphrase=os.environ["POLY_API_PASSPHRASE"],
        wallet_private_key=os.environ["WALLET_PRIVATE_KEY"],
        polygon_rpc_http=os.environ["POLYGON_RPC_HTTP"],
        polygon_rpc_ws=os.environ["POLYGON_RPC_WS"],
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL"),
    )
