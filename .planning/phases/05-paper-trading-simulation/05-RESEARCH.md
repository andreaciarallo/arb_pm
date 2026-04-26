# Phase 5: Paper Trading Simulation - Research

**Researched:** 2026-04-26
**Domain:** Paper trade simulation engine, SQLite schema design, summary analytics
**Confidence:** HIGH

## Summary

Phase 5 adds paper trading simulation to the existing dry-run scanner. The architecture is straightforward: hook into the existing `dry_run.py` scan loop after detection, compute simulated VWAP/Kelly/fees using cached price data, persist results to a new `paper_trades` SQLite table, and provide query functions for analytics. All required components already exist in the codebase as pure functions (`simulate_vwap()`, `kelly_size()`, `get_taker_fee()`) and follow well-established patterns (`init_*_table()` / `insert_*()` in `schema.py`, `AsyncWriter` queue pattern).

The primary technical constraint is that `PriceCache` stores only best-level ask price and depth per token (not full multi-level order book). This means `simulate_vwap()` operates on a single-level book, degenerating to best-ask price when depth exceeds target size. This is an intentional design trade-off (D-02) to avoid exhausting the 60 req/10s CLOB rate limit. The simulation will be accurate for small position sizes relative to best-level depth, and conservative (returning VWAP=1.0 / partial fill) for large sizes.

**Primary recommendation:** Build the paper trading simulator as a self-contained pure-function module (`src/bot/paper/simulator.py`) that accepts an `ArbitrageOpportunity` + `PriceCache` + `BotConfig` and returns a list of `PaperTrade` dataclasses. Wire it into `dry_run.py` after detection. Create `paper_trades` table and summary queries following existing schema patterns exactly.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Paper trade simulation runs inline in `dry_run.py` scan loop, immediately after detection and before the existing opportunity SQLite write
- **D-02:** VWAP uses cached prices from `PriceCache` -- NOT fresh order book fetches
- **D-03:** Paper trade simulation is always enabled in dry-run mode -- no separate toggle
- **D-04:** New `paper_trades` SQLite table via `init_paper_trades_table(conn)` in `storage/schema.py`
- **D-05:** `insert_paper_trade(conn, paper_trade)` function for row insertion
- **D-06:** Paper trade record schema with 18+ fields including `paper_trade_id`, `paper_arb_id`, `leg`, `status`, etc.
- **D-07:** Depth-gated deterministic fill model (no stochastic component)
- **D-08:** Kelly sizing reuses same parameters as live execution
- **D-09:** YES/NO P&L: `gross_pnl = (1.0 - vwap_yes - vwap_no) * size_filled_shares`, fees on both sides
- **D-10:** Cross-market legs simulated sequentially, equal shares sizing
- **D-11:** Partial fill triggers hedge simulation for all previously "filled" legs at $0.01
- **D-12:** Cross-market P&L when fully filled: `gross_pnl = (1.0 - total_yes) * target_shares`
- **D-13:** Summary query module at `src/bot/storage/paper_summary.py` with 4 functions
- **D-14:** Summary aggregation by `paper_arb_id` (not individual legs)
- **D-15:** No new BotConfig fields needed

### Claude's Discretion
- Whether to add a `paper_trade_enabled` BotConfig toggle (likely unnecessary per D-03)
- Whether to log a per-cycle paper trade summary line in the scan loop
- Whether to create a thin CLI entrypoint for querying paper trade summaries
- Exact column types and indexes for the paper_trades table

### Deferred Ideas (OUT OF SCOPE)
- Dashboard panel for paper-trading metrics (PAPER-F01)
- Paper-trade vs live-trade comparison analytics (PAPER-F02)
- Stochastic fill probability model
- WebSocket-based real-time paper trade notifications
- Historical backtesting mode using stored order book snapshots
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PAPER-01 | Dry-run simulates VWAP + Kelly sizing on each detected opportunity | Reuse `simulate_vwap()` from `engine.py` and `kelly_size()` from `kelly.py` with cached `PriceCache` data; depth-gated deterministic fill model (D-07) |
| PAPER-02 | Simulated trades stored in separate paper_trades SQLite table | New table following `init_trades_table()` / `insert_trade()` pattern in `schema.py`; completely isolated from `trades` and `arb_pairs` tables |
| PAPER-03 | Paper-trade records include simulated size, VWAP price, Kelly allocation, estimated fees, and net P&L | 18-field schema defined in D-06; uses `get_taker_fee()` from `fee_model.py` for fee calculation |
| PAPER-04 | Cross-market paper trades simulate N-leg execution with partial fill and hedge scenarios | Sequential leg simulation matching `_execute_cross_market()` pattern in `engine.py`; equal-shares sizing; hedge at $0.01 on partial fill |
| PAPER-05 | Summary queries provide total simulated P&L, win rate, avg spread captured, per-category breakdown | Pure functions in `paper_summary.py` aggregating by `paper_arb_id`; 4 query functions defined in D-13 |
</phase_requirements>

