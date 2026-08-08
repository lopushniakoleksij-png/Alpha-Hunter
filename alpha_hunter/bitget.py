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
            api_key=os.getenv("BITGET_API_KEY"),
            secret_key=os.getenv("BITGET_SECRET_KEY"),
            passphrase=os.getenv("BITGET_API_PASSPHRASE"),
            **kwargs,
        )

    @property
    def private_api_configured(self) -> bool:
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
                    if not self.private_api_configured:
                        raise BitgetAPIError(
                            "Bitget private API credentials "
                            "are not configured"
                        )

                    ts = str(
                        int(
                            time.time() * 1000
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

                    sign = base64.b64encode(
                        hmac.new(
                            self.secret_key.encode(),
                            prehash.encode(),
                            hashlib.sha256,
                        ).digest()
                    ).decode()

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

                response = requests.request(
                    method.upper(),
                    self.base_url + path,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )

                response.raise_for_status()

                payload = response.json()

                if payload.get("code") != "00000":
                    raise BitgetAPIError(
                        "Bitget error "
                        f"{payload.get('code')}: "
                        f"{payload.get('msg')}"
                    )

                return payload.get("data")

            except (
                requests.RequestException,
                ValueError,
                BitgetAPIError,
            ) as exc:

                last_error = exc

                if attempt < self.max_retries:
                    time.sleep(
                        0.5
                        * (
                            2
                            ** (
                                attempt - 1
                            )
                        )
                    )

        raise BitgetAPIError(
            "Request failed after "
            f"{self.max_retries} attempts: "
            f"{last_error}"
        )

    def _get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        private: bool = False,
    ) -> Any:
        return self._request(
            "GET",
            path,
            params,
            private=private,
        )

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
        )

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
                f"No ticker data for {symbol}"
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
                f"No funding data for {symbol}"
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
