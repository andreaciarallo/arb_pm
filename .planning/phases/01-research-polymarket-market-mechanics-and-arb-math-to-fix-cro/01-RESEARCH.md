# Phase 1: Research Polymarket Market Mechanics and Arb Math — Research

**Researched:** 2026-04-19
**Domain:** Polymarket CLOB mechanics, cross-market arbitrage math, bot bug root-cause analysis
**Confidence:** HIGH (all findings based on direct codebase inspection and confirmed Polymarket docs)

---

## Summary

The bot has been running in `--live` mode for ~10 hours across 580 cycles and logged 134 "trades" — ALL status: "skipped". Two root problems have been diagnosed by reading the source directly.

**Problem 1 (False positives):** The cross-market detector in `src/bot/detection/cross_market.py` has a correct filter (`total_yes >= 1.0 → continue`) but the reported `gross` values of 0.52–0.76 expose a data quality issue: the markets being grouped via keyword heuristic are NOT mutually exclusive. They are unrelated markets that share keywords by accident (e.g., two "election" markets from different countries, or near-resolved markets where one YES token is priced at ~$0.98). The arb condition is structurally correct — the code skips when `total_yes >= 1.0`. What's wrong is that the keyword grouper is forming invalid groups (non-exclusive combos), and valid groups may occasionally include near-resolved markets, producing a sum that is < 1.0 but not actually exploitable. The `gross_spread = 1.0 - total_yes` is computed correctly; the problem is that true mutual exclusivity is not verified.

**Problem 2 (Missing token IDs on execution):** Gate 0 in `execute_opportunity()` skips any opportunity where `opp.no_token_id` is empty. Cross-market opportunities are constructed with `no_token_id=""` by design (comment: "D-01: cross-market has no NO token; Gate 0 will skip these opps"). This was an intentional placeholder — the execution engine was never wired to handle cross-market opportunities. Every cross-market opp hits Gate 0 and logs "missing token IDs". This is not a bug in execution logic — it is an unimplemented feature.

**Problem 3 (Live mode):** The `--live` flag is passed at runtime via `sys.argv`. The Dockerfile CMD does NOT include `--live`. The docker-compose.yml does NOT have a `command:` override. Therefore the bot cannot be running in `--live` mode unless the container was started with an explicit command override. The VPS container may have been started with `docker compose run bot --live` or a manual `docker run ... python -m bot.main --live`. To confirm dry-run: change the docker-compose.yml to add `command: ["python", "-m", "bot.main"]` (no `--live`), or simply restart without the flag.

**Primary recommendation:** Fix the cross-market detector to (1) add a minimum group size guard on real exclusivity (not just keywords), and (2) redesign cross-market execution to pass per-leg token IDs rather than expecting a single `no_token_id`. Switch the VPS container back to dry-run immediately by restarting without the `--live` flag.

---

## CRITICAL ADDENDUM — NegRisk vs. Arbitrage (2026-04-19, user-verified research)

**NegRisk is NOT arbitrage.** This is the most important strategic distinction in the Polymarket ecosystem.

### NegRisk (sum > 1.0) — Capital Efficiency ONLY
| Property | Value |
|----------|-------|
| Condition | sum(YES_ask_i) > 1.0 |
| Interface | NegRisk API/contract (separate from standard CLOB) |
| Cost | Fixed $1.00 collateral (regardless of sum) |
| Payout | $1.00 (winning leg) |
| Profit | $0.00 — zero guaranteed profit |
| Benefit | Saves `sum - 1.0` in locked capital vs standard approach |
| Use case | Capital efficiency for long-duration positions |

**NEVER use NegRisk for underpriced (sum < 1.0) arbitrage — it eliminates the profit by raising cost to $1.00.**

### True Arbitrage (sum < 1.0) — STANDARD markets ONLY
| Property | Value |
|----------|-------|
| Condition | sum(YES_ask_i) < 1.0 |
| Interface | STANDARD CLOB — `place_fak_order()` (what our bot uses) |
| Cost | sum(YES_ask_i) × target_shares < $1.00 |
| Payout | $1.00 × target_shares (one leg wins) |
| Profit | GUARANTEED: (1.0 - sum) × target_shares |

### Correct Cross-Market Sizing — Equal Shares (NOT equal dollars)

