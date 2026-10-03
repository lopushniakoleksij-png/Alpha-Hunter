from pathlib import Path

SQL = Path("ops/sql/participation_universe_endpoint_forward_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_new_forward_only_spec_has_new_registration_boundary():
    assert "participation-universe-endpoint-forward-v02" in SQL
    assert "clock_timestamp()" in SQL
    assert "d.captured_at_utc>=v_spec.registered_at_utc" in SQL
    assert "historical_backfill_permitted',false" in SQL
    assert "no diagnostic before registered_at_utc is admitted" in SQL


def test_source_contract_is_frozen_to_full_universe_canonical_ticker():
    assert "public.alpha_hunter_universe_hourly" in SQL
    assert "primary_scanner_cached_tickers" in SQL
    assert "canonical_scan_ticker_snapshot" in SQL
    assert "v_spec.endpoint_max_lag_minutes<>30" in SQL
    assert "v_spec.horizons_hours<>array[1,4,12,24]" in SQL


def test_t0_anchor_is_same_source_same_run_same_timestamp():
    assert "u.selection_run_id=d.run_id" in SQL
    assert "u.observed_at_utc=d.captured_at_utc" in SQL
    assert "check(anchor_selection_run_id=source_run_id)" in SQL
    assert "check(anchor_observed_at_utc=captured_at_utc)" in SQL
    assert "source_signal_reference_price_is_primary_anchor',false" in SQL


def test_primary_return_is_universe_anchor_to_universe_endpoint():
    assert "universe_t0_to_universe_endpoint" in SQL
    assert "100.0*(r.endpoint_price/r.anchor_price-1.0)" in SQL
    assert "'source_consistent',true" in SQL


def test_endpoint_is_first_canonical_universe_row_within_30m():
    assert "uu.observed_at_utc>=d.due_at_utc" in SQL
    assert "uu.observed_at_utc<=d.due_at_utc" in SQL
    assert "make_interval(mins=>v_spec.endpoint_max_lag_minutes)" in SQL
    assert "order by uu.observed_at_utc,uu.observation_id" in SQL
    assert "endpoint_lag_seconds<=1800" in SQL


def test_missing_endpoint_windows_are_explicitly_censored():
    assert "alpha_hunter_participation_universe_endpoint_failures_v02" in SQL
    assert "no_canonical_universe_endpoint_within_30m" in SQL
    assert "endpoint_return_claim_permitted',false" in SQL


def test_scorecard_surfaces_coverage_and_pending_materialization():
    assert "source_coverage_pct" in SQL
    assert "censored_rows" in SQL
    assert "pending_materialization_rows" in SQL
    assert "matured_rows" in SQL


def test_no_silent_source_mixing_or_v01_mutation():
    assert "update private.alpha_hunter_participation_endpoint" not in SQL
    assert "delete from private.alpha_hunter_participation_endpoint" not in SQL
    assert "no v0.1 candidate or outcome row is updated/deleted" in SQL


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


def test_security_and_parallel_cron_are_fail_closed():
    assert "security invoker" in SQL
    assert "set search_path=''" in SQL
    assert "pg_try_advisory_xact_lock" in SQL
    assert "'16 * * * *'" in SQL
    assert "alpha-hunter-participation-universe-endpoint-v02" in SQL
    assert "where jobname='alpha-hunter-participation-universe-endpoint-v02'" in SQL
    assert "alpha-hunter-participation-endpoint-forward-v01" not in SQL


def test_service_role_is_read_only_and_execute_is_postgres_only():
    assert "grant select on private.alpha_hunter_participation_universe_endpoint_scorecard_v02" in SQL
    assert (
        "grant execute on function private.alpha_hunter_run_participation_universe_endpoint_forward_v02()\n"
        "to postgres"
    ) in SQL
