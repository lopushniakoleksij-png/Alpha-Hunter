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
from alpha_hunter.fill_client import ReadOnlyFillClient
from alpha_hunter.fill_ledger import (
    collect_fill_traceability,
    persist_fill_traceability,
)
from alpha_hunter.private_account import collect_private_account_snapshot
from alpha_hunter.storage import SupabaseConfig


WINDOW_HOURS = 2160  # 90 days, within Bitget Classic's documented 3-month max.


def _classify_trade_side(value: object) -> str:
    text = str(value or "").upper().strip()
    if "OPEN" in text:
        return "OPEN"
    if "CLOSE" in text:
        return "CLOSE"
    if text in {"BUY_SINGLE", "SELL_SINGLE"}:
        return "ONE_WAY_UNRESOLVED"
    return "OTHER"


def main() -> int:
    """Recover a sanitized 90-day canonical fill window for round-trip audit."""

    load_env_file(ROOT / ".env", override=True)
    config = load_config(ROOT / "config.json")
    settings = SupabaseConfig.from_environment(config)

    checked_at = datetime.now(timezone.utc)
    result = {
        "checked_at_utc": checked_at.isoformat(),
        "window_hours": WINDOW_HOURS,
        "window_days": WINDOW_HOURS // 24,
        "credentials_configured": False,
        "supabase_configured": settings is not None,
        "account_status": None,
        "account_mode": None,
        "fill_status": "NOT_RUN",
        "fill_count": 0,
        "pages_fetched": 0,
        "complete": False,
        "schema_validated": False,
        "oldest_fill_at_utc": None,
        "newest_fill_at_utc": None,
        "trade_side_distribution": {},
        "open_side_fill_count": 0,
        "close_side_fill_count": 0,
        "one_way_unresolved_fill_count": 0,
        "other_fill_count": 0,
        "persist_attempted_run_rows": 0,
        "persist_attempted_fill_rows": 0,
        "persist_attempted_link_rows": 0,
        "opening_side_recovery_status": "NOT_EVALUATED",
        "read_only_get": True,
        "no_order_write_path": True,
        "raw_trade_ids_printed": False,
        "raw_order_ids_printed": False,
        "shadow_only": True,
        "trade_permission": False,
    }

    client = ReadOnlyFillClient.from_environment(
        timeout=int(config.get("request_timeout_seconds", 12)),
        max_retries=1,
    )
    result["credentials_configured"] = bool(client.private_api_configured)

    if settings is None or not client.private_api_configured:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 3

    private_account = collect_private_account_snapshot(
        client,
        "usdt-futures",
        "USDT",
    )
    result["account_status"] = private_account.get("status")
    result["account_mode"] = private_account.get("account_mode")

    source_run_id = (
        "manual-roundtrip-fill-recovery-"
        + checked_at.strftime("%Y%m%dT%H%M%SZ")
    )

    fill_result = collect_fill_traceability(
        client,
        product_type="usdt-futures",
        source_run_id=source_run_id,
        observed_at_utc=checked_at.isoformat(),
        private_account=private_account,
        window_hours=WINDOW_HOURS,
    )

    row = fill_result.run_row
    result.update(
        {
            "fill_status": row.get("status"),
            "fill_count": int(row.get("fill_count") or 0),
            "pages_fetched": int(row.get("pages_fetched") or 0),
            "complete": bool(row.get("complete")),
            "schema_validated": bool(row.get("schema_validated")),
            "oldest_fill_at_utc": row.get("oldest_fill_at_utc"),
            "newest_fill_at_utc": row.get("newest_fill_at_utc"),
            "shadow_only": row.get("shadow_only") is True,
            "trade_permission": row.get("trade_permission") is True,
        }
    )

    counts: Counter[str] = Counter()
    for fill in fill_result.fill_rows:
        counts[_classify_trade_side(fill.get("trade_side"))] += 1

    result["trade_side_distribution"] = dict(sorted(counts.items()))
    result["open_side_fill_count"] = counts["OPEN"]
    result["close_side_fill_count"] = counts["CLOSE"]
    result["one_way_unresolved_fill_count"] = counts["ONE_WAY_UNRESOLVED"]
    result["other_fill_count"] = counts["OTHER"]
    result["opening_side_recovery_status"] = (
        "OPEN_SIDE_PRESENT"
        if counts["OPEN"] > 0
        else "OPEN_SIDE_NOT_RECOVERED_WITHIN_90_DAY_WINDOW"
    )

    if row.get("complete") is True and row.get("schema_validated") is True:
        run_rows, fill_rows, link_rows = persist_fill_traceability(
            settings,
            fill_result,
        )
        result["persist_attempted_run_rows"] = run_rows
        result["persist_attempted_fill_rows"] = fill_rows
        result["persist_attempted_link_rows"] = link_rows

    print(json.dumps(result, indent=2, sort_keys=True))

    if not result["read_only_get"] or not result["no_order_write_path"]:
        return 10
    if result["trade_permission"] or not result["shadow_only"]:
        return 11
    if not result["complete"] or not result["schema_validated"]:
        return 12
    if result["fill_status"] not in {"CONNECTED", "ZERO_FILLS"}:
        return 13
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
