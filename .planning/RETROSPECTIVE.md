# Retrospective

Living retrospective — appended at each milestone boundary.

---

## Milestone: v1.0 — MVP

**Shipped:** 2026-04-18
**Phases:** 8 | **Plans:** 25 | **Timeline:** 22 days (2026-03-27 → 2026-04-18)

### What Was Built

- **Phases 1-4 (core):** Infrastructure → market scanning → execution engine → observability. Full live trading bot from scratch.
- **Phases 5-8 (gap closure):** Four targeted fixes identified by the v1.0 audit: token ID wiring, Telegram alert wiring, formal requirement verification, CB accuracy bugs.
- End state: bot live in `--live` mode on Hetzner HEL1 with Telegram alerts, FastAPI dashboard, SQLite logging, and 39 passing tests.

### What Worked

- **GSD wave-based parallel execution** — phases with non-overlapping files ran as parallel worktree agents, cutting execution time significantly for multi-plan phases.
- **TDD on bug fixes (Phase 8)** — writing the failing test first (RED) before the 2-line engine.py fix made the fix verifiable and regression-proof immediately.
- **Structured PLAN.md with interfaces block** — the `<interfaces>` section in plans (with exact line numbers and current code snippets) meant executors spent zero time exploring; every change was surgical.
- **`hasattr` guard pattern** — using `if hasattr(risk_gate, "record_order_error")` consistently at both YES-verify and NO-exhaust paths made the code test-mockable without any special fixture setup.
- **VPS migration mid-milestone** — migrating from geo-blocked Ashburn to Helsinki required no code changes; Docker + env_file design made it a copy-and-run operation.

### What Was Inefficient

- **Audit then re-plan** — running `/gsd-audit-milestone` generated phases 5-8 as gap closures. Running the audit earlier (after phase 4) would have surfaced the token ID and CB wiring gaps before they accumulated. Audit → gap plan → execute is the right loop, but the timing lag made it feel like rework.
- **SUMMARY.md `one_liner` field** — several SUMMARY.md files used YAML frontmatter but omitted the `one_liner` field, causing the CLI to emit "One-liner:" placeholders in MILESTONES.md. Executors should always write a `one_liner` key.
- **STATE.md drift** — multiple formats (frontmatter + body) led to field-not-found warnings from gsd-tools. STATE.md should have a single canonical format respected by all writers.

### Patterns Established

- **FAK two-step:** `create_order() + post_order(signed_order, orderType=OrderType.FAK)` — `create_and_post_order()` is GTC-only and forbidden.
- **USDC.e collateral:** Polymarket uses bridged USDC (`0x2791...`), not native USDC (`0x3c499...`). Always check `py-clob-client/config.py`.
- **Ask sort order critical finding:** CLOB returns asks DESCENDING. `asks[0]` is the worst ask, not best. Always `min(asks, key=lambda a: float(a.price))`.
- **`_last_trip_count` before `.clear()`:** When capturing event data before clearing a list, the capture line must precede the clear. Document with a comment referencing the decision.
- **Fire-and-forget Telegram via `asyncio.create_task()`:** Never `await` alert sends in the hot scan loop.
- **100k gas for USDC.e `approve()`:** `estimateGas` returns ~67k but 60k causes revert. Always pass 100k minimum.

### Key Lessons

1. **Run the milestone audit after the first stable phase set, not at the end.** Gaps compound — the earlier you catch them, the cheaper they are to close.
2. **Plan `<interfaces>` blocks with exact file + line numbers.** Executors with fresh context windows produce better diffs when they don't have to re-explore the codebase.
3. **TDD on bug fixes is non-negotiable.** The RED→GREEN cycle is the only proof that the fix actually changes behavior. Two lines of code with a test is worth more than 20 lines without.
4. **Keep SUMMARY.md `one_liner` consistent.** It feeds MILESTONES.md, the retrospective, and subagent context. Missing it is a silent quality degradation.
5. **Geo-blocking is an infrastructure risk.** VPS region choice affects reachability, not just latency. Validate country access early.

### Cost Observations

- Model mix: Sonnet 4.6 throughout (orchestrator + subagents via `executor_model: inherit`)
- Sessions: ~15 across 22 days
- Notable: Parallel worktree agents for 2-plan phases roughly halved wall-clock execution time vs sequential

---

## Cross-Milestone Trends

| Metric | v1.0 |
|--------|------|
| Phases | 8 |
| Plans | 25 |
| Days | 22 |
| Tests | 39 |
| Src LOC | 3,853 |
| Test LOC | 3,039 |
| Gap-closure phases | 4 (50%) |
