"""
Health check for Docker HEALTHCHECK CMD.

Verifies Polymarket CLOB API is reachable. Called every 30s by Docker.
Exit code: 0 = healthy, 1 = unhealthy.

Used in Dockerfile:
    HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \\
        CMD python -m bot.health || exit 1
"""
import sys
import httpx
from loguru import logger

CLOB_TIME_URL = "https://clob.polymarket.com/time"
TIMEOUT_SECONDS = 8


def check_health() -> bool:
    """
    Check CLOB API connectivity.

    Returns True if reachable within timeout, False otherwise.
    Does not log raw RPC URLs (Pitfall 5 avoidance).
    """
    try:
        resp = httpx.get(CLOB_TIME_URL, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        logger.info("Health check OK — CLOB reachable, server time: {}", resp.json())
        return True
    except httpx.HTTPError as exc:
        logger.error("Health check FAILED — CLOB unreachable: {}", exc)
        return False


if __name__ == "__main__":
    healthy = check_health()
    sys.exit(0 if healthy else 1)
