from pathlib import Path

SQL = Path("money_entry_stage_universe_liquidity_binding_v03.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_v03_binds_exact_canonical_scanner_run():
    assert "u.selection_run_id=p_source_run_id" in SQL
    assert "u.symbol=upper(p_symbol)" in SQL


def test_v03_requires_non_future_universe_evidence():
    assert "u.observed_at_utc<=p_source_captured_at_utc" in SQL
    assert "u.selection_snapshot_at_utc<=p_source_captured_at_utc" in SQL


def test_v03_removes_single_run_per_hour_assumption():
    forbidden = [
        "count(distinct selection_run_id)",
        "distinct_selection_runs=1",
        "date_trunc('hour',p_source_captured_at_utc)",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_signature_and_provenance_fields_remain_compatible():
    required = [
        "p_source_run_id text",
        "observation_id text",
        "observed_at_utc timestamptz",
        "selection_run_id text",
        "liquidity_pass boolean",
        "grant execute on function private.alpha_hunter_stage_universe_liquidity",
    ]
    for marker in required:
        assert marker in LOWER


def test_v03_adds_no_execution_authority():
    forbidden = [
        "trade_permission=true",
        "production_execution_enabled=true",
        "place_order",
        "place-order",
        "cancel_order",
        "cancel-order",
        "modify_order",
        "modify-order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER
