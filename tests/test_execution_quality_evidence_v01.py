import json
from pathlib import Path
from unittest.mock import patch

import pytest

from alpha_hunter.execution_quality import (
    ORDER_DETAIL_ENDPOINT,
    ReadOnlyExecutionQualityClient,
    _adverse_delta_bps,
    normalize_order_detail_evidence,
)


SQL = Path("execution_quality_evidence_v01.sql").read_text(encoding="utf-8")
MODULE = Path("alpha_hunter/execution_quality.py").read_text(encoding="utf-8")
SCRIPT = Path("ops/collect_execution_quality_readonly.py").read_text(
    encoding="utf-8"
)


def _fill(**overrides):
    row = {
        "fill_evidence_id": "fill-1",
        "order_id": "raw-order-123",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "price": 100.0,
        "fill_time_utc": "2026-09-20T00:00:00+00:00",
        "enter_point_source": "ios",
    }
    row.update(overrides)
    return row


def _detail(**overrides):
    row = {
        "orderId": "raw-order-123",
        "clientOid": "client-secret-ish-id",
        "symbol": "BTCUSDT",
        "price": "101",
        "priceAvg": "100",
        "state": "filled",
        "side": "buy",
        "force": "gtc",
        "orderType": "limit",
        "enterPointSource": "ios",
        "tradeSide": "close",
        "orderSource": "normal",
        "reduceOnly": "yes",
        "cTime": "1789862400000",
        "uTime": "1789862401000",
    }
    row.update(overrides)
    return row


def test_order_detail_client_uses_get_only_classic_endpoint():
    client = ReadOnlyExecutionQualityClient(
        api_key="k",
        secret_key="s",
        passphrase="p",
        max_retries=1,
    )

    with patch.object(
        client,
        "_get",
        return_value={"orderId": "1"},
    ) as get:
        result = client.futures_order_detail(
            symbol="BTCUSDT",
            product_type="usdt-futures",
            order_id="1",
        )

    assert result == {"orderId": "1"}
    get.assert_called_once_with(
        ORDER_DETAIL_ENDPOINT,
        {
            "symbol": "BTCUSDT",
            "productType": "usdt-futures",
            "orderId": "1",
        },
        private=True,
        retry_deterministic_4xx=False,
    )


def test_limit_buy_delta_positive_means_adverse_and_ids_are_hashed():
    row = normalize_order_detail_evidence(
        _fill(price=102.0),
        _detail(price="101", priceAvg="101.5"),
        observed_at_utc="2026-09-20T02:00:00+00:00",
    )

    assert row["benchmark_class"] == "LIMIT_ORDER_PRICE"
    assert row["fill_vs_limit_delta_bps"] == pytest.approx(
        (102.0 - 101.0) / 101.0 * 10000.0
    )
    assert row["limit_price_delta_claim_permitted"] is True
    assert row["slippage_claim_permitted"] is False
    assert row["fill_origin_class"] == "HUMAN_UI_EXTERNAL"
    assert row["alpha_hunter_execution_claim_permitted"] is False

    serialized = json.dumps(row)
    assert "raw-order-123" not in serialized
    assert "client-secret-ish-id" not in serialized
    assert len(row["order_identity_sha256"]) == 64
    assert len(row["client_oid_sha256"]) == 64


def test_limit_sell_delta_uses_sell_adverse_sign():
    assert _adverse_delta_bps("SELL", 99.0, 100.0) == pytest.approx(
        100.0
    )
    assert _adverse_delta_bps("SELL", 101.0, 100.0) == pytest.approx(
        -100.0
    )


def test_market_order_withholds_slippage_without_pretrade_benchmark():
    row = normalize_order_detail_evidence(
        _fill(),
        _detail(orderType="market", price="0", priceAvg="100"),
        observed_at_utc="2026-09-20T02:00:00+00:00",
    )

    assert row["benchmark_class"] == (
        "MARKET_NO_VERIFIED_PRETRADE_BENCHMARK"
    )
    assert row["fill_vs_limit_delta_bps"] is None
    assert row["order_average_vs_limit_delta_bps"] is None
    assert row["limit_price_delta_claim_permitted"] is False
    assert row["slippage_claim_permitted"] is False


