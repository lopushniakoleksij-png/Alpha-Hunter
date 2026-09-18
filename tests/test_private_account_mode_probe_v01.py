import requests

from alpha_hunter.bitget import (
    BitgetAPIError,
    BitgetClient,
    BitgetDeterministicAPIError,
)
from alpha_hunter.private_account import collect_private_account_snapshot


class FakeClient:
    private_api_configured = True

    def __init__(
        self,
        *,
        account_info=None,
        account_info_error=None,
        settings=None,
        settings_error=None,
        accounts=None,
        positions=None,
    ):
        self.account_info = account_info or {
            "permType": "read-only",
            "permissions": [],
        }
        self.account_info_error = account_info_error
        self.settings = settings
        self.settings_error = settings_error
        self.accounts = accounts or []
        self.positions = positions or []
        self.account_info_calls = 0
        self.settings_calls = 0
        self.classic_account_calls = 0
        self.classic_position_calls = 0

    def account_info_v3(self):
        self.account_info_calls += 1
        if self.account_info_error is not None:
            raise self.account_info_error
        return self.account_info

    def account_settings_v3(self):
        self.settings_calls += 1
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
    assert result["api_permission_probe_status"] == "NOT_CONFIGURED"
    assert client.account_info_calls == 0
    assert client.classic_account_calls == 0
    assert client.classic_position_calls == 0


def test_permission_metadata_is_observed_but_never_grants_trade_authority():
    client = FakeClient(
        account_info={
            "permType": "read-and-write",
            "permissions": ["uta_trade", "uta_mgt", "uta_trade"],
        },
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
    assert result["api_permission_probe_status"] == "CONNECTED"
    assert result["api_permission_type"] == "read-and-write"
    assert result["api_permissions"] == ["uta_mgt", "uta_trade"]
    assert result["classic_v2_risk_evidence_accepted"] is True
    assert "trade_permission" not in result


def test_permission_probe_failure_is_diagnostic_only_and_classic_fallback_survives():
    client = FakeClient(
        account_info_error=BitgetAPIError("account info unavailable"),
        settings_error=BitgetAPIError("UTA settings unavailable"),
        accounts=[{
            "marginCoin": "USDT",
            "available": "7",
            "locked": "0",
            "accountEquity": "7",
            "unrealizedPL": "0",
        }],
        positions=[],
    )
    result = collect_private_account_snapshot(client, "usdt-futures")

    assert result["status"] == "CONNECTED"
    assert result["api_permission_probe_status"] == "UNAVAILABLE"
    assert "account info unavailable" in result["api_permission_probe_error"]
    assert result["api_permission_type"] is None
    assert result["api_permissions"] == []
    assert client.account_info_calls == 1
    assert client.classic_account_calls == 1
    assert client.classic_position_calls == 1


def test_40084_confirms_classic_mode_and_skips_second_uta_probe():
    client = FakeClient(
        account_info_error=BitgetDeterministicAPIError(
            (
                "Bitget HTTP 400 error 40084: You are in Classic Account mode, "
                "and the Unified Account API is not supported at this time"
            ),
            http_status=400,
            bitget_code="40084",
            bitget_message=(
                "You are in Classic Account mode, and the Unified Account API "
                "is not supported at this time"
            ),
        ),
        settings={"accountMode": "unified"},
        accounts=[{
            "marginCoin": "USDT",
            "available": "15",
            "locked": "0",
            "accountEquity": "15",
            "unrealizedPL": "0",
        }],
        positions=[],
    )

    result = collect_private_account_snapshot(client, "usdt-futures")

    assert result["status"] == "CONNECTED"
    assert result["api_permission_probe_status"] == "NOT_APPLICABLE_CLASSIC_ACCOUNT"
    assert result["account_mode_probe_status"] == "CLASSIC_CONFIRMED_FROM_V3_40084"
    assert result["account_mode"] == "classic"
    assert result["classic_v2_risk_evidence_accepted"] is True
    assert client.account_info_calls == 1
    assert client.settings_calls == 0
    assert client.classic_account_calls == 1
    assert client.classic_position_calls == 1


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


class _HTTPResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=self,
            )

    def json(self):
        return self._payload


def test_v3_readonly_probe_does_not_retry_deterministic_400(monkeypatch):
    calls = []
    sleeps = []

    def fake_request(*args, **kwargs):
        calls.append((args, kwargs))
        return _HTTPResponse(
            400,
            {
                "code": "40014",
                "msg": "Incorrect permissions",
            },
        )

    monkeypatch.setattr(
        "alpha_hunter.bitget.requests.request",
        fake_request,
    )
    monkeypatch.setattr(
        "alpha_hunter.bitget.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    client = BitgetClient(
        api_key="test-key",
        secret_key="test-secret",
        passphrase="test-passphrase",
        max_retries=3,
    )

    try:
        client.account_info_v3()
    except BitgetAPIError as exc:
        error = str(exc)
    else:
        raise AssertionError("expected deterministic BitgetAPIError")

    assert len(calls) == 1
    assert sleeps == []
    assert "Bitget HTTP 400 error 40014" in error
    assert "Incorrect permissions" in error


def test_v3_readonly_probe_still_retries_transient_500(monkeypatch):
    calls = []
    sleeps = []

    def fake_request(*args, **kwargs):
        calls.append((args, kwargs))
        return _HTTPResponse(
            500,
            {
                "code": "50000",
                "msg": "temporary server error",
            },
        )

    monkeypatch.setattr(
        "alpha_hunter.bitget.requests.request",
        fake_request,
    )
    monkeypatch.setattr(
        "alpha_hunter.bitget.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    client = BitgetClient(
        api_key="test-key",
        secret_key="test-secret",
        passphrase="test-passphrase",
        max_retries=3,
    )

    try:
        client.account_info_v3()
    except BitgetAPIError as exc:
        error = str(exc)
    else:
        raise AssertionError("expected retry exhaustion")

    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]
    assert "Request failed after 3 attempts" in error


def test_v3_settings_uses_same_deterministic_4xx_fail_fast_path(monkeypatch):
    calls = []

    def fake_request(*args, **kwargs):
        calls.append((args, kwargs))
        return _HTTPResponse(
            400,
            {
                "code": "40001",
                "msg": "settings unavailable",
            },
        )

    monkeypatch.setattr(
        "alpha_hunter.bitget.requests.request",
        fake_request,
    )
    monkeypatch.setattr(
        "alpha_hunter.bitget.time.sleep",
        lambda _seconds: (_ for _ in ()).throw(
            AssertionError("deterministic 4xx must not sleep")
        ),
    )

    client = BitgetClient(
        api_key="test-key",
        secret_key="test-secret",
        passphrase="test-passphrase",
        max_retries=3,
    )

    try:
        client.account_settings_v3()
    except BitgetAPIError as exc:
        error = str(exc)
    else:
        raise AssertionError("expected deterministic BitgetAPIError")

    assert len(calls) == 1
    assert "Bitget HTTP 400 error 40001" in error
