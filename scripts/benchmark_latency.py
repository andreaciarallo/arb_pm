"""
Latency benchmark script — run from the VPS to verify INFRA-01.

Usage (from VPS after docker compose up):
    docker compose exec bot python scripts/benchmark_latency.py

Or directly on VPS without Docker:
    pip install httpx[http2]
    python scripts/benchmark_latency.py

Expected output when sub-100ms requirement is met:
    Samples: 20
    Mean:    45.3 ms
    Median:  44.1 ms
    P95:     67.8 ms
    Min:     40.2 ms
    Max:     89.4 ms

    Median < 100ms: PASS
"""
import math
import statistics
import sys
import time

import httpx

CLOB_TIME_URL = "https://clob.polymarket.com/time"
SAMPLES = 20
THRESHOLD_MS = 100


def benchmark() -> bool:
    """
    Measure round-trip latency to Polymarket CLOB over 20 samples.

    Returns True if median latency is below THRESHOLD_MS.
    """
    latencies: list[float] = []

    with httpx.Client(http2=True) as client:
        # Warm-up request (not measured) — establishes HTTP/2 connection
        client.get(CLOB_TIME_URL, timeout=10)

        for _ in range(SAMPLES):
            t0 = time.perf_counter()
            resp = client.get(CLOB_TIME_URL, timeout=10)
            resp.raise_for_status()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)

    sorted_latencies = sorted(latencies)
    p95_index = max(0, int(math.ceil(SAMPLES * 0.95)) - 1)  # robust for any SAMPLES value

    print(f"Samples: {SAMPLES}")
    print(f"Mean:    {statistics.mean(latencies):.1f} ms")
    print(f"Median:  {statistics.median(latencies):.1f} ms")
    print(f"P95:     {sorted_latencies[p95_index]:.1f} ms")
    print(f"Min:     {min(latencies):.1f} ms")
    print(f"Max:     {max(latencies):.1f} ms")

    passing = statistics.median(latencies) < THRESHOLD_MS
    print(f"\nMedian < {THRESHOLD_MS}ms: {'PASS' if passing else 'FAIL'}")
    return passing


if __name__ == "__main__":
    success = benchmark()
    sys.exit(0 if success else 1)