## Standard Stack

### Core (no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **Python stdlib** | 3.10+ | `uuid`, `dataclasses`, `sqlite3`, `datetime` | All paper trading logic uses stdlib only [VERIFIED: codebase inspection] |
| **SQLite** | 3.51.0 | Paper trades persistence | Already in use for `opportunities`, `trades`, `arb_pairs` tables [VERIFIED: codebase inspection] |
| **Loguru** | 0.7+ | Structured logging | Already imported throughout codebase [VERIFIED: codebase inspection] |

**No new pip dependencies required.** Phase 5 is entirely internal -- reuses existing pure functions and adds new modules using the same patterns. [VERIFIED: codebase inspection of all CONTEXT.md references]

### Reusable Components (already implemented)

| Component | Location | Signature | How Paper Trading Uses It |
|-----------|----------|-----------|--------------------------|
| `simulate_vwap()` | `execution/engine.py:65` | `(asks: list, target_size_usd: float) -> float` | Compute VWAP fill price from cached single-level ask data |
| `kelly_size()` | `execution/kelly.py:17` | `(net_spread, depth, target_size, total_capital, min_order_usd, max_capital_pct) -> float` | Position sizing -- returns 0.0 to skip |
| `get_taker_fee()` | `detection/fee_model.py:66` | `(category: str, config: BotConfig) -> float` | Per-side fee rate by category |
| `get_market_category()` | `detection/fee_model.py:37` | `(market: dict) -> str` | Market category detection |
| `PriceCache.get()` | `scanner/price_cache.py:49` | `(token_id: str) -> MarketPrice \| None` | Cached ask prices and depth |
| `ArbitrageOpportunity` | `detection/opportunity.py:12` | Dataclass with `.legs`, `.yes_ask`, `.no_ask`, `.category`, etc. | Input to paper trade simulator |
| `AsyncWriter` | `storage/writer.py:20` | Queue-based async SQLite writer | Pattern reference (may create second instance for paper trades) |

## Architecture Patterns

### Recommended Project Structure
```
src/bot/
  paper/
    __init__.py
    simulator.py          # NEW: simulate_paper_trade(), simulate_cross_market_paper_trade()
  storage/
    schema.py             # MODIFIED: add init_paper_trades_table(), insert_paper_trade()
    paper_summary.py      # NEW: get_total_pnl(), get_win_rate(), get_avg_spread(), get_category_breakdown()
    writer.py             # UNCHANGED (or minor extension)
  dry_run.py              # MODIFIED: wire paper trade simulation after detection
```

### Pattern 1: Paper Trade Simulator as Pure Function Module

**What:** A standalone module with pure functions that accept `ArbitrageOpportunity` + `PriceCache` + `BotConfig` and return `list[PaperTrade]` dataclasses. No I/O, no side effects.

**When to use:** Always -- matches the existing pattern where detection returns dataclasses and storage is handled by the caller.

**Example:**
```python
# Source: follows pattern from detection/yes_no_arb.py + execution/engine.py
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass
class PaperTrade:
    paper_trade_id: str       # UUID
    paper_arb_id: str         # UUID, groups multi-leg trades
    market_id: str
    market_question: str
    opportunity_type: str     # "yes_no" | "cross_market"
    category: str
    leg: str                  # "yes" | "no" | "leg_1".."leg_N" | "hedge"
    side: str                 # "BUY" | "SELL"
    token_id: str
    ask_price: float
    simulated_size_usd: float  # kelly output
    size_filled_usd: float     # actual fill based on depth
    vwap_price: float
    kelly_fraction: float
    estimated_fees_usd: float
    net_pnl_usd: float
    depth_available: float
    fill_ratio: float         # size_filled / simulated_size
    simulated_at: str         # ISO timestamp
    status: str               # "filled" | "partial" | "failed" | "hedged"


def simulate_yes_no(opp, cache, config) -> list[PaperTrade]:
    """Simulate a YES/NO arb paper trade. Returns 2 PaperTrade rows (YES + NO legs)."""
    ...

def simulate_cross_market(opp, cache, config) -> list[PaperTrade]:
    """Simulate a cross-market arb paper trade. Returns N PaperTrade rows (one per leg + hedges)."""
    ...
```
[VERIFIED: pattern derived from existing `ArbitrageOpportunity`, `ExecutionResult` dataclasses in codebase]

