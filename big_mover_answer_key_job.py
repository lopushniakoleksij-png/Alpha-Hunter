from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from alpha_hunter.big_mover_answer_key import build_answer_key_rows
from alpha_hunter.bitget import BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file


ROOT = Path(__file__).resolve().parent
TABLE = "alpha_hunter_big_mover_answer_key"


def _headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }


def save_rows(url: str, key: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    response = requests.post(
        f"{url.rstrip('/')}/rest/v1/{TABLE}",
        params={"on_conflict": "event_id"},
        headers=_headers(key),
        json=rows,
        timeout=30,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            "Big-mover answer-key persistence failed: "
            f"HTTP {response.status_code}: {response.text[:800]}"
        )
    return len(rows)


def main() -> int:
    load_env_file(ROOT / ".env")
    config = load_config(ROOT / "config.json")
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise SystemExit("Supabase service-role environment is not configured")

    product_type = str(config.get("product_type", "usdt-futures"))
    client = BitgetClient.from_environment(
        timeout=int(config.get("request_timeout_seconds", 12)),
        max_retries=int(config.get("max_retries", 3)),
    )
    observed_at = datetime.now(timezone.utc)
    contracts = client.contracts(product_type) or []
    instruments = client.instruments(product_type) or []
    tickers = client.tickers(product_type) or []

    rows, summary = build_answer_key_rows(
        contracts=contracts,
        instruments=instruments,
        tickers=tickers,
        product_type=product_type,
        config=config,
        observed_at=observed_at,
    )
    summary["persisted_rows"] = save_rows(url, key, rows)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
