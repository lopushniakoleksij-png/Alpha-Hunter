from alpha_hunter.bitget import BitgetAPIError
from alpha_hunter.private_account import collect_private_account_snapshot


class FakeClient:
    private_api_configured = True

    def __init__(self, *, settings=None, settings_error=None, accounts=None, positions=None):
        self.settings = settings
        self.settings_error = settings_error
        self.accounts = accounts or []
        self.positions = positions or []
        self.classic_account_calls = 0
        self.classic_position_calls = 0

    def account_settings_v3(self):
        if self.settings_error is not None:
            raise self.settings_error
        return self.settings

    def futures_accounts(self, product_type):
        self.classic_account_calls += 1
        return self.accounts

    def futures_positions(self, product_type, margin_coin="USDT"):
        self.classic_position_calls += 1
        return self.positions


class NoCredentialClient(FakeClient):
    private_api_configured = False


def test_no_credentials_still_fail_closed_without_classic_reads():
    client = NoCredentialClient(settings=None)
    result = collect_private_account_snapshot(client, "usdt-futures")
    assert result["status"] == "NOT_CONFIGURED"
    assert result["account_mode_probe_status"] == "NOT_CONFIGURED"
    assert client.classic_account_calls == 0
    assert client.classic_position_calls == 0


def test_unified_mode_blocks_classic_v2_risk_evidence():
    client = FakeClient(settings={
        "accountMode": "unified",
        "accountLevel": "normal",
        "assetMode": "single",
        "holdMode": "double_hold",
    }, accounts=[{"marginCoin": "USDT", "available": "99"}])
    result = collect_private_account_snapshot(client, "usdt-futures")
    assert result["status"] == "ACCOUNT_MODE_REQUIRES_V3"
    assert result["account_mode"] == "unified"
    assert result["classic_v2_risk_evidence_accepted"] is False
    assert result["accounts"] == []
    assert client.classic_account_calls == 0
    assert client.classic_position_calls == 0


def test_hybrid_and_transition_modes_fail_closed_before_classic_reads():
    for mode in ("hybrid", "upgrading", "switching"):
        client = FakeClient(settings={"accountMode": mode})
        result = collect_private_account_snapshot(client, "usdt-futures")
        assert result["status"] == "ACCOUNT_MODE_REQUIRES_V3"
        assert result["account_mode"] == mode
        assert result["classic_v2_risk_evidence_accepted"] is False
        assert client.classic_account_calls == 0
        assert client.classic_position_calls == 0


def test_unrecognized_successful_v3_mode_is_not_guessed_as_classic():
    client = FakeClient(settings={"accountMode": "mystery-mode"})
    result = collect_private_account_snapshot(client, "usdt-futures")
    assert result["status"] == "ACCOUNT_MODE_UNRECOGNIZED"
    assert result["classic_v2_risk_evidence_accepted"] is False
    assert client.classic_account_calls == 0
    assert client.classic_position_calls == 0


def test_unavailable_v3_probe_can_use_existing_classic_read_only_path():
    client = FakeClient(
        settings_error=BitgetAPIError("UTA settings unavailable"),
        accounts=[{
            "marginCoin": "USDT",
            "available": "12.5",
            "locked": "0",
            "accountEquity": "12.5",
            "unrealizedPL": "0",
        }],
        positions=[],
    )
    result = collect_private_account_snapshot(client, "usdt-futures")
    assert result["status"] == "CONNECTED"
    assert result["account_source"] == "BITGET_V2_CLASSIC"
    assert result["account_mode_probe_status"] == "UNAVAILABLE_CLASSIC_FALLBACK"
    assert result["classic_v2_risk_evidence_accepted"] is True
    assert result["accounts"][0]["available"] == "12.5"
    assert client.classic_account_calls == 1
    assert client.classic_position_calls == 1


def test_classic_position_normalization_is_preserved_after_probe_fallback():
    client = FakeClient(
        settings_error=BitgetAPIError("UTA settings unavailable"),
        accounts=[{
            "marginCoin": "USDT",
            "available": "100",
            "locked": "0",
            "accountEquity": "100",
            "unrealizedPL": "2",
        }],
        positions=[{
            "symbol": "BTCUSDT",
            "holdSide": "long",
            "total": "0.001",
            "available": "0.001",
            "leverage": "5",
            "marginMode": "crossed",
            "openPriceAvg": "76000",
            "markPrice": "76500",
            "unrealizedPL": "0.5",
            "breakEvenPrice": "76020",
            "liquidationPrice": "62000",
            "takeProfit": None,
            "stopLoss": None,
        }],
    )
    result = collect_private_account_snapshot(client, "usdt-futures")
    assert result["status"] == "CONNECTED"
    assert result["open_position_count"] == 1
    position = result["open_positions"][0]
    assert position["symbol"] == "BTCUSDT"
    assert position["hold_side"] == "long"
    assert position["liquidation_price"] == "62000"
