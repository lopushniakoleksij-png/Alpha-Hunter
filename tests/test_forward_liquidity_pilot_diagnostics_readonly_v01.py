"""P3 post-hoc exit-liquidity pilot diagnostics: safe SELECT-only and exact grain.

These static tests do NOT turn failed historical observations into valid science.
"""
from pathlib import Path
from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
NAME = "future_exit_liquidity_pilot_diagnostics_20261012_readonly_v01.sql"
SQL = (ROOT / "ops/reviews" / NAME).read_text(encoding="utf-8")
ORIGINAL = (ROOT / "ops/reviews/future_exit_liquidity_24h_readonly_v01.sql").read_text(
    encoding="utf-8"
)


def test_diagnostic_is_a_single_read_only_select():
    stmts = parse_sql(SQL)
    assert len(stmts) == 1
    assert stmts[0].stmt.__class__.__name__ == "SelectStmt"


def test_original_frozen_window_fingerprint_and_35m_bound_retained():
    for required in (
        "2026-10-08 12:00:00+00",
        "2026-10-09 12:00:00+00",
        "50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834",
        "'RENDER_CRON'",
        "interval '35 minutes'",
    ):
        assert required in SQL
        assert required in ORIGINAL


def test_duplicate_entries_are_not_independent_quote_observations():
    for required in (
        "GROUP BY symbol,direction,source_run_id",
        "COUNT(DISTINCT (best_bid,best_ask,best_bid_size,best_ask_size))",
        "distinct_books>1",
        "distinct_source_labels>1",
        "COUNT(*) FILTER(WHERE order_attempts>1)",
    ):
        assert required in SQL
    assert "SUM(order_attempts)" in SQL  # raw attempts separately disclosed


def test_correct_exit_side_and_missing_provenance_fail_closed():
    for required in (
        "WHEN a.direction='LONG' THEN a.best_bid_size ELSE a.best_ask_size",
        "SOURCE_NOT_LABELED_IN_ATTEMPT",
        "QUOTE_SOURCE_UNLABELLED",
        "GAP_OVER_35_MINUTES",
        "END_BOUNDARY_MISSING",
        "START_BOUNDARY_MISSING",
        "QUOTE_CONFLICT_OR_INVALID",
        "consistent_book_and_source AND fully_labelled_source",
        "clock_timestamp()>=(SELECT ends_at_utc FROM scope)",
    ):
        assert required in SQL


def test_no_unauthorized_execution_or_scanner_dependency():
    for rel in (
        "run.py",
        "hourly.py",
        "alpha_hunter/storage.py",
        "alpha_hunter/paper_execution.py",
        "alpha_hunter/paper_exit.py",
        "alpha_hunter/paper_horizon.py",
    ):
        code = (ROOT / rel).read_text(encoding="utf-8")
        assert NAME not in code
