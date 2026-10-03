from pathlib import Path

import pytest

from alpha_hunter.paper_reconciliation import (
    build_initial_protective_orders,
    reconcile_open_orders,
)


def snapshot(*, bid=9.9, ask=10.0, bid_size=10.0, ask_size=10.0):
    return {
        "run_id": "run-later",
        "collected_at_utc": "2026-10-01T07:00:00+00:00",
        "symbols": [
            {
                "symbol": "TESTUSDT",
                "bid_price": bid,
                "ask_price": ask,
                "bid_size": bid_size,
                "ask_size": ask_size,
                "funding_rate": 0.0001,
            }
        ],
    }


def open_order(**overrides):
    row = {
        "order_id": "order-1",
        "decision_id": "decision-1",
        "symbol": "TESTUSDT",
        "direction": "LONG",
        "order_type": "LIMIT",
        "limit_price": 10.0,
        "ordered_quantity": 5.0,
        "filled_quantity": 0.0,
        "remaining_quantity": 5.0,
        "execution_state": "SUBMITTED",
        "fill_count": 0,
        "average_fill_price": None,
        "event_sequence": 3,
        "submitted_at_utc": "2026-10-01T06:40:00+00:00",
        "stop_price": 9.5,
        "target_price": 11.0,
        "public_maker_fee_bps": 2.0,
        "public_taker_fee_bps": 6.0,
    }
    row.update(overrides)
    return row


def test_resting_limit_records_no_cross_without_a_fill():
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(ask=10.1), [open_order()]
    )
    assert attempts[0]["outcome"] == "NO_CROSS"
    assert fills == []
    assert events == []
    assert protections == []


def test_complete_later_fill_activates_two_reduce_only_protective_orders():
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(ask_size=8.0), [open_order()]
    )
    assert attempts[0]["outcome"] == "FILL_MODELED"
    assert fills[0]["quantity"] == 5.0
    assert fills[0]["source_run_id"] == "run-later"
    assert events[0]["state"] == "FILLED"
    assert events[0]["sequence"] == 4
    assert {row["protection_type"] for row in protections} == {
        "STOP_LOSS",
        "TAKE_PROFIT",
    }
    assert all(row["reduce_only"] is True for row in protections)
    assert all(row["side"] == "SELL" for row in protections)
    assert all(row["quantity"] == 5.0 for row in protections)


def test_insufficient_full_capacity_does_not_create_partial_fill():
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(ask_size=2.0), [open_order()]
    )
    assert attempts[0]["outcome"] == "NO_FULL_CAPACITY"
    assert attempts[0]["blockers"] == [
        "TOP_OF_BOOK_CAPACITY_INSUFFICIENT_FOR_ALL_OR_NONE_ENTRY"
    ]
    assert fills == []
    assert events == []
    assert protections == []


def test_legacy_partial_entry_is_quarantined_instead_of_completed():
    order = open_order(
        filled_quantity=2.0,
        remaining_quantity=3.0,
        execution_state="PARTIALLY_FILLED",
        fill_count=1,
        average_fill_price=10.0,
        event_sequence=4,
    )
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(ask_size=3.0), [order]
    )
    assert attempts[0]["outcome"] == "QUARANTINED_LEGACY_PARTIAL"
    assert attempts[0]["blockers"] == ["LEGACY_PARTIAL_ENTRY_NOT_R8_ELIGIBLE"]
    assert fills == []
    assert protections == []
    assert events[0]["state"] == "RECONCILIATION_REQUIRED"
    assert events[0]["sequence"] == 5


def test_missing_top_size_fails_closed_as_input_missing():
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(ask_size=None), [open_order()]
    )
    assert attempts[0]["outcome"] == "INPUT_MISSING"
    assert attempts[0]["blockers"] == ["TOP_OF_BOOK_SIZE_MISSING"]
    assert fills == events == protections == []


def test_existing_attempt_is_not_applied_twice():
    rows = reconcile_open_orders(
        snapshot(), [open_order()], attempted_order_ids={"order-1"}
    )
    assert rows == ([], [], [], [])


