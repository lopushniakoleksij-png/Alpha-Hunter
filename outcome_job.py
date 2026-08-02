from __future__ import annotations

from pathlib import Path

from alpha_hunter.bitget import BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.outcome_evaluator import OutcomeEvaluator
from alpha_hunter.storage import SupabaseConfig

HORIZONS = (1, 4, 12, 24)


def main() -> int:
    root = Path(__file__).resolve().parent
    load_env_file(root / ".env")
    config = load_config(root / "config.json")
    settings = SupabaseConfig.from_environment(config)
    if settings is None:
        raise SystemExit("Supabase is not configured")

    evaluator = OutcomeEvaluator(
        settings.url,
        settings.key,
        BitgetClient.from_environment(
            timeout=config.get("request_timeout_seconds", 12),
            max_retries=config.get("max_retries", 3),
        ),
        config["product_type"],
    )

    total_saved = 0
    total_failed = 0
    for horizon in HORIZONS:
        saved, failed = evaluator.evaluate_horizon(horizon)
        total_saved += saved
        total_failed += failed
        print(f"OUTCOMES {horizon}H: saved={saved} failed={failed}")

    print(f"OUTCOME EVALUATION COMPLETE: saved={total_saved} failed={total_failed}")
    return 0 if total_failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
