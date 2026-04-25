# Phase 2: Detection Quality Filters - Research

**Researched:** 2026-04-25
**Domain:** Arbitrage detection filtering / deduplication / Python data structures
**Confidence:** HIGH

## Summary

Phase 2 adds five quality filters to the existing YES/NO and cross-market detection pipeline. The work is entirely Python-internal -- no new dependencies, no API calls, no database changes. All five requirements (DETECT-01 through DETECT-05) are threshold comparisons or timestamp-based deduplication implemented as pure functions and one stateful class in a new `filters.py` module.

The codebase has a well-established gate pattern: sequential `if ... continue` blocks inside detection loops (visible in `yes_no_arb.py` gates 1-3 and `cross_market.py` depth/exclusivity gates). The new filters follow this identical pattern. The existing `BotConfig` frozen dataclass in `config.py` holds all configurable thresholds and the five new fields (D-04, D-05) slot in naturally.

**Primary recommendation:** Implement all filters as stateless functions in `src/bot/detection/filters.py`, plus one `DedupTracker` class for DETECT-05. Wire filters into the existing detector loops before the `opportunities.append()` call. Return filter diagnostic counters alongside detection results. No new dependencies needed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Dedup key is `(market_id, opportunity_type)` -- YES/NO and cross-market detections on the same market are tracked independently
- **D-02:** Dedup state is an in-memory dict mapping `(market_id, type)` to `last_seen` timestamp. Resets on bot restart. Zero I/O overhead in hot detection path.
- **D-03:** Default dedup time window is 5 minutes (~10 scan cycles at 30s interval), configurable via `BotConfig.dedup_window_seconds`
- **D-04:** All filter thresholds are `BotConfig` fields with REQUIREMENTS values as defaults:
  - `min_ask_floor: float = 0.03`
  - `max_ask_sum: float = 0.99`
  - `min_cross_leg_ask: float = 0.005`
  - `min_cross_total_yes: float = 0.10`
  - `dedup_window_seconds: int = 300`
- **D-05:** Follows the established `BotConfig` frozen dataclass pattern
- **D-06:** Two-level reporting: summary counters at INFO level, per-rejection detail at DEBUG level
- **D-07:** Each filter type has its own diagnostic counter
- **D-08:** Dedup suppression count added to cycle summary log line in `dry_run.py`
- **D-09:** New module `src/bot/detection/filters.py` containing all quality filters and dedup logic
- **D-10:** Threshold filters are stateless functions; dedup is a stateful class/function
- **D-11:** Detectors import and call filter functions before appending to opportunities list. Filtered opps never leave the detector.
- **D-12:** Filter diagnostic counters are returned alongside detection results for cycle-level reporting

### Claude's Discretion
- Internal organization of `filters.py` (function signatures, class vs module-level dict for dedup state)
- How counters are returned from detectors (separate return value, dataclass, or dict)
- Exact DEBUG log format for per-rejection messages

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DETECT-01 | Bot skips YES/NO opportunities where either ask <= $0.03 (dead limit orders) | Stateless `is_ask_floor_reject(yes_ask, no_ask, floor)` function; checked after price fetch, before spread calc |
| DETECT-02 | Bot skips YES/NO opportunities where yes_ask + no_ask > $0.99 (near-resolved markets) | Stateless `is_sum_cap_reject(yes_ask, no_ask, cap)` function; checked after DETECT-01 passes |
| DETECT-03 | Bot skips cross-market legs where any leg's ask <= $0.005 (dead cross-market legs) | Stateless `has_dead_leg(legs, floor)` function; checked inside the per-group loop after price collection |
| DETECT-04 | Bot skips cross-market groups where total_yes < $0.10 (degenerate groups with phantom spreads) | Stateless `is_total_yes_reject(total_yes, floor)` function; checked after DETECT-03, before spread calc |
| DETECT-05 | Bot deduplicates opportunities within a configurable time window | `DedupTracker` class with `is_duplicate(market_id, opp_type)` method; checked as final gate before append |
</phase_requirements>

## Standard Stack

### Core
No new libraries needed. This phase uses only Python stdlib.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `time` | 3.10+ | `time.monotonic()` for dedup timestamps | Monotonic clock avoids NTP jumps; already used in `dry_run.py` for cycle timing [VERIFIED: codebase] |
| Python stdlib `dataclasses` | 3.10+ | `@dataclass` for `FilterDiagnostics` counter struct | Matches existing `BotConfig`, `ArbitrageOpportunity`, `MarketPrice` patterns [VERIFIED: codebase] |

