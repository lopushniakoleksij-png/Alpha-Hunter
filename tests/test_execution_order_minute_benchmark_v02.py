from pathlib import Path

SQL = Path("execution_order_minute_benchmark_v02.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_v02_supersedes_boundary_bug_without_mutating_v01():
    required = [
        "Supersedes v0.1",
        "V01_STARTTIME_BOUNDARY_COULD_EXCLUDE_EXPECTED_CANDLE",
        "alpha_hunter_execution_order_minute_benchmark_v02",
        "execution-order-minute-benchmark-v0.2",
    ]
    for marker in required:
        assert marker in SQL
    assert "update public.alpha_hunter_execution_order_minute_benchmark_v01" not in LOWER
    assert "delete from public.alpha_hunter_execution_order_minute_benchmark_v01" not in LOWER


def test_v02_uses_history_endpoint_and_brackets_expected_minute():
    required = [
        "/api/v3/market/history-candles",
        "v_expected-interval '1 minute'",
        "v_expected+interval '1 minute'",
        "=v_expected",
        "exact_expected_minute_required",
    ]
    for marker in required:
        assert marker in SQL


def test_market_order_only_and_private_ctime_anchor():
    required = [
        "e.order_type='MARKET'",
        "e.order_created_at_utc",
        "date_trunc('minute',o.order_created_at_utc)",
        "OPEN_OF_MINUTE_CONTAINING_PRIVATE_ORDER_CTIME",
    ]
    for marker in required:
        assert marker in SQL


def test_claim_ceiling_is_unchanged():
    required = [
        "COARSE_ORDER_MINUTE_OPEN_NOT_SLIPPAGE_V02",
        "benchmark_is_not_slippage",
        "benchmark_mixes_market_movement_and_execution",
        "benchmark_is_not_alpha_hunter_performance",
        "benchmark_is_not_realistic_net_r",
        "slippage_claim_permitted=false",
        "alpha_hunter_execution_claim_permitted=false",
        "cost_model_activation_permitted=false",
        "realistic_net_r_claim_permitted=false",
        "shadow_only=true",
        "trade_permission=false",
    ]
    for marker in required:
        assert marker in SQL


def test_no_exchange_write_or_cron():
    forbidden = [
        "place-order",
        "close-positions",
        "cancel-order",
        "modify-order",
        "set-leverage",
        "cron.schedule",
        "trade_permission=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER
    assert "'new_cron_created',false" in SQL
