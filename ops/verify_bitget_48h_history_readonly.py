from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha_hunter.env import load_env_file
from alpha_hunter.fill_client import ReadOnlyFillClient
from alpha_hunter.private_account import collect_private_account_snapshot


MAX_PAGES = 20
PAGE_LIMIT = 100
PRODUCT_TYPE = "usdt-futures"


def _collect_history(
    client: ReadOnlyFillClient,
    *,
    path: str,
    list_key: str,
    start_ms: int,
    end_ms: int,
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0

    for page_number in range(1, MAX_PAGES + 1):
        params: dict[str, Any] = {
            "productType": PRODUCT_TYPE,
            "startTime": str(start_ms),
            "endTime": str(end_ms),
            "limit": str(PAGE_LIMIT),
        }
        if cursor:
            params["idLessThan"] = cursor

        data = client._get(
            path,
            params,
            private=True,
            retry_deterministic_4xx=False,
        )
        if not isinstance(data, dict):
            raise RuntimeError(f"{path} returned non-object data")

        page = data.get(list_key)
        if not isinstance(page, list):
            raise RuntimeError(f"{path} returned invalid {list_key}")

        pages = page_number
        for raw in page:
            if isinstance(raw, dict):
                rows.append(raw)

        if not page or len(page) < PAGE_LIMIT:
            break

        next_cursor = str(data.get("endId") or "").strip()
        if not next_cursor or next_cursor == cursor:
            raise RuntimeError(f"{path} pagination stalled")
        cursor = next_cursor

    return rows, pages


def _millis_to_iso(value: Any) -> str | None:
    try:
        millis = int(str(value))
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(millis / 1000, timezone.utc).isoformat()


def main() -> int:
    load_env_file(ROOT / ".env", override=True)
    client = ReadOnlyFillClient.from_environment(timeout=12, max_retries=1)
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=48)

    report: dict[str, Any] = {
        "checked_at_utc": now.isoformat(),
        "window_start_utc": start.isoformat(),
        "window_end_utc": now.isoformat(),
        "credentials_configured": bool(client.private_api_configured),
        "account_status": None,
        "account_identity_probe_status": None,
        "account_identity_match": False,
        "account_identity_fingerprint": None,
        "fill_count": 0,
        "order_count": 0,
        "fills_by_symbol": {},
        "orders_by_symbol": {},
        "order_status_counts": {},
        "fill_pages": 0,
        "order_pages": 0,
        "latest_fill_at_utc": None,
        "latest_order_at_utc": None,
        "read_only_get": True,
        "no_order_write_path": True,
        "shadow_only": True,
        "trade_permission": False,
        "raw_order_ids_printed": False,
        "raw_trade_ids_printed": False,
        "secret_values_printed": False,
    }

    if not client.private_api_configured:
        report["account_status"] = "NOT_CONFIGURED"
        print(json.dumps(report, indent=2, sort_keys=True))
        return 3

    account = collect_private_account_snapshot(client, PRODUCT_TYPE, "USDT")
    report.update(
        {
            "account_status": account.get("status"),
            "account_identity_probe_status": account.get(
                "account_identity_probe_status"
            ),
            "account_identity_match": bool(account.get("account_identity_match")),
            "account_identity_fingerprint": account.get(
                "account_identity_fingerprint"
            ),
        }
    )

    if account.get("account_identity_probe_status") == "UNPINNED":
        print(json.dumps(report, indent=2, sort_keys=True))
        return 4
    if account.get("status") != "CONNECTED" or not account.get(
        "account_identity_match"
    ):
        print(json.dumps(report, indent=2, sort_keys=True))
        return 5

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    fills, fill_pages = _collect_history(
        client,
        path="/api/v2/mix/order/fills",
        list_key="fillList",
        start_ms=start_ms,
        end_ms=end_ms,
    )
    orders, order_pages = _collect_history(
        client,
        path="/api/v2/mix/order/orders-history",
        list_key="entrustedList",
        start_ms=start_ms,
        end_ms=end_ms,
    )

    fill_symbols = Counter(
        str(row.get("symbol") or "").upper()
        for row in fills
        if str(row.get("symbol") or "").strip()
    )
    order_symbols = Counter(
        str(row.get("symbol") or "").upper()
        for row in orders
        if str(row.get("symbol") or "").strip()
    )
    order_statuses = Counter(
        str(row.get("status") or "UNKNOWN").upper() for row in orders
    )

    fill_times = [
        value
        for value in (_millis_to_iso(row.get("cTime")) for row in fills)
        if value
    ]
    order_times = [
        value
        for value in (_millis_to_iso(row.get("cTime")) for row in orders)
        if value
    ]

    report.update(
        {
            "fill_count": len(fills),
            "order_count": len(orders),
            "fills_by_symbol": dict(sorted(fill_symbols.items())),
            "orders_by_symbol": dict(sorted(order_symbols.items())),
            "order_status_counts": dict(sorted(order_statuses.items())),
            "fill_pages": fill_pages,
            "order_pages": order_pages,
            "latest_fill_at_utc": max(fill_times, default=None),
            "latest_order_at_utc": max(order_times, default=None),
        }
    )

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
