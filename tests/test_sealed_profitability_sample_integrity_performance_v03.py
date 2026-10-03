from pathlib import Path

SQL = Path(
    "sealed_profitability_sample_integrity_performance_v03.sql"
).read_text(encoding="utf-8").lower()


def test_sample_integrity_uses_per_spec_lateral_aggregates():
    assert "left join lateral" in SQL
    assert "post_baseline_candidate_observation_count" in SQL
    assert "post_baseline_24h_economic_eligible_rows" in SQL


def test_sample_integrity_remains_source_scoped():
    assert "required_run_source" in SQL
    assert "validation_identity" in SQL
    assert "run_source" in SQL


def test_sample_integrity_preserves_left_censor_policy():
    assert "left_censored_candidate_observation_count" in SQL
    assert "left_censored_24h_outcome_rows" in SQL
    assert "left_censored_candidates_are_diagnostic_only" in SQL


def test_sample_integrity_keeps_duplicate_and_contamination_guards():
    required = [
        "contaminated_pre_baseline_economics_rows",
        "duplicate_economics_episode_rows",
        "duplicate_24h_outcome_rows",
        "fail_pre_baseline_contamination",
        "fail_duplicate_sample_rows",
    ]
    for marker in required:
        assert marker in SQL


def test_sample_integrity_has_no_execution_authority():
    required = [
        "true as audit_only",
        "true as paper_only",
        "false as profitability_rule_change_permitted",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in SQL