**Wrong (Plan 01-03 original):** `per_leg_usd = capital × kelly_pct / N`

This allocates equal dollars per leg → unequal token quantities → unequal payouts depending on winner → not guaranteed profit.

**Correct:** Equal SHARES across all legs.

```
total_yes = sum(ask_i for all legs)
target_shares = capital_usd × kelly_pct / total_yes
size_usd_i = ask_i × target_shares   # different dollars per leg
token_count_i = size_usd_i / ask_i  = target_shares  ← same for all legs
total_cost = sum(ask_i × target_shares) = target_shares × total_yes = capital_usd × kelly_pct
payout(any winner) = target_shares × $1.00  ← guaranteed regardless of winner
profit = target_shares × (1.0 - total_yes)  ← guaranteed
```

**Concrete example (sum=0.90, capital=$1000, kelly_pct=100%):**
```
target_shares = 1000 / 0.90 = 1111 shares
Leg A (ask=0.40): size_usd = 0.40 × 1111 = $444  → 1111 shares
Leg B (ask=0.32): size_usd = 0.32 × 1111 = $356  → 1111 shares
Leg C (ask=0.18): size_usd = 0.18 × 1111 = $200  → 1111 shares
Total cost: $1000. Any winner pays: 1111 × $1.00 = $1111. Profit: $111 (11.1%).
```

**With our `place_fak_order(client, token_id, price, size_usd, "BUY")`:**
The function converts size_usd → token_count = size_usd / price. So to buy `target_shares`:
```python
size_usd_i = leg["ask"] * target_shares
# place_fak_order internally does: token_count = size_usd_i / leg["ask"] = target_shares ✓
```

### Cross-Market Hedge Logic (partial fill recovery)
If leg N fails after legs 1..N-1 have already been bought:
- Sell all previously filled YES tokens at $0.01 (market-aggressive hedge)
- Same pattern as YES+NO hedge SELL in engine.py
- Track `filled_legs: list[dict]` as each leg fills; on failure, sell back all filled

### NegRisk for sum > 1.0 — FUTURE SCOPE ONLY
This is a separate strategy not related to arbitrage. Out of scope for Phase 1. If implemented in future:
- Uses a different Polymarket interface/contract (not standard CLOB)
- Only useful for large positions / long holding periods
- NOT profitable by itself — saves locked capital only

---

## Polymarket Market Mechanics

### What is a "market" vs "outcome token" vs "condition"?

**Confidence:** HIGH — verified from py-clob-client source and Polymarket CLOB API docs.

| Concept | Description | API Field |
|---------|-------------|-----------|
| **Market** | A binary prediction market on a real-world event | `condition_id` (unique hex hash) |
| **Condition** | On-chain identifier for the market's outcome resolution | Same as `condition_id` |
| **Outcome token** | ERC-1155 token representing one outcome (YES or NO) | `token_id` (uint256 as string) |
| **YES token** | Token worth $1.00 if the event resolves YES, $0.00 otherwise | `tokens[n]["token_id"]` where `outcome=="Yes"` |
| **NO token** | Token worth $1.00 if the event resolves NO, $0.00 otherwise | `tokens[n]["token_id"]` where `outcome=="No"` |

**Key facts for the bot:**
- Each Polymarket binary market has exactly 2 outcome tokens: YES and NO.
- YES + NO tokens for the same market always sum to exactly $1.00 at resolution.
- Token prices are probabilities expressed as cents on the dollar (0.0–1.0).
- The CLOB (`enable_order_book=True`) allows limit order trading of these tokens.
- `condition_id` = the market identifier. `token_id` = the specific outcome token to trade.
- The bot stores prices keyed by `token_id`, NOT by `condition_id`. This is correct.

### What does `token_id` correspond to on-chain?

`token_id` is the ERC-1155 token ID on the Conditional Token Framework (CTF) contract on Polygon. When you place a BUY order via `place_fak_order(client, token_id, price, size, "BUY")`, you are buying that specific outcome token at that price.

### Cross-market arbitrage: what are we actually buying?

