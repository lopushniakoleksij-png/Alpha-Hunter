from pathlib import Path

SQL = Path("ops/sql/participation_endpoint_forward_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_frozen_scientific_contract_is_fail_closed():
    assert "v_spec.endpoint_max_lag_minutes<>30" in SQL
    assert "v_spec.horizons_hours<>array[1,4,12,24]" in SQL
    assert "'frozen_contract_mismatch'" in SQL


def test_original_forward_registration_boundary_is_preserved():
    assert "d.captured_at_utc>=v_spec.registered_at_utc" in SQL
    assert "historical_pre_registration_backfill_permitted',false" in SQL
    assert "no diagnostic captured before the original registered_at_utc is admitted" in SQL


def test_queue_limit_is_applied_after_canonical_resolution():
    marker = "critical v0.2 change"
    section = SQL[SQL.index(marker):SQL.index("-- explicitly censor matured endpoint windows")]
    join_pos = section.index("join lateral")
    order_pos = section.index("order by d.due_at_utc")
    limit_pos = section.index("limit 2000", order_pos)
    assert join_pos < order_pos < limit_pos
    assert "queue_limit_applied_after_resolution',true" in SQL


def test_missing_endpoint_windows_are_explicitly_censored():
    assert "alpha_hunter_participation_endpoint_failures_v02" in SQL
    assert "no_canonical_snapshot_within_30m" in SQL
    assert "endpoint_return_claim_permitted',false" in SQL
    assert "unique(candidate_id,horizon_hours)" in SQL


def test_censoring_does_not_relax_the_30m_endpoint_window():
    assert "s.collected_at_utc<=d.due_at_utc" in SQL
    assert "make_interval(mins=>v_spec.endpoint_max_lag_minutes)" in SQL
    assert "endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes" in SQL


def test_existing_forward_outcomes_are_immutable():
    assert "update private.alpha_hunter_participation_endpoint_outcomes_v01" not in SQL
    assert "delete from private.alpha_hunter_participation_endpoint_outcomes_v01" not in SQL
    assert "no existing forward outcome row is updated/deleted" in SQL


def test_no_trade_threshold_or_production_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "threshold_derivation_permitted=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_v02_replaces_v01_cron_instead_of_running_both():
    assert "'alpha-hunter-participation-endpoint-forward-v01'" in SQL
    assert "'alpha-hunter-participation-endpoint-forward-v02'" in SQL
    assert "cron.unschedule" in SQL
    assert "'14 * * * *'" in SQL


def test_service_role_remains_read_only():
    assert "grant select on private.alpha_hunter_participation_endpoint_failures_v02" in SQL
    assert "grant select on private.alpha_hunter_participation_endpoint_runs_v02" in SQL
    assert (
        "grant execute on function private.alpha_hunter_run_participation_endpoint_forward_v02()\n"
        "to postgres"
    ) in SQL


def test_overlapping_v02_runs_fail_closed():
    assert "pg_try_advisory_xact_lock" in SQL
    assert "hashtextextended('alpha-hunter-participation-endpoint-forward-v02',0)" in SQL
    assert "'run_already_active'" in SQL
