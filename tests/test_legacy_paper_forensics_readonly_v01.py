"""Reproducible read-only production legacy paper forensics contracts."""
from pathlib import Path

from pglast import parse_sql

PATH = Path("ops/research/legacy_paper_32_forensics_readonly_v01.sql")
SQL = PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_sql_contains_only_select_statements():
    statements = parse_sql(SQL)
    assert len(statements) == 4
    # Every statement is a SELECT (WITH ... SELECT included).
    assert all(stmt.stmt.__class__.__name__ == "SelectStmt" for stmt in statements)
    forbidden = (
        "insert into", "update public.", "delete from", "truncate ",
        "alter table", "create table", "drop table", "perform ",
        "grant ", "revoke ", "cron.alter_job", "pg_sleep(", "http_post",
        "trade_permission=true", "production_promotion_permitted=true",
    )
    for keyword in forbidden:
        assert keyword not in LOWER


def test_all_historical_views_are_strictly_research_only():
    assert LOWER.count("alpha_hunter_paper_completed_trades_valid_v05") == 4
    assert "alpha_hunter_paper_profitability_status_v09" not in LOWER
    assert "alpha_hunter_paper_decisions_v01" in LOWER
    assert "alpha_hunter_symbol_snapshots" in LOWER
    assert "alpha_hunter_paper_exit_observation_delay_audit_v01" in LOWER
    assert "alpha_hunter_paper_exit_minute_path_audit_v01" in LOWER


def test_cost_and_volatility_analysis_cannot_claim_winning_strategy():
    assert "trigger_anchored_net_pnl_ex_funding" in LOWER
    assert "anchor_counterfactual_nonclaim" in LOWER
    assert "counterfactual_only" in LOWER
    assert "profitability_claim_permitted" in LOWER
    assert "atr_1h_pct" in LOWER
    assert "atr_4h_pct" in LOWER
    assert "missing_required_high_tfs" in LOWER