### Supporting
None needed.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `time.monotonic()` | `time.time()` | `time.time()` is subject to NTP jumps; monotonic is safer for interval comparisons. Both work for 5-min windows but monotonic is correct. [ASSUMED] |
| In-memory dict | Redis / SQLite | Overkill for single-process dedup; D-02 explicitly mandates in-memory dict with zero I/O overhead |
| `@dataclass` for counters | `TypedDict` or plain `dict` | `dict` is simpler but lacks IDE autocomplete; `@dataclass` matches codebase convention |

## Architecture Patterns

### Recommended Project Structure
```
src/bot/detection/
    __init__.py
    filters.py          # NEW: all quality filters + DedupTracker (D-09)
    yes_no_arb.py        # MODIFIED: import and call filters before append
    cross_market.py      # MODIFIED: import and call filters before append
    opportunity.py       # UNCHANGED
    fee_model.py         # UNCHANGED
```
[VERIFIED: codebase structure confirmed via glob]

### Pattern 1: Stateless Threshold Filters
**What:** Pure functions that take price values and a threshold, return bool (True = reject).
**When to use:** DETECT-01, DETECT-02, DETECT-03, DETECT-04.
**Why:** Zero state, trivially testable, no side effects. Matches the existing gate pattern in detectors.
**Example:**
```python
# Source: [codebase pattern from yes_no_arb.py lines 83-95]
def is_ask_floor_reject(yes_ask: float, no_ask: float, floor: float) -> bool:
    """Reject if either ask is at or below the floor (dead limit order)."""
    return yes_ask <= floor or no_ask <= floor

def is_sum_cap_reject(yes_ask: float, no_ask: float, cap: float) -> bool:
    """Reject if YES + NO ask sum exceeds the cap (near-resolved)."""
    return (yes_ask + no_ask) > cap

def has_dead_leg(leg_asks: list[float], floor: float) -> bool:
    """Reject if any leg's ask is at or below the floor."""
    return any(ask <= floor for ask in leg_asks)

def is_total_yes_reject(total_yes: float, floor: float) -> bool:
    """Reject if total YES ask sum is below the floor (degenerate group)."""
    return total_yes < floor
```
[VERIFIED: pattern mirrors existing gates in yes_no_arb.py and cross_market.py]

### Pattern 2: Stateful Dedup Tracker (D-01, D-02, D-03)
**What:** A class holding an in-memory dict of `(market_id, opp_type) -> last_seen_monotonic`. The `is_duplicate()` method returns True if the same key was seen within `window_seconds`.
**When to use:** DETECT-05 -- final gate before appending to opportunities list.
**Why:** Dedup requires state across scan cycles. In-memory dict is O(1) lookup, zero I/O (D-02). Resets on bot restart (desired behavior per D-02).
**Example:**
```python
import time

class DedupTracker:
    """Track recently-seen opportunities to suppress duplicate logging."""

    def __init__(self, window_seconds: int = 300):
        self._window = window_seconds
        self._seen: dict[tuple[str, str], float] = {}

    def is_duplicate(self, market_id: str, opp_type: str) -> bool:
        """Return True if this (market_id, opp_type) was seen within the window."""
        key = (market_id, opp_type)
        now = time.monotonic()
        last = self._seen.get(key)
        if last is not None and (now - last) < self._window:
            return True
        self._seen[key] = now
        return False

    def prune(self) -> int:
        """Remove expired entries. Returns number pruned."""
        now = time.monotonic()
        expired = [k for k, t in self._seen.items() if (now - t) >= self._window]
        for k in expired:
            del self._seen[k]
        return len(expired)
```
[ASSUMED: `time.monotonic()` is the right clock; pattern is standard Python]

