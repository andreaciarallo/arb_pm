"""
Shared pytest fixtures for the Polymarket arbitrage bot test suite.

Fixtures that require real secrets are marked with pytest.mark.smoke and will
skip automatically if the required env vars are not set (VPS environment only).
"""
import os
import pytest
from unittest.mock import patch


TEST_PRIVATE_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)


def _test_env(overrides: dict | None = None) -> dict:
    """Return a complete test environment dict with fake-but-valid values."""
    env = {
        "POLY_API_KEY": "test_api_key",
        "POLY_API_SECRET": "test_api_secret",
        "POLY_API_PASSPHRASE": "test_passphrase",
        "WALLET_PRIVATE_KEY": TEST_PRIVATE_KEY,
        "POLYGON_RPC_HTTP": "https://polygon-mainnet.g.alchemy.com/v2/test",
        "POLYGON_RPC_WS": "wss://polygon-mainnet.g.alchemy.com/v2/test",
    }
    if overrides:
        env.update(overrides)
    return env


@pytest.fixture
def bot_config():
    """BotConfig loaded from fake-but-valid test environment."""
    from bot.config import load_config
    with patch.dict(os.environ, _test_env(), clear=True):
        yield load_config()


@pytest.fixture
def real_config():
    """
    BotConfig loaded from real environment variables.

    Only available when POLY_API_KEY is set (VPS or CI with secrets).
    Skip tests that use this fixture when running locally without secrets.
    """
    if not os.environ.get("POLY_API_KEY"):
        pytest.skip("Real secrets not available (set POLY_API_KEY to run smoke tests)")
    from bot.config import load_config
    return load_config()
