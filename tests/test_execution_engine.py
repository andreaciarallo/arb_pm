"""
TDD suite for the execution engine.

Tests cover:
  - VWAP gate (D-05): spread below threshold → skipped
  - Kelly gate (D-01): kelly_size returns 0.0 → skipped
  - Full success path: YES fills + NO fills → 2 "filled" results
  - YES leg failure → failed, NO never attempted
  - YES fills but NO fails all 3 retries → hedge SELL triggered (price=0.01)
  - Kill switch active inside retry loop → retries stop early
  - verify_fill_rest returns False after YES → abort NO leg
  - simulate_vwap with empty asks → VWAP=1.0 → skipped
"""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call
from bot.detection.opportunity import ArbitrageOpportunity
from bot.execution.engine import execute_opportunity, ExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _opp(
    net_spread=0.03,
    yes_ask=0.48,
    no_ask=0.48,
    depth=200.0,
    vwap_yes=0.48,
    vwap_no=0.48,
    yes_token_id="yes_tok",
    no_token_id="no_tok",
):
    return ArbitrageOpportunity(
        market_id="cond_abc",
        market_question="Will X happen?",
        opportunity_type="yes_no",
        category="politics",
        yes_ask=yes_ask,
        no_ask=no_ask,
        gross_spread=1.0 - yes_ask - no_ask,
        estimated_fees=0.01,
        net_spread=net_spread,
        depth=depth,
        vwap_yes=vwap_yes,
        vwap_no=vwap_no,
        confidence_score=0.8,
        detected_at=datetime.utcnow(),
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
    )


def _config(
    min_net_profit_pct=0.015,
    total_capital_usd=1000.0,
    kelly_min_order_usd=5.0,
    kelly_max_capital_pct=0.05,
):
    cfg = MagicMock()
    cfg.min_net_profit_pct = min_net_profit_pct
    cfg.total_capital_usd = total_capital_usd
    cfg.kelly_min_order_usd = kelly_min_order_usd
    cfg.kelly_max_capital_pct = kelly_max_capital_pct
    return cfg


# ---------------------------------------------------------------------------
# Test 1: VWAP gate — spread below threshold → skipped
# ---------------------------------------------------------------------------

@patch("bot.execution.engine.kelly_size", return_value=10.0)
async def test_vwap_gate_low_spread_skips(mock_kelly):
    """VWAP-adjusted spread below min_net_profit_pct → status='skipped'."""
    client = MagicMock()
    # price=0.50 each side → vwap_spread = 1.0 - 0.50 - 0.50 = 0.0 < 0.015 → skipped
    mock_book = MagicMock()
    level = MagicMock()
    level.price = "0.50"
    level.size = "500"
    mock_book.asks = [level]
    mock_book.bids = []
    client.get_order_book.return_value = mock_book
    opp = _opp(net_spread=0.03)
    _, results = await execute_opportunity(client, opp, _config(), MagicMock())
    assert any(r.status == "skipped" for r in results)


# ---------------------------------------------------------------------------
# Test 2: Kelly skip — kelly_size returns 0.0 → skipped
# ---------------------------------------------------------------------------

@patch("bot.execution.engine.kelly_size", return_value=0.0)
async def test_kelly_zero_returns_skipped(mock_kelly):
    """kelly_size returns 0.0 → status='skipped', no order placed."""
    client = MagicMock()
    mock_book = MagicMock()
    level = MagicMock()
    level.price = "0.48"
    level.size = "500"
    mock_book.asks = [level]
    mock_book.bids = []
    client.get_order_book.return_value = mock_book
    _, results = await execute_opportunity(client, _opp(), _config(), MagicMock())
    assert any(r.status == "skipped" for r in results)


# ---------------------------------------------------------------------------
# Test 3: Full success — both YES and NO fill
# ---------------------------------------------------------------------------

@patch("bot.execution.engine.kelly_size", return_value=10.0)
@patch("bot.execution.engine.verify_fill_rest", new_callable=AsyncMock, return_value=True)
async def test_full_success_returns_two_filled_results(mock_verify, mock_kelly):
    """Both YES and NO fill → at least 2 'filled' results."""
    call_counter = {"n": 0}

    async def side_effect(*args, **kwargs):
        call_counter["n"] += 1
        return {"orderID": f"order{call_counter['n']}", "status": "matched"}

    with patch("bot.execution.engine.place_fak_order", new_callable=AsyncMock,
               side_effect=side_effect):
        client = MagicMock()
        mock_book = MagicMock()
        level = MagicMock()
        level.price = "0.48"
        level.size = "500"
        mock_book.asks = [level]
        mock_book.bids = []
        client.get_order_book.return_value = mock_book
        risk_gate = MagicMock()
        risk_gate.is_kill_switch_active.return_value = False
        _, results = await execute_opportunity(
            client, _opp(), _config(), risk_gate,
        )
        filled = [r for r in results if r.status == "filled"]
        assert len(filled) >= 2


# ---------------------------------------------------------------------------
# Test 4: YES leg fails — no exposure, NO never attempted
# ---------------------------------------------------------------------------

@patch("bot.execution.engine.kelly_size", return_value=10.0)
@patch("bot.execution.engine.place_fak_order", new_callable=AsyncMock, return_value=None)
async def test_yes_leg_fails_no_exposure(mock_place, mock_kelly):
    """place_fak_order returns None for YES → failed result, NO never attempted."""
    client = MagicMock()
    mock_book = MagicMock()
    level = MagicMock()
    level.price = "0.48"
    level.size = "500"
    mock_book.asks = [level]
    mock_book.bids = []
    client.get_order_book.return_value = mock_book
    _, results = await execute_opportunity(
        client, _opp(), _config(), MagicMock(),
    )
    failed = [r for r in results if r.leg == "yes" and r.status == "failed"]
    assert len(failed) >= 1
    # Only one call: the YES attempt
    assert mock_place.call_count == 1