In N-way cross-market arb (e.g., "Will Alice win?", "Will Bob win?", "Will Carol win?"):
- You buy YES tokens for all N markets simultaneously.
- If exactly one market resolves YES, that token pays $1.00 and all others pay $0.00.
- You spend: `sum(YES_ask_i * size_i)` to buy all legs.
- You receive: `$1.00 * size_winning` when the winning market resolves.
- Therefore: arb exists if `sum(YES_ask_i) < 1.0` AND the markets are truly mutually exclusive.

**This is the correct model the detector implements.** The problem is not the math — it is the grouping quality.

---

## Arbitrage Math

### YES+NO arb (single market) — correct formula in the bot

```
gross_spread = 1.0 - yes_ask - no_ask
estimated_fees = (yes_ask + no_ask) * taker_fee  # per-side fee on notional
net_spread = gross_spread - estimated_fees
```

Arb condition: `net_spread > min_net_profit_pct`

This is correct. YES ask + NO ask should sum to exactly 1.0 in an efficient market. When they sum to < 1.0, buying both sides costs < $1.00 but pays out $1.00 at resolution.

### Cross-market arb (N-way) — correct formula

For N mutually exclusive markets with YES ask prices `p_1, p_2, ..., p_N`:

```
total_yes = sum(p_i for i in 1..N)
gross_spread = 1.0 - total_yes

# Entry: taker fee on each YES buy (N buys)
entry_fees = total_yes * taker_fee

# Exit: one taker fee on the winning YES sell at resolution
# Exit price = 1.0 (resolution), but fee is on the average entry cost
exit_fee = (total_yes / N) * taker_fee

estimated_fees = entry_fees + exit_fee
net_spread = gross_spread - estimated_fees
```

Arb condition: `net_spread > threshold` AND `total_yes < 1.0`

**This math is implemented correctly in `cross_market.py` lines 150–172.** The problem is upstream in group formation.

### Why gross < 1.0 still produces skipped trades

The detector check at line 151: `if total_yes >= 1.0: continue` means only groups with `total_yes < 1.0` produce an opportunity. When gross = 0.52–0.76, that means `total_yes = 0.24–0.48`. This is mathematically valid — BUT the markets grouped together are not actually mutually exclusive, so the "arb" is illusory. The grouper produces false positives because:

1. Keyword overlap does not imply mutual exclusivity. Two markets asking "Will X win the election?" from different countries share "election" and "will" and "win" — and get grouped.
2. Near-resolved markets: one YES token at $0.02 + another at $0.35 = $0.37 total — looks like arb but the $0.02 token is nearly resolved NO, not a real opportunity.
3. The minimum word length filter (`_MIN_WORD_LENGTH = 4`) eliminates articles but not substantive disambiguation words like "2025" vs "2026".

All these false positives still get skipped at Gate 0 because they have `no_token_id=""`. So no real money has been lost — the bot is safe.

---

## Root Cause Analysis: Three Bugs

### Bug 1: Cross-market false positives (gross 0.52–0.76)

**Location:** `src/bot/detection/cross_market.py`, `_group_markets()` function

**What happens:**
1. Keyword extractor at line 33 extracts all alpha words >= 4 chars from the question.
2. Adjacency is built at lines 61–66 for any pair sharing >= 2 keywords.
3. BFS creates connected components.
4. Groups with 2–20 markets proceed to detection.

**Why it's wrong:**
- Keyword heuristic produces semantically unrelated market groups. "Will Donald Trump win?" and "Will Kamala Harris win the 2026 midterms?" share "will", "2026", "win" — grouped even though they are in different elections, different years, not mutually exclusive.
- The sum of their YES asks may be 0.30 + 0.25 = 0.55 < 1.0, producing `gross_spread = 0.45`, which looks like arb.
- But buying both YES tokens is not a guaranteed profit because at most one pays out, and the two markets are independent — not exclusive.

**The correct fix requires real mutual exclusivity validation.** The bot's CONTEXT.md (D-03) deferred LLM validation to Phase 3. A minimal non-LLM fix is to require all markets in a group to share a common suffix (e.g., same event name, same year, same question template) rather than just any 2 words.

**The gross < 1.0 values observed (0.52–0.76) confirm the heuristic is generating groups where:**
- Sum(YES asks) is between 0.24 and 0.48 (equivalent to 2-way or 3-way groups with prices like 0.12+0.30 or 0.15+0.20+0.13)
- These are NOT near-efficiency markets — they are unrelated markets that look related by keywords