def test_short_completion_creates_buy_side_protection():
    order = open_order(
        direction="SHORT",
        limit_price=10.0,
        stop_price=10.5,
        target_price=9.0,
    )
    _, _, events, protections = reconcile_open_orders(
        snapshot(bid=10.0, bid_size=5.0, ask=10.1), [order]
    )
    assert events[0]["state"] == "FILLED"
    assert all(row["side"] == "BUY" for row in protections)


def test_initial_protection_waits_for_complete_entry_fill():
    decisions = [
        {
            "decision_id": "decision-1",
            "run_id": "run-initial",
            "stop_price": 9.5,
            "target_price": 11.0,
        }
    ]
    orders = [
        {
            "order_id": "order-1",
            "decision_id": "decision-1",
            "symbol": "TESTUSDT",
            "direction": "LONG",
            "quantity": 5.0,
        }
    ]
    partial = [
        {
            "fill_id": "fill-1",
            "order_id": "order-1",
            "quantity": 2.0,
            "filled_at_utc": "2026-10-01T07:00:00+00:00",
        }
    ]
    assert build_initial_protective_orders(decisions, orders, partial) == []
    partial[0]["quantity"] = 5.0
    protections = build_initial_protective_orders(decisions, orders, partial)
    assert len(protections) == 2


def test_database_contract_is_append_only_atomic_and_service_role_only():
    sql = (
        Path(__file__).resolve().parents[1]
        / "ops/sql/paper_reconciliation_v03.sql"
    ).read_text(encoding="utf-8").lower()
    assert sql.count("enable row level security") == 2
    assert "security invoker" in sql
    assert "security definer" not in sql
    assert "before update or delete" in sql
    assert "reduce_only=true" in sql
    assert "protective order forbidden before complete entry fill" in sql
    assert "paper fill exceeds remaining entry quantity" in sql
    assert sql.count("pg_advisory_xact_lock") >= 3
    assert "alpha-hunter-paper-order:" in sql
    assert "for share;" not in sql
    assert "grant execute on function public.alpha_hunter_commit_paper_reconciliation_v03" in sql
    assert "to service_role" in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql


@pytest.mark.parametrize("field", ["run_id", "collected_at_utc"])
def test_reconciliation_requires_immutable_run_identity(field):
    value = snapshot()
    value[field] = ""
    with pytest.raises(ValueError, match="immutable run identity"):
        reconcile_open_orders(value, [open_order()])


def test_current_public_quote_override_reconciles_symbol_absent_from_deep_scan():
    value = snapshot()
    value["symbols"] = []
    captured_at = "2026-10-01T07:01:00+00:00"
    quote_overrides = {
        "TESTUSDT": {
            "symbol": "TESTUSDT",
            "bid_price": 9.9,
            "ask_price": 10.0,
            "bid_size": 10.0,
            "ask_size": 10.0,
            "funding_rate": 0.0001,
            "_captured_at_utc": captured_at,
            "_reconciliation_quote_source":
                "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE",
        }
    }

    attempts, fills, events, protections = reconcile_open_orders(
        value,
        [open_order()],
        quote_overrides=quote_overrides,
    )

    assert attempts[0]["outcome"] == "FILL_MODELED"
    assert attempts[0]["observed_at_utc"] == captured_at
    assert attempts[0]["evidence"]["quote_source"] == (
        "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"
    )
    assert fills[0]["liquidity_source"] == (
        "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"
    )
    assert events[0]["occurred_at_utc"] == captured_at
    assert len(protections) == 2


def test_stale_unfilled_limit_expires_after_35_minutes():
    order = open_order(submitted_at_utc="2026-10-01T06:00:00+00:00")
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(), [order]
    )

    assert attempts[0]["outcome"] == "EXPIRED"
    assert attempts[0]["blockers"] == ["ENTRY_ORDER_EXPIRED_35M"]
    assert fills == []
    assert protections == []
    assert events[0]["state"] == "EXPIRED"
    assert events[0]["event_type"] == "PAPER_ENTRY_ORDER_EXPIRED"
