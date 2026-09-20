from pathlib import Path

STATUS = Path("nonstop_production_status_v03.sql").read_text(
    encoding="utf-8"
)
LOWER = STATUS.lower()


def test_v03_adds_forward_missed_mover_audit():
    required = [
        "alpha_hunter_nonstop_production_status_v03",
        "alpha_hunter_forward_missed_mover_audit_status_v01",
        "mover_answer_key_episode_count",
        "mover_audited_episode_count",
        "mover_unaudited_episode_count",
        "discovery_root_causes",
        "ranking_root_causes",
        "direction_root_causes",
        "confirmation_tax_root_causes",
        "execution_rr_root_causes",
        "data_root_causes",
    ]
    for marker in required:
        assert marker in STATUS


def test_v03_requires_missed_mover_hourly_job():
    assert "alpha-hunter-forward-missed-mover-audit-hourly" in STATUS
    assert "required_active_job_count" in STATUS


def test_anti_drift_detects_hindsight_or_duplicate_scan():
    required = [
        "mover_second_market_scan_used",
        "mover_root_cause_uses_only_pre5_evidence",
        "mover_post_event_magnitude_used_for_classification",
        "mover_future_outcome_used_for_classification",
        "REVIEW_REQUIRED",
    ]
    for marker in required:
        assert marker in STATUS


def test_single_next_action_repairs_stale_audit_not_normal_schedule_gap():
    required = [
        "mover_unaudited_episode_count>0",
        "interval '90 minutes'",
        "REPAIR_MISSED_MOVER_AUDIT",
        "COLLECT_PROSPECTIVE_EVIDENCE",
    ]
    for marker in required:
        assert marker in STATUS



def test_h2_repair_action_requires_capture_or_anchor_outage_not_any_historical_failure():
    required = [
        "h2_capture_failure_events>0",
        "h2_captured_rows=0",
        "h2_triggered_rows>0",
        "independent_h2_anchors=0",
        "REPAIR_H2_CAPTURE",
    ]
    for marker in required:
        assert marker in STATUS



def test_v03_monitors_h2_sealed_collector_and_requires_all_hourly_jobs():
    required = [
        "alpha_hunter_h2_direction_sealed_collection_status_v01",
        "alpha-hunter-h2-direction-sealed-outcome-hourly",
        "required_active_job_count<14",
        "P0_REQUIRED_JOB_MISSING",
        "RESTORE_REQUIRED_HOURLY_JOBS",
        "SEALED_COLLECTION_INCOMPLETE_RETRY_REQUIRED",
        "REPAIR_H2_SEALED_COLLECTION",
        "h2_sealed_collection_status",
    ]
    for marker in required:
        assert marker in STATUS


def test_v03_h2_sealed_results_cannot_silently_unseal():
    required = [
        "h2c.primary_results_exposed is true",
        "h2c.outcome_access_permitted is true",
        "h2c.confirmatory_analysis_permitted is true",
        "h2c.t0_authorized is true",
        "h2c.threshold_change_permitted is true",
        "h2c.production_promotion_permitted is true",
    ]
    for marker in required:
        assert marker in STATUS


def test_v03_preserves_safety_claim_ceiling():
    required = [
        "false as automatic_threshold_change_permitted",
        "false as automatic_production_promotion_permitted",
        "false as live_order_path_permitted",
        "true as shadow_only",
        "false as trade_permission",
    ]
    for marker in required:
        assert marker in STATUS


def test_v03_is_read_only_and_service_role_only():
    assert "grant select on public.alpha_hunter_nonstop_production_status_v03" in LOWER
    for marker in (
        "insert into",
        "update public.",
        "delete from",
        "place_order",
        "cancel_order",
        "modify_order",
    ):
        assert marker not in LOWER