### Pattern 3: Diagnostic Counter Dataclass (D-06, D-07, D-12)
**What:** A `@dataclass` holding per-filter rejection counts plus dedup suppression count. Returned alongside the opportunities list from each detector.
**When to use:** Both detectors return `(list[ArbitrageOpportunity], FilterDiagnostics)`.
**Why:** Structured counters enable the cycle summary log (D-08) and DEBUG-level detail (D-06).
**Example:**
```python
from dataclasses import dataclass, field

@dataclass
class FilterDiagnostics:
    """Counts of opportunities rejected by each quality filter."""
    ask_floor_rejects: int = 0       # DETECT-01
    sum_cap_rejects: int = 0         # DETECT-02
    leg_floor_rejects: int = 0       # DETECT-03
    total_yes_rejects: int = 0       # DETECT-04
    dedup_suppressed: int = 0        # DETECT-05
```
[VERIFIED: mirrors existing counter pattern in yes_no_arb.py (both_cached, depth_fails, spread_fails)]

### Pattern 4: Integration into Detector Loops
**What:** Filter calls inserted into existing detector loops as additional gates before `opportunities.append()`.
**When to use:** `yes_no_arb.py` for DETECT-01/02/05; `cross_market.py` for DETECT-03/04/05.
**Key decision:** Filters are called BEFORE the existing gates (resolved guard, depth check, spread threshold) for DETECT-01/02, because rejecting dead/near-resolved markets early avoids unnecessary fee computation. DETECT-05 dedup is the LAST gate, after all quality checks pass, so we only dedup genuine opportunities.

**YES/NO detector integration order:**
1. Price cache fetch (existing)
2. **NEW: DETECT-01 ask floor check** -- reject if either ask <= 0.03
3. **NEW: DETECT-02 sum cap check** -- reject if sum > 0.99
4. Resolved market guard (existing, becomes partially redundant but harmless)
5. Depth check (existing)
6. Fee/spread calculation (existing)
7. Spread threshold (existing)
8. **NEW: DETECT-05 dedup check** -- reject if seen within window
9. Append to opportunities

**Cross-market detector integration order:**
1. Price collection loop (existing)
2. **NEW: DETECT-03 dead leg check** -- reject if any leg ask <= 0.005
3. **NEW: DETECT-04 total_yes floor** -- reject if total_yes < 0.10
4. Depth gate (existing)
5. Exclusivity check total_yes >= 1.0 (existing)
6. Fee/spread calculation (existing)
7. Spread threshold (existing)
8. **NEW: DETECT-05 dedup check** -- reject if seen within window
9. Append to opportunities

[VERIFIED: integration points confirmed by reading yes_no_arb.py and cross_market.py source]

### Pattern 5: DedupTracker Lifecycle (dry_run.py)
**What:** `DedupTracker` is instantiated once before the scan loop in `dry_run.py` and passed to both detectors. It persists across scan cycles (desired: dedup works across cycles). Optionally prune expired entries every N cycles to prevent unbounded memory growth.
**Why:** D-02 says state resets on bot restart (constructor handles this). D-11 says filtered opps never leave the detector, so the tracker must be available inside both detector calls.

```python
# In dry_run.py, before the loop:
dedup = DedupTracker(window_seconds=config.dedup_window_seconds)

# In the loop:
yes_no_opps, yn_diag = detect_yes_no_opportunities(priced_markets, cache, config, dedup)
cross_opps, cm_diag = detect_cross_market_opportunities(priced_markets[:100], cache, config, dedup)

# Cycle summary includes dedup count (D-08):
logger.info(
    f"Cycle {cycle + 1} | "
    f"{len(yes_no_opps)} YES/NO + {len(cross_opps)} cross-market opps | "
    f"dedup_suppressed={yn_diag.dedup_suppressed + cm_diag.dedup_suppressed} | "
    ...
)
```
[VERIFIED: dry_run.py orchestration pattern confirmed from source]

### Anti-Patterns to Avoid
- **Filtering after append:** D-11 explicitly says filtered opps never leave the detector. Do NOT filter in `dry_run.py` after `detect_*()` returns.
- **Dedup inside filters.py only:** The `DedupTracker` instance must be created in `dry_run.py` and passed in, not created as a module-level singleton. Module-level state makes testing harder and violates D-02 (reset on restart depends on instance lifecycle, not module reload).
- **Using `time.time()` for dedup intervals:** Wall clock can jump backwards (NTP sync). Use `time.monotonic()` for interval comparisons. [ASSUMED]
- **Mutating BotConfig at runtime:** `BotConfig` is `frozen=True`. All threshold values are set at construction time. Do not try to update thresholds during operation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dedup key hashing | Custom hash function for (market_id, type) | Python tuple as dict key | Tuples are hashable and use built-in `__hash__`; no custom code needed [VERIFIED: Python stdlib] |
| Expiring cache | Custom TTL cache with threading | Simple dict + `time.monotonic()` | Single-threaded asyncio event loop; no concurrency concerns. The DedupTracker.prune() method handles cleanup. [VERIFIED: dry_run.py is single-threaded asyncio] |
| Counter aggregation | Manual counter addition logic | `dataclasses.fields()` iteration or just direct attribute addition | FilterDiagnostics has only 5 fields; direct addition in dry_run.py is simplest [ASSUMED] |

**Key insight:** This phase is pure application logic with no external dependencies. The risk is not in technology choices but in getting the filter placement, threshold comparisons, and boundary conditions exactly right.

## Common Pitfalls

### Pitfall 1: Off-by-one in threshold comparisons (<=  vs <)
**What goes wrong:** DETECT-01 says "ask <= $0.03" (inclusive of 0.03). DETECT-02 says "sum > $0.99" (exclusive of 0.99). DETECT-03 says "ask <= $0.005" (inclusive). DETECT-04 says "total_yes < $0.10" (exclusive of 0.10). Getting the comparison operators wrong means the filters either miss edge cases or reject valid opportunities.
**Why it happens:** Requirements use natural language; the exact operator (<=, <, >, >=) matters for boundary values.
**How to avoid:** Write explicit boundary tests: ask=0.03 MUST be rejected (DETECT-01), ask=0.031 must NOT be rejected. Sum=0.99 must NOT be rejected (DETECT-02), sum=0.991 must be rejected. Leg ask=0.005 MUST be rejected (DETECT-03). Total_yes=0.10 must NOT be rejected (DETECT-04), total_yes=0.099 must be rejected.
**Warning signs:** Tests pass with round numbers (0.01, 0.50) but fail at exact boundary values.
[VERIFIED: threshold values and comparison operators from REQUIREMENTS.md]

### Pitfall 2: Float comparison precision
**What goes wrong:** `0.03 + 0.97` might equal `0.9999999999999999` in IEEE 754, causing a sum check to pass when it should fail (or vice versa).
**Why it happens:** Floating point representation of decimal values is inherently imprecise.
**How to avoid:** Use `round(value, 6)` before threshold comparisons (matches existing rounding pattern in `yes_no_arb.py` lines 122-127), or use small epsilon comparisons for boundary tests. For the filter functions, the prices from `PriceCache` are already floats from the CLOB API, so precision loss is minimal at the values we care about ($0.005 to $0.99).
**Warning signs:** Intermittent test failures at exact boundary values.
[VERIFIED: existing code uses round() for spread values]

### Pitfall 3: Dedup tracker memory growth
**What goes wrong:** Over 24 hours at 30s intervals = 2,880 cycles. If each cycle produces unique opportunities (different market_id each time), the dedup dict grows unboundedly.
**Why it happens:** Entries are only added, never pruned.
**How to avoid:** Add a `prune()` method that removes entries older than `window_seconds`. Call it periodically (every 10-50 cycles). With a 5-minute window and 30s cycles, max live entries = opportunities_per_cycle * 10 cycles, which is bounded. But a periodic prune is defensive.
**Warning signs:** Memory usage growing steadily over 24h dry-run.
[ASSUMED: memory growth estimate based on scan cycle frequency from config]

### Pitfall 4: Dedup key collision across opportunity types
**What goes wrong:** A YES/NO opportunity and a cross-market opportunity on the same market_id share a dedup key, causing one to suppress the other.
**Why it happens:** Using only `market_id` as the dedup key without `opportunity_type`.
**How to avoid:** D-01 explicitly mandates key = `(market_id, opportunity_type)`. The tuple includes both fields. This is already in the locked decisions.
**Warning signs:** Cross-market opps disappear when a YES/NO opp on the same market was recently detected (or vice versa).
[VERIFIED: D-01 from CONTEXT.md]

