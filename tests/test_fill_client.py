from unittest.mock import Mock, patch

import pytest

from alpha_hunter.bitget import BitgetAPIError
from alpha_hunter.fill_client import ReadOnlyFillClient


def _client() -> ReadOnlyFillClient:
    return ReadOnlyFillClient(
        api_key="test-key",
        secret_key="test-secret",
        passphrase="test-passphrase",
        max_retries=1,
    )


def test_futures_fills_preserves_bitget_json_error_without_write_path() -> None:
    client = _client()
    response = Mock()
    response.status_code = 400
    response.json.return_value = {
        "code": "400172",
        "msg": "parameter verification failed",
    }

    with patch.object(
        client,
        "_get",
        side_effect=BitgetAPIError("Request failed after 1 attempts: HTTP 400"),
    ), patch(
        "alpha_hunter.fill_client.requests.get",
        return_value=response,
    ) as diagnostic_get:
        with pytest.raises(BitgetAPIError) as exc_info:
            client.futures_fills(
                "usdt-futures",
                start_time_ms=1,
                end_time_ms=2,
            )

    message = str(exc_info.value)
    assert "Bitget HTTP 400 error 400172" in message
    assert "parameter verification failed" in message
    assert diagnostic_get.call_count == 1
    assert diagnostic_get.call_args.args[0].endswith("/api/v2/mix/order/fills")
    assert diagnostic_get.call_args.kwargs["params"]["productType"] == "usdt-futures"


def test_futures_fills_accepts_successful_diagnostic_read() -> None:
    client = _client()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "code": "00000",
        "msg": "success",
        "data": {"fillList": [], "endId": ""},
    }
    response.raise_for_status.return_value = None

    with patch.object(
        client,
        "_get",
        side_effect=BitgetAPIError("transient failure"),
    ), patch(
        "alpha_hunter.fill_client.requests.get",
        return_value=response,
    ):
        result = client.futures_fills(
            "usdt-futures",
            start_time_ms=1,
            end_time_ms=2,
        )

    assert result == {"fillList": [], "endId": ""}
