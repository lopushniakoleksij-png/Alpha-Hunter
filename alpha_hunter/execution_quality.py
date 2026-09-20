from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import requests

from .bitget import BitgetAPIError, BitgetClient
from .storage import SupabaseConfig


ORDER_DETAIL_ENDPOINT = "/api/v2/mix/order/detail"
ORDER_EVIDENCE_TABLE = "alpha_hunter_execution_order_evidence_v01"
ORDER_FAILURE_TABLE = "alpha_hunter_execution_order_failures_v01"
MODEL_VERSION = "execution-quality-order-v0.1"


def _optional_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_from_ms(value: Any) -> str | None:
    try:
        milliseconds = int(str(value))
    except (TypeError, ValueError):
        return None
    if milliseconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(
            milliseconds / 1000.0,
            tz=timezone.utc,
        ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _origin_class(value: Any) -> str:
    source = str(value or "").upper().strip()
    if source == "API":
        return "API_ORIGIN_UNVERIFIED"
    if source in {"IOS", "ANDROID", "WEB", "APP", "MOBILE"}:
        return "HUMAN_UI_EXTERNAL"
    if source:
        return "NON_API_EXTERNAL"
    return "UNKNOWN_ORIGIN"


def _adverse_delta_bps(
    side: str,
    actual_price: float | None,
    benchmark_price: float | None,
) -> float | None:
    if (
        actual_price is None
        or benchmark_price is None
        or actual_price <= 0
        or benchmark_price <= 0
    ):
        return None

    normalized_side = side.upper().strip()
    if normalized_side == "BUY":
        return (
            (actual_price - benchmark_price)
            / benchmark_price
            * 10000.0
        )
    if normalized_side == "SELL":
        return (
            (benchmark_price - actual_price)
            / benchmark_price
            * 10000.0
        )
    return None


class ReadOnlyExecutionQualityClient(BitgetClient):
    """GET-only Bitget execution-evidence client.

    No method in this client places, amends, cancels, transfers, withdraws,
    or changes leverage. Order detail is used only to recover evidence for an
    already-observed immutable fill.
    """

    def futures_order_detail(
        self,
        *,
        symbol: str,
        product_type: str,
        order_id: str,
    ) -> dict[str, Any]:
        data = self._get(
            ORDER_DETAIL_ENDPOINT,
            {
                "symbol": symbol,
                "productType": product_type,
                "orderId": order_id,
            },
            private=True,
            retry_deterministic_4xx=False,
        )
        if not isinstance(data, dict):
            raise BitgetAPIError(
                "Bitget order detail returned invalid schema"
            )
        return data


def normalize_order_detail_evidence(
    fill: dict[str, Any],
    detail: dict[str, Any],
    *,
    observed_at_utc: str,
) -> dict[str, Any]:
    fill_evidence_id = str(fill.get("fill_evidence_id") or "").strip()
    raw_order_id = str(fill.get("order_id") or "").strip()
    symbol = str(fill.get("symbol") or "").upper().strip()
    side = str(fill.get("side") or "").upper().strip()
    fill_price = _optional_float(fill.get("price"))
    fill_time_utc = str(fill.get("fill_time_utc") or "").strip()

    if not fill_evidence_id:
        raise ValueError("fill_evidence_id is required")
    if not raw_order_id:
        raise ValueError("order_id is required for private detail lookup")
    if not symbol:
        raise ValueError("symbol is required")
    if side not in {"BUY", "SELL"}:
        raise ValueError("fill side must be BUY or SELL")
    if fill_price is None or fill_price <= 0:
        raise ValueError("fill price must be positive")
    if not fill_time_utc:
        raise ValueError("fill_time_utc is required")

    order_type = str(detail.get("orderType") or "").lower().strip() or None
    order_price = _optional_float(detail.get("price"))
    order_avg_price = _optional_float(detail.get("priceAvg"))
    order_source = str(detail.get("orderSource") or "").strip() or None
    order_enter_source = (
        str(detail.get("enterPointSource") or "").strip()
        or None
    )
    fill_enter_source = (
        str(fill.get("enter_point_source") or "").strip()
        or None
    )

    if (
        order_enter_source is not None
        and fill_enter_source is not None
    ):
        origin_consistent: bool | None = (
            order_enter_source.upper()
            == fill_enter_source.upper()
        )
    else:
        origin_consistent = None

    if order_type == "limit":
        if order_price is not None and order_price > 0:
            benchmark_class = "LIMIT_ORDER_PRICE"
            fill_delta = _adverse_delta_bps(
                side,
                fill_price,
                order_price,
            )
            avg_delta = _adverse_delta_bps(
                side,
                order_avg_price,
                order_price,
            )
            limit_delta_permitted = fill_delta is not None
        else:
            benchmark_class = "LIMIT_PRICE_UNAVAILABLE"
            fill_delta = None
            avg_delta = None
            limit_delta_permitted = False
    elif order_type == "market":
        benchmark_class = (
            "MARKET_NO_VERIFIED_PRETRADE_BENCHMARK"
        )
        fill_delta = None
        avg_delta = None
        limit_delta_permitted = False
    else:
        benchmark_class = "ORDER_TYPE_UNKNOWN"
        fill_delta = None
        avg_delta = None
        limit_delta_permitted = False

    client_oid = str(detail.get("clientOid") or "").strip()
    detail_order_id = str(detail.get("orderId") or "").strip()
    identity_material = detail_order_id or raw_order_id

    return {
        "order_evidence_id": _sha256_text(
            f"{MODEL_VERSION}|{fill_evidence_id}"
        )[:32],
        "fill_evidence_id": fill_evidence_id,
        "observed_at_utc": observed_at_utc,
        "fill_time_utc": fill_time_utc,
        "symbol": symbol,
        "fill_side": side,
        "fill_price": fill_price,
        "fill_origin_class": _origin_class(
            fill.get("enter_point_source")
        ),
        "order_enter_point_source": order_enter_source,
        "origin_consistent": origin_consistent,
        "order_type": (
            order_type.upper() if order_type else None
        ),
        "order_state": (
            str(detail.get("state") or "").upper().strip()
            or None
        ),
        "order_force": (
            str(detail.get("force") or "").upper().strip()
            or None
        ),
        "order_source": (
            order_source.upper() if order_source else None
        ),
        "order_trade_side": (
            str(detail.get("tradeSide") or "").upper().strip()
            or None
        ),
        "reduce_only": (
            str(detail.get("reduceOnly") or "").upper().strip()
            or None
        ),
        "order_price": order_price,
        "order_average_price": order_avg_price,
        "order_created_at_utc": _iso_from_ms(detail.get("cTime")),
        "order_updated_at_utc": _iso_from_ms(detail.get("uTime")),
        "client_oid_present": bool(client_oid),
        "client_oid_sha256": (
            _sha256_text(client_oid)
            if client_oid
            else None
        ),
        "order_identity_sha256": _sha256_text(
            identity_material
        ),
        "benchmark_class": benchmark_class,
        "fill_vs_limit_delta_bps": fill_delta,
        "order_average_vs_limit_delta_bps": avg_delta,
        "limit_price_delta_claim_permitted": (
            limit_delta_permitted
        ),
        "source_endpoint": ORDER_DETAIL_ENDPOINT,
        "read_only_get": True,
        "raw_order_id_persisted_here": False,
        "raw_client_oid_persisted_here": False,
        "scientific_role": (
            "DESCRIPTIVE_ORDER_EXECUTION_EVIDENCE"
        ),
        "slippage_claim_permitted": False,
        "alpha_hunter_execution_claim_permitted": False,
        "cost_model_activation_permitted": False,
        "realistic_net_r_claim_permitted": False,
        "evidence": {
            "fill_source": "CANONICAL_IMMUTABLE_FILL_LEDGER",
            "private_endpoint_is_get_only": True,
            "limit_delta_positive_means_adverse": True,
            "market_slippage_withheld_without_pretrade_benchmark": True,
            "order_detail_origin_crosscheck_available": (
                origin_consistent is not None
            ),
            "raw_order_or_client_ids_duplicated": False,
        },
        "model_version": MODEL_VERSION,
        "shadow_only": True,
        "trade_permission": False,
    }


def _headers(settings: SupabaseConfig) -> dict[str, str]:
    return {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
    }


def load_pending_order_detail_fills(
    settings: SupabaseConfig,
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{settings.url}/rest/v1/alpha_hunter_fill_evidence",
        params={
            "select": (
                "fill_evidence_id,order_id,symbol,side,price,"
                "fill_time_utc,enter_point_source"
            ),
            "order": "fill_time_utc.asc",
            "limit": str(limit),
        },
        headers=_headers(settings),
        timeout=settings.timeout_seconds,
    )
    if response.status_code != 200:
        raise RuntimeError(
            "Unable to load canonical fills for order audit: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    fills = response.json()
    if not isinstance(fills, list):
        raise RuntimeError(
            "Canonical fill query returned invalid schema"
        )

    existing_response = requests.get(
        f"{settings.url}/rest/v1/{ORDER_EVIDENCE_TABLE}",
        params={
            "select": "fill_evidence_id",
            "limit": str(limit),
        },
        headers=_headers(settings),
        timeout=settings.timeout_seconds,
    )
    if existing_response.status_code != 200:
        raise RuntimeError(
            "Unable to load existing order audit evidence: "
            f"HTTP {existing_response.status_code}: "
            f"{existing_response.text[:500]}"
        )

    existing_payload = existing_response.json()
    if not isinstance(existing_payload, list):
        raise RuntimeError(
            "Order evidence query returned invalid schema"
        )

    existing_ids = {
        str(row.get("fill_evidence_id") or "")
        for row in existing_payload
        if isinstance(row, dict)
    }

    return [
        row
        for row in fills
        if isinstance(row, dict)
        and str(row.get("fill_evidence_id") or "")
        not in existing_ids
    ]


def persist_order_detail_rows(
    settings: SupabaseConfig,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    headers = _headers(settings)
    headers["Prefer"] = (
        "resolution=ignore-duplicates,return=minimal"
    )
    response = requests.post(
        f"{settings.url}/rest/v1/{ORDER_EVIDENCE_TABLE}",
        params={"on_conflict": "fill_evidence_id"},
        headers=headers,
        data=json.dumps(rows, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            "Order evidence persistence failed: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )
    return len(rows)


def persist_order_detail_failure(
    settings: SupabaseConfig,
    *,
    fill_evidence_id: str,
    error_class: str,
    error_message: str,
) -> None:
    row = {
        "failure_id": _sha256_text(
            f"{MODEL_VERSION}|{fill_evidence_id}|"
            f"{datetime.now(timezone.utc).isoformat()}"
        )[:32],
        "fill_evidence_id": fill_evidence_id or None,
        "error_class": error_class,
        "error_message": error_message[:1000],
        "source_endpoint": ORDER_DETAIL_ENDPOINT,
        "read_only_get": True,
        "raw_order_id_printed": False,
        "model_version": MODEL_VERSION,
        "shadow_only": True,
        "trade_permission": False,
    }
    response = requests.post(
        f"{settings.url}/rest/v1/{ORDER_FAILURE_TABLE}",
        headers=_headers(settings),
        data=json.dumps(row, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            "Order audit failure persistence failed: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )
