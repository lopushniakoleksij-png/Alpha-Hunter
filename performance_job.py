from __future__ import annotations

import os
from pathlib import Path

from alpha_hunter.env import load_env_file
from alpha_hunter.performance import PerformanceStorage
from alpha_hunter.storage import SupabaseConfig
from alpha_hunter.collector import load_config, load_previous_snapshot


def main() -> int:
    root = Path(__file__).resolve().parent
    load_env_file(root / ".env")
    config = load_config(root / "config.json")
    snapshot, snapshot_source = load_previous_snapshot(
        root / "config.json",
        config,
    )
    if not snapshot:
        raise SystemExit("No latest snapshot found")

    print(f"PERFORMANCE SNAPSHOT SOURCE: {snapshot_source}")

    settings = SupabaseConfig.from_environment(config)
    if settings is None:
        raise SystemExit("Supabase is not configured")

    count = PerformanceStorage(settings.url, settings.key).save_signals(snapshot)
    print(f"PERFORMANCE SIGNALS SAVED: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
