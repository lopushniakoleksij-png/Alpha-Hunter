#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import requests


EXPECTED_R8_FINGERPRINT = (
    "176b271ab6fe8b1905bfeb5118be77b6183cad6311925795cd912a7b055b99d1"
)
ACTIVATION_ID = "PAPER_EXECUTION_R8"
OPEN_VIEW = "alpha_hunter_paper_reconciliation_open_v08"
DECISION_TABLE = "alpha_hunter_paper_decisions_v01"
SHADOW_TABLE = "alpha_hunter_r8_depth_shadow_v01"
BITGET_DEPTH_URL = "https://api.bitget.com/api/v2/mix/market/merge-depth"
PRODUCT_TYPE = "usdt-futures"
MODEL_VERSION = "r8-depth-shadow-v0.1"


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def _parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _rest_get(
    base_url: str,
    key: str,
    table: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{base_url.rstrip('/')}/rest/v1/{table}",
        params=params,
        headers=_headers(key),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or any(
        not isinstance(row, dict) for row in payload
    ):
        raise RuntimeError(f"Unexpected Supabase payload for {table}")
    return payload


def _rest_insert(
    base_url: str,
    key: str,
    table: str,
    row: dict[str, Any],
) -> None:
    headers = _headers(key)
    headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
    response = requests.post(
        f"{base_url.rstrip('/')}/rest/v1/{table}",
        json=row,
        headers=headers,
        timeout=20,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            f"Supabase shadow insert failed: HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )


def _fetch_depth(symbol: str) -> tuple[dict[str, Any], int | None]:
    response = requests.get(
        BITGET_DEPTH_URL,
        params={
            "symbol": symbol,
            "productType": PRODUCT_TYPE,
            "precision": "scale0",
            "limit": "max",
        },
        headers={"locale": "en-US"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("code") != "00000":
        raise RuntimeError(
            f"Bitget depth unavailable for {symbol}: "
            f"{str(payload)[:300]}"
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"Bitget depth returned invalid data for {symbol}")
    request_time = payload.get("requestTime")
    try:
        request_time_ms = int(request_time) if request_time is not None else None
    except (TypeError, ValueError):
        request_time_ms = None
    return data, request_time_ms


def _levels(
    raw: Any,
) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    if not isinstance(raw, list):
        return rows
    for level in raw:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            continue
        price = _optional_float(level[0])
        quantity = _optional_float(level[1])
        if (
            price is None
            or quantity is None
            or price <= 0
            or quantity <= 0
        ):
            continue
        rows.append((price, quantity))
    return rows


def _eligible_levels(
    direction: str,
    limit_price: float,
    asks: list[tuple[float, float]],
    bids: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if direction == "LONG":
        return sorted(
            [(price, qty) for price, qty in asks if price <= limit_price],
            key=lambda item: item[0],
        )
    return sorted(
        [(price, qty) for price, qty in bids if price >= limit_price],
        key=lambda item: item[0],
        reverse=True,
    )


def _vwap_for_quantity(
    levels: list[tuple[float, float]],
    required_quantity: float,
) -> float | None:
    if required_quantity <= 0:
        return None
    remaining = required_quantity
    notional = 0.0
    filled = 0.0
    for price, available in levels:
        take = min(available, remaining)
        if take <= 0:
            continue
        notional += price * take
        filled += take
        remaining -= take
        if remaining <= 1e-12:
            break
    if filled + 1e-12 < required_quantity:
        return None
    return notional / filled if filled > 0 else None


def classify_depth(
    *,
    order: dict[str, Any],
    depth: dict[str, Any],
    strategy_id: str | None,
    captured_at_utc: str,
    request_time_ms: int | None = None,
    expected_fingerprint: str = EXPECTED_R8_FINGERPRINT,
) -> dict[str, Any]:
    direction = str(order.get("direction") or "").upper()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("Direction must be LONG or SHORT")

    limit_price = _optional_float(order.get("limit_price"))
    remaining_quantity = _optional_float(order.get("remaining_quantity"))
    if limit_price is None or limit_price <= 0:
        raise ValueError("Limit price is invalid")
    if remaining_quantity is None or remaining_quantity <= 0:
        raise ValueError("Remaining quantity is invalid")

    asks = _levels(depth.get("asks"))
    bids = _levels(depth.get("bids"))
    if not asks or not bids:
        raise ValueError("Depth book is missing bids or asks")

    best_ask, best_ask_size = asks[0]
    best_bid, best_bid_size = bids[0]
    crossed = (
        best_ask <= limit_price
        if direction == "LONG"
        else best_bid >= limit_price
    )
    top_side_size = (
        best_ask_size if direction == "LONG" else best_bid_size
    )

    eligible = _eligible_levels(
        direction,
        limit_price,
        asks,
        bids,
    )
    eligible_quantity = sum(quantity for _, quantity in eligible)
    eligible_notional = sum(price * quantity for price, quantity in eligible)

    if not crossed:
        verdict = "NOT_CROSSED"
    elif top_side_size + 1e-12 >= remaining_quantity:
        verdict = "L1_SUFFICIENT"
    elif eligible_quantity + 1e-12 >= remaining_quantity:
        verdict = "DEPTH_SUFFICIENT_BUT_L1_INSUFFICIENT"
    else:
        verdict = "TRUE_INSUFFICIENT_DEPTH"

    vwap = (
        _vwap_for_quantity(eligible, remaining_quantity)
        if eligible_quantity + 1e-12 >= remaining_quantity
        else None
    )

    exchange_ts = depth.get("ts")
    try:
        exchange_timestamp_ms = (
            int(exchange_ts) if exchange_ts is not None else None
        )
    except (TypeError, ValueError):
        exchange_timestamp_ms = None

    capture_seed = "|".join(
        [
            MODEL_VERSION,
            str(order.get("order_id") or ""),
            captured_at_utc,
            str(exchange_timestamp_ms or ""),
        ]
    )
    capture_id = hashlib.sha256(
        capture_seed.encode("utf-8")
    ).hexdigest()[:32]

    return {
        "capture_id": capture_id,
        "captured_at_utc": captured_at_utc,
        "order_id": str(order.get("order_id") or ""),
        "decision_id": str(order.get("decision_id") or ""),
        "symbol": str(order.get("symbol") or "").upper(),
        "strategy_id": strategy_id,
        "direction": direction,
        "limit_price": limit_price,
        "remaining_quantity": remaining_quantity,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "top_side_size": top_side_size,
        "crossed_limit": crossed,
        "depth_source": "BITGET_PUBLIC_MERGE_DEPTH_MAX",
        "exchange_timestamp_ms": exchange_timestamp_ms,
        "depth_levels": [
            [price, quantity]
            for price, quantity in eligible
        ],
        "eligible_depth_quantity": eligible_quantity,
        "eligible_depth_notional": eligible_notional,
        "conservative_vwap": vwap,
        "required_to_l1_ratio": (
            remaining_quantity / top_side_size
            if top_side_size > 0
            else None
        ),
        "required_to_depth_ratio": (
            remaining_quantity / eligible_quantity
            if eligible_quantity > 0
            else None
        ),
        "diagnostic_verdict": verdict,
        "evidence": {
            "model_version": MODEL_VERSION,
            "expected_r8_fingerprint": expected_fingerprint,
            "bitget_request_time_ms": request_time_ms,
            "requested_depth_limit": "max",
            "requested_precision": "scale0",
            "returned_precision": depth.get("precision"),
            "returned_scale": depth.get("scale"),
            "is_max_precision": depth.get("isMaxPrecision"),
            "r8_fill_model_changed": False,
            "historical_outcome_reinterpreted": False,
            "profitability_sample_eligible": False,
            "exchange_order_request_added": False,
        },
        "shadow_only": True,
        "paper_only": True,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }


def _load_activation(
    base_url: str,
    key: str,
    expected_fingerprint: str,
) -> dict[str, Any]:
    rows = _rest_get(
        base_url,
        key,
        "alpha_hunter_paper_execution_integrity_activation_v08",
        {
            "select": (
                "activation_id,scientific_fingerprint_sha256,"
                "maximum_entry_age_minutes,paper_only,exchange_authority,"
                "trade_permission,production_promotion_permitted,order_path"
            ),
            "activation_id": f"eq.{ACTIVATION_ID}",
            "limit": "1",
        },
    )
    if not rows:
        raise RuntimeError("R8 paper execution activation is missing")
    activation = rows[0]
    if str(activation.get("scientific_fingerprint_sha256") or "") != (
        expected_fingerprint
    ):
        raise RuntimeError("R8 scientific fingerprint mismatch")
    if activation.get("paper_only") is not True:
        raise RuntimeError("R8 paper-only invariant failed")
    if activation.get("exchange_authority") is not False:
        raise RuntimeError("R8 exchange-authority invariant failed")
    if activation.get("trade_permission") is not False:
        raise RuntimeError("R8 trade-permission invariant failed")
    if activation.get("production_promotion_permitted") is not False:
        raise RuntimeError("R8 promotion invariant failed")
    if str(activation.get("order_path") or "") != "NONE":
        raise RuntimeError("R8 order-path invariant failed")
    return activation


def _load_open_limits(
    base_url: str,
    key: str,
) -> list[dict[str, Any]]:
    return _rest_get(
        base_url,
        key,
        OPEN_VIEW,
        {
            "select": (
                "order_id,decision_id,symbol,direction,order_type,limit_price,"
                "filled_quantity,remaining_quantity,submitted_at_utc"
            ),
            "order_type": "eq.LIMIT",
            "filled_quantity": "eq.0",
            "limit": "250",
        },
    )


def _load_strategy_id(
    base_url: str,
    key: str,
    decision_id: str,
) -> str | None:
    rows = _rest_get(
        base_url,
        key,
        DECISION_TABLE,
        {
            "select": "strategy_id",
            "decision_id": f"eq.{decision_id}",
            "limit": "1",
        },
    )
    if not rows:
        return None
    value = rows[0].get("strategy_id")
    return str(value) if value is not None else None


def main() -> int:
    base_url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    expected_fingerprint = os.getenv(
        "R8_EXPECTED_FINGERPRINT",
        EXPECTED_R8_FINGERPRINT,
    ).strip()

    result: dict[str, Any] = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "activation_verified": False,
        "open_limits_considered": 0,
        "active_limits_considered": 0,
        "crossed_l1_insufficient": 0,
        "captures_persisted": 0,
        "depth_failures": 0,
        "verdicts": {},
        "shadow_only": True,
        "paper_only": True,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }

    if not base_url or not key:
        result["error"] = "SUPABASE_EVIDENCE_CREDENTIALS_MISSING"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 3

    activation = _load_activation(
        base_url,
        key,
        expected_fingerprint,
    )
    result["activation_verified"] = True
    maximum_age_minutes = int(
        activation.get("maximum_entry_age_minutes") or 35
    )

    now = datetime.now(timezone.utc)
    orders = _load_open_limits(base_url, key)
    result["open_limits_considered"] = len(orders)

    verdict_counts: dict[str, int] = {}

    for order in orders:
        submitted = _parse_utc(order.get("submitted_at_utc"))
        if submitted is None:
            continue
        age_minutes = (now - submitted).total_seconds() / 60.0
        if age_minutes < 0 or age_minutes > maximum_age_minutes:
            continue

        result["active_limits_considered"] += 1
        symbol = str(order.get("symbol") or "").upper()
        decision_id = str(order.get("decision_id") or "")
        if not symbol or not decision_id:
            continue

        captured_at = datetime.now(timezone.utc).isoformat()

        try:
            depth, request_time_ms = _fetch_depth(symbol)
            strategy_id = _load_strategy_id(
                base_url,
                key,
                decision_id,
            )
            row = classify_depth(
                order=order,
                depth=depth,
                strategy_id=strategy_id,
                captured_at_utc=captured_at,
                request_time_ms=request_time_ms,
                expected_fingerprint=expected_fingerprint,
            )
        except Exception:
            result["depth_failures"] += 1
            continue

        verdict = str(row["diagnostic_verdict"])
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

        if verdict != "DEPTH_SUFFICIENT_BUT_L1_INSUFFICIENT" and (
            verdict != "TRUE_INSUFFICIENT_DEPTH"
        ):
            continue

        result["crossed_l1_insufficient"] += 1
        _rest_insert(base_url, key, SHADOW_TABLE, row)
        result["captures_persisted"] += 1

    result["verdicts"] = dict(sorted(verdict_counts.items()))
    print(json.dumps(result, indent=2, sort_keys=True))

    if result["trade_permission"] is not False:
        return 10
    if result["production_promotion_permitted"] is not False:
        return 11
    if result["order_path"] != "NONE":
        return 12
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
