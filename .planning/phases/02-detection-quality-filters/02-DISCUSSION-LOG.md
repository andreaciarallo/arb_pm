# Phase 2: Detection Quality Filters - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 02-detection-quality-filters
**Areas discussed:** Dedup strategy, Threshold config, Rejection telemetry, Filter architecture

---

## Dedup Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| market_id only | Same condition_id = same opportunity regardless of price movement | |
| market_id + type | Separate dedup windows for yes_no vs cross_market on the same market | ✓ |
| market_id + price bucket | Same market at different price levels = different opportunity | |

**User's choice:** market_id + type
**Notes:** YES/NO and cross-market detections on the same market tracked independently

---

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory dict | Simple dict, resets on restart, zero I/O overhead | ✓ |
| SQLite table | Persistent across restarts, query-able for analytics | |

**User's choice:** In-memory dict
**Notes:** Sufficient for continuous-running bot

---

| Option | Description | Selected |
|--------|-------------|----------|
| 5 minutes | ~10 scan cycles at 30s interval | ✓ |
| 15 minutes | More aggressive suppression | |
| 1 minute | Minimal suppression, catches only back-to-back | |

**User's choice:** 5 minutes
**Notes:** Configurable via BotConfig

---

## Threshold Config

| Option | Description | Selected |
|--------|-------------|----------|
| BotConfig fields | Add to BotConfig like existing params, defaults match REQUIREMENTS | ✓ |
| Module-level constants | Hardcoded at top of detection modules | |
| Separate FilterConfig | New dedicated config dataclass | |

**User's choice:** BotConfig fields
**Notes:** Consistent with existing pattern (min_order_book_depth, fee_pct_*)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, BotConfig field | dedup_window_seconds: int = 300 in BotConfig | ✓ |
| Module-level constant | Less noise in BotConfig | |

**User's choice:** Yes, BotConfig field
**Notes:** All configurable params in one place

---

## Rejection Telemetry

| Option | Description | Selected |
|--------|-------------|----------|
| Diagnostic counters | Per-cycle summary counters at INFO level | |
| Per-rejection debug logs | Log each individual rejection at DEBUG level | |
| Both counters + debug | Summary at INFO + detail at DEBUG | ✓ |

**User's choice:** Both counters + debug
**Notes:** Best for threshold tuning from production data

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, add to cycle log | dedup_suppressed=N in dry_run.py cycle summary | ✓ |
| No, counters only inside detector | Keep dedup counter internal | |

**User's choice:** Yes, add to cycle log
**Notes:** Visible signal that dedup is working

---

## Filter Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in detectors | Add gates directly inside existing detector functions | |
| Separate filter module | New src/bot/detection/filters.py with filter functions | ✓ |
| Post-processing in dry_run.py | Detectors return all, dry_run.py filters before logging | |

**User's choice:** Separate filter module
**Notes:** New src/bot/detection/filters.py for all quality filters

---

| Option | Description | Selected |
|--------|-------------|----------|
| In filters.py | All quality filters in one place including dedup | ✓ |
| Own module (dedup.py) | Separate module for stateful dedup | |

**User's choice:** In filters.py
**Notes:** Consolidated — threshold filters and dedup colocated

---

| Option | Description | Selected |
|--------|-------------|----------|
| Detectors call filters | Import and call before appending to opportunities | ✓ |
| dry_run.py applies after | Centralized filter application after detection returns | |

**User's choice:** Detectors call filters
**Notes:** Filtered opps never leave the detector; counters returned with results

---

## Claude's Discretion

- Internal organization of filters.py (function signatures, class vs module-level dict)
- How counters are returned from detectors
- Exact DEBUG log format for per-rejection messages

## Deferred Ideas

None — discussion stayed within phase scope
