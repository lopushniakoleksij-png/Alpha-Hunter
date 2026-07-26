from __future__ import annotations

import argparse
from pathlib import Path

import requests

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Alpha Hunter Supabase connectivity")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    load_env_file(config_path.parent / args.env_file)
    config = load_config(config_path)
    settings = SupabaseConfig.from_environment(config)
    if settings is None:
        print("Supabase is not configured. Create .env from .env.example and add credentials.")
        return 2

    headers = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
    }
    response = requests.get(
        f"{settings.url}/rest/v1/{settings.snapshot_table}",
        params={"select": "run_id", "limit": "1"},
        headers=headers,
        timeout=settings.timeout_seconds,
    )
    if response.status_code != 200:
        print(f"Supabase check failed: HTTP {response.status_code}: {response.text[:500]}")
        return 1
    print(f"Supabase connection OK: {settings.snapshot_table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
