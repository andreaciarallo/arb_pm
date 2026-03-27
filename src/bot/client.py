"""
Authenticated ClobClient factory.

Builds a fully authenticated L2 ClobClient for order placement.
Uses signature_type=0 (EOA) — directly-controlled private key.
Do NOT use signature_type=1 (email/Magic wallet only).
"""
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import POLYGON

from .config import BotConfig

CLOB_HOST = "https://clob.polymarket.com"


def build_client(config: BotConfig) -> ClobClient:
    """
    Build a fully authenticated L2 ClobClient.

    signature_type=0: EOA wallet (directly-controlled private key).
    funder= is not set because the signing key and funded address are identical.
    """
    client = ClobClient(
        CLOB_HOST,
        key=config.wallet_private_key,
        chain_id=POLYGON,       # 137 (Polygon mainnet)
        signature_type=0,        # EOA — do not change to 1 (Magic/email wallet)
    )
    creds = ApiCreds(
        api_key=config.poly_api_key,
        api_secret=config.poly_api_secret,
        api_passphrase=config.poly_api_passphrase,
    )
    client.set_api_creds(creds)
    return client
