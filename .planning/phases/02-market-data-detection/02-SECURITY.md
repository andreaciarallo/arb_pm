# Phase 02 Security Audit — Market Data Detection

**Phase:** 02 — market-data-detection
**ASVS Level:** 1
**Audited:** 2026-04-17
**Auditor:** gsd-security-auditor (Claude Sonnet 4.6)
**block_on:** critical

---

## Summary

**Threats Closed:** 16/17
**Threats Open:** 1/17
**Unregistered Flags:** 0

One open threat (T-09-NaN) is a non-critical data integrity gap: `float("nan")` and `float("inf")` pass Python's `float()` conversion silently and are not blocked at the ingestion boundary. A compromised or malfunctioning exchange server could inject these values. Impact in Phase 2 is limited to producing `nan` net_spread values that would be logged to SQLite; no capital is at risk in dry-run mode. This must be resolved before Phase 3 live execution.

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-01 | Data Integrity — WS malformed message | mitigate | CLOSED | ws_client.py:49 — `except json.JSONDecodeError` in `_handle_message` |
| T-02 | Data Integrity — WS ask sort order | mitigate | CLOSED | ws_client.py:70 — `min(sells, key=lambda s: float(s["price"]))` |
| T-03 | Data Integrity — HTTP ask sort order | mitigate | CLOSED | normalizer.py:61-62 — `sorted(asks, key=lambda a: _price_size(a)[0])` ascending |
| T-04 | Data Integrity — malformed HTTP price strings | mitigate | CLOSED | normalizer.py:63-65 — `except (KeyError, ValueError, TypeError, IndexError)` returns None |
| T-05 | Data Integrity — missing asset_id passes through | mitigate | CLOSED | normalizer.py:47-49 — `if not token_id: return None` with warning log |
| T-06 | Availability — 429 rate limit stalls scan | mitigate | CLOSED | market_filter.py:37-44 — exponential backoff 5s→10s→20s→40s→60s cap, 5 retries |
| T-07 | Availability — WS disconnect stops price updates | mitigate | CLOSED | ws_client.py:126-138 — `ConnectionClosed` caught, backoff 1→2→4→8→30s cap, loop forever |
| T-08 | Logic — resolved market flagged as arbitrage | mitigate | CLOSED | yes_no_arb.py:84 — `if yes_ask >= 1.0 or no_ask >= 1.0: continue` |
| T-09 | Logic — NaN/Inf propagation in float arithmetic | mitigate | OPEN | `float("nan")` and `float("inf")` are not rejected by `float()` and will pass the try/except guards in ws_client.py and normalizer.py. No `math.isfinite()` check exists at any ingestion point. NaN prices would enter PriceCache and produce NaN net_spread values in detection output. |
| T-10 | Logic — trades on illiquid markets (depth gate) | mitigate | CLOSED | yes_no_arb.py:93 — `if depth < config.min_order_book_depth: continue`; cross_market.py:139 — same gate |
| T-11 | Logic — bid-side prices used for detection | mitigate | CLOSED | ws_client.py:7 — "Prices are always parsed from 'sells' (ask side) per D-05"; ws_client.py:70 uses `sells`; normalizer.py uses `asks` array |
| T-12 | Code Execution — eval() on external data | mitigate | CLOSED | No `eval()` found across all Phase 2 src files; external data enters only via `json.loads()` and `float()` |
| T-13 | Availability — SQLite writes block async loop | mitigate | CLOSED | writer.py:34 — `asyncio.Queue(maxsize=1000)` + background `_worker` coroutine; scan loop calls `enqueue()` which is synchronous non-blocking |
| T-14 | Availability — SQLite queue DoS via flood | mitigate | CLOSED | writer.py:51-56 — `put_nowait()` catches `asyncio.QueueFull`, logs warning, drops opportunity; scan loop never blocks |
| T-15 | Secrets — RPC URL with embedded API key logged | mitigate | CLOSED | config.py:40-41 — inline comments "Contains Alchemy API key — never log raw value"; no log statements reference `polygon_rpc_http` or `polygon_rpc_ws` in Phase 2 modules |
| T-16 | Availability — one HTTP fetch error stops all polling | mitigate | CLOSED | http_poller.py:83-88 — per-token `except Exception` block continues to next token; 404 marks token dead, other errors log warning |
| T-17 | Logic — O(n²) blowup from large cross-market groups | mitigate | CLOSED | cross_market.py:29 — `_MAX_GROUP_SIZE = 20`; dry_run.py:100 — `priced_markets[:100]` scan cap |

