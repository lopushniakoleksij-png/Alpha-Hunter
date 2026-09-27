from pathlib import Path

SQL_PATH = Path("ops/sql/storage_growth_runway_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_storage_growth_monitor_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_storage_growth_samples_v01" in LOWER
    assert "alpha_hunter_storage_growth_status_v01" in LOWER


def test_samples_are_append_only_rls_service_role_only():
    assert "enable row level security" in LOWER
    assert "alpha_hunter_block_append_only_mutation" in LOWER
    assert (
        "grant select,insert on table "
        "public.alpha_hunter_storage_growth_samples_v01"
    ) in LOWER
    assert "to service_role" in LOWER


def test_capture_is_telemetry_only_and_trade_disabled():
    for marker in [
        "'telemetry_only',true",
        "'mutation_permitted',false",
        "'trade_permission',false",
        "'order_path','none'",
    ]:
        assert marker in LOWER


def test_compaction_regressions_are_explicit():
    for marker in [
        "parent_compaction_regression",
        "signal_compaction_regression",
        "feature_source_compaction_regression",
        "current_writes_compact",
    ]:
        assert marker in LOWER


def test_growth_projection_uses_measured_delta_not_provider_quota():
    assert "measured_database_bytes_per_hour" in LOWER
    assert "projected_positive_growth_24h_bytes" in LOWER
    assert "projected_positive_growth_30d_bytes" in LOWER
    assert "projected_database_bytes_30d" in LOWER
    for forbidden in [
        "free_plan",
        "pro_plan",
        "disk_quota",
        "storage_limit_bytes",
    ]:
        assert forbidden not in LOWER


def test_hourly_storage_capture_runs_after_control_plane_watchdog_window():
    assert "alpha-hunter-storage-growth-hourly-v01" in SQL
    assert "'27 * * * *'" in SQL


def test_no_evidence_rewrite_or_cleanup_action_is_added():
    for forbidden in [
        "delete from public.alpha_hunter_",
        "truncate ",
        "vacuum full",
        "alter table public.alpha_hunter_snapshots alter column payload",
        "alter table public.alpha_hunter_symbol_snapshots alter column payload",
        "place_order",
        "cancel_order",
        "modify_order",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in LOWER
