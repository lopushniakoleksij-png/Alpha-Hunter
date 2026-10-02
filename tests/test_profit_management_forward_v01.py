from pathlib import Path

from pglast import parse_sql

SQL = Path("ops/sql/profit_management_forward_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_forward_monitor_sql_parses():
    assert parse_sql(SQL)


def test_activation_timestamp_makes_monitor_forward_only():
    assert "activated_at_utc timestamptz not null default clock_timestamp()" in LOWER
    assert "new.captured_at_utc < v_activated_at" in LOWER
    assert "no_historical_backfill" in LOWER
    assert "after insert on public.alpha_hunter_open_position_snapshots" in LOWER
    assert "insert into public.alpha_hunter_profit_management_forward_v01" in LOWER

    forbidden = [
        "insert into public.alpha_hunter_profit_management_forward_v01\nselect",
        "insert into public.alpha_hunter_profit_management_forward_v01 select",
        "update public.alpha_hunter_open_position_snapshots",
        "delete from public.alpha_hunter_open_position_snapshots",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_three_preregistered_policies_are_persisted():
    for policy in [
        "BE_AFTER_3PCT",
        "LOCK_25_AFTER_5PCT",
        "LOCK_50_AFTER_5PCT",
    ]:
        assert policy in SQL
    assert "policy_count integer not null default 3" in LOWER


def test_episode_continuity_is_conservative():
    required = [
        "CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT",
        "ENTRY_CHANGED_RESTART",
        "FORWARD_ANCHOR_MISSING_RESTART",
        "NEW_FORWARD_EPISODE",
        "a.captured_at_utc < new.captured_at_utc",
        "p.account_snapshot_id=v_prev_account_id",
        "p.symbol=new.symbol",
        "p.direction=new.direction",
        "abs(new.average_entry-v_prev_average_entry) > v_entry_tolerance",
    ]
    for marker in required:
        assert marker in SQL


def test_quantity_change_is_recorded_but_does_not_guess_new_entry():
    assert "quantity_changed_from_previous" in SQL
    assert "v_quantity_changed" in SQL
    assert "episode_initial_quantity" in SQL


def test_running_favorable_move_is_direction_correct():
    required = [
        "greatest(",
        "v_prev_policy.running_favorable_mark",
        "least(",
        "100.0*(v_running_favorable_mark-v_anchor_entry_price)",
        "100.0*(v_anchor_entry_price-v_running_favorable_mark)",
    ]
    for marker in required:
        assert marker in SQL


def test_trigger_requires_observed_mark_cross_and_freezes_terminal_state():
    required = [
        "new.mark_price <= v_shadow_stop",
        "new.mark_price >= v_shadow_stop",
        "v_prev_policy.shadow_state='TRIGGERED'",
        "freeze its terminal evidence",
        "shadow_trigger_observed_mark",
        "shadow_stop_at_trigger",
    ]
    for marker in required:
        assert marker in SQL


def test_shadow_failure_cannot_block_canonical_ledger():
    assert "exception when others then" in LOWER
    assert "shadow-monitor failure must never block canonical account evidence" in LOWER
    assert "return new;" in LOWER


def test_monitor_is_append_only_and_service_role_only():
    assert "before update or delete on public.alpha_hunter_profit_management_forward_v01" in LOWER
    assert "private.alpha_hunter_block_append_only_mutation()" in LOWER
    assert "enable row level security" in LOWER
    assert "grant select,insert on public.alpha_hunter_profit_management_forward_v01" in LOWER
    assert "grant update" not in LOWER
    assert "grant delete" not in LOWER


def test_live_management_and_execution_remain_impossible():
    required = [
        "management_change_permitted boolean not null default false",
        "stop_change_permitted boolean not null default false",
        "target_change_permitted boolean not null default false",
        "promotion_permitted boolean not null default false",
        "trade_permission boolean not null default false",
        "order_path text not null default 'NONE'",
        "counterfactual_net_pnl_claim_permitted boolean not null default false",
    ]
    for marker in required:
        assert marker.lower() in LOWER

    forbidden = [
        "api.bitget.com",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer(",
        "trade_permission=true",
        "trade_permission = true",
        "promotion_permitted=true",
        "promotion_permitted = true",
        "management_change_permitted=true",
        "management_change_permitted = true",
        "stop_change_permitted=true",
        "stop_change_permitted = true",
        "target_change_permitted=true",
        "target_change_permitted = true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_coverage_view_detects_missing_rows_and_safety_violations():
    required = [
        "alpha_hunter_profit_management_forward_coverage_v01",
        "expected_observation_count",
        "position_snapshot_coverage_pct",
        "policy_observation_coverage_pct",
        "preactivation_observation_violations",
        "trade_permission_violations",
        "order_path_violations",
        "forward_monitoring_complete",
    ]
    for marker in required:
        assert marker in SQL
