from pathlib import Path

SQL = Path("geometry_feasibility_decomposition_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_five_r_boundary_is_exact_not_invented():
    required = [
        "1.0/6.0 as max_range_fraction_for_5r",
        "(b.target_price+5.0*b.stop_price)/6.0",
        "(5.0*b.stop_price+b.target_price)/6.0",
        "c.reward_distance/5.0 as max_risk_distance_for_5r_current_target",
        "5.0*c.risk_distance as required_reward_distance_for_5r_current_stop",
    ]
    for marker in required:
        assert marker in SQL


def test_view_decomposes_entry_stop_and_target_without_changing_them():
    required = [
        "adverse_entry_gap_to_5r_pct",
        "stop_tightening_needed_pct",
        "target_extension_needed_pct",
        "stop_tightening_needed_atr1h",
        "target_extension_needed_atr1h",
        "range_fraction_from_stop_side",
        "risk_pct",
        "reward_pct",
    ]
    for marker in required:
        assert marker in SQL


def test_scanner_and_explicit_cohorts_are_separate():
    required = [
        "ALL_SHADOW_GEOMETRY",
        "SCANNER_DIRECTION_ALIGNED",
        "EXPLICIT_EXECUTION_GEOMETRY",
        "scanner_direction_aligned=true",
        "explicit_geometry_complete=true",
    ]
    for marker in required:
        assert marker in SQL


def test_feasibility_class_uses_current_geometry_only():
    required = [
        "GEOMETRY_ORIENTATION_INVALID",
        "CURRENT_GEOMETRY_RR5_FEASIBLE",
        "ENTRY_BEYOND_RR5_RANGE_BOUNDARY",
        "RR5_INFEASIBLE_OTHER",
    ]
    for marker in required:
        assert marker in SQL


def test_scientific_safety_boundary_is_explicit():
    required = [
        "DECISION_TIME_GEOMETRY_DIAGNOSTIC_ONLY",
        "false as threshold_change_permitted",
        "false as production_promotion_permitted",
        "false as outcome_evidence_used",
        "false as sealed_holdout_outcome_read",
        "true as shadow_only",
        "false as trade_permission",
    ]
    for marker in required:
        assert marker in SQL


def test_views_are_service_role_only():
    for view in (
        "alpha_hunter_geometry_feasibility_observations_v01",
        "alpha_hunter_geometry_feasibility_status_v01",
    ):
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER


def test_no_production_or_execution_mutation():
    forbidden = [
        "insert into",
        "update public.",
        "delete from",
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled",
        "place_order",
        "cancel_order",
        "modify_order",
        "set-leverage",
        "alter table",
        "cron.schedule",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_no_sealed_holdout_table_is_read():
    assert "geometry_holdout_outcomes_sealed" not in LOWER
    assert "evaluator_failures" not in LOWER
