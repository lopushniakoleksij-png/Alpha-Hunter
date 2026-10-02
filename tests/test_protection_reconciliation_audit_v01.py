from pathlib import Path

SQL = Path("ops/sql/protection_reconciliation_audit_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_audit_is_forward_only_and_append_only():
    assert "after insert on public.alpha_hunter_open_position_snapshots" in LOWER
    assert "before update or delete on public.alpha_hunter_protection_reconciliation_events_v01" in LOWER
    assert "private.alpha_hunter_block_append_only_mutation()" in LOWER
    assert "'forward_only',true" in SQL
    assert "update public.alpha_hunter_open_position_snapshots" not in LOWER
    assert "delete from public.alpha_hunter_open_position_snapshots" not in LOWER


def test_audit_distinguishes_unknown_observed_partial_and_none():
    for state in [
        "OBSERVED_BOTH",
        "OBSERVED_STOP_ONLY",
        "OBSERVED_TP_ONLY",
        "NONE_OBSERVED",
        "UNKNOWN",
    ]:
        assert state in SQL
    assert "observation_status <> 'CONNECTED'" in SQL
    assert "stop_present and take_profit_present" in SQL


def test_pending_tpsl_fallback_is_tracked_as_position_field_gap():
    assert "position_field_gap_detected" in SQL
    assert "PENDING_TPSL" in SQL
    assert "exchange_stop_loss_source" in SQL
    assert "exchange_take_profit_source" in SQL


def test_all_observed_plan_levels_are_counted():
    assert "loss_plan" in SQL
    assert "pos_loss" in SQL
    assert "profit_plan" in SQL
    assert "pos_profit" in SQL
    assert "stop_order_count" in SQL
    assert "take_profit_order_count" in SQL


def test_audit_failure_cannot_block_canonical_position_persistence():
    assert "exception when others then" in LOWER
    assert "audit failure must not block canonical position persistence" in LOWER
    assert "return new;" in LOWER


def test_no_exchange_or_order_authority_is_added():
    for forbidden in [
        "api.bitget.com",
        "http_get",
        "http_post",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer(",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in LOWER
    assert "trade_permission boolean not null default false" in LOWER
    assert "false as trade_permission" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_current_view_is_immediately_queryable_from_immutable_evidence():
    assert "create or replace view public.alpha_hunter_protection_reconciliation_current_v01" in LOWER
    assert "alpha_hunter_open_position_snapshots" in LOWER
    assert "alpha_hunter_account_state_snapshots" in LOWER
    assert "canonical_run_id" in LOWER
