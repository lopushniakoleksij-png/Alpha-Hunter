from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests


class BitgetAPIError(RuntimeError):
    pass


class BitgetDeterministicAPIError(BitgetAPIError):
    """Deterministic Bitget client error that must not be retried."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int,
        bitget_code: str | None = None,
        bitget_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.bitget_code = bitget_code
        self.bitget_message = bitget_message


@dataclass
class BitgetClient:
    base_url: str = "https://api.bitget.com"
    timeout: int = 12
    max_retries: int = 3
    api_key: str | None = None
    secret_key: str | None = None
    passphrase: str | None = None

    @classmethod
    def from_environment(
        cls,
        **kwargs: Any,
    ) -> "BitgetClient":
        return cls(
            api_key=os.getenv(
                "BITGET_API_KEY"
            ),
            secret_key=os.getenv(
                "BITGET_SECRET_KEY"
            ),
            passphrase=os.getenv(
                "BITGET_API_PASSPHRASE"
            ),
            **kwargs,
        )

    @property
    def private_api_configured(
        self,
    ) -> bool:
        return bool(
            self.api_key
            and self.secret_key
            and self.passphrase
        )

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        private: bool = False,
        retry_deterministic_4xx: bool = True,
    ) -> Any:

        params = params or {}
        last_error = None

        for attempt in range(
            1,
            self.max_retries + 1,
        ):
            try:

                headers = {
                    "locale": "en-US"
                }

                if private:

                    if (
                        not self
                        .private_api_configured
                    ):
                        raise BitgetAPIError(
                            "Bitget private API "
                            "credentials are not "
                            "configured"
                        )

                    ts = str(
                        int(
                            time.time()
                            * 1000
                        )
                    )

                    query = urlencode(
                        params
                    )

                    target = (
                        path
                        + (
                            f"?{query}"
                            if query
                            else ""
                        )
                    )

                    prehash = (
                        f"{ts}"
                        f"{method.upper()}"
                        f"{target}"
                    )

                    sign = (
                        base64.b64encode(
                            hmac.new(
                                self.secret_key
                                .encode(),
                                prehash.encode(),
                                hashlib.sha256,
                            ).digest()
                        ).decode()
                    )

                    headers.update({
                        "ACCESS-KEY":
                            self.api_key,

                        "ACCESS-SIGN":
                            sign,

                        "ACCESS-TIMESTAMP":
                            ts,

                        "ACCESS-PASSPHRASE":
                            self.passphrase,

                        "Content-Type":
                            "application/json",
                    })

                response = (
                    requests.request(
                        method.upper(),
                        self.base_url
                        + path,
                        params=params,
                        headers=headers,
                        timeout=self.timeout,
                    )
                )

                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:
                    status = response.status_code
                    if (
                        not retry_deterministic_4xx
                        and 400 <= status < 500
                        and status not in {408, 429}
                    ):
                        try:
                            error_payload = response.json()
                        except ValueError:
                            error_payload = None

                        if isinstance(error_payload, dict):
                            code = error_payload.get("code")
                            msg = error_payload.get("msg")
                            if code is not None or msg is not None:
                                raise BitgetDeterministicAPIError(
                                    f"Bitget HTTP {status} error "
                                    f"{code}: {msg}",
                                    http_status=status,
                                    bitget_code=str(code) if code is not None else None,
                                    bitget_message=str(msg) if msg is not None else None,
                                ) from exc

                        raise BitgetDeterministicAPIError(
                            f"Bitget HTTP {status}: "
                            f"{response.text[:500]}",
                            http_status=status,
                        ) from exc
                    raise

                payload = response.json()

                if (
                    payload.get("code")
                    != "00000"
                ):
                    raise BitgetAPIError(
                        "Bitget error "
                        f"{payload.get('code')}: "
                        f"{payload.get('msg')}"
                    )

                return payload.get(
                    "data"
                )

            except BitgetDeterministicAPIError:
                raise

            except (
                requests.RequestException,
                ValueError,
                BitgetAPIError,
            ) as exc:

                last_error = exc

                if (
                    attempt
                    < self.max_retries
                ):
                    time.sleep(
                        0.5
                        * (
                            2
                            ** (
                                attempt
                                - 1
                            )
                        )
                    )

        raise BitgetAPIError(
            "Request failed after "
            f"{self.max_retries} "
            "attempts: "
            f"{last_error}"
        )

    def _get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        private: bool = False,
        retry_deterministic_4xx: bool = True,
    ) -> Any:

        return self._request(
            "GET",
            path,
            params,
            private=private,
            retry_deterministic_4xx=retry_deterministic_4xx,
        )

    # -------------------------------------------------
    # MARKET UNIVERSE
    # -------------------------------------------------

    def contracts(
        self,
        product_type: str,
    ):
        return self._get(
            "/api/v2/mix/market/contracts",
            {
                "productType":
                    product_type
            },
        ) or []

    def instruments(
        self,
        product_type: str,
    ):
        """
        Bitget V3 instrument metadata.

        Used by Alpha Hunter V7.1
        to distinguish crypto futures
        from RWA / reality / other
        non-crypto contracts.
        """

        category = (
            product_type.upper()
        )

        return self._get(
            "/api/v3/market/instruments",
            {
                "category":
                    category
            },
        ) or []

    def tickers(
        self,
        product_type: str,
    ):
        return self._get(
            "/api/v2/mix/market/tickers",
            {
                "productType":
                    product_type
            },
        ) or []

    # -------------------------------------------------
    # SYMBOL MARKET DATA
    # -------------------------------------------------

    def ticker(
        self,
        symbol: str,
        product_type: str,
    ):

        data = self._get(
            "/api/v2/mix/market/ticker",
            {
                "symbol":
                    symbol,

                "productType":
                    product_type,
            },
        )

        if not data:
            raise BitgetAPIError(
                "No ticker data for "
                f"{symbol}"
            )

        return data[0]

    def symbol_price(
        self,
        symbol: str,
        product_type: str,
    ):

        data = self._get(
            "/api/v2/mix/market/symbol-price",
            {
                "symbol":
                    symbol,

                "productType":
                    product_type,
            },
        )

        if not data:
            raise BitgetAPIError(
                "No symbol-price data "
                f"for {symbol}"
            )

        return data[0]

    def candles(
        self,
        symbol: str,
        product_type: str,
        granularity: str,
        limit: int,
    ):

        return self._get(
            "/api/v2/mix/market/candles",
            {
                "symbol":
                    symbol,

                "productType":
                    product_type,

                "granularity":
                    granularity,

                "limit":
                    str(limit),
            },
        )

    # -------------------------------------------------
    # DERIVATIVES PARTICIPATION
    # -------------------------------------------------

    def open_interest(
        self,
        symbol: str,
        product_type: str,
    ):

        return self._get(
            "/api/v2/mix/market/open-interest",
            {
                "symbol":
                    symbol,

                "productType":
                    product_type,
            },
        )

    def current_funding(
        self,
        symbol: str,
        product_type: str,
    ):

        data = self._get(
            "/api/v2/mix/market/current-fund-rate",
            {
                "symbol":
                    symbol,

                "productType":
                    product_type,
            },
        )

        if not data:
            raise BitgetAPIError(
                "No funding data for "
                f"{symbol}"
            )

        return data[0]

    def funding_history(
        self,
        symbol: str,
        product_type: str,
        page_size: int = 30,
    ):

        return self._get(
            "/api/v2/mix/market/history-fund-rate",
            {
                "symbol":
                    symbol,

                "productType":
                    product_type,

                "pageSize":
                    str(page_size),

                "pageNo":
                    "1",
            },
        )

    # -------------------------------------------------
    # PRIVATE ACCOUNT (READ ONLY)
    # -------------------------------------------------

    def account_info_v3(
        self,
    ) -> dict[str, Any]:
        """Read Bitget API-key permission metadata. No trade permission required."""
        data = self._get(
            "/api/v3/account/info",
            {},
            private=True,
            retry_deterministic_4xx=False,
        )
        if not isinstance(data, dict):
            raise BitgetAPIError(
                "Bitget v3 account info returned invalid schema"
            )
        return data

    def account_settings_v3(
        self,
    ) -> dict[str, Any]:
        """Read Bitget v3 account mode/settings. No write or order capability."""
        data = self._get(
            "/api/v3/account/settings",
            {},
            private=True,
            retry_deterministic_4xx=False,
        )
        if not isinstance(data, dict):
            raise BitgetAPIError(
                "Bitget v3 account settings returned invalid schema"
            )
        return data

    def spot_account_info_v2(
        self,
    ) -> dict[str, Any]:
        """Read Classic-account identity/permission metadata via signed GET only."""
        data = self._get(
            "/api/v2/spot/account/info",
            {},
            private=True,
            retry_deterministic_4xx=False,
        )
        if not isinstance(data, dict):
            raise BitgetAPIError(
                "Bitget v2 spot account info returned invalid schema"
            )
        return data

    def futures_accounts(
        self,
        product_type: str,
    ):

        return self._get(
            "/api/v2/mix/account/accounts",
            {
                "productType":
                    product_type
            },
            private=True,
        ) or []

    def futures_positions(
        self,
        product_type: str,
        margin_coin: str = "USDT",
    ):

        return self._get(
            "/api/v2/mix/position/all-position",
            {
                "productType":
                    product_type,

                "marginCoin":
                    margin_coin,
            },
            private=True,
        ) or []
