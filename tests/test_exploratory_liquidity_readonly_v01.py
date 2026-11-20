"""Provenance for an exploratory analysis, not a production threshold."""
from pathlib import Path

from pglast import parse_sql


SQL = (
    Path(__file__).resolve().parents[1]
    / "ops/reviews/exploratory_exit_depth_20261008_readonly_v01.sql"
).read_text(encoding="utf-8")


def test_exploratory_audit_is_fixed_window_and_single_select():
    statements = parse_sql(SQL)
    assert len(statements) == 1
    assert statements[0].stmt.__class__.__name__ == "SelectStmt"
    assert "2026-10-08 03:38:50+00" in SQL
    assert "2026-10-08 08:27:38+00" in SQL


def test_exploratory_audit_counts_independent_symbol_direction_series():
    assert "DISTINCT ON (a.symbol, a.direction, a.source_run_id)" in SQL
    assert "PARTITION BY symbol,direction" in SQL
    assert "independent_symbol_direction_series" in SQL
    assert "RENDER_CRON" in SQL
    assert "50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834" in SQL
