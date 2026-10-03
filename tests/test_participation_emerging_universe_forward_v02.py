from pathlib import Path

SQL = Path("ops/sql/participation_emerging_universe_forward_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_rule_is_preexisting_partial_concept():
    assert "preexisting_alpha_hunter_analysis_partial_classification" in SQL
    assert "volume_state_1h_in_elevated_high or open_interest_change_pct_gt_0" in SQL


def test_new_version_binds_only_to_source_consistent_endpoint_v02():
    assert "participation-universe-endpoint-forward-v02" in SQL
    assert "private.alpha_hunter_participation_universe_endpoint_candidates_v02" in SQL
    assert "private.alpha_hunter_participation_universe_endpoint_outcomes_v02" in SQL
    assert "private.alpha_hunter_participation_universe_endpoint_failures_v02" in SQL
    assert "private.alpha_hunter_participation_endpoint_candidates_v01" not in SQL
    assert "private.alpha_hunter_participation_endpoint_outcomes_v01" not in SQL


def test_source_endpoint_contract_is_fail_closed():
    assert "frozen_source_contract_mismatch" in SQL
    assert "universe_t0_to_universe_endpoint" in SQL
    assert "primary_scanner_cached_tickers" in SQL
    assert "canonical_scan_ticker_snapshot" in SQL
    assert "endpoint_max_lag_minutes<>30" in SQL
    assert "horizons_hours<>array[1,4,12,24]" in SQL


def test_forward_boundary_and_no_backfill():
    assert "ep.captured_at_utc>=v_spec.registered_at_utc" in SQL
    assert "historical_backfill_permitted',false" in SQL
    assert "registered_at_utc is admitted" in SQL


def test_confirmed_rows_are_separate():
    assert "scanner_confirmed" in SQL
    assert "when s.scanner_participation_confirmed is true" in SQL


def test_scorecard_surfaces_endpoint_missingness():
    assert "matured_rows" in SQL
    assert "evaluated_rows" in SQL
    assert "censored_rows" in SQL
    assert "pending_materialization_rows" in SQL
    assert "source_coverage_pct" in SQL


def test_no_t1_mapping_threshold_trade_or_production_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "t1_stage_mapping_permitted=true",
        "threshold_derivation_permitted=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_service_role_is_read_only_and_execute_is_postgres_only():
    assert (
        "grant select on private.alpha_hunter_participation_emerging_universe_scorecard_v02"
        in SQL
    )
    assert (
        "grant execute on function private.alpha_hunter_capture_participation_emerging_universe_v02()\n"
        "to postgres"
    ) in SQL


def test_stacked_hourly_cron_runs_after_universe_endpoint_capture():
    assert "'17 * * * *'" in SQL
    assert "alpha-hunter-participation-emerging-universe-v02" in SQL
    assert "it does not modify source jobs" in SQL


def test_scorecard_stratifies_long_and_short_instead_of_pooling_direction():
    assert "candidate_direction" in SQL
    assert "group by challenger_class,candidate_direction,horizon_hours" in SQL
