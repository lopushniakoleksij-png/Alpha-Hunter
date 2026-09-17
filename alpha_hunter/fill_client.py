from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import requests

from .bitget import BitgetAPIError, BitgetClient


class ReadOnlyFillClient(BitgetClient):
    """Bitget client extension exposing only the documented GET fill-history route."""

    def _diagnostic_fill_get(
        self,
        path: str,
        params: dict[str, Any],
        original_error: BitgetAPIError,
    ) -> dict[str, Any]:
        """Repeat a failed fill GET once so Bitget's JSON code/msg is preserved.

        The shared client currently raises on HTTP status before parsing Bitget's
        JSON error body. This scoped read-only retry is diagnostic only and never
        introduces an order/write route.
        """
        if not self.private_api_configured:
            raise original_error

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

        try:
            response = requests.get(
                self.base_url + path,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            try:
                payload = response.json()
            except ValueError:
                raise BitgetAPIError(
                    f"{original_error}; diagnostic HTTP {response.status_code} "
                    "returned non-JSON body"
                ) from original_error

            code = str(payload.get("code") or "")
            message = str(payload.get("msg") or "")
            if code != "00000":
                raise BitgetAPIError(
                    f"{original_error}; Bitget HTTP {response.status_code} "
                    f"error {code or 'UNKNOWN'}: {message or 'UNKNOWN'}"
                ) from original_error

            response.raise_for_status()
            data = payload.get("data")
            return data if isinstance(data, dict) else {}
        except requests.RequestException as exc:
            raise BitgetAPIError(
                f"{original_error}; diagnostic GET failed: {exc}"
            ) from original_error

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

        path = "/api/v2/mix/order/fills"
        try:
            data = self._get(
                path,
                params,
                private=True,
            )
        except BitgetAPIError as exc:
            data = self._diagnostic_fill_get(path, params, exc)
        return data if isinstance(data, dict) else {}
