"""
Smoke tests for Polymarket CLOB and Alchemy Polygon RPC connectivity.

These tests require real environment variables (POLY_API_KEY, POLYGON_RPC_HTTP, etc.)
and must be run from the VPS with secrets.env populated.

All tests auto-skip when POLY_API_KEY is not set (local dev machines).

Run on VPS:
    pytest tests/test_connectivity.py -v -m smoke
"""
import asyncio
import statistics
import time

import httpx
import pytest
import websockets

from bot.client import CLOB_HOST, build_client

CLOB_TIME_URL = f"{CLOB_HOST}/time"
LATENCY_SAMPLES = 10
LATENCY_THRESHOLD_MS = 100

pytestmark = pytest.mark.smoke


@pytest.mark.smoke
def test_clob_http_reachable(real_config):
    """INFRA-01: Polymarket CLOB HTTP endpoint returns 200."""
    with httpx.Client() as client:
        resp = client.get(CLOB_TIME_URL, timeout=10)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@pytest.mark.smoke
def test_latency_under_100ms(real_config):
    """INFRA-01: Median HTTP round-trip latency to CLOB is under 100ms."""
    latencies: list[float] = []
    with httpx.Client(http2=True) as client:
        # Warm-up
        client.get(CLOB_TIME_URL, timeout=10)
        # Measure
        for _ in range(LATENCY_SAMPLES):
            t0 = time.perf_counter()
            resp = client.get(CLOB_TIME_URL, timeout=10)
            resp.raise_for_status()
            latencies.append((time.perf_counter() - t0) * 1000)

    median_ms = statistics.median(latencies)
    assert median_ms < LATENCY_THRESHOLD_MS, (
        f"Median latency {median_ms:.1f}ms exceeds {LATENCY_THRESHOLD_MS}ms threshold. "
        f"Ensure bot is running from Hetzner London VPS (uk-lon1), not local dev machine."
    )


@pytest.mark.smoke
def test_alchemy_http_rpc(real_config):
    """INFRA-02: Alchemy Polygon RPC HTTP endpoint responds to eth_blockNumber."""
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_blockNumber",
        "params": [],
        "id": 1,
    }
    with httpx.Client() as client:
        # Do not log real_config.polygon_rpc_http — it contains the Alchemy API key
        resp = client.post(real_config.polygon_rpc_http, json=payload, timeout=10)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert "result" in data, f"Expected 'result' in response, got: {data}"
    block_hex = data["result"]
    assert block_hex.startswith("0x"), f"Expected hex block number, got: {block_hex}"


@pytest.mark.smoke
async def test_alchemy_ws_rpc(real_config):
    """INFRA-02: Alchemy Polygon RPC WebSocket endpoint accepts a connection."""
    # Do not log real_config.polygon_rpc_ws — it contains the Alchemy API key
    async with websockets.connect(real_config.polygon_rpc_ws, open_timeout=10) as ws:
        assert ws.open, "WebSocket connection should be open"


@pytest.mark.smoke
def test_clob_client_wallet_address(real_config):
    """INFRA-05: ClobClient returns the correct wallet address for the private key."""
    from eth_account import Account

    # Derive expected address from private key
    account = Account.from_key(real_config.wallet_private_key)
    expected_address = account.address  # checksummed

    # Build client and get address via ClobClient
    client = build_client(real_config)
    actual_address = client.get_address()

    assert actual_address == expected_address, (
        f"ClobClient address {actual_address} does not match "
        f"derived address {expected_address}"
    )
