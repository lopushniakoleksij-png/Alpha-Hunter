from pathlib import Path

SQL_PATH = Path("ops/sql/test_engine_fast_refresh_v03.sql")
SQL = SQL_PATH.read_text(encoding="utf-8").lower()


def test_fast_refresh_keeps_gate_critical_views():
    for view in [
        "alpha_hunter_profitability_validation_status_v01",
        "alpha_hunter_profitability_cadence_integrity_v01",
        "alpha_hunter_profitability_sample_integrity_v01",
        "alpha_hunter_private_fill_cost_readiness_v01",
    ]:
        assert view in SQL


def test_fast_refresh_drops_non_gating_full_status_scans():
    assert "alpha_hunter_realtime_profitability_monitor_v01" not in SQL
    assert "alpha_hunter_strategy_forward_status_v01" not in SQL
    assert "alpha_hunter_strategy_opportunity_status_v01" not in SQL
    assert "'non_gating_counts_carried_forward',true" in SQL


def test_fast_refresh_remains_paper_only_and_fail_closed():
    for marker in [
        "'paper_only',true",
        "'trade_permission',false",
        "'production_promotion_permitted',false",
        "'order_path','none'",
        "validated_execution_cost_model_missing",
        "realistic_net_r_claim_not_permitted",
        "cadence_integrity_failed",
        "sample_integrity_failed",
    ]:
        assert marker in SQL


def test_fast_refresh_does_not_change_trading_thresholds():
    for forbidden in [
        "update public.alpha_hunter_profitability_test_specs_v01",
        "insert into public.alpha_hunter_profitability_test_specs_v01",
        "minimum_reward_risk =",
        "trade_permission=true",
        "production_promotion_permitted=true",
        "place_order",
        "cancel_order",
        "modify_order",
    ]:
        assert forbidden not in SQL


def test_cron_moves_to_hourly_fast_refresh():
    assert "alpha-hunter-test-engine-db-refresh-v02" in SQL
    assert "schedule := '2 * * * *'" in SQL
    assert "alpha_hunter_refresh_test_engine_v03()" in SQL
