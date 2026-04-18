# Deferred Items — Phase 03

## Pre-existing Test Failures (Out of Scope)

### test_market_filter.py::test_fetch_liquid_markets_filters_by_volume

- **Discovered during:** Plan 03-01 full suite run
- **Status:** Pre-existing failure (confirmed via git stash verification — fails on master before any 03-01 changes)
- **Issue:** `fetch_liquid_markets` returns 0 markets when mock returns markets without `active`, `enable_order_book`, `accepting_orders` fields set to True. Test mock data doesn't set those boolean flags, so markets fail the CLOB filter.
- **Impact:** Cosmetic — does not affect bot runtime behavior (real API returns proper fields)
- **Fix:** Update mock in `test_market_filter.py` to include `active=True, enable_order_book=True, accepting_orders=True` in `_make_market()` helper, OR relax filter logic
- **Owner:** Future plan or quick fix pass
