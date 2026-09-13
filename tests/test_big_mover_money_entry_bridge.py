from pathlib import Path


BRIDGE_SQL = Path("big_mover_money_entry_bridge.sql").read_text(encoding="utf-8")
PARENT_SQL = Path("big_mover_parent_direction_shadow.sql").read_text(encoding="utf-8")
SHADOW_SCHEMA = Path("big_mover_shadow_schema.sql").read_text(encoding="utf-8")


def test_raw_and_direction_normalized_moves_are_explicit():
    assert "raw_change_24h_pct" in SHADOW_SCHEMA
    assert "direction_normalized_move_pct" in SHADOW_SCHEMA
    assert "CURRENT_MOVE_OPPOSES_DIRECTION" in BRIDGE_SQL


def test_parent_direction_is_isolated_and_fail_closed():
    assert "timeframe in ('12H','1D')" in PARENT_SQL
    assert "PARENT_12H_NOT_ALIGNED" in BRIDGE_SQL
    assert "PARENT_1D_NOT_ALIGNED" in BRIDGE_SQL
    assert "PARENT_12H_DATA_UNAVAILABLE" in BRIDGE_SQL
    assert "PARENT_1D_DATA_UNAVAILABLE" in BRIDGE_SQL
    assert "EXECUTION_GEOMETRY_MISSING" in BRIDGE_SQL


def test_bridge_and_parent_runtime_cannot_grant_trade_permission():
    for sql in (BRIDGE_SQL, PARENT_SQL):
        assert "check (shadow_only = true)" in sql
        assert "check (trade_permission = false)" in sql
        assert "trade_permission=false" in sql
        assert "revoke execute" in sql
        assert "service_role" in sql


def test_runtime_order_is_big_mover_then_parent_then_bridge():
    assert "'11 * * * *'" in PARENT_SQL
    assert "'12 * * * *'" in BRIDGE_SQL
    assert "alpha_hunter_collect_big_mover_parent_direction" in PARENT_SQL
    assert "alpha_hunter_run_big_mover_money_entry_pipeline" in BRIDGE_SQL


def test_bridge_does_not_claim_t0_or_invent_thresholds():
    assert "'thresholds_invented',false" in BRIDGE_SQL
    assert "'t0_authorized',false" in BRIDGE_SQL
    assert "Exact T0/T1/T2 decision remains fail-closed" in BRIDGE_SQL