def test_order_origin_crosscheck_is_preserved_without_execution_claim():
    consistent = normalize_order_detail_evidence(
        _fill(enter_point_source="ios"),
        _detail(enterPointSource="ios"),
        observed_at_utc="2026-09-20T02:00:00+00:00",
    )
    mismatch = normalize_order_detail_evidence(
        _fill(enter_point_source="ios"),
        _detail(enterPointSource="api"),
        observed_at_utc="2026-09-20T02:00:00+00:00",
    )

    assert consistent["origin_consistent"] is True
    assert mismatch["origin_consistent"] is False
    assert consistent["alpha_hunter_execution_claim_permitted"] is False
    assert mismatch["alpha_hunter_execution_claim_permitted"] is False


def test_sql_markout_contract_uses_public_exact_minute_reference():
    required = [
        "/api/v3/market/candles",
        "BITGET_PUBLIC_V3_1M_CANDLES",
        "horizon_minutes in (1,5,15,60)",
        "reference_expected_at_utc",
        "ceil(extract(epoch from v_target)/60.0)*60.0",
        "FIRST_EXACT_1M_OPEN_AT_OR_AFTER_HORIZON",
        "DATA_INSUFFICIENT",
        "signed_post_fill_markout_bps",
        "DESCRIPTIVE_POST_FILL_MARKOUT_NOT_SLIPPAGE",
    ]
    for marker in required:
        assert marker in SQL


def test_markout_sign_is_fill_side_aligned_and_not_slippage():
    assert "(v_reference_open-f.price)/f.price*10000.0" in SQL
    assert "(f.price-v_reference_open)/f.price*10000.0" in SQL
    assert "'markout_is_not_slippage',true" in SQL
    assert "check (slippage_claim_permitted=false)" in SQL
    assert "false as realistic_net_r_claim_permitted" in SQL


def test_execution_quality_schema_is_append_only_and_fail_closed():
    lower = SQL.lower()

    for table in (
        "alpha_hunter_execution_order_evidence_v01",
        "alpha_hunter_execution_order_failures_v01",
        "alpha_hunter_execution_markout_evidence_v01",
        "alpha_hunter_execution_markout_failures_v01",
    ):
        assert f"alter table public.{table} enable row level security" in lower

    assert lower.count("alpha_hunter_block_append_only_mutation") >= 4
    assert "alpha-hunter-execution-markouts-hourly" in lower
    assert "'47 * * * *'" in SQL

    for forbidden in (
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled",
        "place_order",
        "cancel_order",
        "modify_order",
        "set-leverage",
        "/api/v2/mix/order/place-order",
    ):
        assert forbidden not in lower


def test_mac_collector_never_prints_raw_ids_or_claims_cost_model():
    required = [
        '"raw_order_ids_printed": False',
        '"raw_client_oids_printed": False',
        '"slippage_model_validated": False',
        '"cost_model_activated": False',
        '"realistic_net_r_claimed": False',
        '"read_only_get": True',
        '"no_order_write_path": True',
        '"trade_permission": False',
        "_redact_identity",
    ]
    for marker in required:
        assert marker in SCRIPT

    forbidden = [
        "print(order_id",
        "print(client_oid",
        "place_order",
        "cancel_order",
        "modify_order",
        "transfer",
        "withdraw",
    ]
    for marker in forbidden:
        assert marker not in SCRIPT.lower()


def test_private_order_evidence_does_not_duplicate_raw_ids():
    assert '"raw_order_id_persisted_here": False' in MODULE
    assert '"raw_client_oid_persisted_here": False' in MODULE
    assert '"raw_order_or_client_ids_duplicated": False' in MODULE