### Pattern 2: SQLite Table Following Existing Schema Pattern

**What:** New `paper_trades` table created via `init_paper_trades_table(conn)` with `CREATE TABLE IF NOT EXISTS`. Row insertion via `insert_paper_trade(conn, paper_trade)`.

**When to use:** Always -- exactly matches `init_trades_table()` / `insert_trade()` pattern in `schema.py`.

**Example:**
```python
# Source: follows pattern from storage/schema.py lines 91-179
_CREATE_PAPER_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id TEXT UNIQUE NOT NULL,
    paper_arb_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    opportunity_type TEXT NOT NULL,
    category TEXT NOT NULL,
    leg TEXT NOT NULL,
    side TEXT NOT NULL,
    token_id TEXT NOT NULL,
    ask_price REAL NOT NULL,
    simulated_size_usd REAL NOT NULL,
    size_filled_usd REAL NOT NULL,
    vwap_price REAL NOT NULL,
    kelly_fraction REAL NOT NULL,
    estimated_fees_usd REAL NOT NULL,
    net_pnl_usd REAL NOT NULL,
    depth_available REAL NOT NULL,
    fill_ratio REAL NOT NULL,
    simulated_at TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

_CREATE_PAPER_TRADES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_paper_trades_arb_id ON paper_trades(paper_arb_id)",
    "CREATE INDEX IF NOT EXISTS idx_paper_trades_simulated_at ON paper_trades(simulated_at)",
    "CREATE INDEX IF NOT EXISTS idx_paper_trades_opp_type ON paper_trades(opportunity_type)",
    "CREATE INDEX IF NOT EXISTS idx_paper_trades_category ON paper_trades(category)",
    "CREATE INDEX IF NOT EXISTS idx_paper_trades_status ON paper_trades(status)",
]
```
[VERIFIED: mirrors exact pattern from `schema.py` `_CREATE_TRADES_TABLE` and `_CREATE_TRADES_INDEXES`]

### Pattern 3: Summary Query Module as Pure SQL Functions

**What:** Standalone module with pure functions accepting `sqlite3.Connection` and returning dicts. No ORM, no external dependencies.

**When to use:** Always -- the project uses raw SQLite everywhere.

**Example:**
```python
# Source: follows project convention of pure functions with Connection param
def get_total_pnl(conn: sqlite3.Connection) -> dict:
    """Aggregate total gross P&L, fees, net P&L, and trade count."""
    row = conn.execute("""
        SELECT
            COUNT(DISTINCT paper_arb_id) as trade_count,
            SUM(net_pnl_usd) as total_net_pnl,
            SUM(estimated_fees_usd) as total_fees,
            SUM(net_pnl_usd) + SUM(estimated_fees_usd) as total_gross_pnl
        FROM paper_trades
        WHERE leg NOT IN ('hedge')
    """).fetchone()
    return {
        "trade_count": row[0] or 0,
        "total_net_pnl": round(row[1] or 0.0, 4),
        "total_fees": round(row[2] or 0.0, 4),
        "total_gross_pnl": round(row[3] or 0.0, 4),
    }
```
[VERIFIED: raw SQLite query pattern used throughout codebase]

### Pattern 4: dry_run.py Integration Point

**What:** Insert paper trade simulation in `dry_run.py` after detection, before the existing `writer.enqueue(opp)` call.

**Integration point (line ~113-118 of dry_run.py):**
```python
# Existing code:
all_opps = yes_no_opps + cross_opps

# NEW: Paper trade simulation (Phase 5)
paper_trades = []
for opp in all_opps:
    if opp.opportunity_type == "yes_no":
        paper_trades.extend(simulate_yes_no(opp, cache, config))
    elif opp.opportunity_type == "cross_market":
        paper_trades.extend(simulate_cross_market(opp, cache, config))

for pt in paper_trades:
    paper_writer.enqueue(pt)

# Existing code continues:
for opp in all_opps:
    writer.enqueue(opp)
```
[VERIFIED: `dry_run.py` line 113 shows `all_opps = yes_no_opps + cross_opps`]

### Anti-Patterns to Avoid

