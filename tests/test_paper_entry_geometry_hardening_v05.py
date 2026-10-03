from pathlib import Path

from pglast import parse_sql

from alpha_hunter.paper_execution import _fill_from_order
from alpha_hunter.paper_reconciliation import reconcile_open_orders


def snapshot(*, bid=9.9, ask=10.0, bid_size=100.0, ask_size=100.0):
    return {
        "run_id": "run-geometry-v05",
        "collected_at_utc": "2026-10-03T00:00:00+00:00",
        "symbols": [{
            "symbol": "TESTUSDT",
            "bid_price": bid,
            "ask_price": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "funding_rate": 0.0001,
        }],
    }


def open_order(**overrides):
    row = {
        "order_id": "order-geometry-v05",
        "decision_id": "decision-geometry-v05",
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
        "stop_price": 9.5,
        "target_price": 11.0,
        "public_maker_fee_bps": 2.0,
        "public_taker_fee_bps": 6.0,
    }
    row.update(overrides)
    return row


def test_delayed_long_limit_uses_limit_price_not_late_favorable_quote():
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(bid=8.9, ask=9.0),
        [open_order()],
    )

    assert attempts[0]["outcome"] == "FILL_MODELED"
    assert fills[0]["fill_price"] == 10.0
    assert fills[0]["midpoint_reference"] == 10.0
    assert fills[0]["cross_price_reference"] == 10.0
    assert fills[0]["spread_cost_usdt"] == 0.0
    assert fills[0]["slippage_cost_usdt"] == 0.0
    assert events[0]["state"] == "FILLED"
    assert len(protections) == 2


def test_delayed_short_limit_uses_limit_price_not_late_favorable_quote():
    order = open_order(
        direction="SHORT",
        limit_price=10.0,
        stop_price=10.5,
        target_price=9.0,
    )
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(bid=11.0, ask=11.1),
        [order],
    )

    assert attempts[0]["outcome"] == "FILL_MODELED"
    assert fills[0]["fill_price"] == 10.0
    assert events[0]["state"] == "FILLED"
    assert len(protections) == 2


def test_completed_partial_fill_checks_weighted_average_geometry():
    order = open_order(
        ordered_quantity=5.0,
        filled_quantity=2.0,
        remaining_quantity=3.0,
        execution_state="PARTIALLY_FILLED",
        fill_count=1,
        average_fill_price=9.8,
        event_sequence=4,
    )
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(ask_size=3.0),
        [order],
    )

    assert attempts[0]["outcome"] == "FILL_MODELED"
    assert fills[0]["quantity"] == 3.0
    assert events[0]["state"] == "FILLED"
    assert len(protections) == 2


def test_corrupted_prior_average_fails_closed_before_completion():
    order = open_order(
        ordered_quantity=5.0,
        filled_quantity=4.0,
        remaining_quantity=1.0,
        execution_state="PARTIALLY_FILLED",
        fill_count=1,
        average_fill_price=8.0,
        event_sequence=4,
    )
    attempts, fills, events, protections = reconcile_open_orders(
        snapshot(ask_size=1.0),
        [order],
    )

    assert attempts[0]["outcome"] == "INPUT_MISSING"
    assert attempts[0]["blockers"] == ["COMPLETED_ENTRY_GEOMETRY_INVALID"]
    assert fills == []
    assert events == []
    assert protections == []


def test_immediate_limit_fill_beyond_stop_is_not_modeled_as_valid_entry():
    decision = {
        "decision_id": "decision-immediate",
        "run_id": "run-immediate",
        "stop_price": 9.5,
        "target_price": 11.0,
        "evidence": {"funding_rate": 0.0},
    }
    order = {
        "order_id": "order-immediate",
        "decision_id": "decision-immediate",
        "direction": "LONG",
        "order_type": "LIMIT",
        "limit_price": 10.0,
        "quantity": 5.0,
        "best_bid": 8.9,
        "best_ask": 9.0,
        "best_bid_size": 100.0,
        "best_ask_size": 100.0,
        "public_maker_fee_bps": 2.0,
        "public_taker_fee_bps": 6.0,
    }
    config = {
        "virtual_equity_usdt": 1000.0,
        "risk_fraction": 0.0025,
        "base_market_slippage_bps": 1.0,
        "maximum_market_slippage_bps": 5.0,
    }

    fill, blockers = _fill_from_order(decision, order, config)

    assert fill is None
    assert blockers == ["ENTRY_FILL_GEOMETRY_INVALID"]


def test_geometry_hardening_sql_is_append_only_and_exposes_valid_trade_view():
    root = Path(__file__).resolve().parents[1]
    sql = (
        root / "ops/sql/paper_entry_geometry_hardening_v05.sql"
    ).read_text(encoding="utf-8")
    lower = sql.lower()

    assert parse_sql(sql)
    assert "invalid_entry_geometry_pre_fix" in lower
    assert "alpha_hunter_paper_completed_trades_valid_v05" in lower
    assert "protective order geometry invalid relative to cumulative entry fill" in lower
    assert "historical_rows_deleted',false" in lower
    assert "delete from public.alpha_hunter_paper" not in lower
    assert "update public.alpha_hunter_paper" not in lower
    assert "trade_permission,true" not in lower
    assert "exchange_authority,true" not in lower


def test_geometry_migration_appends_view_column_without_reordering_existing_contract():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "ops/sql/paper_reconciliation_v03.sql",
        "ops/sql/paper_entry_geometry_hardening_v05.sql",
    ):
        sql = (root / relative).read_text(encoding="utf-8").lower()
        view_start = sql.index(
            "create or replace view public.alpha_hunter_paper_reconciliation_open_v03"
        )
        view_end = sql.index(
            "from public.alpha_hunter_paper_orders_v02 o",
            view_start,
        )
        projection = sql[view_start:view_end]
        assert projection.index("o.order_path") < projection.index("x.average_fill_price")
        assert projection.rstrip().endswith("x.average_fill_price")
