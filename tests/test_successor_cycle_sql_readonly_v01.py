"""Read-only monitoring cycle SQL: parent != persisted children, no false PASS."""
from pathlib import Path
from pglast import parse_sql

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "ops/reviews/successor_monitoring_cycle_rolling24h_readonly_v01.sql").read_text(encoding="utf-8")
DETAIL = (ROOT / "ops/reviews/successor_monitoring_cycle_incomplete_runs_readonly_v01.sql").read_text(encoding="utf-8")


def test_both_sql_queries_are_one_select_no_mutations():
    for sql in (MAIN, DETAIL):
        stmts = parse_sql(sql)
        assert len(stmts) == 1
        assert stmts[0].stmt.__class__.__name__ == "SelectStmt"


def test_completed_run_continuity_only_counts_persisted_symbols():
    for term in ("alpha_hunter_snapshots", "alpha_hunter_symbol_snapshots",
                 "child_stage_complete", "distinct_child_symbols", "completed_intervals",
                 "max_completed_cycle_gap", "completed_cycle_gaps_over_35m",
                 "interval '35 minutes'", "PARENT_PERSISTED_CHILD_STAGE_INCOMPLETE"):
        assert term in MAIN


def test_never_claim_position_monitoring_complete_from_attempts_alone():
    for term in ("ASOF_POSITION_COVERAGE_UNKNOWN_WITHOUT_IMMUTABLE_INVENTORY",
                 "ASOF_POSITION_INVENTORY_REQUIRED", "alpha_hunter_paper_exit_attempts_v04"):
        assert term in MAIN
    assert "alpha_hunter_paper_reconciliation_attempts_v03" in DETAIL
    assert "INCOMPLETE_MONITORING_CYCLE" in DETAIL


def test_active_runtime_does_not_import_synthetic_receipt_code():
    for rel in ("alpha_hunter/storage.py", "alpha_hunter/paper_exit.py", "hourly.py", "run.py"):
        txt = (ROOT / rel).read_text(encoding="utf-8")
        assert "successor_quote_receipts_v01" not in txt
        assert "successor_monitoring_cycle_rolling24h_readonly_v01" not in txt