- **Fetching fresh order books for paper trades:** D-02 explicitly forbids this. The 60 req/10s rate limit would be exhausted. Use `PriceCache` data only.
- **Modifying existing `trades` or `arb_pairs` tables:** Paper trades MUST be in a completely separate `paper_trades` table (D-04). Never mix paper and live data.
- **Adding stochastic fill probability:** D-07 explicitly locks on deterministic depth-gated model. No random components.
- **Creating a separate async task/runner:** D-01 specifies inline execution in the scan loop, not a separate background processor.
- **Mixing per-leg and per-arb P&L in summaries:** D-14 requires aggregation by `paper_arb_id` to count complete arb attempts.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| VWAP calculation | Custom VWAP function | `simulate_vwap()` from `engine.py` | Already handles dict + object access, partial depth, edge cases |
| Position sizing | Custom Kelly formula | `kelly_size()` from `kelly.py` | Modified Kelly with depth cap, floor, ceiling -- already tested |
| Fee calculation | Hardcoded fee rates | `get_taker_fee()` from `fee_model.py` | Category-aware, reads from BotConfig -- single source of truth |
| Category detection | Keyword matching | `get_market_category()` from `fee_model.py` | Tag-first, keyword-fallback -- already handles all categories |
| UUID generation | Custom ID scheme | `str(uuid.uuid4())` | Matches existing `arb_id` pattern in `execute_opportunity()` |
| Async SQLite writes | Synchronous inserts in scan loop | `AsyncWriter` pattern from `writer.py` | Non-blocking, bounded queue, graceful shutdown |

**Key insight:** Every computation needed for paper trading already exists as a tested pure function. The paper trading module is primarily an orchestrator that wires these together with cached data.

## Common Pitfalls

### Pitfall 1: PriceCache Stores Single-Level Data Only

**What goes wrong:** `simulate_vwap()` expects a list of ask levels (price, size pairs). `PriceCache` stores only one `MarketPrice` per token with `yes_ask` and `yes_depth` (best-level only). Passing the full cache entry to `simulate_vwap()` as-is would break.

**Why it happens:** `PriceCache` is designed for detection speed (O(1) lookups), not for full order book reconstruction. WebSocket and HTTP polling only store the best ask level.

**How to avoid:** Construct a single-element ask list from `MarketPrice`: `[{"price": mp.yes_ask, "size": mp.yes_depth}]`. This gives `simulate_vwap()` one level to work with. When `target_size_usd <= depth`, VWAP = best_ask (exact). When `target_size_usd > depth`, VWAP returns 1.0 (worst case), and `fill_ratio = depth / target_size` captures the partial fill.

**Warning signs:** `simulate_vwap()` returning 1.0 for every paper trade -- means target sizes consistently exceed cached depth.

### Pitfall 2: YES/NO P&L Needs Shares, Not Dollars

**What goes wrong:** Computing `gross_pnl = (1.0 - vwap_yes - vwap_no) * size_usd` gives wrong result. The formula in D-09 uses `size_filled_shares`, not USD.

**Why it happens:** `kelly_size()` returns USD, but payout is in shares. One share pays $1.00 on resolution.

**How to avoid:** Convert USD to shares: `shares = size_filled_usd / vwap_price`. For YES/NO: `yes_shares = size_filled_usd_yes / vwap_yes`, `no_shares = size_filled_usd_no / vwap_no`. For equal-dollar sizing, shares differ. D-09 formula: `gross_pnl = (1.0 - vwap_yes - vwap_no) * size_filled_shares` assumes equal shares on both sides. Need to determine whether to use min(yes_shares, no_shares) or a different approach.

**Warning signs:** Paper trade P&L numbers that don't match `net_spread * size` approximately.

### Pitfall 3: Cross-Market Hedge P&L Sign

**What goes wrong:** Recording hedge P&L with wrong sign. The hedge is a SELL at $0.01 of a token bought at higher price -- it's always a loss.

**Why it happens:** Confusing the hedge sale price with the payout value.

**How to avoid:** D-11 specifies: `net_pnl = -(fill_price - 0.01) * shares`. The loss is the difference between what was paid and the $0.01 recovery price. Each hedged leg is a separate `PaperTrade` row with `status='hedged'`.

**Warning signs:** Hedge legs showing positive P&L.

### Pitfall 4: Double-Counting Fees in Summary Queries

**What goes wrong:** Summing `estimated_fees_usd` across all legs including hedges gives inflated fee totals.

**Why it happens:** Hedge legs may have their own fee entry, or fees may be split across legs differently than expected.

**How to avoid:** D-14 says aggregate by `paper_arb_id`. Within each arb group, fees are computed per-leg at simulation time. The summary query should sum all `estimated_fees_usd` within the arb group for the total. Hedge legs should have `estimated_fees_usd = 0` since hedging at $0.01 is a fire-sale, not a normal trade (matching live behavior).

**Warning signs:** Total fees exceeding total gross P&L for profitable trades.

### Pitfall 5: Kelly Returns 0 for Thin Markets

