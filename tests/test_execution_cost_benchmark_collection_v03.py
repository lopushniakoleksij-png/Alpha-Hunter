from pathlib import Path

SQL = Path("execution_cost_benchmark_collection_v03.sql").read_text(
    encoding="utf-8"
).lower()


def test_hourly_collector_is_scheduled():
    assert "alpha-hunter-order-minute-benchmark-v02-hourly" in SQL
    assert "'49 * * * *'" in SQL
    assert "alpha_hunter_collect_order_minute_benchmark_v02(25)" in SQL


def test_readiness_view_preserves_scientific_claim_ceiling():
    required = [
        "coarse_benchmark_is_slippage",
        "alpha_hunter_execution_performance_claim_permitted",
        "cost_model_activation_permitted",
        "realistic_net_r_model_activation_permitted",
        "waiting_for_decision_time_quote_and_fill_slippage_validation",
        "capture_prospective_decision_time_top_of_book_plus_matched_fill",
    ]
    for marker in required:
        assert marker in SQL


def test_no_execution_authority():
    required = [
        "true as shadow_only",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in SQL
