from __future__ import annotations

from typing import Any

from .bitget import BitgetClient


class ReadOnlyFillClient(BitgetClient):
    """Bitget client extension exposing only the documented GET fill-history route."""

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

        data = self._get(
            "/api/v2/mix/order/fills",
            params,
            private=True,
        )
        return data if isinstance(data, dict) else {}
