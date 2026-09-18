from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import requests

from .bitget import BitgetAPIError, BitgetClient


FILL_ENDPOINT = "/api/v2/mix/order/fills"
FUTURES_ORDER_PERMISSION_ERROR_CODE = "40014"
FUTURES_ORDER_READ_PERMISSION = "FUTURES_ORDER_READ"


class BitgetFillPermissionError(BitgetAPIError):
    """Deterministic Bitget fill-history permission blocker."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.bitget_code = FUTURES_ORDER_PERMISSION_ERROR_CODE
        self.required_permission = FUTURES_ORDER_READ_PERMISSION
        self.retryable = False


class ReadOnlyFillClient(BitgetClient):
    """Bitget client extension exposing only the documented GET fill-history route."""

    def _signed_fill_get_once(
        self,
        path: str,
        params: dict[str, Any],
    ) -> requests.Response:
        """Issue exactly one signed read-only fill-history GET."""
        if not self.private_api_configured:
            raise BitgetAPIError(
                "Bitget private API credentials are not configured"
            )

        timestamp = str(int(time.time() * 1000))
        query = urlencode(params)
        target = path + (f"?{query}" if query else "")
        prehash = f"{timestamp}GET{target}"
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode(),
                prehash.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        headers = {
            "locale": "en-US",
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

        return requests.get(
            self.base_url + path,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )

    def _parse_fill_response(
        self,
        response: requests.Response,
    ) -> dict[str, Any]:
        """Parse Bitget's JSON before HTTP raising so deterministic codes survive."""
        try:
            payload = response.json()
        except ValueError as exc:
            raise BitgetAPIError(
                f"Fill GET HTTP {response.status_code} returned non-JSON body"
            ) from exc

        code = str(payload.get("code") or "")
        message = str(payload.get("msg") or "")

        if code == FUTURES_ORDER_PERMISSION_ERROR_CODE:
            raise BitgetFillPermissionError(
                f"Bitget HTTP {response.status_code} error {code}: "
                f"{message or 'Incorrect permissions'}; "
                f"required_permission={FUTURES_ORDER_READ_PERMISSION}"
            )

        if code != "00000":
            raise BitgetAPIError(
                f"Bitget HTTP {response.status_code} error "
                f"{code or 'UNKNOWN'}: {message or 'UNKNOWN'}"
            )

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BitgetAPIError(
                f"Fill GET HTTP {response.status_code} failed: {exc}"
            ) from exc

        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def futures_fills(
        self,
        product_type: str,
        *,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 100,
        id_less_than: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "productType": product_type,
            "startTime": str(start_time_ms),
            "endTime": str(end_time_ms),
            "limit": str(limit),
        }
        if id_less_than:
            params["idLessThan"] = id_less_than

        attempts = max(1, int(self.max_retries))
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = self._signed_fill_get_once(FILL_ENDPOINT, params)
            except requests.RequestException as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                raise BitgetAPIError(
                    f"Fill GET transport failed after {attempts} attempts: {exc}"
                ) from exc

            if response.status_code >= 500:
                last_error = BitgetAPIError(
                    f"Bitget transient HTTP {response.status_code}"
                )
                if attempt < attempts:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue

            try:
                return self._parse_fill_response(response)
            except BitgetFillPermissionError:
                raise
            except BitgetAPIError as exc:
                last_error = exc
                if response.status_code >= 500 and attempt < attempts:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                raise

        raise BitgetAPIError(
            f"Fill GET failed after {attempts} attempts: {last_error}"
        )
