from pathlib import Path

SQL = Path("ops/sql/payoff_geometry_health_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_monitor_is_forward_only():
    assert "new.frozen_at_utc<v_spec.registered_at_utc" in SQL
    assert "does not insert any pre-registration decision" in SQL
    assert "insert into private.alpha_hunter_payoff_geometry_health_observations_v01" in SQL
    assert "select * from public.alpha_hunter_execution_decision_freezes_v01" not in SQL


def test_history_is_cut_off_at_decision_time():
    assert "o.evaluated_at_utc<=new.frozen_at_utc" in SQL
    assert "history_cutoff_at_decision_utc" in SQL


def test_geometry_health_uses_mae_mfe_and_cost():
    assert "percentile_cont(0.5)" in SQL
    assert "percentile_cont(0.90)" in SQL
    assert "observable_taker_round_trip_floor_median_bps" in SQL
    assert "stop_inside_median_mae" in SQL
    assert "target_beyond_p90_mfe" in SQL
    assert "cost_fragile" in SQL


def test_cost_floor_is_not_mislabeled_as_validated():
    assert "'cost_floor_is_validated_model',false" in SQL
    assert "'cost_floor_assumption','descriptive_median_taker_round_trip_floor'" in SQL


def test_monitor_has_no_trade_authority():
    for marker in [
        "shadow_only boolean not null default true",
        "trade_permission boolean not null default false",
        "threshold_change_permitted boolean not null default false",
        "production_promotion_permitted boolean not null default false",
        "order_path text not null default 'none'",
        "'trade_gate_applied',false",
        "'production_selector_changed',false",
    ]:
        assert marker in SQL

    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL
