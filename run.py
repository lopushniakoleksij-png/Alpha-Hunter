from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from alpha_hunter.collector import load_config, main
from alpha_hunter.storage import SupabaseConfig
from alpha_hunter.universe_ledger import (
    build_rows_from_existing_scan,
    capture_existing_universe_calls,
    persist_rows,
)


def run() -> int:
    """Run the canonical scanner once, then persist its already-fetched universe evidence."""
    with capture_existing_universe_calls() as captured:
        code = main()

    if code != 0:
        return code

    root = Path(__file__).resolve().parent
    config = load_config(root / "config.json")
    settings = SupabaseConfig.from_environment(config)
    if settings is None or not config.get("supabase", {}).get("enabled", False):
        return code

    required = ("contracts", "instruments", "tickers")
    missing = [name for name in required if not captured.get(name)]
    if missing:
        print("Universe ledger: FAILED missing existing scanner payload: " + ",".join(missing))
        return 2

    latest_path = root / config["snapshot_directory"] / "latest.json"
    try:
        snapshot = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Universe ledger: FAILED unable to bind scanner snapshot: {exc}")
        return 2

    run_id = str(snapshot.get("run_id") or "")
    collected_at = str(snapshot.get("collected_at_utc") or "")
    if not run_id or not collected_at:
        print("Universe ledger: FAILED scanner snapshot lacks immutable run identity")
        return 2

    selected_symbols = {
        str(symbol).upper()
        for symbol in snapshot.get("universe", {}).get("selected_symbols", [])
        if symbol
    }
    try:
        observed_at = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        rows = build_rows_from_existing_scan(
            contracts=captured["contracts"],
            instruments=captured["instruments"],
            tickers=captured["tickers"],
            selected_symbols=selected_symbols,
            selection_snapshot_at_utc=collected_at,
            selection_run_id=run_id,
            product_type=str(config.get("product_type", "usdt-futures")),
            config=config,
            observed_at=observed_at,
        )
        attempted = persist_rows(settings, rows)
    except Exception as exc:
        print(f"Universe ledger: FAILED {exc}")
        return 2

    print(f"Universe ledger: SAVED_OR_ALREADY_PRESENT {attempted} rows from canonical scanner payload")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
