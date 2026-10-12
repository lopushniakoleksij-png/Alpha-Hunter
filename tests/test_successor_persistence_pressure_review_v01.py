"""P0 query contract: inspect write pressure without mutating frozen R10."""
from pathlib import Path

from pglast import parse_sql

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = ROOT / "ops/reviews/successor_persistence_load_diagnostic_readonly_20261012.sql"
DESIGN = ROOT / "ops/reviews/successor_persistence_repair_contract_20261012.md"


def test_pressure_query_is_only_one_select():
    sql = DIAGNOSTIC.read_text(encoding="utf-8")
    tree = parse_sql(sql)
    assert len(tree) == 1
    assert tree[0].stmt.__class__.__name__ == "SelectStmt"


def test_pressure_query_inspects_real_postgrest_write_path_and_trigger():
    sql = DIAGNOSTIC.read_text(encoding="utf-8")
    for required in (
        "extensions.pg_stat_statements",
        "alpha_hunter_symbol_snapshots",
        "alpha_hunter_strategy_observations_v01",
        "trg_ah_capture_strategy_observations_v01",
        "temp_blks_written",
        "wal_bytes",
        "pg_total_relation_size",
        "statement_timeout",
        "observed_at_utc>=now()-interval '24 hours'",
        "READ_ONLY_DIAGNOSTIC_NOT_PROOF_OF_TRIGGER_EXCLUSIVE_CAUSE",
    ):
        assert required in sql


def test_successor_contract_denies_shortcuts_and_preserves_frozen_evidence():
    txt = DESIGN.read_text(encoding="utf-8")
    for required in (
        "READ_ONLY_DIAGNOSTIC",   # Never claim causal proof from a counter.
        "P0",
        "35-minute",
        "12s",
        "AS-OF",
        "deterministic",
        "R10",
        "rollback",
        "no production",
    ):
        assert required.lower() in txt.lower()
    assert "41,050" in txt and "4,105" in txt


def test_no_live_scanner_import_or_production_change():
    for rel in (
        "alpha_hunter/storage.py",
        "alpha_hunter/paper_exit.py",
        "alpha_hunter/paper_horizon.py",
        "hourly.py",
        "run.py",
    ):
        code = (ROOT / rel).read_text(encoding="utf-8")
        assert DIAGNOSTIC.name not in code
        assert "successor_persistence_repair_contract_20261012" not in code
