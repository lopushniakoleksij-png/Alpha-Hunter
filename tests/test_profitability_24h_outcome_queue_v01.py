from pathlib import Path

SQL_PATH = Path("ops/sql/profitability_24h_outcome_queue_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8").lower()


def test_queue_is_ops_only_and_private():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "private.alpha_hunter_strategy_24h_outcome_queue_v01" in SQL
    assert "create trigger trg_ah_enqueue_strategy_24h_outcome_v01" in SQL


def test_queue_uses_due_index_instead_of_global_missing_scan():
    assert "idx_ah_strategy_24h_queue_pending_due_v01" in SQL
    assert "q.status='pending'" in SQL
    assert "q.due_at_utc<=clock_timestamp()" in SQL
    assert "limit 30" in SQL


def test_backfill_is_bounded_to_current_outage_window():
    assert "max(o.evaluated_at_utc)-interval '24 hours'" in SQL
    assert "clock_timestamp()-interval '48 hours'" in SQL
    assert "'pending'" in SQL


def test_outcome_science_is_preserved():
    for marker in [
        "foreach v_horizon in array array[1,4,12,24]",
        "target_stop_same_candle_ambiguous",
        "trigger_candle_excluded",
        "partial_signal_hour_excluded",
        "path_measurement_quality",
        "not_bound_to_cost_evidence",
    ]:
        assert marker in SQL


def test_queue_does_not_grant_trade_authority():
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


def test_profitability_queue_is_hourly_and_general_catchup_is_reduced():
    assert "alpha-hunter-strategy-24h-profitability-catchup-v01" in SQL
    assert "'52 * * * *'" in SQL
    assert "alpha-hunter-strategy-forward-outcome-v01-hourly" in SQL
    assert "schedule := '53 */6 * * *'" in SQL
