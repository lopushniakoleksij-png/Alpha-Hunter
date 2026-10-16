"""P3 audit query contract: offline SQL parser only, no Supabase connection."""
from pathlib import Path

from pglast import parse_sql
from pglast.ast import SelectStmt

ROOT = Path(__file__).resolve().parents[1]
QUERY = (ROOT / "ops/reviews/p3_existing_execution_exact_linkage_readonly_20261015.sql").read_text()


def test_forensic_query_is_only_one_select_statement():
    statements = parse_sql(QUERY)
    assert len(statements) == 1
    assert isinstance(statements[0].stmt, SelectStmt)
    # Defensive syntax guard: this must remain an aggregate read-only diagnostic.
    sql = "\n".join(line for line in QUERY.splitlines()
                    if not line.lstrip().startswith("--")).lower()
    for disallowed in ("insert into", "delete from", "update public.",
                       "create table", "alter table", "drop table",
                       "grant ", "revoke ", "copy ", "execute ", "perform ",
                       "call ", "pg_sleep("):
        assert disallowed not in sql


def test_separates_symbol_time_heuristics_from_exact_user_confirmed_binding():
    assert "alpha_hunter_execution_decision_freezes_v01" in QUERY
    assert "alpha_hunter_fill_evidence" in QUERY
    assert "alpha_hunter_execution_order_evidence_v01" in QUERY
    assert "alpha_hunter_execution_fill_confirmation_candidates_v01" in QUERY
    assert "alpha_hunter_execution_fill_bindings_v01" in QUERY
    assert "alpha_hunter_verified_execution_attribution_v01" in QUERY
    assert "unique_heuristic_pairs_NOT_verified" in QUERY
    assert "explicit_user_confirmed_bindings" in QUERY
    assert "verified_alpha_hunter_executions" in QUERY
    assert "unique_limit_signal_market_order_conflicts" in QUERY
    assert "NO_VERIFIED_EXACT_DECISION_TO_VENUE_FILL_ATTRIBUTION" in QUERY
    assert "false AS model_validation_or_trading_permission_from_this_audit" in QUERY


def test_candidate_rows_never_become_confirmed_without_external_identity_evidence():
    sql = QUERY.lower()
    assert "explicit_user_confirmation" in sql
    assert "verified_alpha_hunter_execution" in sql
    assert "candidate.unique_pairs" in sql
    assert "candidate.ambiguous_pairs" in sql
    assert "case when bindings.confirmed > 0 and verified.verified > 0" in sql
    assert "then 'explicit_bindings_exist_require_independent_row_audit'" in sql
    assert "no_verifiable" not in sql  # preserve explicit named failed gate
