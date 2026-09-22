from pathlib import Path

from alpha_hunter.collector import build_validation_identity


SQL = Path("sealed_profitability_validation_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_validation_identity_is_deterministic(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "abc123")
    monkeypatch.setenv("GIT_BRANCH", "main")
    config = {
        "minimum_reward_risk": 5.0,
        "multi_strategy_engine": {"minimum_shadow_reward_risk": 5.0},
    }

    first = build_validation_identity(config)
    second = build_validation_identity(dict(reversed(list(config.items()))))

    assert first["git_commit"] == "abc123"
    assert first["git_branch"] == "main"
    assert first["config_sha256"] == second["config_sha256"]
    assert first["test_contract"] == "sealed-profitability-v0.1"


def test_preregistration_freezes_minimum_duration_sample_and_rr():
    required = [
        "minimum_test_days integer not null default 30 check(minimum_test_days>=30)",
        "minimum_completed_paper_trades integer not null default 100",
        "required_minimum_rr double precision not null default 5.0 check(required_minimum_rr>=5.0)",
        "confidence_z double precision not null default 1.96",
    ]
    for marker in required:
        assert marker in LOWER


def test_activation_requires_clean_current_architecture_baseline():
    required = [
        "validation_identity",
        "previous_snapshot_context",
        "catalyst_summary",
        "='0.2'",
        "multi_strategy_engine",
        "microstructure",
        "last_closed_candle",
    ]
    for marker in required:
        assert marker in SQL


def test_build_and_config_drift_invalidate_the_test():
    assert "identity_drift_scans" in SQL
    assert "invalidated_by_build_or_config_drift" in LOWER
    assert "config_sha256" in SQL
    assert "git_commit" in SQL


def test_paper_economics_uses_only_triggered_complete_unambiguous_outcomes():
    required = [
        "TRIGGERED_EXECUTE_NOW",
        "TRIGGERED_LIMIT",
        "path_measurement_quality='COMPLETE_ENOUGH'",
        "ordering_ambiguous=false",
        "horizon_hours=s.evaluation_horizon_hours",
    ]
    for marker in required:
        assert marker in SQL


def test_gross_r_is_path_based_and_not_invented():
    required = [
        "path_outcome_class='TARGET_FIRST'",
        "then b.remaining_r_at_candidate",
        "path_outcome_class='STOP_FIRST'",
        "then -1.0",
        "path_outcome_class='OPEN_AT_HORIZON'",
        "direction_adjusted_endpoint_return_pct/nullif(b.risk_pct,0)",
    ]
    for marker in required:
        assert marker in SQL


def test_observed_cost_floor_is_stress_test_not_realistic_net_claim():
    assert "observable_taker_round_trip_floor_p90_bps" in SQL
    assert "observed_floor_cost_r" in SQL
    assert "floor_adjusted_r" in SQL
    assert "no_validated_realistic_net_model" in LOWER


def test_modeled_net_requires_active_validated_cost_model_claim_gate():
    required = [
        "upper(m.status)='ACTIVE'",
        "validated_at_utc is not null",
        "activated_at_utc is not null",
        "floor_realistic_net_claim_permitted is true",
        "modeled_net_r",
    ]
    for marker in required:
        assert marker in SQL


def test_profitability_gate_requires_duration_sample_ci_and_profit_factor():
    required = [
        "duration_gate_met",
        "sample_gate_met",
        "modeled_net_r_lower_95",
        "modeled_net_profit_factor",
        ">=sa.minimum_test_days",
        ">=sa.minimum_completed_paper_trades",
        ">1.0",
    ]
    for marker in required:
        assert marker in SQL


def test_live_money_claim_is_never_granted_by_paper_test():
    assert "false as live_money_claim_permitted" in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_hourly_activation_job_is_present():
    assert "alpha-hunter-profitability-test-activation-v01-hourly" in SQL
    assert "'6 * * * *'" in SQL
