from pathlib import Path

SQL = Path("ops/sql/test_engine_direct_gates_v04.sql").read_text(encoding="utf-8").lower()


def test_v04_avoids_heavy_wrapper_views():
    assert "alpha_hunter_profitability_validation_status_v01" not in SQL
    assert "alpha_hunter_profitability_sample_integrity_v01" not in SQL
    assert "alpha_hunter_execution_cost_floor_status_v01" not in SQL


def test_v04_preserves_gate_inputs():
    for marker in [
        "alpha_hunter_profitability_cadence_integrity_v01",
        "alpha_hunter_strategy_paper_economics_v01",
        "identity_drift_scans",
        "sample_integrity_ok",
        "minimum_test_days",
        "minimum_completed_paper_trades",
        "confidence_z",
        "floor_profit_factor",
        "modeled_net_edge_gate_met",
    ]:
        assert marker in SQL


def test_v04_reports_cadence_failure_as_operational_blocker():
    assert "cadence_integrity_failed" in SQL
    assert "cadence_integrity_ok" in SQL
    assert "excessive_gap_intervals" in SQL


def test_v04_remains_fail_closed_on_cost_model():
    assert "'validated_execution_cost_model_missing'" in SQL
    assert "'realistic_net_r_claim_not_permitted'" in SQL
    assert "false,false," in SQL
    assert "'blocked_no_validated_realistic_cost_model'" in SQL


def test_v04_never_grants_trade_authority():
    for forbidden in [
        "trade_permission,true",
        "trade_permission = true",
        "production_promotion_permitted,true",
        "production_promotion_permitted = true",
        "live_money_claim_permitted,true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
