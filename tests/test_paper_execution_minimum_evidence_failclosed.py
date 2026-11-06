"""Synthetic no-network checks for explicit exchange minimum evidence."""
import pytest

from alpha_hunter.paper_execution import _order_from_decision


def _decision(constraints):
    return {
        "decision_id": "synthetic-minimum-evidence",
        "observed_at_utc": "2026-11-06T19:00:00Z",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry_price": 100.0,
        "stop_price": 99.0,
        "target_price": 102.0,
        "action_status": "EXECUTE_NOW_PAPER",
        "evidence": {"instrument_constraints": {"size_multiplier": "0.001", **constraints}},
    }


CONFIG = {"virtual_equity_usdt": 1000.0, "risk_fraction": 0.0025}


@pytest.mark.parametrize(
    ("key", "bad", "blocker"),
    [
        ("minimum_trade_number", True, "BITGET_MINIMUM_QUANTITY_INVALID"),
        ("minimum_trade_number", "not-a-number", "BITGET_MINIMUM_QUANTITY_INVALID"),
        ("minimum_trade_number", 0, "BITGET_MINIMUM_QUANTITY_INVALID"),
        ("minimum_trade_number", -1, "BITGET_MINIMUM_QUANTITY_INVALID"),
        ("minimum_trade_usdt", False, "BITGET_MINIMUM_NOTIONAL_INVALID"),
        ("minimum_trade_usdt", "nan", "BITGET_MINIMUM_NOTIONAL_INVALID"),
        ("minimum_trade_usdt", 0, "BITGET_MINIMUM_NOTIONAL_INVALID"),
        ("minimum_trade_usdt", -1, "BITGET_MINIMUM_NOTIONAL_INVALID"),
    ],
)
def test_explicit_invalid_exchange_minimum_blocks_order(key, bad, blocker):
    order, blockers = _order_from_decision(_decision({key: bad}), CONFIG)
    assert order is None
    assert blocker in blockers


def test_valid_exchange_minima_preserve_synthetic_order():
    order, blockers = _order_from_decision(
        _decision({"minimum_trade_number": "0.001", "minimum_trade_usdt": "5"}),
        CONFIG,
    )
    assert blockers == []
    assert order is not None
    assert order["paper_only"] is True
    assert order["exchange_authority"] is False


def test_omitted_optional_minima_preserve_legacy_behavior():
    order, blockers = _order_from_decision(_decision({}), CONFIG)
    assert blockers == []
    assert order is not None
