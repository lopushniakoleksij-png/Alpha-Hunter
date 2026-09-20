from pathlib import Path

SQL = Path("scientific_forward_holdout_v02.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_v02_is_a_new_prospective_spec_not_a_v01_mutation():
    required = [
        "AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V02",
        "H_EARLY_OPERATIONAL_BUNDLE_DISCRIMINATION_12H_V2",
        "supersedes_spec_id",
        "outcome_evidence_used_in_amendment',false",
        "v0.1 evidence remains immutable",
    ]
    for marker in required:
        assert marker in SQL


def test_v02_matching_rule_has_common_support_controls():
    required = [
        "exact direction, lifecycle, liquidity_state and candidate_quality_status",
        "absolute decision-time gap <=24 hours",
        "abs(abs_move_test-abs_move_control)/5",
        "abs(similarity_test-similarity_control)/100",
        "abs(feature_coverage_test-feature_coverage_control)",
        "abs(time_gap_hours)/24",
        "bridge_status",
        "source_run_id exact-match",
    ]
    for marker in required:
        assert marker in SQL


def test_v02_does_not_change_assignment_or_primary_endpoint():
    required = [
        "scanner_direction equals candidate direction",
        "geometry_source SCANNER_EXECUTION_SETUP",
        "geometry_direction_bound explicitly true",
        "same prospective EARLY safety and source contract",
        "decision_anchor_direction_adjusted_close_return_pct",
        "'decision_anchor_direction_adjusted_close_return_pct',12,24,100,30,20,25,60",
    ]
    for marker in required:
        assert marker in SQL


def test_v02_outcomes_are_locked_and_promotion_is_impossible():
    required = [
        "outcomes are prohibited",
        "false as outcome_access_permitted",
        "false as primary_results_exposed",
        "false as confirmatory_analysis_permitted",
        "false as production_promotion_permitted",
        "true as shadow_only",
        "false as trade_permission",
        "'NONE'::text as order_path",
    ]
    for marker in required:
        assert marker in SQL


def test_v02_capture_is_strictly_post_registration():
    required = [
        "new.created_at <= v_spec.registered_at_utc",
        "new.candidate_at_utc <= v_spec.registered_at_utc",
        "NOT_STRICTLY_POST_REGISTRATION",
        "AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V02",
    ]
    for marker in required:
        assert marker in SQL


def test_v02_view_is_security_invoker_and_service_role_read_only():
    assert "security_invoker=true" in LOWER
    assert "grant select on public.alpha_hunter_scientific_holdout_status_v02" in LOWER
    assert "to service_role" in LOWER
    forbidden = [
        "trade_permission=true",
        "production_execution_enabled=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER
