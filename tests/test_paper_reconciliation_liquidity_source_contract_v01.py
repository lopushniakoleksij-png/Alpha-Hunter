from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
BASE_SQL = (ROOT / "ops/sql/paper_execution_v02.sql").read_text(
    encoding="utf-8"
)
MIGRATION_SQL = (
    ROOT / "ops/sql/paper_reconciliation_liquidity_source_contract_v01.sql"
).read_text(encoding="utf-8")
RECONCILIATION_PY = (
    ROOT / "alpha_hunter/paper_reconciliation.py"
).read_text(encoding="utf-8")
STORAGE_PY = (
    ROOT / "alpha_hunter/storage.py"
).read_text(encoding="utf-8")


def test_sql_contracts_parse():
    assert parse_sql(BASE_SQL)
    assert parse_sql(MIGRATION_SQL)


def test_fill_table_accepts_both_read_only_quote_sources():
    for sql in (BASE_SQL, MIGRATION_SQL):
        assert "BITGET_TOP_OF_BOOK_SNAPSHOT" in sql
        assert "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE" in sql


def test_runtime_emitted_override_source_matches_database_contract():
    marker = "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"
    assert marker in STORAGE_PY
    assert "_reconciliation_quote_source" in RECONCILIATION_PY
    assert marker in BASE_SQL
    assert marker in MIGRATION_SQL


def test_migration_changes_only_liquidity_source_constraint():
    lower = MIGRATION_SQL.lower()
    assert "alter table public.alpha_hunter_paper_fills_v02" in lower
    assert "drop constraint if exists alpha_hunter_paper_fills_v02_liquidity_source_check" in lower
    assert "add constraint alpha_hunter_paper_fills_v02_liquidity_source_check" in lower

    forbidden = [
        "update public.alpha_hunter_paper_fills_v02",
        "delete from public.alpha_hunter_paper_fills_v02",
        "truncate",
        "trade_permission=true",
        "exchange_authority=true",
        "place_order",
        "cancel_order",
        "modify_order",
    ]
    for marker in forbidden:
        assert marker not in lower


def test_exit_fill_contract_already_accepts_same_two_sources():
    exit_sql = (
        ROOT / "ops/sql/paper_exit_reconciliation_v04.sql"
    ).read_text(encoding="utf-8")
    assert "BITGET_TOP_OF_BOOK_SNAPSHOT" in exit_sql
    assert "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE" in exit_sql
