from __future__ import annotations

import os
from pathlib import Path

import requests

from alpha_hunter.env import load_env_file
from alpha_hunter.feature_capture import FeatureStorage


def headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def latest_signal_snapshot(url: str, key: str) -> dict:
    first = requests.get(
        f"{url}/rest/v1/alpha_hunter_signals",
        params={
            "select": "run_id,detected_at_utc",
            "order": "detected_at_utc.desc",
            "limit": "1",
        },
        headers=headers(key),
        timeout=20,
    )
    first.raise_for_status()
    latest = first.json()

    if not latest:
        raise RuntimeError("No Alpha Hunter signals found")

    run_id = str(latest[0]["run_id"])
    detected_at = latest[0]["detected_at_utc"]

    response = requests.get(
        f"{url}/rest/v1/alpha_hunter_signals",
        params={
            "select": (
                "signal_id,run_id,symbol,detected_at_utc,state,direction,"
                "trade_permission,huge_rr_score,confidence_estimate_pct,"
                "reward_risk,reference_price,payload"
            ),
            "run_id": f"eq.{run_id}",
            "order": "symbol.asc",
            "limit": "1000",
        },
        headers=headers(key),
        timeout=30,
    )
    response.raise_for_status()
    signals = response.json()

    symbols = []
    for signal in signals:
        payload = signal.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        row = dict(payload)
        row["symbol"] = signal.get("symbol")
        row["state"] = signal.get("state")
        row["trade_permission"] = bool(signal.get("trade_permission"))

        setup = row.get("execution_setup")
        if not isinstance(setup, dict):
            setup = {}
        setup.setdefault("direction", signal.get("direction"))
        setup.setdefault("rr", signal.get("reward_risk"))
        row["execution_setup"] = setup

        intelligence = row.get("intelligence")
        if not isinstance(intelligence, dict):
            intelligence = {}
        intelligence.setdefault("huge_rr_score", signal.get("huge_rr_score"))
        intelligence.setdefault(
            "confidence_estimate_pct",
            signal.get("confidence_estimate_pct"),
        )
        row["intelligence"] = intelligence

        symbols.append(row)

    return {
        "run_id": run_id,
        "collected_at_utc": detected_at,
        "symbols": symbols,
    }


def main() -> int:
    root = Path(__file__).resolve().parent
    load_env_file(root / ".env")

    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        raise SystemExit("Supabase environment variables are not configured")

    snapshot = latest_signal_snapshot(url, key)
    saved = FeatureStorage(url, key).save(snapshot)

    print(f"FEATURE ROWS SAVED: {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
