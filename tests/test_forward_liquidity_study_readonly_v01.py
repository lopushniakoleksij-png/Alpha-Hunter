"""Future liquidity pilot: strictly read-only, delayed score, dependent-grain guard.

The test does not query production or add a scheduled job.
"""
from datetime import datetime, timezone
from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "ops/reviews/future_exit_liquidity_24h_readonly_v01.sql").read_text(
    encoding="utf-8"
)


def test_forward_protocol_sql_is_a_single_read_only_select():
    statements = parse_sql(SQL)
    assert len(statements) == 1
    assert statements[0].stmt.__class__.__name__ == "SelectStmt"


def test_study_is_fixed_ahead_of_time_and_has_an_immutable_maturity_boundary():
    starts = datetime.fromisoformat("2026-10-08 12:00:00+00:00")
    ends = datetime.fromisoformat("2026-10-09 12:00:00+00:00")
    assert ends - starts == __import__("datetime").timedelta(hours=24)
    assert "2026-10-08 12:00:00+00" in SQL
    assert "2026-10-09 12:00:00+00" in SQL
    assert "IMMATURE_DO_NOT_SCORE" in SQL
    assert "NOT_STARTED" in SQL
    assert "clock_timestamp() < (SELECT ends_at_utc FROM scope)" in SQL


def test_canonical_fingerprint_and_35_minute_scientific_filter_are_preserved():
    assert "'RENDER_CRON'" in SQL
    assert "scientific_fingerprint_sha256" in SQL
    assert "50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834" in SQL
    assert "interval '35 minutes'" in SQL
    assert "NOT complete_24h_window" in SQL


def test_dependence_grain_deduplicated_across_multiple_orders():
    assert "DISTINCT ON (a.symbol, a.direction, a.source_run_id)" in SQL
    assert "PARTITION BY q.symbol, q.direction" in SQL
    assert "WHEN a.direction='LONG' THEN a.best_bid_size ELSE a.best_ask_size" in SQL
    assert "unlabelled_quote_source_samples" in SQL


def test_no_scanner_or_trade_execution_wiring():
    active_paths = (
        "hourly.py",
        "run.py",
        "alpha_hunter/storage.py",
        "alpha_hunter/paper_horizon.py",
        "alpha_hunter/paper_exit.py",
        "alpha_hunter/paper_execution.py",
    )
    for relative in active_paths:
        code = (ROOT / relative).read_text(encoding="utf-8")
        assert "future_exit_liquidity_24h_readonly_v01" not in code
