from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/paper_exit_minute_path_audit_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_minute_path_audit_sql_parses():
    assert parse_sql(SQL)


def test_uses_public_bitget_one_minute_history_candles_only():
    required = [
        "/api/v3/market/history-candles",
        "category=USDT-FUTURES",
        "interval=1m",
        "limit=100",
        "BITGET_PUBLIC_V3_1M_HISTORY_CANDLES",
        "public_market_data_only",
    ]
    for marker in required:
        assert marker in SQL


def test_first_touch_logic_is_directionally_correct():
    required = [
        "t.direction='LONG' then v_low<=t.stop_trigger_price",
        "t.direction='SHORT' then v_high>=t.stop_trigger_price",
        "t.direction='LONG' then v_high>=t.target_trigger_price",
        "t.direction='SHORT' then v_low<=t.target_trigger_price",
    ]
    for marker in required:
        assert marker in SQL


def test_entry_minute_and_same_minute_ordering_fail_closed():
    assert "ENTRY_MINUTE_ORDERING_AMBIGUOUS" in SQL
    assert "AMBIGUOUS_SAME_MINUTE" in SQL
    assert "same_minute_stop_target_is_ambiguous" in SQL
    assert "t.entry_completed_at_utc>v_entry_minute" in SQL


def test_path_collection_is_bounded_and_bracketed():
    assert "interval '90 minutes'" in SQL
    assert "v_cursor-interval '1 minute'" in SQL
    assert "p_limit must be between 1 and 20" in SQL
    assert "PATH_WINDOW_EXCEEDS_24H" in SQL
    assert "'max_path_minutes',1440" in SQL


def test_existing_paper_outcomes_are_never_rewritten():
    forbidden = (
        "update public.alpha_hunter_paper_",
        "delete from public.alpha_hunter_paper_",
        "truncate",
        "insert into public.alpha_hunter_paper_exit_fills_v04",
        "insert into public.alpha_hunter_paper_completed_trades",
    )
    for marker in forbidden:
        assert marker not in LOWER
    assert "'recorded_exits_rewritten',false" in LOWER
    assert "'exit_model_changed',false" in LOWER


def test_audit_and_failure_evidence_are_append_only():
    assert "alpha_hunter_paper_exit_minute_path_audit_v01" in LOWER
    assert "alpha_hunter_paper_exit_minute_path_failures_v01" in LOWER
    assert LOWER.count("alpha_hunter_block_paper_lifecycle_mutation_v01") >= 2


def test_no_profitability_or_exchange_authority():
    required = [
        "exit_model_change_permitted=false",
        "profitability_claim_permitted=false",
        "trade_permission=false",
        "production_promotion_permitted=false",
        "order_path='none'",
    ]
    for marker in required:
        assert marker in LOWER
    for forbidden in (
        "place_order(",
        "cancel_order(",
        "modify_order(",
        "set_leverage(",
    ):
        assert forbidden not in LOWER


def test_status_reports_reason_agreement_and_observation_delay():
    assert "alpha_hunter_paper_exit_minute_path_status_v01" in LOWER
    assert "recorded_reason_matches" in LOWER
    assert "recorded_reason_mismatches" in LOWER
    assert "average_minutes_first_touch_to_observed_exit" in LOWER
    assert "maximum_minutes_first_touch_to_observed_exit" in LOWER
