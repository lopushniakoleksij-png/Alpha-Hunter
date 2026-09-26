from pathlib import Path

SQL = Path("storage_reclaim_audit_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_storage_reclaim_audit_is_read_only_telemetry():
    required = [
        "alpha_hunter_storage_reclaim_audit_v01",
        "alpha_hunter_storage_reclaim_summary_v01",
        "pg_total_relation_size",
        "pg_database_size(current_database())",
        "toast_live_rows",
        "toast_dead_rows",
        "telemetry_only",
        "false as mutation_permitted",
    ]
    for marker in required:
        assert marker in LOWER

    forbidden = [
        "delete from",
        "truncate ",
        "vacuum full",
        "cluster ",
        "alter table",
        "drop table",
        "update public.",
        "insert into public.",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_storage_reclaim_audit_targets_known_large_evidence_tables():
    for table in [
        "alpha_hunter_snapshots",
        "alpha_hunter_symbol_snapshots",
        "alpha_hunter_signals",
        "alpha_hunter_signal_features",
        "alpha_hunter_strategy_observations_v01",
        "alpha_hunter_universe_hourly",
    ]:
        assert table in LOWER


def test_storage_reclaim_audit_does_not_overclaim_vacuum_recovery():
    assert "live_toast_archive_or_recompact_review" in LOWER
    assert "ordinary_vacuum_analyze_review" in LOWER
    assert "ordinary_vacuum_expected_to_solve_live_payload_size" in LOWER
    assert "when toast_bytes >= 50::bigint * 1024 * 1024" in LOWER
    assert "and toast_live_rows>0" in LOWER
    assert "then false" in LOWER


def test_storage_reclaim_surfaces_are_service_role_read_only():
    assert (
        "grant select on public.alpha_hunter_storage_reclaim_audit_v01"
        in LOWER
    )
    assert (
        "grant select on public.alpha_hunter_storage_reclaim_summary_v01"
        in LOWER
    )
    assert "to service_role" in LOWER
