from __future__ import annotations

from pathlib import Path

from alpha_hunter.fill_ledger import collect_fill_traceability


class FakeFillClient:
    def __init__(self, pages=None, configured=True):
        self.private_api_configured = configured
        self.pages = list(pages or [])
        self.calls = []

    def futures_fills(
        self,
        product_type,
        *,
        start_time_ms,
        end_time_ms,
        limit=100,
        id_less_than=None,
    ):
        self.calls.append(
            {
                "product_type": product_type,
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
                "limit": limit,
                "id_less_than": id_less_than,
            }
        )
        return self.pages.pop(0) if self.pages else {"fillList": [], "endId": ""}


def connected_classic_account():
    return {
        "status": "CONNECTED",
        "account_mode_probe_status": "UNAVAILABLE_CLASSIC_FALLBACK",
        "classic_v2_risk_evidence_accepted": True,
    }


def valid_fill(trade_id="trade-1", order_id="order-1"):
    return {
        "tradeId": trade_id,
        "orderId": order_id,
        "symbol": "BTCUSDT",
        "side": "buy",
        "tradeSide": "open",
        "posMode": "hedge_mode",
        "tradeScope": "taker",
        "price": "60000",
        "baseVolume": "0.001",
        "quoteVolume": "60",
        "profit": "0",
        "feeDetail": [{"feeCoin": "USDT", "totalFee": "-0.036"}],
        "enterPointSource": "API",
        "cTime": "1789640400000",
    }


def test_not_configured_never_calls_exchange():
    client = FakeFillClient(configured=False)
    result = collect_fill_traceability(
        client,
        product_type="usdt-futures",
        source_run_id="run-1",
        observed_at_utc="2026-09-17T13:00:00+00:00",
        private_account={"status": "NOT_CONFIGURED"},
    )
    assert result.run_row["status"] == "NOT_CONFIGURED"
    assert result.run_row["complete"] is False
    assert result.fill_rows == []
    assert client.calls == []


def test_uta_or_unverified_account_family_blocks_classic_fill_endpoint():
    client = FakeFillClient(configured=True)
    result = collect_fill_traceability(
        client,
        product_type="usdt-futures",
        source_run_id="run-2",
        observed_at_utc="2026-09-17T13:00:00+00:00",
        private_account={
            "status": "ACCOUNT_MODE_REQUIRES_V3",
            "account_mode_probe_status": "CONNECTED",
            "classic_v2_risk_evidence_accepted": False,
        },
    )
    assert result.run_row["status"] == "BLOCKED_ACCOUNT_API_FAMILY_UNVERIFIED"
    assert result.fill_rows == []
    assert client.calls == []


def test_valid_fill_is_append_only_evidence_not_slippage_claim():
    client = FakeFillClient(
        pages=[{"fillList": [valid_fill()], "endId": "cursor-1"}], configured=True
    )
    result = collect_fill_traceability(
        client,
        product_type="usdt-futures",
        source_run_id="run-3",
        observed_at_utc="2026-09-17T13:00:00+00:00",
        private_account=connected_classic_account(),
    )
    assert result.run_row["status"] == "CONNECTED"
    assert result.run_row["complete"] is True
    assert result.run_row["schema_validated"] is True
    assert result.run_row["fill_count"] == 1
    assert result.run_row["trade_permission"] is False
    assert len(client.calls) == 1

    row = result.fill_rows[0]
    assert row["trade_id"] == "trade-1"
    assert row["symbol"] == "BTCUSDT"
    assert row["trade_scope"] == "TAKER"
    assert row["fee_amount"] == -0.036
    assert row["fee_coin"] == "USDT"
    assert row["cost_fields_complete"] is True
    assert row["trade_permission"] is False
    assert row["shadow_only"] is True
    assert row["evidence"]["slippage_claim_permitted"] is False
    assert row["evidence"]["realistic_net_r_claim_permitted"] is False
    assert "slippage_bps" not in row
    assert "arrival_price" not in row
    assert "intended_price" not in row


def test_zero_fills_is_validated_but_not_connected_traceability_pass():
    client = FakeFillClient(pages=[{"fillList": [], "endId": ""}], configured=True)
    result = collect_fill_traceability(
        client,
        product_type="usdt-futures",
        source_run_id="run-4",
        observed_at_utc="2026-09-17T13:00:00+00:00",
        private_account=connected_classic_account(),
    )
    assert result.run_row["status"] == "ZERO_FILLS"
    assert result.run_row["complete"] is True
    assert result.run_row["schema_validated"] is True
    assert result.run_row["fill_count"] == 0
    assert result.run_row["evidence"]["zero_fills_do_not_pass_traceability"] is True


def test_invalid_fill_schema_fails_closed_without_partial_valid_claim():
    broken = valid_fill()
    broken.pop("tradeId")
    client = FakeFillClient(
        pages=[{"fillList": [broken], "endId": "cursor-1"}], configured=True
    )
    result = collect_fill_traceability(
        client,
        product_type="usdt-futures",
        source_run_id="run-5",
        observed_at_utc="2026-09-17T13:00:00+00:00",
        private_account=connected_classic_account(),
    )
    assert result.run_row["status"] == "INVALID_SCHEMA"
    assert result.run_row["complete"] is False
    assert result.run_row["schema_validated"] is False
    assert result.fill_rows == []
    assert result.run_row["trade_permission"] is False


def test_get_only_adapter_and_no_order_route():
    source = Path("alpha_hunter/fill_client.py").read_text().lower()
    assert '"/api/v2/mix/order/fills"' in source
    assert "self._get(" in source
    for forbidden in (
        "self._post(",
        "self._delete(",
        "place_order",
        "place-order",
        "cancel_order",
        "cancel-order",
        "modify-order",
        "set-leverage",
    ):
        assert forbidden not in source


def test_database_schema_is_append_only_and_has_no_slippage_authority():
    sql = Path("canonical_readonly_fill_ledger_v01.sql").read_text().lower()
    assert "alpha_hunter_fill_traceability_runs" in sql
    assert "alpha_hunter_fill_evidence" in sql
    assert "enable row level security" in sql
    assert "alpha_hunter_block_append_only_mutation" in sql
    assert "check (shadow_only = true)" in sql
    assert "check (trade_permission = false)" in sql
    assert "idx_ah_fill_evidence_traceability_run" in sql
    assert "on public.alpha_hunter_fill_evidence(traceability_run_id)" in sql
    for forbidden_field in (
        "slippage_bps",
        "entry_slippage",
        "exit_slippage",
        "arrival_price",
        "intended_price",
    ):
        assert forbidden_field not in sql
    assert "realistic_net_r" not in sql
    assert "production_execution_enabled" not in sql


def test_run_wires_fill_evidence_after_account_evidence():
    source = Path("run.py").read_text()
    account_pos = source.index("persist_account_ledger")
    fill_pos = source.index("collect_fill_traceability")
    assert fill_pos > account_pos
    assert "persist_fill_traceability" in source
    assert 'trade_permission=false' in source
