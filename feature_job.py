from __future__ import annotations

import os
from pathlib import Path

import requests

from alpha_hunter.env import load_env_file
from alpha_hunter.feature_capture import FeatureStorage


def latest_snapshot(url: str, key: str, table: str) -> dict:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    response = requests.get(
        f"{url.rstrip('/')}/rest/v1/{table}",
        params={"select": "payload", "order": "collected_at_utc.desc", "limit": "1"},
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise SystemExit("No Alpha Hunter snapshot found")
    return rows[0].get("payload") or {}


def main() -> int:
    root = Path(__file__).resolve().parent
    load_env_file(root / ".env")

    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    table = os.getenv("ALPHA_HUNTER_SNAPSHOT_TABLE", "alpha_hunter_snapshots")

    if not url or not key:
        raise SystemExit("Supabase environment variables are not configured")

    saved = FeatureStorage(url, key).save(latest_snapshot(url, key, table))
    print(f"FEATURE ROWS SAVED: {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
