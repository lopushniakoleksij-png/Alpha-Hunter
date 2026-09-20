from pathlib import Path

SQL = Path("readiness_score_compatibility_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_score_timing_compatibility_is_audit_only():
    required = [
        "alpha_hunter_readiness_score_compatibility_v01",
        "joint_score_and_early",
        "joint_score_early_eligible_phase",
        "joint_score_early_phase_direction",
        "JOINT_GATE_UNREACHED_IN_OBSERVED_7D_COHORT",
        "OBSERVATIONAL_AUDIT_ONLY",
        "false as threshold_changed",
        "false as trade_permission_granted_by_audit",
        "true as shadow_only",
        "false as trade_permission",
    ]
    for marker in required:
        assert marker in SQL


def test_current_reference_gate_is_explicit_not_mutated():
    assert "7.5::double precision as reference_execution_score" in SQL
    assert "'EARLY'::text as reference_required_timing" in SQL

    forbidden = [
        "update public.",
        "insert into public.",
        "delete from",
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled",
        "minimum_execution_score =",
        "minimum_execution_score:",
        "minimum_execution_reward_risk =",
        "minimum_execution_reward_risk:",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_oi_missingness_is_separated_from_observed_component_value():
    required = [
        "previous_behaviour_score",
        "open_interest_change_pct",
        "open_interest_component",
        "NO_PREVIOUS_SELECTED_OBSERVATION",
        "HAS_PREVIOUS_SELECTED_OBSERVATION",
        "oi_change_missing",
        "oi_component_zero",
        "MISSING_OI_IS_CURRENTLY_SCORED_AS_ZERO_IN_PRODUCTION",
        "AUDIT_ONLY_DO_NOT_REWEIGHT_FROM_THIS_VIEW",
    ]
    for marker in required:
        assert marker in SQL


def test_views_use_seven_day_observational_window():
    assert "s.collected_at_utc >= now()-interval '7 days'" in SQL


def test_views_are_service_role_only():
    for view in (
        "alpha_hunter_readiness_score_compatibility_v01",
        "alpha_hunter_oi_score_coverage_v01",
    ):
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER
        assert "to service_role" in LOWER


def test_no_execution_authority_is_added():
    for forbidden in (
        "place_order",
        "cancel_order",
        "modify_order",
        "set-leverage",
        "/api/v2/mix/order/place-order",
        "/api/v2/mix/order/cancel-order",
        "realistic_net_r_claim_permitted=true",
        "production_promotion_permitted=true",
    ):
        assert forbidden not in LOWER
