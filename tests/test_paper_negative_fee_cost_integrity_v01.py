"""Synthetic fee-cost integrity checks; never reads production or admits positions."""

import pytest

from alpha_hunter.paper_execution import _fill_from_order


def _decision():
    return {
        "decision_id": "synthetic",
        "run_id": "synthetic-run",
        "observed_at_utc": "2026-11-06T00:00:00Z",
        "stop_price": 90.0,
        "target_price": 120.0,
        "evidence": {},
    }


def _order(order_type, fee):
    return {
        "direction": "LONG",
        "best_bid": 100.0,
        "best_ask": 101.0,
        "best_ask_size": 20.0,
        "quantity": 1.0,
        "order_type": order_type,
        "limit_price": 102.0,
        "public_taker_fee_bps": fee,
        "public_maker_fee_bps": fee,
        "order_id": "synthetic-order",
    }


CONFIG = {"maximum_market_slippage_bps": 5.0, "base_market_slippage_bps": 1.0}


@pytest.mark.parametrize("order_type", ["MARKET", "LIMIT"])
@pytest.mark.parametrize("fee", [-0.01, -5.0])
def test_unevidenced_negative_fee_never_generates_paper_fill(order_type, fee):
    fill, blockers = _fill_from_order(_decision(), _order(order_type, fee), CONFIG)
    assert fill is None
    assert blockers == ["NEGATIVE_FEE_REBATE_UNVERIFIED"]


@pytest.mark.parametrize("order_type", ["MARKET", "LIMIT"])
@pytest.mark.parametrize("fee", [0.0, 5.0])
def test_nonnegative_fee_preserves_paper_only_cost_linkage(order_type, fee):
    fill, blockers = _fill_from_order(_decision(), _order(order_type, fee), CONFIG)
    assert blockers == []
    assert fill["fee_bps"] == fee
    assert fill["fee_usdt"] == pytest.approx(fill["notional_usdt"] * fee / 10000)
    assert fill["fee_usdt"] >= 0
    assert fill["paper_only"] is True
    assert fill["exchange_authority"] is False
    assert fill["trade_permission"] is False
    assert fill["order_path"] == "NONE"
