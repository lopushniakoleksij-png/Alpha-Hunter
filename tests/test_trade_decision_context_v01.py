from pathlib import Path

from pglast import parse_sql

SQL = Path("ops/sql/trade_decision_context_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_sql_parses():
    assert parse_sql(SQL)


def test_context_is_not_causal_attribution():
    assert "false as causal_attribution_claim_permitted" in LOWER
    assert "false as alpha_hunter_execution_claim_inferred_from_context" in LOWER
    assert "ATTRIBUTABLE_TO_ALPHA_HUNTER" in SQL


def test_freshness_is_bounded_to_thirty_minutes():
    assert "interval '30 minutes'" in LOWER
    assert "preentry_signal_lag_minutes" in SQL
    assert "fresh_preentry_signal_context" in SQL


def test_context_classes_cover_money_relevant_cases():
    required = [
        "ALPHA_HUNTER_EXECUTION_ATTRIBUTABLE",
        "NO_FRESH_PREENTRY_SIGNAL_CONTEXT",
        "NON_AH_CONTRARY_TO_FRESH_SIGNAL_DIRECTION",
        "NON_AH_ALIGNED_WITH_REJECTED_SIGNAL",
        "NON_AH_ALIGNED_NONEXECUTABLE_SIGNAL",
        "NON_AH_ALIGNED_EXECUTABLE_SIGNAL_CONTEXT",
    ]
    for marker in required:
        assert marker in SQL


def test_open_position_context_exists():
    assert "alpha_hunter_open_position_decision_context_v01" in SQL
    assert "OPEN_POSITION_CONTRARY_TO_FRESH_SIGNAL_DIRECTION" in SQL
    assert "OPEN_POSITION_ALIGNED_WITH_REJECTED_SIGNAL" in SQL


def test_money_status_groups_by_context_without_strategy_claim():
    assert "alpha_hunter_trade_decision_context_status_v01" in SQL
    assert "total_fee_adjusted_pnl_ex_funding_usdt" in SQL
    assert "expectancy_usdt_per_trade_ex_funding" in SQL
    assert "profit_factor_ex_funding" in SQL
    assert "false as profitability_claim_permitted" in LOWER
    assert "false as strategy_change_permitted" in LOWER


def test_no_live_authority():
    forbidden = [
        "api.bitget.com",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer(",
        "trade_permission=true",
        "trade_permission = true",
    ]
    for marker in forbidden:
        assert marker not in LOWER
    assert "false as trade_permission" in LOWER
    assert "'NONE'::text as order_path" in SQL


def test_views_are_service_role_read_only():
    for view in [
        "alpha_hunter_trade_decision_context_v01",
        "alpha_hunter_trade_decision_context_status_v01",
        "alpha_hunter_open_position_decision_context_v01",
    ]:
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER
