"""
One-time script to generate Polymarket CLOB API credentials from a wallet private key.

Run once before deploying the bot. Output the three credential values into secrets.env.

Usage:
    WALLET_PRIVATE_KEY=0x... python scripts/create_api_key.py

Output (copy into secrets.env):
    POLY_API_KEY=...
    POLY_API_SECRET=...
    POLY_API_PASSPHRASE=...

Note: create_or_derive_api_creds() is deterministic — running it again with the same
private key produces the same credentials. Safe to re-run if credentials are lost.
"""
import os
import sys

from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

CLOB_HOST = "https://clob.polymarket.com"


def main():
    wallet_key = os.environ.get("WALLET_PRIVATE_KEY")
    if not wallet_key:
        print("ERROR: WALLET_PRIVATE_KEY environment variable is not set.", file=sys.stderr)
        print("Usage: WALLET_PRIVATE_KEY=0x... python scripts/create_api_key.py", file=sys.stderr)
        sys.exit(1)

    print("Connecting to Polymarket CLOB to derive API credentials...")
    client = ClobClient(
        CLOB_HOST,
        key=wallet_key,
        chain_id=POLYGON,
        signature_type=0,  # EOA
    )
    creds = client.create_or_derive_api_creds()

    print("\nAdd these to secrets.env on the VPS:")
    print(f"POLY_API_KEY={creds.api_key}")
    print(f"POLY_API_SECRET={creds.api_secret}")
    print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")


if __name__ == "__main__":
    main()