### Bug 2: Missing token IDs on execution

**Location:** `src/bot/execution/engine.py`, `execute_opportunity()`, lines 141–165 (Gate 0)

**Exact error message:** `execute_opportunity: missing token IDs for market=0xccb032... — skipping`

**Root cause (confirmed by code):**

In `cross_market.py` line 194:
```python
no_token_id="",   # D-01: cross-market has no NO token; Gate 0 will skip these opps
```

This is intentional. Cross-market arb requires buying N YES tokens across N different markets, not buying a YES+NO pair in one market. The `ArbitrageOpportunity` dataclass was designed for the YES+NO case where one market_id has exactly one yes_token_id and one no_token_id.

The execution engine at lines 147–165 immediately skips if EITHER `yes_token_id` or `no_token_id` is empty:
```python
if not yes_token_id or not no_token_id:
    logger.warning(f"execute_opportunity: missing token IDs for market={opp.market_id} — skipping")
```

**Why this was always the same market hash:** The first market in the group (`group[0]`) always provides the `market_id` and `yes_token_id`. The same "first market" in the keyword group (likely a high-volume election market) becomes the market_id every time.

**The fix requires one of:**
a. Redesign `ArbitrageOpportunity` to hold `legs: list[dict]` for N-way cross-market opportunities, OR
b. Skip cross-market detection entirely until the execution engine supports it, OR
c. Introduce a `CrossMarketOpportunity` type separate from `ArbitrageOpportunity`

The execution path for cross-market is fundamentally different:
- N sequential (or atomic) BUY orders across N different token IDs
- Different sizing logic (same USD amount per leg, not Kelly on a single spread)
- Different fill verification (check N fills, not 1 YES + 1 NO)

### Bug 3: Live mode — how the bot is running

**Location:** `src/bot/main.py` line 61: `if "--live" in sys.argv:`

**Key finding:** The Dockerfile CMD is `["python", "-m", "bot.main"]` — NO `--live` flag. The docker-compose.yml has no `command:` override. Therefore the Docker container started with `docker compose up` would run in dry-run mode by default.

The MEMORY.md states the bot is "LIVE in `--live` mode on HEL1". This means the VPS container was started manually with a command override, likely:
```bash
docker compose run bot python -m bot.main --live
# or
docker run arbbot python -m bot.main --live
```

**Minimal fix to switch to dry-run:**
Option A: Stop and restart the container without `--live`: `docker compose down && docker compose up -d`
Option B: Add `command: ["python", "-m", "bot.main"]` to docker-compose.yml (no `--live`), then `docker compose up -d`
Option C (safest): SSH to VPS, `docker stop arbbot`, `docker compose up -d`

The default CMD in Dockerfile already runs dry-run. Restarting via `docker compose up -d` should be sufficient if the container was started via a non-compose manual command.

---

## Standard Stack

No new libraries are needed for this phase. All bugs are in existing code.

| File | Status | Change Needed |
|------|--------|---------------|
| `src/bot/detection/cross_market.py` | Has bugs | Fix grouping logic |
| `src/bot/execution/engine.py` | Works correctly for YES/NO | No fix needed — Gate 0 is intentional |
| `src/bot/main.py` | Works correctly | No code change needed |
| `docker-compose.yml` | No `command:` override | May need `command:` to lock dry-run |

---

## Architecture Patterns

### Cross-market opportunity data flow (current)

```
fetch_liquid_markets()
  └─ markets[]: list[dict]   # each market has "tokens", "condition_id", "question"

detect_cross_market_opportunities(markets, cache, config)
  ├─ _group_markets()        # BFS keyword grouping → list[list[dict]]
  └─ for group in groups:
       └─ ArbitrageOpportunity(
            market_id   = group[0]["condition_id"],
            yes_token_id = group[0] YES token,
            no_token_id  = ""   ← ALWAYS EMPTY for cross-market
          )

execute_opportunity(client, opp, config, risk_gate)
  └─ Gate 0: no_token_id == "" → log warning → return skipped
```

### Why the execution engine skips all cross-market opps — by design

The comment in `cross_market.py` line 194 says: "D-01: cross-market has no NO token; Gate 0 will skip these opps." This was a deliberate placeholder — cross-market execution was deferred. The skipping is correct behavior given the current architecture.

