from pathlib import Path

from pglast import parse_sql

from alpha_hunter.paper_lifecycle import PaperState, transition_allowed
from alpha_hunter.paper_reconciliation import reconcile_open_orders


SQL = Path(
    "ops/sql/r8_reconciliation_required_containment_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def _snapshot(at="2026-10-03T12:00:00+00:00"):
    return {
        "run_id": "run-recovery",
        "collected_at_utc": at,
        "symbols": [
            {
                "symbol": "TESTUSDT",
                "bid_price": 9.99,
                "ask_price": 10.01,
                "bid_size": 1000.0,
                "ask_size": 1000.0,
            }
        ],
    }


def _reconciliation_required_order(
    submitted="2026-10-03T11:40:00+00:00",
):
    return {
        "order_id": "order-rr",
        "decision_id": "decision-rr",
        "symbol": "TESTUSDT",
        "direction": "LONG",
        "order_type": "MARKET",
        "limit_price": None,
        "ordered_quantity": 5.0,
        "filled_quantity": 0.0,
        "remaining_quantity": 5.0,
        "execution_state": "RECONCILIATION_REQUIRED",
        "fill_count": 0,
        "average_fill_price": None,
        "event_sequence": 4,
        "submitted_at_utc": submitted,
        "stop_price": 9.5,
        "target_price": 11.0,
        "public_maker_fee_bps": 2.0,
        "public_taker_fee_bps": 6.0,
    }


def test_sql_parses():
    assert parse_sql(SQL)


def test_db_view_exposes_only_zero_fill_initial_reconciliation_required_rows():
    assert "le.state='RECONCILIATION_REQUIRED'" in SQL
    assert "le.event_type='PAPER_FILL_EVIDENCE_INCOMPLETE'" in SQL
    assert "coalesce(x.filled_quantity,0)=0" in SQL
    assert "then 'RECONCILIATION_REQUIRED'" in SQL


def test_attempt_contract_accepts_true_reconciliation_required_prior_state():
    assert "'RECONCILIATION_REQUIRED'" in SQL
    assert "alpha_hunter_paper_reconciliation_attempts_v0_prior_state_check" in SQL


def test_reconciliation_required_has_exactly_fail_closed_expiry_recovery():
    assert transition_allowed(
        PaperState.RECONCILIATION_REQUIRED, PaperState.EXPIRED
    )
    assert not transition_allowed(
        PaperState.RECONCILIATION_REQUIRED, PaperState.FILLED
    )
    assert not transition_allowed(
        PaperState.RECONCILIATION_REQUIRED, PaperState.PARTIALLY_FILLED
    )
    assert not transition_allowed(
        PaperState.RECONCILIATION_REQUIRED, PaperState.SUBMITTED
    )


def test_reconciliation_required_never_delayed_fills_before_expiry():
    attempts, fills, events, protections = reconcile_open_orders(
        _snapshot(), [_reconciliation_required_order()]
    )
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "INPUT_MISSING"
    assert attempts[0]["prior_state"] == "RECONCILIATION_REQUIRED"
    assert attempts[0]["blockers"] == [
        "RECONCILIATION_REQUIRED_NO_DELAYED_FILL"
    ]
    assert fills == []
    assert events == []
    assert protections == []


def test_reconciliation_required_expires_after_frozen_35_minutes():
    attempts, fills, events, protections = reconcile_open_orders(
        _snapshot(),
        [_reconciliation_required_order(
            submitted="2026-10-03T11:00:00+00:00"
        )],
    )
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "EXPIRED"
    assert attempts[0]["prior_state"] == "RECONCILIATION_REQUIRED"
    assert attempts[0]["blockers"] == ["ENTRY_ORDER_EXPIRED_35M"]
    assert fills == []
    assert protections == []
    assert len(events) == 1
    assert events[0]["state"] == "EXPIRED"
    assert (
        events[0]["event_type"]
        == "PAPER_RECONCILIATION_REQUIRED_ENTRY_EXPIRED"
    )


def test_containment_status_is_read_only_and_live_authority_stays_off():
    required = [
        "delayed_fill_forbidden",
        "all_or_none_preserved",
        "false as live_money_claim_permitted",
        "false as exchange_authority",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'NONE'::text as order_path",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
        "cron.schedule",
        "cron.alter_job",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_status_view_is_service_role_read_only():
    assert "alpha_hunter_r8_reconciliation_required_status_v01" in LOWER
    assert (
        "grant select on public.alpha_hunter_r8_reconciliation_required_status_v01"
        in LOWER
    )