**What goes wrong:** Most detected opportunities may produce `kelly_size() = 0.0`, resulting in no paper trades being recorded even though opportunities were detected.

**Why it happens:** Kelly requires `net_spread > 0` and `depth >= some threshold`. Thin markets (depth < $50) or tiny spreads will produce 0.0. The $5 minimum order floor also filters out small positions.

**How to avoid:** D-08 says skip when kelly returns 0.0 (same as live). This is correct behavior -- log a debug message when skipping so it's observable. The cycle summary line should include `paper_trades_simulated` and `paper_kelly_skips` counters.

**Warning signs:** Zero paper trades after many cycles despite detected opportunities.

### Pitfall 6: AsyncWriter Uses insert_opportunity -- Not insert_paper_trade

**What goes wrong:** Using the existing `AsyncWriter` instance for paper trades calls `insert_opportunity()` instead of `insert_paper_trade()`.

**Why it happens:** `AsyncWriter._worker()` hardcodes `insert_opportunity(self._conn, opportunity)` on line 81 of `writer.py`.

**How to avoid:** Either (a) create a `PaperTradeWriter` class (copy of `AsyncWriter` calling `insert_paper_trade()`) or (b) make `AsyncWriter` generic by accepting an insert function as a constructor parameter. Option (b) is cleaner but modifies existing code. Option (a) is safer -- small code duplication but zero risk to existing functionality. Recommendation: option (a) to avoid touching proven code.

**Warning signs:** Paper trades appearing in the `opportunities` table or `TypeError` from schema mismatch.

## Code Examples

### YES/NO Paper Trade Simulation
```python
# Source: derived from engine.py execute_opportunity() + D-09 formula
def simulate_yes_no(
    opp: ArbitrageOpportunity,
    cache: PriceCache,
    config: BotConfig,
) -> list[PaperTrade]:
    """Simulate a YES/NO arb. Returns 0 or 2 PaperTrade rows."""
    from bot.execution.engine import simulate_vwap
    from bot.execution.kelly import kelly_size
    from bot.detection.fee_model import get_taker_fee

    arb_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    # Build single-level ask lists from cached prices
    yes_price = cache.get(opp.yes_token_id)
    no_price = cache.get(opp.no_token_id)
    if not yes_price or not no_price:
        return []

    target_size = config.total_capital_usd * config.kelly_max_capital_pct
    yes_asks = [{"price": yes_price.yes_ask, "size": yes_price.yes_depth}]
    no_asks = [{"price": no_price.yes_ask, "size": no_price.yes_depth}]

    vwap_yes = simulate_vwap(yes_asks, target_size)
    vwap_no = simulate_vwap(no_asks, target_size)

    # Kelly sizing
    kelly_usd = kelly_size(
        net_spread=opp.net_spread,
        depth=opp.depth,
        target_size=target_size,
        total_capital=config.total_capital_usd,
        min_order_usd=config.kelly_min_order_usd,
        max_capital_pct=config.kelly_max_capital_pct,
    )
    if kelly_usd == 0.0:
        return []

    kelly_frac = kelly_usd / config.total_capital_usd

    # Depth-gated fill (D-07)
    yes_depth = yes_price.yes_depth
    no_depth = no_price.yes_depth
    yes_filled = min(kelly_usd, yes_depth)
    no_filled = min(kelly_usd, no_depth)
    yes_fill_ratio = yes_filled / kelly_usd if kelly_usd > 0 else 0.0
    no_fill_ratio = no_filled / kelly_usd if kelly_usd > 0 else 0.0

    # Fees (D-09)
    fee_rate = get_taker_fee(opp.category, config)
    yes_fees = fee_rate * yes_filled
    no_fees = fee_rate * no_filled

    # P&L (D-09): use min filled as effective shares
    effective_shares = min(yes_filled / vwap_yes, no_filled / vwap_no) if vwap_yes > 0 and vwap_no > 0 else 0.0
    gross_pnl = (1.0 - vwap_yes - vwap_no) * effective_shares
    total_fees = yes_fees + no_fees
    net_pnl = gross_pnl - total_fees

    # Allocate P&L proportionally to each leg
    yes_pnl = net_pnl / 2.0 if net_pnl != 0 else 0.0
    no_pnl = net_pnl / 2.0 if net_pnl != 0 else 0.0

    trades = []
    for leg_name, token_id, ask, filled, fill_ratio, vwap, fees, pnl, depth_avail in [
        ("yes", opp.yes_token_id, opp.yes_ask, yes_filled, yes_fill_ratio, vwap_yes, yes_fees, yes_pnl, yes_depth),
        ("no", opp.no_token_id, opp.no_ask, no_filled, no_fill_ratio, vwap_no, no_fees, no_pnl, no_depth),
    ]:
        status = "filled" if fill_ratio >= 1.0 else ("partial" if fill_ratio > 0 else "failed")
        trades.append(PaperTrade(
            paper_trade_id=str(uuid.uuid4()),
            paper_arb_id=arb_id,
            market_id=opp.market_id,
            market_question=opp.market_question,
            opportunity_type="yes_no",
            category=opp.category,
            leg=leg_name,
            side="BUY",
            token_id=token_id,
            ask_price=ask,
            simulated_size_usd=kelly_usd,
            size_filled_usd=filled,
            vwap_price=vwap,
            kelly_fraction=kelly_frac,
            estimated_fees_usd=fees,
            net_pnl_usd=pnl,
            depth_available=depth_avail,
            fill_ratio=fill_ratio,
            simulated_at=now,
            status=status,
        ))
    return trades
```

