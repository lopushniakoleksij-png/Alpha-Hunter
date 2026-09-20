from pathlib import Path

SQL = Path("execution_order_minute_benchmark_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_market_order_only_and_uses_private_order_ctime():
    required = [
        "from public.alpha_hunter_execution_order_evidence_v01",
        "e.order_type='MARKET'",
        "e.order_created_at_utc",
        "date_trunc('minute',o.order_created_at_utc)",
        "OPEN_OF_MINUTE_CONTAINING_PRIVATE_ORDER_CTIME",
    ]
    for marker in required:
        assert marker in SQL


def test_public_historical_reference_is_exact_one_minute_open():
    required = [
        "/api/v3/market/candles",
        "category=USDT-FUTURES",
        "interval=1m",
        "bar->>1",
        "=v_expected",
        "max_reference_age_seconds',60",
    ]
    for marker in required:
        assert marker in SQL


def test_signed_delta_direction_is_explicit():
    assert "(o.fill_price-v_open)/v_open*10000.0" in SQL
    assert "(v_open-o.fill_price)/v_open*10000.0" in SQL
    assert "positive_delta_means_adverse_to_fill_side" in SQL


def test_claim_ceiling_forbids_slippage_and_profitability_claims():
    required = [
        "COARSE_ORDER_MINUTE_OPEN_NOT_SLIPPAGE",
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


def test_no_exchange_write_or_new_cron_path():
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


def test_append_only_and_service_role_read_only():
    assert "alpha_hunter_block_append_only_mutation" in SQL
    assert "grant select on public.alpha_hunter_execution_order_minute_benchmark_v01 to service_role" in LOWER
    assert "grant select on public.alpha_hunter_execution_order_minute_benchmark_failures_v01 to service_role" in LOWER