---

## Open Threats

### T-09 — NaN/Inf Propagation in Float Arithmetic

**Category:** Data Integrity / Logic
**Severity:** Medium (Phase 2 dry-run: no capital at risk; Phase 3: trade trigger risk)

**Gap Description:**

Python's `float()` does not raise `ValueError` for the strings `"nan"`, `"inf"`, `"-inf"`, `"infinity"`. These are valid IEEE 754 representations accepted silently:

```python
float("nan")   # → nan  (no exception)
float("inf")   # → inf  (no exception)
```

Both ingestion paths lack explicit `math.isfinite()` checks:

- `ws_client.py:70-72` — `float(best_sell["price"])` inside `try/except (KeyError, ValueError, IndexError)`. A `"nan"` price string passes this block cleanly and enters PriceCache with `yes_ask=nan`.
- `normalizer.py:26` — `_price_size()` calls `float(entry["price"])`. Same exposure via HTTP order book API.

**Impact in Phase 2:** A NaN ask price stored in PriceCache propagates to `gross_spread = 1.0 - nan - nan = nan`, `net_spread = nan`. The threshold gate `net_spread < threshold` evaluates to `False` for NaN (IEEE 754 comparison), meaning a NaN opportunity **passes the threshold gate** and is enqueued to SQLite. The row insertion succeeds with `net_spread = nan` stored as a float. No crash, but the log and DB contain corrupted entries.

**Impact in Phase 3:** If execution logic inherits this path without an isfinite guard, a NaN net_spread could trigger position sizing on an invalid opportunity.

**Mitigation Required Before Phase 3:** Add `math.isfinite(price)` validation at the point where `float()` converts price strings, in both `ws_client.py._handle_message()` and `normalizer.py._price_size()`. Return early / return None on non-finite values.

**Suggested check pattern:**
```python
import math
price = float(raw_str)
if not math.isfinite(price):
    logger.warning(f"Non-finite price rejected: {raw_str!r}")
    return  # or return None
```

---

## Unregistered Flags

None. No `## Threat Flags` sections were present in any Phase 02 SUMMARY files.

---

## Accepted Risks Log

*(No threats were accepted in Phase 02.)*

---

## Verification Methodology

Each `mitigate` threat was verified by pattern search against the cited implementation files. All searches were performed read-only on:

- `src/bot/scanner/ws_client.py`
- `src/bot/scanner/normalizer.py`
- `src/bot/scanner/market_filter.py`
- `src/bot/scanner/http_poller.py`
- `src/bot/scanner/price_cache.py`
- `src/bot/detection/yes_no_arb.py`
- `src/bot/detection/cross_market.py`
- `src/bot/detection/fee_model.py`
- `src/bot/detection/opportunity.py`
- `src/bot/dry_run.py`
- `src/bot/storage/writer.py`
- `src/bot/storage/schema.py`

Implementation files were not modified.

---

## Next Steps

1. **Before Phase 3:** Resolve T-09 — add `math.isfinite()` guards in `ws_client.py._handle_message()` and `normalizer.py._price_size()`. Re-run `/gsd-secure-phase` after fix.
2. Phase 3 security audit should extend threat coverage to include: order placement authentication, FAK order retry logic, Kelly sizing arithmetic overflow, and kill-switch race conditions.
