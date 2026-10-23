#!/usr/bin/env python3
"""One-shot independent public quote probe for two historically managed symbols.

READ-ONLY research job run by GitHub Actions on an UNMERGED draft branch.
No private exchange or Supabase credentials; no source inventory, fills,
position management, live alert provider, cron, or trading authority.
The public quote's raw bytes are temporarily archived in GitHub Actions
for reproducible SHA-256 validation; not persistent independently signed
market data and NOT a per-position monitoring observation.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import secrets

from successor_public_https_capture_v01 import capture_public_quote

SYMBOLS = ("NIGHTUSDT", "SOONUSDT")
OUT = Path("p02-public-quote-ci-proof")


def main() -> None:
    if (
        os.getenv("GITHUB_ACTIONS") != "true" or
        os.getenv("AH_P02_SYMBOL_PROBE_APPROVAL") != "EPHEMERAL_CI_PUBLIC_GET_ONLY"
    ):
        raise RuntimeError("NOT_AUTHORIZED_OUTSIDE_ISOLATED_CI")
    forbidden = (
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL",
        "BITGET_API_KEY", "BITGET_SECRET_KEY", "BITGET_API_PASSPHRASE",
    )
    if any(os.getenv(n) for n in forbidden):
        raise RuntimeError("CREDENTIALS_ARE_PROHIBITED_FOR_PUBLIC_QUOTE_PROBE")

    OUT.mkdir(exist_ok=True)
    rows = []
    for symbol in SYMBOLS:
        run_id = "p02-independent-public-" + secrets.token_hex(8)
        try:
            capture, raw = capture_public_quote(
                run_id, include_raw_bytes=True, symbol=symbol
            )
            if not raw or len(raw) > 65536:
                raise ValueError("RAW_PUBLIC_RESPONSE_SIZE_INVALID")
            raw_hash = sha256(raw).hexdigest()
            if raw_hash != capture["response_sha256"]:
                raise ValueError("RAW_PUBLIC_RESPONSE_HASH_MISMATCH")
            file = "public-" + symbol.lower() + "-ticker.json"
            (OUT / file).write_bytes(raw)
            if sha256((OUT / file).read_bytes()).hexdigest() != raw_hash:
                raise ValueError("ARTIFACT_READBACK_HASH_MISMATCH")
            rows.append({
                "symbol": symbol, "status": "PUBLIC_HTTPS_TRANSPORT_CAPTURED_ONLY",
                "run_id": run_id, "raw_response_file": file,
                "raw_response_sha256": raw_hash,
                "quote_row_sha256": capture["raw_response_row_sha256"],
                "transport_manifest_sha256": capture["capture_manifest_sha256"],
                "exchange_timestamp_ms": capture["exchange_timestamp_ms"],
                "transport_captured_at_utc": capture["transport_captured_at_utc"],
                "request_id": capture["request_id"],
                "tls_host_checked": True, "venue_signed_price": False,
            })
        except (ValueError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            rows.append({
                "symbol": symbol, "status": "PUBLIC_QUOTE_UNKNOWN_FAIL_CLOSED",
                "failure_class": type(exc).__name__,
                "authenticated_public_quote": False,
            })

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "public Bitget USDT-FUTURES over checked HTTPS only",
        "reason": "independent one-shot research comparison with historical paper symbols",
        "quote_receipts": rows,
        "expected_public_symbols": list(SYMBOLS),
        "public_quote_captured_count": sum(
            r["status"] == "PUBLIC_HTTPS_TRANSPORT_CAPTURED_ONLY" for r in rows
        ),
        "operational_position_inventory_authenticated": False,
        "source_run_and_paper_position_bound": False,
        "independent_position_observation": False,
        "actual_durable_alert_delivered": False,
        "verified_recipient_delivery": False,
        "continuous_35_minute_monitoring": False,
        "permanent_independent_journal": False,
        "scientific_test_pass": False,
        "production_modified": False,
        "live_exchange_authority": False,
        "retention_limit_days": 30,
        "all_paths_paper_only": True,
    }
    (OUT / "selected-symbols-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("P02_SELECTED_PUBLIC_SYMBOL_QUOTE_PROBE " + json.dumps({
        "symbols_probed": len(SYMBOLS),
        "public_quotes_captured": manifest["public_quote_captured_count"],
        "all_success": manifest["public_quote_captured_count"] == len(SYMBOLS),
        "operational_source_authenticated": False,
        "verified_live_delivery": False, "production_modified": False,
    }, sort_keys=True))
    if manifest["public_quote_captured_count"] != len(SYMBOLS):
        raise RuntimeError("PUBLIC_SYMBOL_QUOTE_PROBE_INCOMPLETE_FAIL_CLOSED")


if __name__ == "__main__":
    main()
