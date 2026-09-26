from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_capacity_guard_creates_compact_readiness_ledger_and_metrics():
    sql = (ROOT / "supabase_capacity_guard_v01.sql").read_text(encoding="utf-8")

    assert "alpha_hunter_readiness_observations_v01" in sql
    assert "alpha_hunter_storage_pressure_v01" in sql
    assert "pg_database_size(current_database())" in sql
    assert "primary key (run_id, symbol)" in sql


def test_capacity_guard_does_not_create_trade_authority():
    sql = (ROOT / "supabase_capacity_guard_v01.sql").read_text(encoding="utf-8").lower()

    assert "create table" in sql
    assert "insert into" not in sql
    assert "update " not in sql
    assert "delete from" not in sql
    assert "trade_permission boolean not null default false" in sql
