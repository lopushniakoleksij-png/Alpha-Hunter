from pathlib import Path

SQL = Path("money_entry_stage_universe_liquidity_binding_v02.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_v02_removes_impossible_cross_scanner_run_id_equality():
    assert "u.selection_run_id=p_source_run_id" not in SQL
    assert "separate canonical" in LOWER
    assert "not equated" in LOWER


def test_v02_requires_same_symbol_same_hour_non_future():
    required = [
        "u.symbol=upper(p_symbol)",
        "u.observed_at_utc<=p_source_captured_at_utc",
        "u.observed_at_utc>=date_trunc('hour',p_source_captured_at_utc)",
        "u.observed_at_utc<date_trunc('hour',p_source_captured_at_utc)+interval '1 hour'",
    ]
    for marker in required:
        assert marker in SQL


def test_v02_fails_closed_if_hour_has_ambiguous_selection_runs():
    required = [
        "count(distinct selection_run_id)",
        "distinct_selection_runs",
        "where g.distinct_selection_runs=1",
    ]
    for marker in required:
        assert marker in SQL


def test_v02_preserves_provenance_fields():
    required = [
        "observation_id text",
        "observed_at_utc timestamptz",
        "selection_run_id text",
        "liquidity_pass boolean",
    ]
    for marker in required:
        assert marker in SQL


def test_signature_and_service_role_contract_remain_compatible():
    assert "alpha_hunter_stage_universe_liquidity(" in SQL
    assert "p_source_run_id text" in SQL
    assert "grant execute on function private.alpha_hunter_stage_universe_liquidity" in LOWER


def test_no_trade_or_threshold_authority_is_added():
    forbidden = [
        "trade_permission=true",
        "production_execution_enabled=true",
        "place-order",
        "cancel-order",
        "modify-order",
        "set_leverage",
        "activate threshold",
    ]
    for marker in forbidden:
        assert marker not in LOWER
