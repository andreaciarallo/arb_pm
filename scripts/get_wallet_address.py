#!/usr/bin/env python3
"""Print the wallet address for funding (reads from secrets.env)."""

import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

# Load secrets.env
env_path = os.path.join(os.path.dirname(__file__), "..", "secrets.env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Try standard location
    load_dotenv()

private_key = os.environ.get("WALLET_PRIVATE_KEY")

if not private_key:
    print("ERROR: WALLET_PRIVATE_KEY not found in secrets.env")
    print("Make sure the file exists and contains the key.")
    sys.exit(1)

try:
    from eth_account import Account
    account = Account.from_key(private_key)
    print(f"Wallet address: {account.address}")
    print(f"Network: Polygon (send USDC on Polygon only)")
except Exception as e:
    print(f"ERROR: Failed to derive address: {e}")
    sys.exit(1)
