from pathlib import Path

from pglast import parse_sql

SQL = Path("ops/sql/money_economic_ledger_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_money_sql_parses():
    assert parse_sql(SQL)


def test_account_and_alpha_hunter_economics_are_separated():
    required = [
        "account_economic_observation",
        "verified_alpha_hunter_execution",
        "alpha_hunter_execution_claim_permitted",
        "ATTRIBUTABLE_TO_ALPHA_HUNTER",
        "NOT_ATTRIBUTABLE_TO_ALPHA_HUNTER",
        "alpha_hunter_attributable_trade_count",
        "alpha_hunter_profitability_measurement_status",
    ]
    for marker in required:
        assert marker in SQL


def test_unresolved_funding_is_not_silently_zeroed():
    required = [
        "funding_coverage_complete",
        "funding_coverage_status",
        "full_economic_pnl_claim_permitted",
        "FEES_AND_BOUND_FUNDING",
        "FEES_ONLY_FUNDING_INCOMPLETE",
    ]
    for marker in required:
        assert marker in SQL
    assert "coalesce(bound_funding_account_effect" not in LOWER


def test_money_status_contains_core_expectancy_metrics():
    required = [
        "win_rate_pct_ex_funding",
        "total_fee_adjusted_pnl_ex_funding_usdt",
        "expectancy_usdt_per_trade_ex_funding",
        "average_win_usdt_ex_funding",
        "average_loss_usdt_ex_funding",
        "profit_factor_ex_funding",
        "max_realized_drawdown_usdt_ex_funding",
        "account_fee_adjusted_profit_positive",
        "account_profit_factor_above_one",
    ]
    for marker in required:
        assert marker in SQL


def test_realized_r_requires_persisted_planned_risk():
    assert "first_planned_risk_usdt" in SQL
    assert "realized_r_ex_funding_if_planned_risk_observed" in SQL
    assert "realized_r_observation_available" in SQL
    assert "fp.first_planned_risk_usdt > 0" in SQL


def test_profit_retention_and_management_shadow_are_descriptive():
    required = [
        "observed_peak_gross_capture_pct",
        "observed_peak_gross_giveback_pct",
        "retention_evidence_status",
        "management_shadow_evidence",
        "counterfactual_net_pnl_claim_permitted",
        "promotion_permitted",
    ]
    for marker in required:
        assert marker in SQL


def test_profitability_claim_is_blocked_without_attribution():
    assert "NO_ATTRIBUTABLE_ALPHA_HUNTER_CLOSED_TRADES" in SQL
    assert "false as alpha_hunter_profitability_claim_permitted" in LOWER
    assert "false as profitability_claim_from_unattributed_trade_permitted" in LOWER


def test_direction_and_symbol_concentration_views_exist():
    assert "alpha_hunter_money_direction_status_v01" in SQL
    assert "alpha_hunter_money_symbol_concentration_v01" in SQL


def test_no_live_trading_authority_is_added():
    required = [
        "false as management_change_permitted",
        "false as threshold_change_permitted",
        "false as promotion_permitted",
        "false as trade_permission",
        "'NONE'::text as order_path",
    ]
    for marker in required:
        assert marker in SQL

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
        "promotion_permitted=true",
        "promotion_permitted = true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_views_are_read_only_service_role_surfaces():
    for view in [
        "alpha_hunter_economic_trade_ledger_v01",
        "alpha_hunter_money_status_v01",
        "alpha_hunter_money_direction_status_v01",
        "alpha_hunter_money_symbol_concentration_v01",
    ]:
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER
        assert f"grant insert on public.{view}" not in LOWER
        assert f"grant update on public.{view}" not in LOWER
        assert f"grant delete on public.{view}" not in LOWER
