from pathlib import Path

SQL = Path("nonstop_production_status_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_status_surface_covers_required_nonstop_components():
    required = [
        "alpha_hunter_control_plane_runs",
        "alpha_hunter_geometry_holdout_collection_status_v01",
        "alpha_hunter_geometry_feasibility_status_v01",
        "alpha_hunter_direction_confirmation_tax_status_v01",
        "alpha_hunter_money_entry_stage_snapshots",
        "cron.job",
        "p0_continuity_status",
        "anti_drift_status",
        "single_next_action",
        "primary_development_priority",
    ]
    for marker in required:
        assert marker in SQL


def test_single_next_action_prioritizes_safety_then_continuity_then_research():
    ordered = [
        "INVESTIGATE_SAFETY_IMMEDIATELY",
        "RESTORE_P0_CONTINUITY",
        "REPAIR_FAILED_PRODUCTION_STAGE",
        "RESTORE_DATA_FRESHNESS",
        "REPAIR_PROSPECTIVE_CAPTURE",
        "COLLECT_PROSPECTIVE_EVIDENCE",
        "WAIT_FOR_SEALED_EVALUATOR",
        "SCIENTIFIC_REVIEW_ONLY_NO_AUTOMATIC_PROMOTION",
    ]
    positions = [SQL.index(x) for x in ordered]
    assert positions == sorted(positions)


def test_status_never_authorizes_thresholds_promotion_or_live_orders():
    required = [
        "false as automatic_threshold_change_permitted",
        "false as automatic_production_promotion_permitted",
        "false as live_order_path_permitted",
        "true as shadow_only",
        "false as trade_permission",
    ]
    for marker in required:
        assert marker in SQL


def test_anti_drift_checks_all_research_claim_boundaries():
    required = [
        "geometry_threshold_change_permitted",
        "geometry_production_promotion_permitted",
        "geometry_sealed_outcome_read",
        "confirmation_outcome_evidence_used",
        "confirmation_sealed_outcome_read",
        "t0_authorized",
        "confirmation_threshold_change_permitted",
        "confirmation_production_promotion_permitted",
        "holdout_production_promotion_permitted",
    ]
    for marker in required:
        assert marker in SQL


def test_view_is_service_role_only():
    assert (
        "revoke all on public.alpha_hunter_nonstop_production_status_v01"
        in LOWER
    )
    assert (
        "grant select on public.alpha_hunter_nonstop_production_status_v01"
        in LOWER
    )
    assert "to service_role" in LOWER


def test_status_view_is_read_only_and_does_not_touch_sealed_outcomes():
    forbidden = [
        "insert into",
        "update public.",
        "delete from",
        "alter table",
        "cron.schedule",
        "place_order",
        "cancel_order",
        "modify_order",
        "trade_permission=true",
        "trade_permission = true",
        "geometry_holdout_outcomes_sealed",
        "evaluator_failures",
    ]
    for marker in forbidden:
        assert marker not in LOWER