### Cross-Market Paper Trade Simulation
```python
# Source: derived from engine.py _execute_cross_market() + D-10/D-11/D-12
def simulate_cross_market(
    opp: ArbitrageOpportunity,
    cache: PriceCache,
    config: BotConfig,
) -> list[PaperTrade]:
    """Simulate a cross-market arb. Returns N leg rows + optional hedge rows."""
    from bot.execution.engine import simulate_vwap
    from bot.execution.kelly import kelly_size
    from bot.detection.fee_model import get_taker_fee

    arb_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    if not opp.legs:
        return []

    # Equal shares sizing (D-10)
    total_yes = sum(leg["ask"] for leg in opp.legs)
    target_size = config.total_capital_usd * config.kelly_max_capital_pct

    kelly_usd = kelly_size(
        net_spread=opp.net_spread,
        depth=opp.depth,
        target_size=target_size,
        total_capital=config.total_capital_usd,
        min_order_usd=config.kelly_min_order_usd,
        max_capital_pct=config.kelly_max_capital_pct,
    )
    if kelly_usd == 0.0:
        return []

    kelly_frac = kelly_usd / config.total_capital_usd
    target_shares = kelly_usd / total_yes

    fee_rate = get_taker_fee(opp.category, config)
    trades = []
    filled_legs = []

    for i, leg in enumerate(opp.legs):
        token_id = leg["token_id"]
        ask_price = leg["ask"]
        leg_depth = leg.get("depth", 0.0)
        leg_size_usd = ask_price * target_shares  # proportional

        # Single-level VWAP from cache
        cached = cache.get(token_id)
        if cached:
            asks = [{"price": cached.yes_ask, "size": cached.yes_depth}]
            vwap = simulate_vwap(asks, leg_size_usd)
            depth_avail = cached.yes_depth
        else:
            vwap = ask_price
            depth_avail = leg_depth

        # Depth-gated fill (D-07)
        filled_usd = min(leg_size_usd, depth_avail)
        fill_ratio = filled_usd / leg_size_usd if leg_size_usd > 0 else 0.0
        leg_fees = fee_rate * filled_usd

        if fill_ratio < 1.0:
            # Partial fill -- trigger hedge for all previously filled legs (D-11)
            trades.append(PaperTrade(
                paper_trade_id=str(uuid.uuid4()),
                paper_arb_id=arb_id,
                # ... partial/failed leg record
                status="partial" if fill_ratio > 0 else "failed",
                # ...
            ))
            # Hedge all previously filled legs
            for filled in filled_legs:
                hedge_pnl = -(filled["vwap"] - 0.01) * (filled["filled_usd"] / filled["vwap"])
                trades.append(PaperTrade(
                    # ... hedge record with status="hedged", net_pnl_usd=hedge_pnl
                ))
            break

        filled_legs.append({"token_id": token_id, "vwap": vwap, "filled_usd": filled_usd})
        leg_pnl = 0.0  # individual leg P&L calculated at arb level below
        trades.append(PaperTrade(
            paper_trade_id=str(uuid.uuid4()),
            paper_arb_id=arb_id,
            # ... filled leg record
            status="filled",
        ))

    # If all legs filled, compute arb P&L (D-12)
    if len(filled_legs) == len(opp.legs):
        gross_pnl = (1.0 - total_yes) * target_shares
        total_fees = sum(t.estimated_fees_usd for t in trades)
        net_pnl = gross_pnl - total_fees
        # Distribute net P&L evenly across legs
        per_leg_pnl = net_pnl / len(trades) if trades else 0.0
        for t in trades:
            t.net_pnl_usd = per_leg_pnl  # note: PaperTrade must NOT be frozen

    return trades
```

