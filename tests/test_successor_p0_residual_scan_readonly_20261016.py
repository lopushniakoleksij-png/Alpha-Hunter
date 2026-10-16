"""Zero-spend P0 historical safety diagnostic static contract, NO DB/network.

All live source counts are obtained separately with the reviewed SELECT only.
This test cannot prove an uninterrupted operational 35m observer.
"""
from pathlib import Path

from pglast import parse_sql
from pglast.ast import SelectStmt

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"ops/reviews/successor_p0_residual_and_scan_gate_readonly_20261016.sql").read_text()
BODY="\n".join(line for line in SQL.splitlines() if not line.lstrip().startswith("--")).lower()


def test_only_one_read_only_select_statement():
    stmts=parse_sql(SQL)
    assert len(stmts)==1 and isinstance(stmts[0].stmt,SelectStmt)
    for s in ("insert into","update public.","delete from","create table",
              "alter table","drop table","grant ","revoke ","copy ",
              "call ","execute ","pg_sleep("):
        assert s not in BODY


def test_full_source_coverage_includes_partials_and_all_quarantines():
    for table in ("alpha_hunter_paper_orders_v02","alpha_hunter_paper_fills_v02",
                  "alpha_hunter_paper_exit_fills_v04","alpha_hunter_paper_protection_open_v04",
                  "alpha_hunter_paper_protective_orders_v03","alpha_hunter_paper_exit_attempts_v04",
                  "alpha_hunter_paper_entry_quarantine_v06","alpha_hunter_paper_exit_quarantine_v04",
                  "alpha_hunter_paper_reconciliation_quarantine_v04"):
        assert f"public.{table}" in BODY
    assert "coalesce(e.entered_qty,0::numeric)-coalesce(x.exited_qty,0::numeric)" in BODY
    assert "from all_order_residuals where residual_qty<0" in BODY
    assert "from all_order_residuals where residual_qty>0" in BODY  # positive exposure is retained
    assert "else 'unexplained_unmanaged'" in BODY


def test_managed_only_view_cannot_erase_partial_unmanaged_exposure():
    assert "left join public.alpha_hunter_paper_protection_open_v04" in BODY
    assert "when managed then 'managed_view'" in BODY
    assert "when quarantined then 'quarantined_unresolved'" in BODY
    assert "source_exit_attempt_rows" in BODY
    assert "raw_protection_count" in BODY
    assert "unexplained_unmanaged" in BODY


def test_scan_parent_must_have_exact_child_count_and_attempt_evidence():
    for field in ("alpha_hunter_snapshots","alpha_hunter_symbol_snapshots",
                  "payload->'validation_identity'->>'run_source'='render_cron'",
                  "coalesce(c.child_rows,0)=p.symbol_count",
                  "cycles where exit_attempt_rows=0",
                  "completed_scan_gaps_over_frozen_35m",
                  "lag(collected_at_utc)","completed_scan_gap_seconds>2100"):
        assert field in BODY


def test_fail_closed_and_no_live_or_scientific_promotion():
    for marker in (
         "unknown_source_or_parent_empty_fail_closed",
         "fail_closed_residual_or_scan_evidence_incomplete",
         "source_counts_structurally_reconciled_not_live_monitoring_proof",
         "false as independent_live_source_or_quote_authenticated",
         "false as all_cohort_continuous_monitoring_proven",
         "false as scientific_pass_or_admissions_permitted",
         "false as permission_to_change_r10_or_start_pilot",
         "2100 as frozen_monitor_maximum_seconds",
    ):
        assert marker in BODY
    assert "2101" not in BODY or "completed_scan_gap_seconds>2100" in BODY
