# Phase 8: Fix Circuit Breaker & Alert Accuracy — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 08-fix-circuit-breaker-alert-accuracy
**Areas discussed:** CB error call site, property name, test scope

---

## CB error call site

| Option | Description | Selected |
|--------|-------------|----------|
| At the top — before hedge | Record NO exhaustion as error immediately, regardless of hedge outcome | ✓ |
| After hedge fails too | Only record error if hedge SELL also fails | |

**User's choice:** At the top — before hedge (recommended)
**Notes:** Semantically clean: NO retries failed = error. Hedge is mitigation, not a second chance.

---

## Property name (gate.py live count)

| Option | Description | Selected |
|--------|-------------|----------|
| last_trip_error_count | Describes what it stores: count from last CB trip | ✓ |
| triggering_error_count | More action-oriented name | |
| You decide | Pick most natural name for codebase style | |

**User's choice:** `last_trip_error_count` (recommended)
**Notes:** Will be accessed as `risk_gate.last_trip_error_count` in live_run.py.

---

## Test scope

| Option | Description | Selected |
|--------|-------------|----------|
| Two new fixes only | NO exhaustion trips CB + CB alert shows live count | |
| Fixes + regression for existing CB behavior | Two new tests + verify YES verify failure still trips CB | ✓ |

**User's choice:** Fixes + regression for existing CB behavior
**Notes:** Three tests total: NO exhaustion, CB live count alert, YES verify regression.

---

## Claude's Discretion

- `hasattr` guard pattern for NO-leg `record_order_error()` call (consistency with YES path)
- Whether to guard against kill-switch-abort case in `if not no_filled:` block
- Type annotation placement for `_last_trip_count`

## Deferred Ideas

None — discussion stayed within phase scope.
