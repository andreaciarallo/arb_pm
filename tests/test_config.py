import os
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.unit


def _full_env():
    return {
        "POLY_API_KEY": "test_api_key",
        "POLY_API_SECRET": "test_api_secret",
        "POLY_API_PASSPHRASE": "test_passphrase",
        # Known valid private key for testing (not a real funded wallet)
        "WALLET_PRIVATE_KEY": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        "POLYGON_RPC_HTTP": "https://polygon-mainnet.g.alchemy.com/v2/test_key",
        "POLYGON_RPC_WS": "wss://polygon-mainnet.g.alchemy.com/v2/test_key",
    }


def test_missing_secret_raises():
    """D-06: load_config() must raise immediately on any missing required secret."""
    env = _full_env()
    del env["POLY_API_KEY"]
    with patch.dict(os.environ, env, clear=True):
        from bot.config import load_config
        with pytest.raises(RuntimeError) as exc_info:
            load_config()
    assert "POLY_API_KEY" in str(exc_info.value)


def test_missing_passphrase_raises():
    """Pitfall 1: Three-part auth — POLY_API_PASSPHRASE is required."""
    env = _full_env()
    del env["POLY_API_PASSPHRASE"]
    with patch.dict(os.environ, env, clear=True):
        from bot.config import load_config
        with pytest.raises(RuntimeError) as exc_info:
            load_config()
    assert "POLY_API_PASSPHRASE" in str(exc_info.value)


def test_config_loads():
    """All 6 required secrets present — config loads successfully."""
    with patch.dict(os.environ, _full_env(), clear=True):
        from bot.config import load_config
        config = load_config()
    assert config.poly_api_key == "test_api_key"
    assert config.poly_api_secret == "test_api_secret"
    assert config.poly_api_passphrase == "test_passphrase"
    assert config.polygon_rpc_http == "https://polygon-mainnet.g.alchemy.com/v2/test_key"
    assert config.polygon_rpc_ws == "wss://polygon-mainnet.g.alchemy.com/v2/test_key"


def test_optional_secrets_default_none():
    """Optional Phase 4 secrets are None when absent — bot still starts."""
    with patch.dict(os.environ, _full_env(), clear=True):
        from bot.config import load_config
        config = load_config()
    assert config.telegram_bot_token is None
    assert config.telegram_chat_id is None  # D-04: replaces discord_webhook_url


def test_wallet_address_derivation():
    """INFRA-05: EOA wallet address is derivable from WALLET_PRIVATE_KEY."""
    from eth_account import Account
    private_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    account = Account.from_key(private_key)
    address = account.address
    assert address.startswith("0x")
    assert len(address) == 42
    # Known address for this test key (Hardhat account 0)
    assert address == "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def test_build_client_returns_instance():
    """build_client() returns a ClobClient instance configured for EOA signing."""
    from bot.config import load_config
    from bot.client import build_client
    from py_clob_client.client import ClobClient
    with patch.dict(os.environ, _full_env(), clear=True):
        config = load_config()
    client = build_client(config)
    assert isinstance(client, ClobClient)
