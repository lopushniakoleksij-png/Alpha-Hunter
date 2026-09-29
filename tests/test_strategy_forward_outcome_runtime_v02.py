from pathlib import Path

SQL_PATH = Path("ops/sql/strategy_forward_outcome_runtime_v02.sql")
SQL = SQL_PATH.read_text(encoding="utf-8").lower()


def test_runtime_patch_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_capture_strategy_forward_outcomes_v01" in SQL


def test_runtime_patch_bounds_symbol_snapshot_reads():
    assert "s.collected_at_utc>=v_measurement_start" in SQL
    assert "idx_ah_symbol_time" in SQL


def test_runtime_patch_uses_bounded_batch():
    assert "limit 120" in SQL
    assert "limit 500" not in SQL


def test_scientific_boundaries_remain_unchanged():
    for marker in [
        "fully closed 1h candles",
        "trigger_candle_excluded",
        "partial_signal_hour_excluded",
        "target_stop_same_candle_ambiguous",
        "path_measurement_quality",
        "not_bound_to_cost_evidence",
    ]:
        assert marker in SQL


def test_runtime_patch_never_grants_trade_authority():
    for forbidden in [
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