### Pitfall 5: Filter placement relative to existing gates
**What goes wrong:** Placing DETECT-01/02 after the spread calculation wastes CPU on opportunities that will be filtered. Worse, placing DETECT-05 dedup before quality filters means the dedup timestamp is set even for opportunities that fail other quality checks, causing them to be suppressed in future cycles when they might pass.
**Why it happens:** Not thinking about the order of filter evaluation.
**How to avoid:** DETECT-01/02 go early (before spread calculation). DETECT-05 dedup goes LAST (after all quality checks pass). Only opportunities that pass all quality gates get their timestamp recorded in the dedup tracker.
**Warning signs:** Opportunities intermittently disappear because dedup timestamp was set on a quality-rejected pass.
[VERIFIED: analysis of yes_no_arb.py gate ordering]

### Pitfall 6: Detector return type change breaks dry_run.py
**What goes wrong:** Changing `detect_yes_no_opportunities()` return type from `list[ArbitrageOpportunity]` to `tuple[list[ArbitrageOpportunity], FilterDiagnostics]` breaks `dry_run.py` line 105: `yes_no_opps = detect_yes_no_opportunities(...)`.
**Why it happens:** Return type change is a breaking API change.
**How to avoid:** Update ALL call sites in the same commit. There are exactly 3 callers:
1. `dry_run.py` line 105-107 (both detectors)
2. `tests/test_yes_no_arb.py` (7 tests)
3. `tests/test_cross_market.py` (8 tests)
4. `tests/test_dry_run.py` (3 tests, but these mock the detectors)
**Warning signs:** `TypeError: cannot unpack non-sequence list` at runtime.
[VERIFIED: grep for function call sites in codebase]

## Code Examples

Verified patterns from the codebase:

### Existing Gate Pattern (yes_no_arb.py)
```python
# Source: src/bot/detection/yes_no_arb.py lines 83-96
# Gate 1: Skip resolved markets
if yes_ask >= 1.0 or no_ask >= 1.0:
    continue

# Gate 2: Depth check
depth = min(yes_price.yes_depth, no_price.yes_depth)
if depth < config.min_order_book_depth:
    depth_fails += 1
    continue
```
[VERIFIED: codebase]

### Existing BotConfig Pattern (config.py)
```python
# Source: src/bot/config.py lines 24-63
@dataclass(frozen=True)
class BotConfig:
    # Phase 2: Market scanning parameters
    min_order_book_depth: float = 50.0
    scan_interval_seconds: int = 30
    # ... etc
```
[VERIFIED: codebase]

### New Filter Integration in YES/NO Detector
```python
# After fetching yes_ask and no_ask from cache:

# NEW Gate: DETECT-01 ask floor
if is_ask_floor_reject(yes_ask, no_ask, config.min_ask_floor):
    diag.ask_floor_rejects += 1
    logger.debug(f"DETECT-01 reject: ask floor | {market.get('question', '')[:40]} | yes={yes_ask} no={no_ask}")
    continue

# NEW Gate: DETECT-02 sum cap
if is_sum_cap_reject(yes_ask, no_ask, config.max_ask_sum):
    diag.sum_cap_rejects += 1
    logger.debug(f"DETECT-02 reject: sum cap | {market.get('question', '')[:40]} | sum={yes_ask + no_ask:.4f}")
    continue

# ... existing gates (resolved, depth, spread) ...

# NEW Gate: DETECT-05 dedup (LAST, after all quality checks pass)
if dedup.is_duplicate(market.get("condition_id", ""), "yes_no"):
    diag.dedup_suppressed += 1
    logger.debug(f"DETECT-05 suppress: dedup | {market.get('question', '')[:40]}")
    continue

# Append to opportunities
opportunities.append(opportunity)
```
[ASSUMED: integration pattern; based on existing gate pattern verified from codebase]

### New Filter Integration in Cross-Market Detector
```python
# After collecting all leg asks and total_yes:

# NEW Gate: DETECT-03 dead legs
leg_asks = [leg["ask"] for leg in legs_data]
if has_dead_leg(leg_asks, config.min_cross_leg_ask):
    diag.leg_floor_rejects += 1
    logger.debug(f"DETECT-03 reject: dead leg | min_ask={min(leg_asks):.4f}")
    continue

# NEW Gate: DETECT-04 total_yes floor
if is_total_yes_reject(total_yes, config.min_cross_total_yes):
    diag.total_yes_rejects += 1
    logger.debug(f"DETECT-04 reject: total_yes floor | total_yes={total_yes:.4f}")
    continue

# ... existing gates (depth, exclusivity, spread) ...

# NEW Gate: DETECT-05 dedup
if dedup.is_duplicate(group[0].get("condition_id", ""), "cross_market"):
    diag.dedup_suppressed += 1
    continue
```
[ASSUMED: integration pattern; based on existing gate pattern verified from codebase]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No quality filters | Gate-style sequential filters in detector loop | v1.2 (this phase) | Eliminates ~93% false positives per CONTEXT.md |
| No dedup | In-memory timestamp dedup with configurable window | v1.2 (this phase) | Prevents same opp from being logged every 30s cycle |
| Return list only | Return (list, FilterDiagnostics) tuple | v1.2 (this phase) | Enables cycle-level observability of filter behavior |

