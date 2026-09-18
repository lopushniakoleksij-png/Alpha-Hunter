from unittest.mock import Mock, patch

import pytest
import requests

from alpha_hunter.bitget import BitgetAPIError
from alpha_hunter.fill_client import (
    FUTURES_ORDER_READ_PERMISSION,
    BitgetFillPermissionError,
    ReadOnlyFillClient,
)


def _client(max_retries: int = 3) -> ReadOnlyFillClient:
    return ReadOnlyFillClient(
        api_key="test-key",
        secret_key="test-secret",
        passphrase="test-passphrase",
        max_retries=max_retries,
    )


def _response(status_code: int, payload: dict) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(
            f"{status_code} response"
        )
    else:
        response.raise_for_status.return_value = None
    return response


def test_permission_40014_is_non_retryable_and_preserves_required_permission() -> None:
    client = _client(max_retries=3)
    response = _response(
        400,
        {
            "code": "40014",
            "msg": (
                "Incorrect permissions, need future order read "
                "or future order write permissions"
            ),
        },
    )

    with patch(
        "alpha_hunter.fill_client.requests.get",
        return_value=response,
    ) as fill_get, patch("alpha_hunter.fill_client.time.sleep") as sleep:
        with pytest.raises(BitgetFillPermissionError) as exc_info:
            client.futures_fills(
                "usdt-futures",
                start_time_ms=1,
                end_time_ms=2,
            )

    error = exc_info.value
    assert error.bitget_code == "40014"
    assert error.required_permission == FUTURES_ORDER_READ_PERMISSION
    assert error.retryable is False
    assert "required_permission=FUTURES_ORDER_READ" in str(error)
    assert fill_get.call_count == 1
    assert sleep.call_count == 0
    assert fill_get.call_args.args[0].endswith("/api/v2/mix/order/fills")
    assert fill_get.call_args.kwargs["params"]["productType"] == "usdt-futures"


def test_other_4xx_is_non_retryable_but_preserves_bitget_json_error() -> None:
    client = _client(max_retries=3)
    response = _response(
        400,
        {
            "code": "400172",
            "msg": "parameter verification failed",
        },
    )

    with patch(
        "alpha_hunter.fill_client.requests.get",
        return_value=response,
    ) as fill_get, patch("alpha_hunter.fill_client.time.sleep") as sleep:
        with pytest.raises(BitgetAPIError) as exc_info:
            client.futures_fills(
                "usdt-futures",
                start_time_ms=1,
                end_time_ms=2,
            )

    message = str(exc_info.value)
    assert "Bitget HTTP 400 error 400172" in message
    assert "parameter verification failed" in message
    assert fill_get.call_count == 1
    assert sleep.call_count == 0


def test_transient_5xx_retries_then_accepts_successful_read() -> None:
    client = _client(max_retries=3)
    transient = _response(
        503,
        {"code": "50000", "msg": "temporary unavailable"},
    )
    success = _response(
        200,
        {
            "code": "00000",
            "msg": "success",
            "data": {"fillList": [], "endId": ""},
        },
    )

    with patch(
        "alpha_hunter.fill_client.requests.get",
        side_effect=[transient, success],
    ) as fill_get, patch("alpha_hunter.fill_client.time.sleep") as sleep:
        result = client.futures_fills(
            "usdt-futures",
            start_time_ms=1,
            end_time_ms=2,
        )

    assert result == {"fillList": [], "endId": ""}
    assert fill_get.call_count == 2
    assert sleep.call_count == 1


def test_transport_failure_retries_then_accepts_successful_read() -> None:
    client = _client(max_retries=2)
    success = _response(
        200,
        {
            "code": "00000",
            "msg": "success",
            "data": {"fillList": [], "endId": ""},
        },
    )

    with patch(
        "alpha_hunter.fill_client.requests.get",
        side_effect=[requests.Timeout("timeout"), success],
    ) as fill_get, patch("alpha_hunter.fill_client.time.sleep") as sleep:
        result = client.futures_fills(
            "usdt-futures",
            start_time_ms=1,
            end_time_ms=2,
        )

    assert result == {"fillList": [], "endId": ""}
    assert fill_get.call_count == 2
    assert sleep.call_count == 1


def test_missing_credentials_never_calls_exchange() -> None:
    client = ReadOnlyFillClient(max_retries=3)

    with patch("alpha_hunter.fill_client.requests.get") as fill_get:
        with pytest.raises(BitgetAPIError) as exc_info:
            client.futures_fills(
                "usdt-futures",
                start_time_ms=1,
                end_time_ms=2,
            )

    assert "credentials are not configured" in str(exc_info.value)
    assert fill_get.call_count == 0
