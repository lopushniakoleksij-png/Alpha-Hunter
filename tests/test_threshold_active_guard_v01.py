from pathlib import Path

SQL = Path("ops/sql/threshold_active_guard_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_active_requires_complete_t0_t1_t2_numbers():
    assert "complete t0/t1/t2 numeric thresholds are required" in SQL
    assert "new.max_t0_stop_distance_pct is null" in SQL
    assert "new.min_t0_remaining_r is null" in SQL
    assert "new.min_t1_remaining_r is null" in SQL
    assert "new.min_t2_remaining_r is null" in SQL


def test_global_table_requires_both_direction_validation():
    assert "global_both_directions" in SQL
    assert "independent long and short validation must both pass" in SQL
    assert "long_validation" in SQL
    assert "short_validation" in SQL


def test_same_frozen_contract_required_for_both_directions():
    assert "threshold_contract_hash" in SQL
    assert "v_contract_hash<>v_long_hash" in SQL
    assert "v_contract_hash<>v_short_hash" in SQL


def test_active_threshold_requires_validated_active_cost_model():
    assert "validated_execution_cost_model_id" in SQL
    assert "c.status='active'" in SQL
    assert "c.validated_at_utc is not null" in SQL
    assert "c.activated_at_utc is not null" in SQL


def test_guard_does_not_activate_or_trade():
    assert "if new.status<>'active' then" in SQL
    assert "existing rows are untouched" in SQL
    for forbidden in [
        "update public.alpha_hunter_money_entry_threshold_sets",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
    ]:
        assert forbidden not in SQL


def test_security_boundary_is_explicit():
    assert "security invoker" in SQL
    assert "revoke all on function private.alpha_hunter_guard_money_entry_threshold_active_v01()" in SQL