**Deprecated/outdated:**
- Nothing deprecated; this is additive functionality on existing detection pipeline.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `time.monotonic()` is preferred over `time.time()` for dedup interval tracking | Architecture Patterns, Anti-Patterns | LOW -- `time.time()` would also work; monotonic is slightly safer against NTP jumps |
| A2 | Memory growth from dedup dict is bounded by opportunities_per_cycle * 10 (5min window / 30s cycle) | Common Pitfalls | LOW -- even if unbounded, a periodic prune() call handles it; 24h of unique market_ids is at most a few thousand entries |
| A3 | Returning `tuple[list, FilterDiagnostics]` is preferable over separate method or global counter | Architecture Patterns | LOW -- any approach works; tuple return matches functional style and avoids mutable global state |

## Open Questions

1. **DETECT-03 placement relative to price collection loop**
   - What we know: Cross-market detector collects prices in a for-loop over group members. DETECT-03 (dead leg check) needs all leg asks to evaluate.
   - What's unclear: Should we check each leg individually during collection (fail fast on first dead leg) or collect all prices first and then check? Fail-fast saves a few cache lookups but adds complexity.
   - Recommendation: Collect all prices first (existing pattern), then check `has_dead_leg()` on the collected list. Simpler, and the cache lookups are O(1) dict reads -- not worth optimizing away.

