"""Synthetic paper-only market evidence type guards; no I/O or admissions."""

import pytest

from alpha_hunter.paper_execution import _fill_from_order, _optional_float


@pytest.mark.parametrize("value", [True, False])
def test_boolean_is_not_numeric_market_evidence(value):
    assert _optional_float(value) is None


def _decision():
    return {"decision_id": "synthetic", "run_id": "synthetic-run",
            "observed_at_utc": "2026-11-06T00:00:00Z",
            "stop_price": 90.0, "target_price": 120.0, "evidence": {}}


def _order():
    return {"direction": "LONG", "best_bid": 100.0, "best_ask": 101.0,
            "best_ask_size": 20.0, "quantity": 1.0,
            "order_type": "MARKET", "public_taker_fee_bps": 5.0,
            "order_id": "synthetic-order"}


@pytest.mark.parametrize(
    "field,invalid,blocker",
    [
        ("best_bid", True, "TOP_OF_BOOK_PRICE_INVALID"),
        ("best_ask", True, "TOP_OF_BOOK_PRICE_INVALID"),
        ("best_ask_size", True, "TOP_OF_BOOK_SIZE_MISSING"),
        ("quantity", True, "ENTRY_QUANTITY_INVALID"),
        ("public_taker_fee_bps", True, "TAKER_FEE_EVIDENCE_MISSING"),
    ],
)
def test_boolean_quote_or_fee_never_generates_paper_fill(field, invalid, blocker):
    order = _order()
    order[field] = invalid
    fill, blockers = _fill_from_order(
        _decision(), order,
        {"maximum_market_slippage_bps": 5.0, "base_market_slippage_bps": 1.0},
    )
    assert fill is None
    assert blocker in blockers


def test_valid_numeric_quote_still_creates_paper_only_fill():
    fill, blockers = _fill_from_order(
        _decision(), _order(),
        {"maximum_market_slippage_bps": 5.0, "base_market_slippage_bps": 1.0},
    )
    assert blockers == []
    assert fill["paper_only"] is True
    assert fill["trade_permission"] is False
    assert fill["exchange_authority"] is False
    assert fill["order_path"] == "NONE"
