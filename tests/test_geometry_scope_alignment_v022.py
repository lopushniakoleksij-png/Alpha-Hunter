from pathlib import Path

SQL = Path('geometry_scope_alignment_v022.sql').read_text()


def test_geometry_scope_matches_money_entry_candidate_scope():
    required = [
        "b.research_status=''SHADOW_QUEUE''",
        "b.lifecycle in (''PRE_MOVER'',''IGNITION'',''EXPANSION'')",
        "where b.run_id=v_run_id",
        "geometry-diagnostics-v0.2.2-money-entry-scope-aligned",
    ]
    for marker in required:
        assert marker in SQL


def test_old_evidence_is_not_rewritten_and_migration_is_fail_closed():
    assert "geometry-diagnostics-v0.2.1-volatility-context" in SQL
    assert "expected v0.2.1 geometry bridge scope not found; refusing unsafe replacement" in SQL
    assert "expected v0.2.1 model identity not found; refusing unsafe replacement" in SQL
    assert "update public.alpha_hunter_geometry_diagnostics" not in SQL.lower()
    assert "delete from public.alpha_hunter_geometry_diagnostics" not in SQL.lower()


def test_stage_writer_and_schedule_are_not_modified():
    forbidden = [
        "alpha_hunter_capture_money_entry_stage_snapshots",
        "cron.alter_job",
        "alpha-hunter-money-entry-stage-hourly",
        "money_entry_threshold_sets",
        "status='ACTIVE'",
    ]
    for marker in forbidden:
        assert marker not in SQL


def test_execution_safety_boundary_is_unchanged():
    forbidden = [
        "trade_permission=true",
        "production_execution_enabled=true",
        "/api/v3/trade/place-order",
        "/api/v2/mix/order/place-order",
        "http_get(",
        "http_post(",
    ]
    for marker in forbidden:
        assert marker not in SQL

    assert "revoke all on function private.alpha_hunter_capture_geometry_diagnostics() from public,anon,authenticated" in SQL
    assert "grant execute on function private.alpha_hunter_capture_geometry_diagnostics() to service_role" in SQL