### Summary Query -- Win Rate by Type
```python
# Source: standard SQLite aggregation pattern
def get_win_rate(conn: sqlite3.Connection) -> dict:
    """Win rate by opportunity_type. A win = paper_arb_id group with sum(net_pnl_usd) > 0."""
    rows = conn.execute("""
        SELECT
            opportunity_type,
            COUNT(*) as total,
            SUM(CASE WHEN arb_pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM (
            SELECT paper_arb_id, opportunity_type, SUM(net_pnl_usd) as arb_pnl
            FROM paper_trades
            GROUP BY paper_arb_id, opportunity_type
        )
        GROUP BY opportunity_type
    """).fetchall()
    result = {}
    for opp_type, total, wins in rows:
        result[opp_type] = {
            "total": total,
            "wins": wins,
            "win_rate": round(wins / total, 4) if total > 0 else 0.0,
        }
    return result
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No paper trading | Phase 5 adds simulation | v1.2 | Can measure profitability before going live |
| Live VWAP uses fresh order books | Paper VWAP uses cached single-level data | v1.2 design | Trade-off: accuracy vs rate limit preservation |
| No cross-market execution simulation | Deterministic N-leg simulation with hedge | v1.2 design | Validates cross-market strategy viability |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `PaperTrade` dataclass should NOT be frozen (mutable) to allow P&L redistribution after all legs computed | Architecture Patterns | Minor -- could use a dict intermediary instead if frozen is preferred |
| A2 | Hedge legs should have `estimated_fees_usd = 0` since fire-sale at $0.01 | Pitfall 4 | Minor -- fees on hedge are negligible anyway |
| A3 | A separate `PaperTradeWriter` class (copy of `AsyncWriter`) is safer than making `AsyncWriter` generic | Pitfall 6 | Low risk -- small code duplication vs modifying proven code |
| A4 | Per-cycle paper trade summary log line is worth adding (Claude's discretion) | Architecture | None -- purely observability improvement |
| A5 | CLI entrypoint for querying summaries is NOT worth building in Phase 5 | Architecture | None -- summary functions can be called from Python REPL |

## Open Questions

1. **YES/NO equal-shares vs equal-dollars sizing**
   - What we know: D-09 says `gross_pnl = (1.0 - vwap_yes - vwap_no) * size_filled_shares`. Live execution uses `kelly_usd` for both legs (equal dollars, not equal shares).
   - What's unclear: Should paper trading mirror live execution exactly (equal dollars per leg), or use equal shares (which would require different dollar amounts per leg)?
   - Recommendation: Mirror live execution -- use same `kelly_usd` for both YES and NO legs. Compute `effective_shares = min(yes_shares, no_shares)` for P&L since the excess shares on one side are not hedged.

2. **PaperTrade mutability for P&L distribution**
   - What we know: Cross-market P&L is only known after all legs complete. Individual leg rows are created as we iterate.
   - What's unclear: Whether to use a mutable dataclass, build dicts first and convert, or compute P&L in a second pass.
   - Recommendation: Use a regular (non-frozen) dataclass for `PaperTrade` and update `net_pnl_usd` in a second pass. This is the simplest approach.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pytest.ini` (asyncio_mode = auto) |
