from alpha_hunter.account_ledger import build_account_ledger_rows
from alpha_hunter.bitget import BitgetAPIError, BitgetClient
from alpha_hunter.private_account import collect_private_account_snapshot


class ProtectionClient:
    private_api_configured = True

    def __init__(self, *, pending=None, pending_error=None):
        self.pending = pending or []
        self.pending_error = pending_error
        self.pending_calls = 0

    def account_info_v3(self):
        return {"permType": "read-only", "permissions": []}

    def account_settings_v3(self):
        raise BitgetAPIError("classic fallback")

    def futures_accounts(self, product_type):
        return [{
            "marginCoin": "USDT",
            "available": "3.9",
            "locked": "0",
            "accountEquity": "4.9",
            "unrealizedPL": "1.0",
        }]

    def futures_positions(self, product_type, margin_coin="USDT"):
        return [{
            "symbol": "QNTUSDT",
            "holdSide": "long",
            "total": "0.06",
            "available": "0.06",
            "leverage": "15",
            "marginMode": "crossed",
            "openPriceAvg": "230.48",
            "markPrice": "247.04",
            "unrealizedPL": "0.9936",
            "breakEvenPrice": "230.44",
            "liquidationPrice": "166.64",
            "takeProfit": "",
            "stopLoss": "",
        }]

    def pending_tpsl_orders(self, product_type):
        self.pending_calls += 1
        if self.pending_error is not None:
            raise self.pending_error
        return self.pending


def _order(plan_type, trigger_price, *, pos_side="long", size="0.06"):
    return {
        "planType": plan_type,
        "symbol": "QNTUSDT",
        "size": size,
        "orderId": f"{plan_type}-{trigger_price}",
        "clientOid": "",
        "triggerPrice": str(trigger_price),
        "triggerType": "mark_price",
        "planStatus": "not_trigger",
        "posSide": pos_side,
        "marginMode": "crossed",
        "cTime": "1790950000000",
        "uTime": "1790950100000",
    }


def test_pending_tpsl_client_uses_documented_profit_loss_endpoint(monkeypatch):
    client = BitgetClient(
        api_key="key",
        secret_key="secret",
        passphrase="pass",
    )
    calls = []

    def fake_get(path, params, **kwargs):
        calls.append((path, params, kwargs))
        return {"entrustedList": [_order("pos_loss", "234.29")]}

    monkeypatch.setattr(client, "_get", fake_get)

    rows = client.pending_tpsl_orders("usdt-futures", symbol="QNTUSDT")

    assert len(rows) == 1
    path, params, kwargs = calls[0]
    assert path == "/api/v2/mix/order/orders-plan-pending"
    assert params == {
        "planType": "profit_loss",
        "productType": "usdt-futures",
        "symbol": "QNTUSDT",
    }
    assert kwargs["private"] is True
    assert kwargs["retry_deterministic_4xx"] is False


def test_pending_position_tp_sl_are_bound_to_open_position():
    client = ProtectionClient(
        pending=[
            _order("pos_profit", "270"),
            _order("pos_loss", "234.29"),
        ]
    )

    result = collect_private_account_snapshot(client, "usdt-futures")

    assert result["status"] == "CONNECTED"
    assert result["protection_observation_status"] == "CONNECTED"
    assert result["pending_tpsl_order_count"] == 2
    assert client.pending_calls == 1

    position = result["open_positions"][0]
    assert position["take_profit"] == "270"
    assert position["stop_loss"] == "234.29"
    assert position["take_profit_source"] == "PENDING_TPSL"
    assert position["stop_loss_source"] == "PENDING_TPSL"
    assert position["protection_observation_status"] == "CONNECTED"
    assert len(position["protection_orders"]) == 2


def test_multiple_take_profit_levels_are_not_collapsed_into_invented_scalar():
    client = ProtectionClient(
        pending=[
            _order("profit_plan", "257.40", size="0.03"),
            _order("profit_plan", "270", size="0.03"),
            _order("pos_loss", "234.29"),
        ]
    )

    result = collect_private_account_snapshot(client, "usdt-futures")
    position = result["open_positions"][0]

    assert position["take_profit"] is None
    assert position["take_profit_source"] is None
    assert position["stop_loss"] == "234.29"
    assert len(position["protection_orders"]) == 3


def test_failed_protection_observer_is_unknown_not_confirmed_absent():
    client = ProtectionClient(
        pending_error=BitgetAPIError("pending TP/SL unavailable")
    )

    private_account = collect_private_account_snapshot(client, "usdt-futures")
    position = private_account["open_positions"][0]

    assert private_account["status"] == "CONNECTED"
    assert private_account["protection_observation_status"] == "FAILED"
    assert "unavailable" in private_account["protection_observation_error"]
    assert position["take_profit"] is None
    assert position["stop_loss"] is None

    account_row, position_rows = build_account_ledger_rows({
        "run_id": "run-protection-failed",
        "collected_at_utc": "2026-10-02T17:10:00+00:00",
        "private_account": private_account,
    })

    assert account_row["connection_status"] == "CONNECTED_READ_ONLY"
    evidence = position_rows[0]["evidence"]
    assert evidence["exchange_protection_observation_status"] == "FAILED"
    assert evidence["exchange_protection_absence_confirmed"] is False


def test_connected_empty_protection_query_can_confirm_absence():
    private_account = collect_private_account_snapshot(
        ProtectionClient(pending=[]),
        "usdt-futures",
    )

    _, position_rows = build_account_ledger_rows({
        "run_id": "run-protection-none",
        "collected_at_utc": "2026-10-02T17:11:00+00:00",
        "private_account": private_account,
    })

    evidence = position_rows[0]["evidence"]
    assert evidence["exchange_protection_observation_status"] == "CONNECTED"
    assert evidence["exchange_protection_orders_observed"] == []
    assert evidence["exchange_protection_absence_confirmed"] is True
