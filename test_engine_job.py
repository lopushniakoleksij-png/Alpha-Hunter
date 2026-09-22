from __future__ import annotations

from pathlib import Path

from alpha_hunter.collector import load_config
from alpha_hunter.storage import SupabaseConfig
from alpha_hunter.test_engine import RealtimeTestEngine, format_report


def main() -> int:
    root = Path(__file__).resolve().parent
    config = load_config(root / "config.json")
    settings = SupabaseConfig.from_environment(config)

    if settings is None:
        print("Test engine: FAILED Supabase is not configured")
        return 2

    engine = RealtimeTestEngine(settings)

    try:
        report = engine.evaluate()
        engine.persist(report)
    except Exception as exc:
        print(f"Test engine: FAILED {exc}")
        return 2

    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