# ---------------------------------------------------------------------------
# Test 5: YES fills but NO fails all 3 retries → hedge SELL triggered
# ---------------------------------------------------------------------------

@patch("bot.execution.engine.kelly_size", return_value=10.0)
@patch("bot.execution.engine.verify_fill_rest", new_callable=AsyncMock, return_value=True)
async def test_no_leg_retry_then_hedge(mock_verify, mock_kelly):
    """YES fills; NO always None for 3 retries → hedge SELL at price=0.01."""
    call_counter = {"n": 0}

    async def side_effect(*args, **kwargs):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            # First call: YES BUY → success
            return {"orderID": "yes1", "status": "matched"}
        # Determine if this is the hedge SELL (side="SELL")
        side_arg = kwargs.get("side") or (args[4] if len(args) > 4 else None)
        if side_arg == "SELL":
            return {"orderID": "hedge1", "status": "matched"}
        return None  # NO BUY attempts all fail

    with patch("bot.execution.engine.place_fak_order", new_callable=AsyncMock,
               side_effect=side_effect):
        client = MagicMock()
        mock_book = MagicMock()
        level = MagicMock()
        level.price = "0.48"
        level.size = "500"
        mock_book.asks = [level]
        mock_book.bids = []
        client.get_order_book.return_value = mock_book
        risk_gate = MagicMock()
        risk_gate.is_kill_switch_active.return_value = False
        _, results = await execute_opportunity(
            client, _opp(), _config(), risk_gate,
        )
        hedge_results = [r for r in results if r.status == "hedged" or r.leg == "hedge"]
        assert len(hedge_results) >= 1


# ---------------------------------------------------------------------------
# Test 6: Kill switch active inside retry loop → retries stop early
# ---------------------------------------------------------------------------

@patch("bot.execution.engine.kelly_size", return_value=10.0)
@patch("bot.execution.engine.verify_fill_rest", new_callable=AsyncMock, return_value=True)
async def test_kill_switch_stops_no_retries(mock_verify, mock_kelly):
    """Kill switch active after YES fill → NO retries stop early (< 3 attempts)."""
    call_counter = {"n": 0}

    async def side_effect_place(*args, **kwargs):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            return {"orderID": "yes1", "status": "matched"}
        return None  # NO fails

    with patch("bot.execution.engine.place_fak_order", new_callable=AsyncMock,
               side_effect=side_effect_place):
        client = MagicMock()
        mock_book = MagicMock()
        level = MagicMock()
        level.price = "0.48"
        level.size = "500"
        mock_book.asks = [level]
        mock_book.bids = []
        client.get_order_book.return_value = mock_book
        risk_gate = MagicMock()
        # Kill switch is active from the first check inside the retry loop
        risk_gate.is_kill_switch_active.return_value = True
        _, results = await execute_opportunity(
            client, _opp(), _config(), risk_gate,
        )
        no_attempts = call_counter["n"] - 1  # subtract YES attempt
        # Should not have made 3 full NO retry attempts
        assert no_attempts <= 1


# ---------------------------------------------------------------------------
# Test 7: verify_fill_rest returns False → abort NO leg
# ---------------------------------------------------------------------------

@patch("bot.execution.engine.kelly_size", return_value=10.0)
@patch("bot.execution.engine.place_fak_order", new_callable=AsyncMock,
       return_value={"orderID": "yes1", "status": "matched"})
@patch("bot.execution.engine.verify_fill_rest", new_callable=AsyncMock, return_value=False)
async def test_yes_verify_false_aborts_no_leg(mock_verify, mock_place, mock_kelly):
    """YES response has orderID but verify_fill_rest returns False → NO not attempted."""
    client = MagicMock()
    mock_book = MagicMock()
    level = MagicMock()
    level.price = "0.48"
    level.size = "500"
    mock_book.asks = [level]
    mock_book.bids = []
    client.get_order_book.return_value = mock_book
    _, results = await execute_opportunity(
        client, _opp(), _config(), MagicMock(),
    )
    # YES was attempted (place called once)
    assert mock_place.call_count == 1
    # No filled NO leg
    assert not any(r.leg == "no" and r.status == "filled" for r in results)
    # Result should be failed or similar (not filled)
    assert not any(r.status == "filled" for r in results)


# ---------------------------------------------------------------------------
# Test 8: simulate_vwap with empty asks → VWAP=1.0 → skipped
# ---------------------------------------------------------------------------

@patch("bot.execution.engine.kelly_size", return_value=10.0)
async def test_vwap_gate_insufficient_depth_skips(mock_kelly):
    """simulate_vwap with empty asks → VWAP=1.0 → vwap_spread < threshold → skipped."""
    with patch("bot.execution.engine.simulate_vwap", return_value=1.0):
        client = MagicMock()
        # client.get_order_book mock needed so sorted() in Gate 1 doesn't fail
        # simulate_vwap is patched to return 1.0 regardless of asks content
        mock_book = MagicMock()
        level = MagicMock()
        level.price = "0.48"
        level.size = "1"
        mock_book.asks = [level]
        mock_book.bids = []
        client.get_order_book.return_value = mock_book
        # simulate_vwap returns 1.0 → 1.0 - 1.0 - 1.0 = -1.0 → deeply negative → skipped
        opp = _opp(net_spread=0.03)
        _, results = await execute_opportunity(client, opp, _config(), MagicMock())
        assert any(r.status == "skipped" for r in results)
