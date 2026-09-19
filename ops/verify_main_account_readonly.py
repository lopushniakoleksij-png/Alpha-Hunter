from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha_hunter.env import load_env_file
from alpha_hunter.fill_client import ReadOnlyFillClient
from alpha_hunter.fill_ledger import (
    MODEL_VERSION,
    collect_fill_traceability_with_historical_diagnostic,
)
from alpha_hunter.private_account import collect_private_account_snapshot


def main() -> int:
    """Verify the Mac credential cutover without printing secrets or trading IDs."""
    load_env_file(ROOT / ".env", override=True)

    client = ReadOnlyFillClient.from_environment(timeout=12, max_retries=1)
    checked_at = datetime.now(timezone.utc)

    result = {
        "checked_at_utc": checked_at.isoformat(),
        "credentials_configured": bool(client.private_api_configured),
        "fill_model_version": MODEL_VERSION,
        "account_status": None,
        "account_mode": None,
        "account_source": None,
        "api_permission_probe_status": None,
        "api_permission_type": None,
        "api_permissions": [],
        "fill_status": "NOT_RUN",
        "fill_count": 0,
        "pages_fetched": 0,
        "complete": False,
        "schema_validated": False,
        "historical_diagnostic_used": False,
        "historical_diagnostic_window_hours": None,
        "read_only_get": True,
        "no_order_write_path": True,
        "shadow_only": True,
        "trade_permission": False,
        "secret_values_printed": False,
        "raw_trade_or_order_ids_printed": False,
    }

    if not client.private_api_configured:
        result["fill_status"] = "NOT_CONFIGURED"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 3

    private_account = collect_private_account_snapshot(
        client,
        "usdt-futures",
        "USDT",
    )
    result.update(
        {
            "account_status": private_account.get("status"),
            "account_mode": private_account.get("account_mode"),
            "account_source": private_account.get("account_source"),
            "api_permission_probe_status": private_account.get(
                "api_permission_probe_status"
            ),
            "api_permission_type": private_account.get("api_permission_type"),
            "api_permissions": private_account.get("api_permissions") or [],
        }
    )

    fill_result = collect_fill_traceability_with_historical_diagnostic(
        client,
        product_type="usdt-futures",
        source_run_id="manual-main-account-readonly-cutover-check",
        observed_at_utc=checked_at.isoformat(),
        private_account=private_account,
    )

    row = fill_result.run_row
    evidence = row.get("evidence") or {}
    result.update(
        {
            "fill_status": row.get("status"),
            "fill_count": int(row.get("fill_count") or 0),
            "pages_fetched": int(row.get("pages_fetched") or 0),
            "complete": bool(row.get("complete")),
            "schema_validated": bool(row.get("schema_validated")),
            "historical_diagnostic_used": bool(
                evidence.get("historical_diagnostic_used")
            ),
            "historical_diagnostic_window_hours": evidence.get(
                "historical_diagnostic_window_hours"
            ),
            "read_only_get": evidence.get("read_only_get") is True,
            "no_order_write_path": evidence.get("no_order_write_path") is True,
            "shadow_only": row.get("shadow_only") is True,
            "trade_permission": row.get("trade_permission") is True,
        }
    )

    print(json.dumps(result, indent=2, sort_keys=True))

    if not result["read_only_get"] or not result["no_order_write_path"]:
        return 10
    if result["trade_permission"] or not result["shadow_only"]:
        return 11
    if not result["complete"] or not result["schema_validated"]:
        return 12
    if result["fill_status"] == "CONNECTED" and result["fill_count"] > 0:
        return 0
    if result["fill_status"] == "ZERO_FILLS":
        return 2
    return 13


if __name__ == "__main__":
    raise SystemExit(main())
