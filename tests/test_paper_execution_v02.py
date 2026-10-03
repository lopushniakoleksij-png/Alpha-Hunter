from pathlib import Path

import pytest
from pglast import parse_sql

from alpha_hunter.paper_execution import build_initial_paper_execution


def _decision(
    *,
    action_status="EXECUTE_NOW_PAPER",
    direction="LONG",
    quantity_at_top=1000.0,
    best_bid=9.99,
    best_ask=10.01,
):
    return {
        "decision_id": "decision-release-2-2",
        "run_id": "run-release-2-2",
        "observed_at_utc": "2026-10-01T06:00:00+00:00",
        "symbol": "TESTUSDT",
        "strategy_id": "S2",
        "direction": direction,
        "action_status": action_status,
        "entry_price": 10.0,
        "stop_price": 9.0 if direction == "LONG" else 11.0,
        "target_price": 12.0 if direction == "LONG" else 8.0,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "best_bid_size": quantity_at_top,
        "best_ask_size": quantity_at_top,
        "public_maker_fee_bps": 2.0,
        "public_taker_fee_bps": 6.0,
        "paper_authority": True,
        "evidence": {
            "funding_rate": 0.0001,
            "instrument_constraints": {
                "size_multiplier": "0.1",
                "minimum_trade_number": "0.1",
                "minimum_trade_usdt": "5",
            },
        },
        "paper_only": True,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }


def test_market_order_models_spread_slippage_fee_and_unaccrued_funding():
    orders, fills, events = build_initial_paper_execution([_decision()])

    assert len(orders) == len(fills) == 1
    order = orders[0]
    fill = fills[0]
    assert order["quantity"] == pytest.approx(2.5)
    assert order["planned_risk_usdt"] == pytest.approx(2.5)
    assert order["sizing_source"] == "VIRTUAL_PAPER_CAPITAL"
    assert fill["fill_price"] > 10.01
    assert fill["fee_usdt"] > 0
    assert fill["spread_cost_usdt"] > 0
    assert fill["slippage_cost_usdt"] > 0
    assert fill["projected_next_funding_usdt"] is not None
    assert fill["accrued_funding_usdt"] == 0
    assert fill["funding_status"] == "NOT_ACCRUED"
    assert [event["state"] for event in events] == ["SUBMITTED", "FILLED"]
    assert all(event["exchange_authority"] is False for event in events)


def test_top_of_book_capacity_never_creates_an_unprotected_partial_fill():
    orders, fills, events = build_initial_paper_execution(
        [_decision(quantity_at_top=1.0)]
    )

    assert orders[0]["quantity"] == pytest.approx(2.5)
    assert fills == []
    assert [event["state"] for event in events] == [
        "SUBMITTED",
        "RECONCILIATION_REQUIRED",
    ]
    assert (
        "TOP_OF_BOOK_CAPACITY_INSUFFICIENT_FOR_ALL_OR_NONE_ENTRY"
        in events[-1]["payload"]["blockers"]
    )


def test_resting_limit_is_submitted_without_inventing_a_fill():
    orders, fills, events = build_initial_paper_execution(
        [_decision(action_status="PLACE_LIMIT_PAPER", best_ask=10.01)]
    )

    assert orders[0]["order_type"] == "LIMIT"
    assert fills == []
    assert [event["state"] for event in events] == ["SUBMITTED"]


def test_missing_top_size_requires_reconciliation_instead_of_a_fill():
    _, fills, events = build_initial_paper_execution(
        [_decision(quantity_at_top=None)]
    )

    assert fills == []
    assert [event["state"] for event in events] == [
        "SUBMITTED",
        "RECONCILIATION_REQUIRED",
    ]
    assert "TOP_OF_BOOK_SIZE_MISSING" in events[-1]["payload"]["blockers"]


def test_execution_rows_are_deterministic_and_retry_safe():
    decision = _decision()
    assert build_initial_paper_execution([decision]) == build_initial_paper_execution(
        [decision]
    )


def test_execution_sql_is_append_only_rls_scoped_and_has_no_live_path():
    sql = Path("ops/sql/paper_execution_v02.sql").read_text(encoding="utf-8").lower()

    assert parse_sql(sql)
    assert sql.count("enable row level security") == 2
    assert sql.count("before update or delete") == 2
    assert "security_invoker=true" in sql
    assert "grant select,insert" in sql
    assert "exchange_authority=false" in sql
    assert "trade_permission=false" in sql
    assert "order_path='none'" in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql


def test_active_exposure_key_blocks_duplicate_paper_submission():
    decision = _decision()
    key = ("TESTUSDT", "S2", "LONG")

    orders, fills, events = build_initial_paper_execution(
        [decision],
        active_exposure_keys={key},
    )

    assert orders == []
    assert fills == []
    assert [event["state"] for event in events] == ["CANCELLED"]
    assert "ACTIVE_PAPER_EXPOSURE_EXISTS" in events[0]["payload"]["blockers"]


def test_same_scan_duplicate_exposure_only_admits_first_order():
    first = _decision()
    second = _decision()
    second["decision_id"] = "decision-release-2-2-second"

    orders, fills, events = build_initial_paper_execution([first, second])

    assert len(orders) == 1
    assert len(fills) == 1
    assert [event["state"] for event in events] == [
        "SUBMITTED",
        "FILLED",
        "CANCELLED",
    ]
    assert "ACTIVE_PAPER_EXPOSURE_EXISTS" in events[-1]["payload"]["blockers"]


def test_r8_execution_gate_blocks_all_submissions_before_activation():
    orders, fills, events = build_initial_paper_execution(
        [_decision()],
        execution_gate_open=False,
    )

    assert orders == []
    assert fills == []
    assert [event["state"] for event in events] == ["CANCELLED"]
    assert "PAPER_R8_INTEGRITY_NOT_ACTIVATED" in events[0]["payload"]["blockers"]