| Quick run command | `python -m pytest tests/test_paper_trading.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PAPER-01 | simulate_yes_no() computes VWAP + Kelly from cached prices | unit | `python -m pytest tests/test_paper_simulator.py::test_simulate_yes_no_basic -x` | No -- Wave 0 |
| PAPER-01 | simulate_yes_no() returns [] when kelly returns 0 | unit | `python -m pytest tests/test_paper_simulator.py::test_simulate_yes_no_kelly_skip -x` | No -- Wave 0 |
| PAPER-01 | simulate_cross_market() computes VWAP + Kelly for N legs | unit | `python -m pytest tests/test_paper_simulator.py::test_simulate_cross_market_basic -x` | No -- Wave 0 |
| PAPER-02 | init_paper_trades_table() creates table and indexes | unit | `python -m pytest tests/test_paper_storage.py::test_init_paper_trades_table -x` | No -- Wave 0 |
| PAPER-02 | insert_paper_trade() inserts row correctly | unit | `python -m pytest tests/test_paper_storage.py::test_insert_paper_trade -x` | No -- Wave 0 |
| PAPER-02 | paper_trades table is isolated from trades table | unit | `python -m pytest tests/test_paper_storage.py::test_table_isolation -x` | No -- Wave 0 |
| PAPER-03 | Paper trade record has all 18+ required fields | unit | `python -m pytest tests/test_paper_simulator.py::test_paper_trade_fields -x` | No -- Wave 0 |
| PAPER-04 | Cross-market partial fill triggers hedge for filled legs | unit | `python -m pytest tests/test_paper_simulator.py::test_cross_market_partial_hedge -x` | No -- Wave 0 |
| PAPER-04 | Cross-market full fill computes correct arb P&L | unit | `python -m pytest tests/test_paper_simulator.py::test_cross_market_full_fill_pnl -x` | No -- Wave 0 |
| PAPER-05 | get_total_pnl() returns correct aggregates | unit | `python -m pytest tests/test_paper_summary.py::test_get_total_pnl -x` | No -- Wave 0 |
| PAPER-05 | get_win_rate() by opportunity type | unit | `python -m pytest tests/test_paper_summary.py::test_get_win_rate -x` | No -- Wave 0 |
| PAPER-05 | get_avg_spread() by category | unit | `python -m pytest tests/test_paper_summary.py::test_get_avg_spread -x` | No -- Wave 0 |
| PAPER-05 | get_category_breakdown() returns per-category stats | unit | `python -m pytest tests/test_paper_summary.py::test_get_category_breakdown -x` | No -- Wave 0 |
| PAPER-01 | dry_run.py integration: paper trades created during scan cycle | integration | `python -m pytest tests/test_dry_run.py::test_paper_trade_integration -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_paper_simulator.py tests/test_paper_storage.py tests/test_paper_summary.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_paper_simulator.py` -- covers PAPER-01, PAPER-03, PAPER-04
- [ ] `tests/test_paper_storage.py` -- covers PAPER-02
- [ ] `tests/test_paper_summary.py` -- covers PAPER-05
- [ ] Framework install: none needed -- pytest 9.0.2 already installed

## Security Domain

Security enforcement is not explicitly set to `false` in config, so including this section.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- paper trading has no auth (uses existing bot session) |
| V3 Session Management | No | N/A -- no sessions in paper trading |
| V4 Access Control | No | N/A -- single-user bot, no access control needed |
| V5 Input Validation | Yes | Validate cached price data is non-negative, non-NaN before simulation; validate opportunity fields before insertion |
| V6 Cryptography | No | N/A -- no crypto operations in paper trading |

### Known Threat Patterns for SQLite + Pure Python

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via market_question text | Tampering | Parameterized queries (already used -- `?` placeholders in all SQL) |
| NaN/Inf price corruption | Tampering | Existing `math.isfinite()` checks in normalizer.py + ws_client.py; paper simulator should also validate |
| Integer overflow in P&L calculation | Tampering | Python handles arbitrary precision; SQLite REAL is 64-bit float -- sufficient |

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/bot/execution/engine.py` -- `simulate_vwap()` signature, `ExecutionResult` dataclass, `_execute_cross_market()` pattern
- Codebase inspection: `src/bot/execution/kelly.py` -- `kelly_size()` signature, edge case handling
- Codebase inspection: `src/bot/detection/fee_model.py` -- `get_taker_fee()`, `get_market_category()` signatures
- Codebase inspection: `src/bot/detection/opportunity.py` -- `ArbitrageOpportunity` dataclass fields
- Codebase inspection: `src/bot/storage/schema.py` -- `init_trades_table()`, `insert_trade()`, `init_arb_pairs_table()` patterns
- Codebase inspection: `src/bot/storage/writer.py` -- `AsyncWriter` class pattern
- Codebase inspection: `src/bot/scanner/price_cache.py` -- `PriceCache`, `MarketPrice` dataclass (single-level only)
- Codebase inspection: `src/bot/dry_run.py` -- scan loop structure, integration point at line 113
- Codebase inspection: `src/bot/config.py` -- `BotConfig` frozen dataclass fields
- Codebase inspection: `src/bot/scanner/ws_client.py` -- confirms PriceCache stores best-level only
- Codebase inspection: `tests/conftest.py` -- `bot_config` fixture pattern
- Codebase inspection: `tests/test_storage.py` -- test pattern for schema functions

### Secondary (MEDIUM confidence)
- Phase 5 CONTEXT.md -- all locked decisions (D-01 through D-15)
- Phase 5 REQUIREMENTS.md -- PAPER-01 through PAPER-05

### Tertiary (LOW confidence)
- None -- all findings verified from codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all components verified in codebase
- Architecture: HIGH -- follows established patterns exactly, integration points verified
- Pitfalls: HIGH -- identified from direct code inspection of PriceCache, engine.py, schema.py

**Research date:** 2026-04-26
**Valid until:** 2026-05-26 (stable -- no external dependencies to go stale)