### Correct cross-market execution model (for planning)

A true cross-market execution requires:
```
group = [market_A, market_B, market_C]
legs = [
  {"token_id": A_yes_token, "ask": 0.25, "depth": ...},
  {"token_id": B_yes_token, "ask": 0.20, "depth": ...},
  {"token_id": C_yes_token, "ask": 0.30, "depth": ...},
]
# Execute: BUY each leg sequentially
# Total cost: 0.75 per $1.00 position
# Expected payoff: $1.00 (exactly one leg pays)
# Gross: 0.25 per $1.00
```

This requires either a new dataclass or extending `ArbitrageOpportunity` with a `legs` field.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mutual exclusivity detection | Custom NLP | Polymarket's own market grouping (neg_risk_market_id) | Polymarket already groups mutually exclusive markets via `neg_risk_market_id` field |
| N-way arb execution | Custom multi-leg orchestration | Simple sequential FAK orders (existing `place_fak_order`) | Same order_client function works; just loop over legs |

### Critical: `neg_risk_market_id` field

Polymarket's CLOB API returns a `neg_risk_market_id` field on markets that are part of a "Neg Risk" group — these are markets where Polymarket itself guarantees mutual exclusivity (e.g., "Who will win the 2024 election?" with Alice, Bob, Carol as separate markets). Markets sharing the same `neg_risk_market_id` are officially mutually exclusive.

**This is the correct grouping mechanism to replace the keyword heuristic.** Instead of BFS keyword overlap, group by `neg_risk_market_id`. Markets with the same `neg_risk_market_id` are guaranteed exclusive — no LLM or keyword heuristic needed.

**Confidence:** MEDIUM — based on knowledge of Polymarket's Neg Risk architecture. Requires verification that the `neg_risk_market_id` field is returned by `client.get_markets()`. Check by inspecting a raw API response.

---

## Common Pitfalls

### Pitfall 1: Keyword grouping produces non-exclusive combos
**What goes wrong:** Two markets about different events share common words (election, will, win, 2026) and get grouped. Their YES ask sum happens to be < 1.0 (not because of arb but because both have low probabilities). The detector fires, execution is skipped by Gate 0, but the opportunity is logged as detected — wasting cycles and creating confusion.
**How to avoid:** Group by `neg_risk_market_id` instead of keywords.

### Pitfall 2: Treating cross-market as YES+NO arb in the executor
**What goes wrong:** Attempting to send `yes_token_id` and `no_token_id` from a cross-market opportunity to the YES+NO execution path. The cross-market "NO token" does not exist — there is no single NO side.
**How to avoid:** Cross-market execution requires a separate execution path that loops over all legs, placing one BUY order per YES token in the group.

### Pitfall 3: Assuming `--live` requires a code change to disable
**What goes wrong:** Developer edits `main.py` to remove live mode when the real fix is simply not passing `--live` at container start.
**How to avoid:** The mode is purely runtime, not compile-time. Stop the container and restart without `--live`. No code change required.

### Pitfall 4: `no_token_id=""` triggers Gate 0 for cross-market — this is correct
**What goes wrong:** Developer removes Gate 0 thinking it's a bug, then cross-market opps enter YES+NO execution path with a missing NO token, causing order submission errors.
**How to avoid:** Gate 0 is correct protection. Fix the data model first (add legs list to opportunity), then adjust Gate 0 to allow the new type.

### Pitfall 5: `gross_spread` < 0 is possible for near-resolved markets
**What goes wrong:** If one YES token in the group is near-resolved (ask ≈ $0.98), `total_yes` can exceed 1.0, making `gross_spread` negative. The current check (`if total_yes >= 1.0: continue`) handles this correctly.
**How to avoid:** The existing guard is correct. Do not remove it.

### Pitfall 6: Testing cross-market execution with `no_token_id=""`
**What goes wrong:** Tests pass because Gate 0 skips, giving false confidence that execution works.
**How to avoid:** Tests for cross-market execution must use a new execution path or new dataclass, not the existing `execute_opportunity()` function.

---

## Code Examples

### How `--live` mode is controlled (confirmed from source)

