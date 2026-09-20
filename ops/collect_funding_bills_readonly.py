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
from alpha_hunter.funding_bills import (
    ReadOnlyFundingBillClient,
    collect_funding_bills,
    persist_funding_bills,
)
from alpha_hunter.private_account import collect_private_account_snapshot
from alpha_hunter.storage import SupabaseConfig


def main() -> int:
    """Collect sanitized 90-day GET-only funding bill evidence."""

    load_env_file(ROOT / ".env", override=True)
    config = load_config(ROOT / "config.json")
    settings = SupabaseConfig.from_environment(config)
    checked_at = datetime.now(timezone.utc)

    result = {
        "checked_at_utc": checked_at.isoformat(),
        "credentials_configured": False,
        "supabase_configured": settings is not None,
        "account_status": None,
        "account_mode": None,
        "funding_status": "NOT_RUN",
        "complete": False,
        "schema_validated": False,
        "window_days": 90,
        "window_count": 3,
        "pages_fetched": 0,
        "funding_bill_count": 0,
        "funding_coin_distribution": {},
        "funding_symbol_count": 0,
        "funding_account_effect_sum": 0.0,
        "persist_attempted_run_rows": 0,
        "persist_attempted_bill_rows": 0,
        "persist_attempted_link_rows": 0,
        "read_only_get": True,
        "no_order_write_path": True,
        "raw_bill_ids_printed": False,
        "raw_order_ids_printed": False,
        "raw_trade_ids_printed": False,
        "full_economic_pnl_claimed": False,
        "realistic_net_r_claimed": False,
        "shadow_only": True,
        "trade_permission": False,
    }

    client = ReadOnlyFundingBillClient.from_environment(
        timeout=int(config.get("request_timeout_seconds", 12)),
        max_retries=1,
    )
    result["credentials_configured"] = bool(
        client.private_api_configured
    )

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

    funding = collect_funding_bills(
        client,
        product_type="usdt-futures",
        observed_at_utc=checked_at.isoformat(),
        private_account=private_account,
    )

    run = funding.run_row
    result.update(
        {
            "funding_status": run.get("status"),
            "complete": bool(run.get("complete")),
            "schema_validated": bool(
                run.get("schema_validated")
            ),
            "pages_fetched": int(
                run.get("pages_fetched") or 0
            ),
            "funding_bill_count": int(
                run.get("funding_bill_count") or 0
            ),
            "shadow_only": run.get("shadow_only") is True,
            "trade_permission": (
                run.get("trade_permission") is True
            ),
        }
    )

    coins: Counter[str] = Counter()
    symbols: set[str] = set()
    funding_effect = 0.0

    for row in funding.bill_rows:
        coin = str(row.get("coin") or "UNKNOWN").upper()
        coins[coin] += 1
        symbol = str(row.get("symbol") or "").upper().strip()
        if symbol:
            symbols.add(symbol)
        funding_effect += float(
            row.get("funding_account_effect") or 0.0
        )

    result["funding_coin_distribution"] = dict(
        sorted(coins.items())
    )
    result["funding_symbol_count"] = len(symbols)
    result["funding_account_effect_sum"] = funding_effect

    run_rows, bill_rows, link_rows = persist_funding_bills(
        settings,
        funding,
    )
    result["persist_attempted_run_rows"] = run_rows
    result["persist_attempted_bill_rows"] = bill_rows
    result["persist_attempted_link_rows"] = link_rows

    print(json.dumps(result, indent=2, sort_keys=True))

    if not result["read_only_get"] or not result["no_order_write_path"]:
        return 10
    if result["trade_permission"] or not result["shadow_only"]:
        return 11
    if not result["complete"] or not result["schema_validated"]:
        return 12
    if result["funding_status"] not in {
        "CONNECTED",
        "ZERO_FUNDING_BILLS",
    }:
        return 13
    if result["persist_attempted_bill_rows"] != result["funding_bill_count"]:
        return 14
    if result["persist_attempted_link_rows"] != result["funding_bill_count"]:
        return 15
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