2. **Cross-market dedup key when group[0] changes order**
   - What we know: D-01 says dedup key is `(market_id, opportunity_type)`. For cross-market, `market_id` comes from `group[0].get("condition_id")`. But `_group_by_event()` returns groups as `list[dict]` from a `defaultdict(list)`, and dict iteration order is insertion order (Python 3.7+), so `group[0]` is deterministic within a session.
   - What's unclear: If the market list order changes between scan cycles (e.g., due to market list refresh), could `group[0]` change, making the dedup key unstable?
   - Recommendation: Use the event_id (from `_event_groups`) as part of the dedup key for cross-market, not `group[0].condition_id`. The event_id is stable. OR sort the group by condition_id before taking [0]. Either approach adds stability.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pytest.ini` (asyncio_mode = auto) |
| Quick run command | `python -m pytest tests/ -m unit -x -q` |
| Full suite command | `python -m pytest tests/ -m unit -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DETECT-01 | Reject YES/NO where either ask <= 0.03 | unit | `python -m pytest tests/test_filters.py::test_ask_floor_reject -x` | Wave 0 |
| DETECT-01 | Boundary: ask=0.03 rejected, ask=0.031 passes | unit | `python -m pytest tests/test_filters.py::test_ask_floor_boundary -x` | Wave 0 |
| DETECT-02 | Reject YES/NO where sum > 0.99 | unit | `python -m pytest tests/test_filters.py::test_sum_cap_reject -x` | Wave 0 |
| DETECT-02 | Boundary: sum=0.99 passes, sum=0.991 rejected | unit | `python -m pytest tests/test_filters.py::test_sum_cap_boundary -x` | Wave 0 |
| DETECT-03 | Reject cross-market group with any leg ask <= 0.005 | unit | `python -m pytest tests/test_filters.py::test_dead_leg_reject -x` | Wave 0 |
| DETECT-03 | Boundary: leg=0.005 rejected, leg=0.006 passes | unit | `python -m pytest tests/test_filters.py::test_dead_leg_boundary -x` | Wave 0 |
| DETECT-04 | Reject cross-market where total_yes < 0.10 | unit | `python -m pytest tests/test_filters.py::test_total_yes_reject -x` | Wave 0 |
| DETECT-04 | Boundary: total_yes=0.10 passes, total_yes=0.099 rejected | unit | `python -m pytest tests/test_filters.py::test_total_yes_boundary -x` | Wave 0 |
| DETECT-05 | Dedup suppresses same (market_id, type) within window | unit | `python -m pytest tests/test_filters.py::test_dedup_suppresses -x` | Wave 0 |
| DETECT-05 | Dedup allows re-detection after window expires | unit | `python -m pytest tests/test_filters.py::test_dedup_expires -x` | Wave 0 |
| DETECT-05 | Different opp_type on same market_id not suppressed (D-01) | unit | `python -m pytest tests/test_filters.py::test_dedup_separate_types -x` | Wave 0 |
| Integration | YES/NO detector returns filtered results + diagnostics | unit | `python -m pytest tests/test_yes_no_arb.py -x` | Existing (update needed) |
| Integration | Cross-market detector returns filtered results + diagnostics | unit | `python -m pytest tests/test_cross_market.py -x` | Existing (update needed) |
| Integration | dry_run.py logs dedup_suppressed in cycle summary | unit | `python -m pytest tests/test_dry_run.py -x` | Existing (update needed) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -m unit -x -q`
- **Per wave merge:** `python -m pytest tests/ -m unit -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_filters.py` -- covers DETECT-01 through DETECT-05 with boundary tests
- [ ] Update `tests/test_yes_no_arb.py` -- adapt to new return type (list, diagnostics)
- [ ] Update `tests/test_cross_market.py` -- adapt to new return type + dedup param
- [ ] Update `tests/test_dry_run.py` -- mock new return types, verify dedup_suppressed in log

## Security Domain

This phase has no security implications. It adds pure filtering logic (threshold comparisons and in-memory dedup) to the existing detection pipeline. No new network calls, no user input handling, no authentication changes, no data persistence changes.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | No | Prices come from PriceCache (internal), not user input |
| V6 Cryptography | No | N/A |

## Project Constraints (from CLAUDE.md)

- **WebSearch is BLOCKED** by Vertex AI org policy -- use WebFetch for URL-based research [VERIFIED: CLAUDE.md]
- **GSD workflow enforcement** -- all edits through GSD commands [VERIFIED: CLAUDE.md]
- **Tech stack** -- Python + py-clob-client ecosystem [VERIFIED: CLAUDE.md]
- **Latency constraint** -- filters must be zero-overhead in hot detection path (all O(1) operations) [VERIFIED: CLAUDE.md "Ultra-low latency execution"]
- **Existing conventions** -- frozen dataclass for config, Loguru for logging, gate-style filtering [VERIFIED: codebase]

## Sources

### Primary (HIGH confidence)
- `src/bot/detection/yes_no_arb.py` -- existing YES/NO detector with gate pattern, diagnostic counters
- `src/bot/detection/cross_market.py` -- existing cross-market detector with event grouping
- `src/bot/detection/opportunity.py` -- ArbitrageOpportunity dataclass
- `src/bot/config.py` -- BotConfig frozen dataclass pattern
- `src/bot/dry_run.py` -- scan loop orchestrator
- `src/bot/scanner/price_cache.py` -- PriceCache and MarketPrice dataclass
- `src/bot/detection/fee_model.py` -- category-aware fee model
- `.planning/phases/02-detection-quality-filters/02-CONTEXT.md` -- locked decisions D-01 through D-12
- `.planning/REQUIREMENTS.md` -- DETECT-01 through DETECT-05 requirements
- `tests/test_yes_no_arb.py` -- 7 existing unit tests for YES/NO detector
- `tests/test_cross_market.py` -- 8 existing unit tests for cross-market detector
- `tests/test_dry_run.py` -- 3 existing unit tests for dry-run orchestrator
- `pytest.ini` -- test framework configuration

### Secondary (MEDIUM confidence)
- None needed -- all findings from codebase inspection

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all Python stdlib [VERIFIED: codebase]
- Architecture: HIGH -- follows established codebase patterns exactly [VERIFIED: codebase]
- Pitfalls: HIGH -- derived from concrete code analysis and requirement boundary conditions [VERIFIED: REQUIREMENTS.md + codebase]

**Research date:** 2026-04-25
**Valid until:** 2026-06-25 (stable -- pure Python application logic, no external dependency drift)
