#!/usr/bin/env python3
"""Private-only PG17 nested-trigger timing instrumentation.

Run ONLY inside the existing isolated Codespace clone. Uses the existing
authentic schema/fixture preflight, rolls back every transaction, and refuses
to report timing if PostgreSQL function-statistics instrumentation is absent.

This is NOT a production benchmark and MUST NOT be run in public CI.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

BENCHMARK_PATH = Path(__file__).with_name("qa_authentic_pg17_rpc_latency_v01.py")
STAGES = {
    "alpha_hunter_capture_strategy_observations_v01": "symbol_to_strategy",
    "alpha_hunter_capture_shadow_decision_quote_v01": "observation_to_shadow_quote",
    "alpha_hunter_enqueue_strategy_24h_outcome_v01": "episode_to_24h_queue",
    "alpha_hunter_enrich_signal_feature_geometry_context_v01": "feature_enrichment",
    "alpha_hunter_create_paper_order_v01": "signal_to_paper_order",
}
STAT_SQL = """
SELECT coalesce(json_agg(json_build_object(
    'function', funcname,
    'calls', calls,
    'total_ms', total_time,
    'self_ms', self_time
) ORDER BY funcname), '[]'::json)::text
FROM pg_stat_user_functions
WHERE schemaname = 'private'
AND funcname IN (
  'alpha_hunter_capture_strategy_observations_v01',
  'alpha_hunter_capture_shadow_decision_quote_v01',
  'alpha_hunter_enqueue_strategy_24h_outcome_v01',
  'alpha_hunter_enrich_signal_feature_geometry_context_v01',
  'alpha_hunter_create_paper_order_v01'
);
"""


def parse_stats(raw: str) -> dict[str, tuple[int, float, float]]:
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise ValueError("Function statistics are not a JSON array")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid function statistics row")
        name = row.get("function")
        calls, total, own = row.get("calls"), row.get("total_ms"), row.get("self_ms")
        if name not in STAGES or name in result or type(calls) is not int or calls < 0:
            raise ValueError("Unexpected function or invalid call count")
        if type(total) not in (int, float) or type(own) not in (int, float):
            raise ValueError("Invalid function timing")
        if not (0 <= own <= total):
            raise ValueError("Invalid inclusive/exclusive timing")
        result[name] = (calls, float(total), float(own))
    return result


def delta(before: dict, after: dict) -> list[dict]:
    rows = []
    for name, stage in STAGES.items():
        if name not in after:
            raise ValueError("Missing expected function statistics: " + stage)
        b, a = before.get(name, (0, 0.0, 0.0)), after[name]
        dc, dt, ds = (a[i] - b[i] for i in range(3))
        if dc <= 0 or dt < 0 or ds < 0:
            raise ValueError("No trustworthy positive function-statistics delta: " + stage)
        rows.append({
            "stage": stage,
            "calls": dc,
            "inclusive_ms": round(dt, 2),
            "self_ms": round(ds, 2),
            "mean_self_ms_per_call": round(ds / dc, 3),
        })
    return rows


def main() -> int:
    spec = importlib.util.spec_from_file_location("private_qa", BENCHMARK_PATH)
    if spec is None or spec.loader is None:
        print("BLOCKED: private QA benchmark unavailable")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        mode = module.ensure_offline_clone()
        if module.psql("SHOW track_functions;").strip() != "all":
            raise module.QABlocked("Isolated PostgreSQL track_functions=all required")
        if module.psql("SELECT current_setting('pg_stat_statements.track',true);").strip() not in ("top", "all"):
            raise module.QABlocked("PostgreSQL statistics configuration unavailable")
        base = Path.home() / ".alpha-hunter-private-dbqa"
        folder = base / "bench-fixtures"
        if base.is_symlink() or not base.is_dir() or base.stat().st_mode & 0o777 != 0o700:
            raise module.QABlocked("Private fixture base missing or unsafe")
        if folder.is_symlink() or not folder.is_dir() or folder.stat().st_mode & 0o777 != 0o700:
            raise module.QABlocked("Private fixture folder missing or unsafe")
        for size in module.SIZES:
            path = folder / f"{size}.json"
            module.require_private_file(path, 0o600)
            fixture = module.validate_fixture(json.loads(path.read_text(encoding="utf-8")), size)
            before = parse_stats(module.psql(STAT_SQL))
            # Existing runner enforces pre/post rollback cleanliness, complete
            # nested coverage, and 20 measured RPC trials after two warmups.
            rpc = module.benchmark_one(fixture)
            # pg_stat_force_next_flush affects this connection only; if stats
            # have not become visible, delta() fails closed, never invents data.
            after = parse_stats(module.psql(STAT_SQL))
            stages = delta(before, after)
            print(json.dumps({
                "mode": "PRIVATE_OFFLINE_ONLY_NOT_CERTIFIED",
                "symbols": size,
                "index_mode": mode,
                "rpc": rpc,
                "function_statistics": stages,
                "limitations": [
                    "aggregated across warmups and trials, not per-stage p95/p99",
                    "function self_time excludes nested function time, not SQL time",
                    "requires no concurrent background writers in private clone",
                    "not a concurrent-workload benchmark or independent sign-off",
                ],
            }, sort_keys=True))
        return 0
    except (module.QABlocked, ValueError, OSError, RuntimeError) as exc:
        print("BLOCKED: " + (str(exc) if isinstance(exc, (module.QABlocked, ValueError)) else "private QA unavailable"))
        print("NO PRODUCTION FALLBACK; NO AUTHENTIC MEASUREMENT CLAIM")
        return 2


if __name__ == "__main__":
    sys.exit(main())
