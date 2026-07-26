from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


class BitgetAPIError(RuntimeError):
    pass


@dataclass
class BitgetClient:
    base_url: str = "https://api.bitget.com"
    timeout: int = 12
    max_retries: int = 3

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(
                    f"{self.base_url}{path}", params=params, timeout=self.timeout
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") != "00000":
                    raise BitgetAPIError(
                        f"Bitget error {payload.get('code')}: {payload.get('msg')}"
                    )
                return payload.get("data")
            except (requests.RequestException, ValueError, BitgetAPIError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
        raise BitgetAPIError(f"Request failed after {self.max_retries} attempts: {last_error}")

    def contracts(self, product_type: str) -> list[dict[str, Any]]:
        return self._get("/api/v2/mix/market/contracts", {"productType": product_type})

    def ticker(self, symbol: str, product_type: str) -> dict[str, Any]:
        data = self._get(
            "/api/v2/mix/market/ticker",
            {"symbol": symbol, "productType": product_type},
        )
        if not data:
            raise BitgetAPIError(f"No ticker data for {symbol}")
        return data[0]

    def symbol_price(self, symbol: str, product_type: str) -> dict[str, Any]:
        data = self._get(
            "/api/v2/mix/market/symbol-price",
            {"symbol": symbol, "productType": product_type},
        )
        if not data:
            raise BitgetAPIError(f"No symbol-price data for {symbol}")
        return data[0]

    def candles(
        self, symbol: str, product_type: str, granularity: str, limit: int
    ) -> list[list[str]]:
        return self._get(
            "/api/v2/mix/market/candles",
            {
                "symbol": symbol,
                "productType": product_type,
                "granularity": granularity,
                "limit": str(limit),
            },
        )

    def open_interest(self, symbol: str, product_type: str) -> dict[str, Any]:
        return self._get(
            "/api/v2/mix/market/open-interest",
            {"symbol": symbol, "productType": product_type},
        )

    def current_funding(self, symbol: str, product_type: str) -> dict[str, Any]:
        data = self._get(
            "/api/v2/mix/market/current-fund-rate",
            {"symbol": symbol, "productType": product_type},
        )
        if not data:
            raise BitgetAPIError(f"No funding data for {symbol}")
        return data[0]
    def funding_history(self, symbol: str, product_type: str, page_size: int = 30) -> list[dict[str, Any]]:
        return self._get(
            "/api/v2/mix/market/history-fund-rate",
            {
                "symbol": symbol,
                "productType": product_type,
                "pageSize": str(page_size),
                "pageNo": "1",
            },
        )

