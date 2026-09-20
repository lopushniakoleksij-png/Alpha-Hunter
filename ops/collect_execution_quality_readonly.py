from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.execution_quality import (
    ReadOnlyExecutionQualityClient,
    load_pending_order_detail_fills,
    normalize_order_detail_evidence,
    persist_order_detail_failure,
    persist_order_detail_rows,
)
from alpha_hunter.storage import SupabaseConfig


def _redact_identity(message: str, raw_order_id: str) -> str:
    text = str(message)
    if raw_order_id:
        text = text.replace(raw_order_id, "<REDACTED_ORDER_ID>")
    return text


def main() -> int:
    """Collect sanitized GET-only order detail evidence for immutable fills."""

    load_env_file(ROOT / ".env", override=True)
    config = load_config(ROOT / "config.json")
    settings = SupabaseConfig.from_environment(config)

    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "credentials_configured": False,
        "supabase_configured": settings is not None,
        "fills_considered": 0,
        "order_details_connected": 0,
        "order_detail_failures": 0,
        "rows_persisted": 0,
        "limit_orders": 0,
        "market_orders": 0,
        "other_or_unknown_orders": 0,
        "explicit_limit_benchmarks": 0,
        "market_slippage_withheld": 0,
        "origin_consistent": 0,
        "origin_mismatch": 0,
        "origin_unknown": 0,
        "fill_origin_distribution": {},
        "order_origin_distribution": {},
        "read_only_get": True,
        "no_order_write_path": True,
        "raw_order_ids_printed": False,
        "raw_client_oids_printed": False,
        "slippage_model_validated": False,
        "cost_model_activated": False,
        "realistic_net_r_claimed": False,
        "shadow_only": True,
        "trade_permission": False,
    }

    if settings is None:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 3

    client = ReadOnlyExecutionQualityClient.from_environment(
        timeout=int(config.get("request_timeout_seconds", 12)),
        max_retries=1,
    )
    result["credentials_configured"] = bool(
        client.private_api_configured
    )

    if not client.private_api_configured:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 4

    fills = load_pending_order_detail_fills(settings)
    result["fills_considered"] = len(fills)

    fill_origins: Counter[str] = Counter()
    order_origins: Counter[str] = Counter()
    rows = []

    for fill in fills:
        fill_id = str(fill.get("fill_evidence_id") or "")
        symbol = str(fill.get("symbol") or "").upper().strip()
        order_id = str(fill.get("order_id") or "").strip()

        fill_source = str(
            fill.get("enter_point_source") or "UNKNOWN"
        ).upper()
        fill_origins[fill_source] += 1

        if not fill_id or not symbol or not order_id:
            result["order_detail_failures"] += 1
            try:
                persist_order_detail_failure(
                    settings,
                    fill_evidence_id=fill_id,
                    error_class="CANONICAL_FILL_IDENTITY_INCOMPLETE",
                    error_message=(
                        "Required fill/order identity fields are unavailable"
                    ),
                )
            except RuntimeError:
                pass
            continue

        try:
            detail = client.futures_order_detail(
                symbol=symbol,
                product_type="usdt-futures",
                order_id=order_id,
            )
            row = normalize_order_detail_evidence(
                fill,
                detail,
                observed_at_utc=datetime.now(
                    timezone.utc
                ).isoformat(),
            )
        except Exception as exc:
            result["order_detail_failures"] += 1
            try:
                persist_order_detail_failure(
                    settings,
                    fill_evidence_id=fill_id,
                    error_class=exc.__class__.__name__,
                    error_message=_redact_identity(
                        str(exc),
                        order_id,
                    ),
                )
            except RuntimeError:
                pass
            continue

        result["order_details_connected"] += 1

        order_type = str(row.get("order_type") or "")
        if order_type == "LIMIT":
            result["limit_orders"] += 1
        elif order_type == "MARKET":
            result["market_orders"] += 1
        else:
            result["other_or_unknown_orders"] += 1

        if row.get("limit_price_delta_claim_permitted") is True:
            result["explicit_limit_benchmarks"] += 1

        if row.get("benchmark_class") == (
            "MARKET_NO_VERIFIED_PRETRADE_BENCHMARK"
        ):
            result["market_slippage_withheld"] += 1

        consistency = row.get("origin_consistent")
        if consistency is True:
            result["origin_consistent"] += 1
        elif consistency is False:
            result["origin_mismatch"] += 1
        else:
            result["origin_unknown"] += 1

        order_source = str(
            row.get("order_enter_point_source") or "UNKNOWN"
        ).upper()
        order_origins[order_source] += 1

        rows.append(row)

    if rows:
        result["rows_persisted"] = persist_order_detail_rows(
            settings,
            rows,
        )

    result["fill_origin_distribution"] = dict(
        sorted(fill_origins.items())
    )
    result["order_origin_distribution"] = dict(
        sorted(order_origins.items())
    )

    print(json.dumps(result, indent=2, sort_keys=True))

    if result["trade_permission"] is not False:
        return 10
    if not result["read_only_get"] or not result["no_order_write_path"]:
        return 11
    if result["fills_considered"] == 0:
        return 0
    if result["order_detail_failures"] > 0:
        return 12
    if result["order_details_connected"] != result["fills_considered"]:
        return 13
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