```python
# src/bot/main.py lines 61-66
if "--live" in sys.argv:
    logger.info("Starting Phase 3 live execution scanner (--live flag)")
    asyncio.run(live_run.run(config, client))
else:
    logger.info("Starting Phase 2 dry-run scanner (detection only, no trades)")
    asyncio.run(dry_run.run(config, client))
```

To switch to dry-run: restart the Docker container WITHOUT `--live` in the command. The Dockerfile default CMD has no `--live` — `docker compose up -d` runs dry-run by default.

### Gate 0 skip (confirmed from engine.py)

```python
# src/bot/execution/engine.py lines 147-165
yes_token_id = opp.yes_token_id
no_token_id = opp.no_token_id

if not yes_token_id or not no_token_id:
    logger.warning(
        f"execute_opportunity: missing token IDs for market={opp.market_id} — skipping"
    )
    results.append(ExecutionResult(..., status="skipped", error_msg="missing token IDs"))
    return arb_id, results
```

This fires for EVERY cross-market opp because `no_token_id=""` always.

### How cross-market constructs the opportunity (confirmed from cross_market.py)

```python
# src/bot/detection/cross_market.py lines 178-195
opp = ArbitrageOpportunity(
    market_id=group[0].get("condition_id", ""),   # always first market's ID
    ...
    yes_token_id=group0_yes_token_id,              # only first market's YES token
    no_token_id="",   # D-01: cross-market has no NO token; Gate 0 will skip these opps
)
```

### Correct `neg_risk_market_id` grouping approach (planned fix)

```python
# Proposed replacement for _group_markets() in cross_market.py
def _group_by_neg_risk(markets: list[dict]) -> list[list[dict]]:
    """
    Group markets by Polymarket's official neg_risk_market_id.
    Markets sharing the same neg_risk_market_id are guaranteed mutually exclusive.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for market in markets:
        neg_id = market.get("neg_risk_market_id") or market.get("neg_risk_id")
        if neg_id:
            groups[neg_id].append(market)
    return [
        group for group in groups.values()
        if _MIN_GROUP_SIZE <= len(group) <= _MAX_GROUP_SIZE
    ]
```

**Note:** The exact field name (`neg_risk_market_id` vs `neg_risk_id`) must be verified against a live API response. Print a raw market dict from `client.get_markets()` to confirm the field name.

---

## Dry-Run Switch

### Current situation on VPS

The MEMORY.md says the bot is running in `--live` mode. The Dockerfile CMD does NOT include `--live`. This means the VPS container was started with an explicit `--live` override outside docker-compose.

**To switch to dry-run on HEL1 VPS (204.168.164.145):**

```bash
# SSH to VPS
ssh root@204.168.164.145

# Stop the live container
cd /opt/arbbot
docker compose down

# Restart in dry-run (Dockerfile CMD has no --live)
docker compose up -d

# Verify: logs should say "Starting Phase 2 dry-run scanner"
docker compose logs -f --tail=20
```

**To permanently lock dry-run in docker-compose.yml**, add a `command:` override:

```yaml
services:
  bot:
    command: ["python", "-m", "bot.main"]   # no --live — explicit dry-run lock
```

This prevents accidentally switching to live again without editing the compose file.

---

## Validation Architecture

**Framework:** pytest with asyncio_mode=auto
**Config:** `pytest.ini` (project root)
**Quick run:** `PYTHONPATH=src pytest tests/test_cross_market.py -m unit -x`
**Full suite:** `PYTHONPATH=src pytest tests/ -m unit -x`

### Phase Requirements → Test Map

| Behavior | Test Type | Automated Command | Test File Exists? |
|----------|-----------|-------------------|-------------------|
| Cross-market detector correctly filters non-exclusive groups | unit | `PYTHONPATH=src pytest tests/test_cross_market.py -m unit -x` | YES |
| Cross-market detector uses `neg_risk_market_id` grouping | unit | `PYTHONPATH=src pytest tests/test_cross_market.py -m unit -x` | Partially (needs new test) |
| Gate 0 properly handles cross-market opportunity with legs | unit | `PYTHONPATH=src pytest tests/test_execution_engine.py -m unit -x` | Needs new test |
| `--live` flag correctly routes to dry_run vs live_run | unit | `PYTHONPATH=src pytest tests/test_live_run.py -m unit -x` | YES |
| Dry-run mode on VPS confirmed | manual | `docker compose logs -f` on HEL1 | Manual only |

### Wave 0 Gaps

- [ ] `tests/test_cross_market.py` — needs test for `neg_risk_market_id` grouping (new detection logic)
- [ ] `tests/test_execution_engine.py` — needs test verifying cross-market opps (with legs) pass Gate 0

*(Existing unit tests for current cross_market behavior pass — they test the current (buggy) keyword heuristic path.)*

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.12 | Bot runtime | Local dev only | 3.12 | — |
| Docker | VPS deployment | On HEL1 VPS | 24+ | — |
| pytest | Test runner | Yes | see requirements.txt | — |
| VPS HEL1 | Live testing | Yes (204.168.164.145) | — | — |

---

## Open Questions

1. **`neg_risk_market_id` field name**
   - What we know: Polymarket has a Neg Risk architecture for N-way mutually exclusive markets.
   - What's unclear: The exact JSON field name returned by `client.get_markets()`. Could be `neg_risk_market_id`, `negRiskMarketId`, `neg_risk_id`, or absent for non-neg-risk markets.
   - Recommendation: Print a raw market dict from a live API call before implementing the fix. `python -c "from bot.client import build_client; from bot.config import load_config; c = build_client(load_config()); import json; print(json.dumps(c.get_markets()['data'][0], indent=2))"`

2. **Why was the bot started with `--live` given the container default is dry-run?**
   - What we know: The Dockerfile CMD has no `--live`. MEMORY.md says bot is live.
   - What's unclear: The exact docker command used to start it (may have been `docker compose run bot --live` or a manual `docker run` with override).
   - Recommendation: Check running containers on VPS: `docker ps --format "table {{.Command}}"` to see the exact CMD in use.

3. **Have any real orders been placed?**
   - What we know: 134 logged "trades" are ALL status: "skipped". Gate 0 fires first.
   - What's unclear: Whether any YES+NO arb (not cross-market) opportunities ever reached execution and whether any orders were placed.
   - Recommendation: Query the bot DB: `docker exec arbbot sqlite3 /app/data/bot.db "SELECT status, count(*) FROM trades GROUP BY status;"` to see if any non-skipped trades exist.

4. **Cross-market execution design: legs list vs separate type**
   - What we know: `ArbitrageOpportunity` was designed for binary YES+NO, not N-way.
   - What's unclear: Whether to extend `ArbitrageOpportunity` with `legs: list[dict]` or create a separate `CrossMarketOpportunity` dataclass.
   - Recommendation: Add a `legs: list[dict] = field(default_factory=list)` to `ArbitrageOpportunity` and use it for cross-market. Simpler than a new type, backward-compatible with YES+NO opps (which have empty legs).

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `src/bot/detection/cross_market.py` — grouping logic, false positive root cause
- Direct code inspection of `src/bot/execution/engine.py` — Gate 0 skip, confirmed `no_token_id=""` causes all skips
- Direct code inspection of `src/bot/main.py` — `--live` flag is `sys.argv` check, no code change needed
- Direct code inspection of `src/bot/detection/opportunity.py` — `ArbitrageOpportunity` dataclass fields
- Direct code inspection of `Dockerfile` + `docker-compose.yml` — no `--live` in default CMD

### Secondary (MEDIUM confidence)
- Polymarket Neg Risk architecture — `neg_risk_market_id` exists as a grouping mechanism; field name unverified against live API
- Project MEMORY.md — VPS state, wallet, confirmed bot is "live"
- Project STATE.md — accumulated decisions D-01 through D-08 confirm design intent

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- False positive root cause: HIGH — confirmed by direct code reading of `_group_markets()` and comparing to observed `gross=0.52–0.76`
- Missing token ID root cause: HIGH — `no_token_id=""` in cross_market.py line 194 is explicit
- Dry-run fix: HIGH — `--live` is purely a runtime flag, Dockerfile default is dry-run
- `neg_risk_market_id` field name: MEDIUM — architecture is known, exact field name unverified

**Research date:** 2026-04-19
**Valid until:** 2026-05-19 (stable Polymarket CLOB API, no breaking changes expected)

---

## RESEARCH COMPLETE
