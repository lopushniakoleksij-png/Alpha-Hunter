"""Static safety contract for a successor-only, uninstalled PostgreSQL RPC.

These checks do NOT prove PostgreSQL transaction behavior. A genuine disposable
PG16/17 rollback/timeout test remains a release-blocking independent task.
"""
from pathlib import Path
import re

SQL = Path("research/successor_atomic_snapshot_v01.sql").read_text(encoding="utf-8").lower()


def test_no_production_or_authority_wiring():
    assert "security invoker" in SQL
    assert "security definer" not in SQL
    assert not re.search(r"(?m)^\s*(grant|revoke|alter role|alter table|drop table)\b", SQL)
    assert "trade_permission=true" not in SQL
    assert "paper_admission" not in SQL
    assert "insert into public.alpha_hunter_snapshots" in SQL
    assert "insert into public.alpha_hunter_symbol_snapshots" in SQL


def test_one_plpgsql_call_contains_parent_and_children():
    assert "language plpgsql" in SQL
    assert "begin" in SQL
    assert "end;" in SQL
    assert SQL.index("insert into public.alpha_hunter_snapshots") < SQL.index(
        "insert into public.alpha_hunter_symbol_snapshots"
    )
    assert "get diagnostics v_actual = row_count" in SQL
    assert "canonical child insert count mismatch" in SQL


def test_rejects_missing_partial_duplicate_and_foreign_children():
    for required in (
        "jsonb_array_length(p_children)",
        "v_actual <> v_expected",
        "count(distinct value->>'symbol')",
        "duplicate canonical child symbol",
        "value->>'run_id' is distinct from v_run_id",
        "value->'payload'->>'symbol' is distinct from value->>'symbol'",
        "parent compact payload run id mismatch",
    ):
        assert required in SQL


def test_never_mutates_existing_parent_or_child_evidence():
    assert "on conflict" not in SQL
    assert not re.search(r"(?m)^\s*(update|delete|truncate)\s+", SQL)
    assert "return v_actual" in SQL


def test_schema_columns_exist_in_current_main_schema():
    schema = Path("supabase_schema.sql").read_text(encoding="utf-8").lower()
    assert "create table if not exists public.alpha_hunter_snapshots" in schema
    assert "create table if not exists public.alpha_hunter_symbol_snapshots" in schema
    for column in (
        "run_id", "collected_at_utc", "version", "product_type",
        "symbol_count", "error_count", "payload", "symbol",
        "state_changed", "trade_permission", "data_integrity_score",
    ):
        assert re.search(r"(?m)^\s*" + column + r"\s+", schema)
