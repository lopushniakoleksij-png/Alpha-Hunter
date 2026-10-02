from pathlib import Path

from pglast import parse_sql

from alpha_hunter.paper_exit import reconcile_active_protections


def snapshot(symbol="TESTUSDT", *, bid=9.4, ask=9.5, bid_size=1000, ask_size=1000):
    return {
        "run_id": "run-exit-1",
        "collected_at_utc": "2026-10-02T09:00:00+00:00",
        "symbols": [{
            "symbol": symbol,
            "bid_price": bid,
            "ask_price": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
        }],
    }


def position(
    direction="LONG",
    *,
    stop=9.5,
    target=15.0,
    entry=10.0,
    quantity=10.0,
    completed_source_run="run-entry-1",
):
    return {
        "entry_order_id": "order-1",
        "decision_id": "decision-1",
        "symbol": "TESTUSDT",
        "direction": direction,
        "entry_quantity": quantity,
        "average_entry_fill_price": entry,
        "entry_fee_usdt": 0.02,
        "entry_spread_cost_usdt": 0.01,
        "entry_slippage_cost_usdt": 0.0,
        "entry_completed_at_utc": "2026-10-02T08:40:00+00:00",
        "entry_completed_source_run_id": completed_source_run,
        "planned_risk_usdt": 2.5,
        "public_taker_fee_bps": 6.0,
        "protection_count": 2,
        "stop_protective_order_id": "protect-stop",
        "stop_trigger_price": stop,
        "target_protective_order_id": "protect-target",
        "target_trigger_price": target,
        "event_sequence": 4,
    }


def test_long_stop_creates_one_terminal_exit_and_event():
    attempts, fills, events = reconcile_active_protections(
        snapshot(bid=9.4, ask=9.5),
        [position()],
    )

    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "STOP_TRIGGERED"
    assert len(fills) == 1
    assert fills[0]["protection_type"] == "STOP_LOSS"
    assert fills[0]["side"] == "SELL"
    assert fills[0]["triggered_protective_order_id"] == "protect-stop"
    assert fills[0]["exit_price"] < 9.4
    assert fills[0]["gross_pnl_usdt"] < 0
    assert fills[0]["paper_net_pnl_ex_funding"] < fills[0]["gross_pnl_usdt"]
    assert fills[0]["full_economic_pnl_claim_permitted"] is False
    assert len(events) == 1
    assert events[0]["state"] == "STOPPED"
    assert events[0]["sequence"] == 5


def test_long_target_uses_sellable_bid_and_targets():
    attempts, fills, events = reconcile_active_protections(
        snapshot(bid=15.2, ask=15.3),
        [position()],
    )

    assert attempts[0]["outcome"] == "TARGET_TRIGGERED"
    assert fills[0]["protection_type"] == "TAKE_PROFIT"
    assert fills[0]["side"] == "SELL"
    assert fills[0]["gross_pnl_usdt"] > 0
    assert events[0]["state"] == "TARGETED"


def test_short_stop_and_target_use_buyable_ask():
    short = position(
        "SHORT",
        stop=10.5,
        target=5.0,
        entry=10.0,
    )

    stop_attempts, stop_fills, stop_events = reconcile_active_protections(
        snapshot(bid=10.5, ask=10.6),
        [short],
    )
    assert stop_attempts[0]["outcome"] == "STOP_TRIGGERED"
    assert stop_fills[0]["side"] == "BUY"
    assert stop_events[0]["state"] == "STOPPED"

    target_snapshot = snapshot(bid=4.8, ask=4.9)
    target_snapshot["run_id"] = "run-exit-2"
    target_attempts, target_fills, target_events = reconcile_active_protections(
        target_snapshot,
        [short],
    )
    assert target_attempts[0]["outcome"] == "TARGET_TRIGGERED"
    assert target_fills[0]["side"] == "BUY"
    assert target_events[0]["state"] == "TARGETED"


def test_no_trigger_remains_open_without_exit_fill():
    attempts, fills, events = reconcile_active_protections(
        snapshot(bid=10.1, ask=10.2),
        [position()],
    )

    assert attempts[0]["outcome"] == "NO_TRIGGER"
    assert fills == []
    assert events == []


def test_same_snapshot_entry_and_exit_is_fail_closed_as_ambiguous():
    attempts, fills, events = reconcile_active_protections(
        snapshot(bid=9.4, ask=9.5),
        [position(completed_source_run="run-exit-1")],
    )

    assert attempts[0]["outcome"] == "AMBIGUOUS"
    assert attempts[0]["blockers"] == [
        "ENTRY_AND_EXIT_ORDERING_AMBIGUOUS_SAME_SNAPSHOT"
    ]
    assert fills == []
    assert events == []


def test_insufficient_top_of_book_capacity_does_not_fake_full_close():
    attempts, fills, events = reconcile_active_protections(
        snapshot(bid=9.4, ask=9.5, bid_size=2.0, ask_size=2.0),
        [position(quantity=10.0)],
    )

    assert attempts[0]["outcome"] == "INPUT_MISSING"
    assert attempts[0]["blockers"] == ["EXIT_TOP_OF_BOOK_CAPACITY_INSUFFICIENT"]
    assert fills == []
    assert events == []


def test_quote_override_preserves_capture_timestamp_and_source():
    value = snapshot()
    value["symbols"] = []
    captured_at = "2026-10-02T09:01:17+00:00"

    attempts, fills, events = reconcile_active_protections(
        value,
        [position()],
        quote_overrides={
            "TESTUSDT": {
                "symbol": "TESTUSDT",
                "bid_price": 9.4,
                "ask_price": 9.5,
                "bid_size": 1000,
                "ask_size": 1000,
                "_captured_at_utc": captured_at,
                "_reconciliation_quote_source":
                    "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE",
            }
        },
    )

    assert attempts[0]["observed_at_utc"] == captured_at
    assert attempts[0]["evidence"]["quote_source"] == (
        "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"
    )
    assert fills[0]["filled_at_utc"] == captured_at
    assert fills[0]["liquidity_source"] == (
        "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"
    )
    assert events[0]["occurred_at_utc"] == captured_at


def test_sql_contract_is_append_only_paper_only_and_oco_derived():
    sql = Path("ops/sql/paper_exit_reconciliation_v04.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert parse_sql(sql)
    assert "before update or delete" in sql
    assert "grant select,insert" in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql
    assert "exchange_authority=false" in sql
    assert "trade_permission=false" in sql
    assert "order_path='none'" in sql
    assert "cancelled_oco" in sql
    assert "triggered_paper" in sql
    assert "latest_state is distinct from 'filled'" in sql
    assert "full_economic_pnl_claim_permitted=false" in sql
    assert "pre_exit_reconciliation_gap" in sql
    assert "retroactive_exit_forbidden" in sql
    assert "quarantined_gap" in sql
    assert "pre_activation_gap" in sql
    assert "alpha_hunter_activate_paper_exit_v04" in sql
    assert "production_runtime_matched" in sql
