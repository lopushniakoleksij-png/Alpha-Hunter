from pathlib import Path

SQL = Path("realtime_test_engine_db_refresh_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_db_refresh_uses_live_source_isolated_views():
    required = [
        "alpha_hunter_realtime_profitability_monitor_v01",
        "alpha_hunter_profitability_validation_status_v01",
        "alpha_hunter_profitability_cadence_integrity_v01",
        "alpha_hunter_profitability_sample_integrity_v01",
        "alpha_hunter_execution_cost_floor_status_v01",
    ]
    for marker in required:
        assert marker in SQL


def test_db_refresh_reports_integrity_failures_as_blockers():
    assert "cadence_integrity_failed" in SQL
    assert "sample_integrity_failed" in SQL
    assert "build_or_config_drift" in SQL
    assert "live_scan_stale" in SQL


def test_db_refresh_is_status_only():
    required = [
        "paper_only",
        "trade_permission",
        "production_promotion_permitted",
        "order_path",
        "'none'",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "trade_permission = true",
    ]
    for marker in forbidden:
        assert marker not in SQL


def test_db_refresh_is_cron_backed_not_market_scan():
    assert "*/10 * * * *" in SQL
    assert "alpha-hunter-test-engine-db-refresh-v02" in SQL
    assert "api.bitget.com" not in SQL


def test_db_refresh_exposes_sealed_sample_counts():
    required = [
        "post_baseline_candidate_observations",
        "left_censored_candidate_observations",
        "post_baseline_candidate_episodes",
        "post_baseline_24h_outcomes",
        "post_baseline_24h_economic_eligible",
    ]
    for marker in required:
        assert marker in SQL


def test_db_refresh_prefers_active_non_invalidated_cohort():
    required = [
        "real_counted_baseline_started_at_utc is not null",
        "not like 'invalidated_%'",
        "real_counted_baseline_started_at_utc is null",
    ]
    for marker in required:
        assert marker in SQL
