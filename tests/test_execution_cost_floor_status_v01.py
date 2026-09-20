from pathlib import Path

SQL = Path("execution_cost_floor_status_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_cost_floor_uses_observed_quote_and_fee_evidence():
    required = [
        "alpha_hunter_execution_cost_evidence",
        "alpha_hunter_realized_fee_status_v01",
        "observed_spread_pct",
        "median_realized_fee_bps",
        "2.0*f.taker_fee_bps+a.median_spread_bps",
        "TWO_TAKER_FEES_PLUS_ONE_ROUND_TRIP_SPREAD_CROSSING",
    ]
    for marker in required:
        assert marker in SQL


def test_spread_percent_is_converted_to_bps_once():
    assert "percentile_cont(0.5) within group(order by observed_spread_pct) * 100.0" in SQL
    assert "observed_spread_abs/mid_price*100.0" in SQL
    assert "* 10000" not in SQL
    assert "*10000" not in SQL


def test_claim_ceiling_cannot_activate_cost_model_or_net_r():
    required = [
        "false as slippage_included",
        "false as latency_included",
        "false as market_impact_included",
        "false as funding_included",
        "false as adverse_selection_included",
        "false as cost_model_validated",
        "false as cost_model_activation_permitted",
        "false as realistic_net_r_claim_permitted",
        "DESCRIPTIVE_OBSERVED_COST_FLOOR_ONLY",
        "FORWARD_DECISION_TO_FILL_BENCHMARK_AND_SLIPPAGE_VALIDATION",
        "true as shadow_only",
        "false as trade_permission",
    ]
    for marker in required:
        assert marker in SQL


def test_status_view_is_read_only_and_service_role_only():
    assert "security_invoker=true" in LOWER
    assert "grant select on public.alpha_hunter_execution_cost_floor_status_v01" in LOWER
    forbidden = [
        "insert into",
        "update public.",
        "delete from",
        "trade_permission=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER
