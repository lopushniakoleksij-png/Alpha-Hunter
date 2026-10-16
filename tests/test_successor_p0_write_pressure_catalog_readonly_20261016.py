"""R0 read-only database-catalog review must never mutate production."""
from pathlib import Path

from pglast import parse_sql
from pglast.ast import SelectStmt

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"ops/reviews/successor_p0_write_pressure_catalog_readonly_20261016.sql").read_text()
BODY="\n".join(x for x in SQL.splitlines() if not x.lstrip().startswith("--")).lower()

def test_one_select_only_no_mutations_or_perf_workload():
    stmts=parse_sql(SQL)
    assert len(stmts)==1 and isinstance(stmts[0].stmt,SelectStmt)
    for bad in ("insert into","update public.","delete from","alter table","create table",
                "drop table","grant ","revoke ","call ","copy ","do $$",
                "pg_sleep(","explain analyze","vacuum","reindex","set statement_timeout"):
        assert bad not in BODY

def test_catalog_reports_existing_trigger_cascade_without_trigger_changes():
    for s in ("pg_trigger","pg_class","pg_proc",
              "alpha_hunter_symbol_snapshots",
              "alpha_hunter_strategy_observations_v01",
              "alpha_hunter_strategy_episodes_v01",
              "alpha_hunter_capture_strategy_observations_v01",
              "enabled_symbol_strategy_trigger_count"):
        assert s in BODY
    assert "alter function" not in BODY
    assert "disable trigger" not in BODY

def test_role_timeouts_are_metadata_only_not_release_authority():
    for s in ("pg_db_role_setting","pg_roles","statement_timeout=%",
              "catalog_reader_statement_timeout_not_api_role",
              "false as exact_source_of_57014_proven",
              "false as authorization_to_change_timeout_or_trigger",
              "false as permission_to_deploy_successor"):
        assert s in BODY

def test_review_keeps_primary_writer_and_35m_boundary_unmodified():
    doc=(ROOT/"ops/reviews/successor_p0_r0_independent_design_review_20261016.md").read_text().lower()
    assert "cannot repair the existing primary" in doc
    assert "12s" in doc and "15s" in doc and "2,100s" in doc
    assert "no-go" in doc and "$0" in doc
    assert "nmr" in doc and "r1" in doc and "r2" in doc
