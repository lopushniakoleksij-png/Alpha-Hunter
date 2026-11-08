#!/usr/bin/env python3
"""Private-only latency measurement of the *authentic restored* PG17 trigger graph.

NOT a public CI benchmark, schema export, restore or release certification.
Only accepts synthetic core-RPC JSON fixtures from an owner-only local folder.
Writes nothing to production; each measured transaction rolls back in an
offline named Docker container. No SQL, identifiers or secrets leave the host.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

CONTAINER = "alpha-hunter-private-postgres17-qa"
DATABASE = "alpha_hunter_private_qa"
BRANCH = "fix/supabase-write-timeout-qa"
SIZES = (30, 50, 61)
FAMILIES = ("p_parent", "p_children", "p_signals", "p_features", "p_readiness")
REPEATS = 20
WARMUPS = 2


class QABlocked(RuntimeError):
    """Precondition failed; never proceed to a different database."""


def require_private_file(path: Path, mode: int) -> None:
    if path.is_symlink() or not path.is_file() and mode == 0o600:
        raise QABlocked("Private QA fixture file missing or symlinked")
    if not path.exists() or path.is_symlink() or (path.stat().st_mode & 0o777) != mode:
        raise QABlocked("Private QA path is missing or has unsafe permissions")


def validate_fixture(raw: object, size: int) -> dict:
    if not isinstance(raw, dict) or raw.get("synthetic_only") is not True:
        raise QABlocked("Explicit synthetic-only fixture marker missing")
    if any(not isinstance(raw.get(key), list) for key in FAMILIES):
        raise QABlocked("One or more required RPC arrays are missing")
    parents = raw["p_parent"]
    children = raw["p_children"]
    if len(parents) != 1 or not isinstance(parents[0], dict):
        raise QABlocked("Fixture must contain exactly one parent")
    parent = parents[0]
    run_id = parent.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"QA_ISOLATED_[A-Za-z0-9_-]{8,64}", run_id):
        raise QABlocked("Fixture uses a non-QA run ID")
    if len(children) != size or type(parent.get("symbol_count")) is not int or parent["symbol_count"] != size:
        raise QABlocked("Fixture symbol count does not match scenario")
    if any(not isinstance(row, dict) or row.get("run_id") != run_id
           for key in FAMILIES for row in raw[key]):
        raise QABlocked("Fixture has invalid or cross-run evidence")
    if any(row.get("trade_permission") is True
           for key in FAMILIES for row in raw[key]):
        raise QABlocked("QA fixtures must not authorize real trades")
    return {key: raw[key] for key in FAMILIES}


def statement_for_fixture(fixture: dict) -> str:
    # JSON values are SQL string literals, NEVER executable SQL or shell args.
    args = []
    for key in FAMILIES:
        value = json.dumps(fixture[key], separators=(",", ":"), ensure_ascii=True)
        args.append("'" + value.replace("'", "''") + "'::jsonb")
    return ("EXPLAIN (ANALYZE, BUFFERS, WAL, FORMAT JSON) "
            "SELECT public.alpha_hunter_commit_core_scan_v01("
            + ", ".join(args) + ");")


def psql(sql: str) -> str:
    command = [
        "docker", "exec", "-i", "-u", "postgres", CONTAINER,
        "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
        "-v", "VERBOSITY=terse", "-h", "/var/run/postgresql", "-d", DATABASE,
    ]
    result = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=35)
    if result.returncode:
        # Never print raw SQL, trigger contexts, payloads, or private identifiers.
        category = "statement_timeout" if "statement timeout" in result.stderr.lower() else "database_error"
        raise QABlocked(f"Offline QA RPC failed ({category}); private details withheld")
    return result.stdout.strip()


def ensure_offline_clone() -> str:
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise QABlocked("Existing Codespace only; never run in GitHub Actions")
    branch = subprocess.run(["git", "branch", "--show-current"],
                            capture_output=True, text=True, check=True).stdout.strip()
    if branch != BRANCH:
        raise QABlocked("Wrong Git branch; production baseline is protected")
    status = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}|{{.HostConfig.NetworkMode}}", CONTAINER],
        capture_output=True, text=True, timeout=8,
    )
    if status.returncode or status.stdout.strip() != "true|none":
        raise QABlocked("Network-isolated, already-running private PG17 clone not available")
    identity = psql("SELECT current_database() || '|' || current_user || '|' || current_setting('server_version_num');")
    if not re.fullmatch(r"alpha_hunter_private_qa\|postgres\|17[0-9]{4}", identity):
        raise QABlocked("Offline database name, role or PG17 server identity mismatched")
    # Immutable 8 November live baseline: real private function bodies, owner, ACL
    # and runtime settings must match before latency is measured.
    # This SQL returns only hashes/counts; never print raw private definitions.
    custody_sql = Path("ops/sql/readonly_p0_private_function_catalog_fingerprint_v01.sql").read_text(encoding="utf-8")
    custody = psql(custody_sql).splitlines()
    if "private|110|65|110|8fae5afad12f3040d30d0416cbfd9be1" not in custody:
        raise QABlocked("Private function custody fingerprint differs from inspected production")
    # A trigger count alone is not enough: verify every direct trigger's
    # definition and body digest, all 128 public application tables/columns,
    # all baseline indexes, and table grants/RLS. The only permitted
    # difference is the named candidate index, excluded from baseline hash.
    structural_sql = Path(
        "ops/sql/readonly_stage2_candidate_aware_fingerprint_v01.sql"
    ).read_text(encoding="utf-8")
    verify_structural_fingerprint(psql(structural_sql))
    index_mode = private_candidate_index_mode(psql("""
        SELECT CASE
          WHEN count(*) = 0 THEN 'baseline'
          WHEN count(*) = 1
           AND bool_and(
             n.nspname = 'public' AND tbl.relname =
               'alpha_hunter_strategy_forward_outcomes_v01'
             AND coalesce(i.indisvalid, false)
             AND coalesce(i.indisready, false)
             AND coalesce(i.indislive, false)
             AND position('(strategy_id, direction, evaluated_at_utc)'
                  in coalesce(pg_get_indexdef(ic.oid), '')) > 0
             AND position('INCLUDE (max_adverse_excursion_pct, max_favorable_excursion_pct)'
                  in coalesce(pg_get_indexdef(ic.oid), '')) > 0
             AND position('horizon_hours = 24' in coalesce(pg_get_indexdef(ic.oid), '')) > 0
             AND position('entry_trigger_status' in coalesce(pg_get_indexdef(ic.oid), '')) > 0
             AND position('path_measurement_quality' in coalesce(pg_get_indexdef(ic.oid), '')) > 0
             AND position('ordering_ambiguous = false'
                  in coalesce(pg_get_indexdef(ic.oid), '')) > 0
           ) THEN 'candidate'
          ELSE 'invalid'
        END
        FROM pg_class ic
        JOIN pg_namespace n ON n.oid=ic.relnamespace
        LEFT JOIN pg_index i ON i.indexrelid=ic.oid
        LEFT JOIN pg_class tbl ON tbl.oid=i.indrelid
        WHERE ic.relname='idx_ah_payoff_geometry_percentiles_candidate_v01';
    """))
    checked = psql("""
        SELECT (SELECT count(*) FROM pg_proc p JOIN pg_namespace n
                ON n.oid=p.pronamespace
                WHERE n.nspname='public' AND p.proname='alpha_hunter_commit_core_scan_v01'
                AND pg_get_function_identity_arguments(p.oid) =
                    'p_parent jsonb, p_children jsonb, p_signals jsonb, p_features jsonb, p_readiness jsonb')
               || '|' ||
               (SELECT count(*) FROM public.alpha_hunter_strategy_forward_outcomes_v01);
    """)
    parts = checked.split("|")
    if len(parts) != 2 or parts[0] != "1" or int(parts[1]) < 500000:
        raise QABlocked("Candidate RPC or >=500k isolated historical outcome rows missing")
    return index_mode


STRUCTURAL_BASELINE = (
    "128", "128", "3012", "360", "0", "131", "108", "36", "21",
    "c802a3e3d96d620a20adc8c3af350472",
    "5a7e8cbe8b8450677f6be84a77caaa6e",
    "5c5b202307ef6bb57b4a9b08082c2a1e",
    "c9785c793fa51a732c2edc96ba22c7eb",
)
REQUIRED_EXTENSIONS = frozenset({
    "http|1.6|extensions",
    "pg_cron|1.6.4|pg_catalog",
    "pg_net|0.20.4|extensions",
    "pg_stat_statements|1.11|extensions",
    "pgcrypto|1.3|extensions",
    "plpgsql|1.0|pg_catalog",
    "supabase_vault|0.3.1|vault",
    "uuid-ossp|1.1|extensions",
})


def verify_structural_fingerprint(output: str) -> None:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines or tuple(lines[0].split("|")) != STRUCTURAL_BASELINE:
        raise QABlocked("Private QA structural, trigger or baseline-index fingerprint mismatch")
    if not REQUIRED_EXTENSIONS.issubset(set(lines[1:])):
        raise QABlocked("Private QA extension version/schema mismatch")


def private_candidate_index_mode(output: str) -> str:
    state = output.strip()
    if state not in {"baseline", "candidate"}:
        raise QABlocked("Candidate index not verified; no trustworthy index comparison")
    return state


def scan_evidence_query(run_id: str) -> str:
    # run_id was regex-validated by validate_fixture; never interpolate raw SQL.
    if not re.fullmatch(r"QA_ISOLATED_[A-Za-z0-9_-]{8,64}", run_id):
        raise QABlocked("Non-synthetic run identifier rejected in audit")
    return f"""
        SELECT json_build_object(
          'parents', (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id='{run_id}'),
          'symbols', (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id='{run_id}'),
          'signals', (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id='{run_id}'),
          'features', (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id='{run_id}'),
          'readiness', (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id='{run_id}'),
          'observations', (SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id='{run_id}'),
          'quotes', (SELECT count(*) FROM public.alpha_hunter_shadow_decision_quotes_v01 WHERE run_id='{run_id}'),
          'freezes', (SELECT count(*) FROM public.alpha_hunter_execution_decision_freezes_v01 WHERE decision_run_id='{run_id}'),
          'payoff', (SELECT count(*) FROM private.alpha_hunter_payoff_geometry_health_observations_v01 WHERE run_id='{run_id}'),
          'calibrated_orders', (SELECT count(*) FROM private.alpha_hunter_calibrated_paper_orders_v01 WHERE run_id='{run_id}'),
          'queue', (SELECT count(*) FROM private.alpha_hunter_strategy_24h_outcome_queue_v01 q
                    WHERE EXISTS (
                      SELECT 1 FROM public.alpha_hunter_strategy_episodes_v01 e
                      JOIN public.alpha_hunter_strategy_observations_v01 o
                        ON o.observation_id=e.first_observation_id
                      WHERE q.episode_id=e.episode_id AND o.run_id='{run_id}'
                    ))
        );
    """


def parse_measured_trial(output: str, fixture: dict) -> float:
    try:
        plan, offset = json.JSONDecoder().raw_decode(output)
        coverage = json.loads(output[offset:].strip())
        elapsed_ms = float(plan[0]["Execution Time"])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise QABlocked("Offline EXPLAIN/coverage result malformed") from exc
    if not isinstance(coverage, dict) or elapsed_ms < 0:
        raise QABlocked("Offline execution metrics or coverage malformed")
    expected = {
        "parents": len(fixture["p_parent"]),
        "symbols": len(fixture["p_children"]),
        "signals": len(fixture["p_signals"]),
        "features": len(fixture["p_features"]),
        "readiness": len(fixture["p_readiness"]),
    }
    for family, count in expected.items():
        if type(coverage.get(family)) is not int or coverage[family] != count:
            raise QABlocked("Offline atomic transaction evidence count mismatch: " + family)
    for branch in ("observations", "quotes", "freezes", "payoff", "calibrated_orders", "queue"):
        if type(coverage.get(branch)) is not int or coverage[branch] < 1:
            raise QABlocked("Representative fixture failed to exercise nested branch: " + branch)
    return elapsed_ms


AUDIT_FAMILIES = (
    "parents", "symbols", "signals", "features", "readiness",
    "observations", "quotes", "freezes", "payoff",
    "calibrated_orders", "queue",
)


def require_clean_qa_run(run_id: str) -> None:
    """Reject existing evidence: otherwise a fast idempotent replay looks real.

    Check before each transaction and after ROLLBACK, including nested tables.
    The network-isolated QA container must not be used by another writer.
    """
    try:
        rows = json.loads(psql(scan_evidence_query(run_id)))
    except (ValueError, TypeError) as exc:
        raise QABlocked("Offline QA run cleanliness result malformed") from exc
    if (not isinstance(rows, dict)
            or set(rows) != set(AUDIT_FAMILIES)
            or any(type(rows[name]) is not int or rows[name] != 0
                   for name in AUDIT_FAMILIES)):
        raise QABlocked("Offline QA run contains preexisting or unrolled-back evidence")


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    low = int(index)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (index - low)


def benchmark_one(fixture: dict) -> dict:
    sql = ("BEGIN; SET LOCAL ROLE service_role; "
           "SET LOCAL statement_timeout = '12000ms'; "
           "SET LOCAL lock_timeout = '8000ms'; "
           + statement_for_fixture(fixture)
           + scan_evidence_query(fixture["p_parent"][0]["run_id"])
           + " ROLLBACK;")
    times = []
    for trial in range(WARMUPS + REPEATS):
        # A stale QA run makes INSERT ... WHERE NOT EXISTS skip authentic
        # triggers, producing misleadingly fast measurements.
        require_clean_qa_run(fixture["p_parent"][0]["run_id"])
        output = psql(sql)
        elapsed_ms = parse_measured_trial(output, fixture)
        # Demonstrate the trial's ROLLBACK really left no core or nested rows.
        require_clean_qa_run(fixture["p_parent"][0]["run_id"])
        if trial >= WARMUPS:
            times.append(elapsed_ms)
    return {
        "n": len(times),
        "p50_ms": round(percentile(times, .50), 2),
        "p95_ms": round(percentile(times, .95), 2),
        "p99_ms": round(percentile(times, .99), 2),
        "max_ms": round(max(times), 2),
    }


def main() -> int:
    try:
        index_mode = ensure_offline_clone()
        base = Path.home() / ".alpha-hunter-private-dbqa"
        input_dir = base / "bench-fixtures"
        if base.is_symlink() or not base.is_dir() or (base.stat().st_mode & 0o777) != 0o700:
            raise QABlocked("Private QA base missing or not mode 700")
        if input_dir.is_symlink() or not input_dir.is_dir() or (input_dir.stat().st_mode & 0o777) != 0o700:
            raise QABlocked("Private synthetic fixtures directory missing or not mode 700")
        cases = {}
        for size in SIZES:
            path = input_dir / f"{size}.json"
            require_private_file(path, 0o600)
            cases[size] = validate_fixture(json.loads(path.read_text(encoding="utf-8")), size)
        print("OFFLINE_QA_ONLY: authentic schema and workload authenticity still require independent review")
        print("PRODUCTION_CONNECTION=NONE; REAL_ORDERS=DISABLED; TRANSACTIONS=ROLLBACK")
        print("PRIVATE_QA_INDEX_MODE=" + index_mode)
        for size in SIZES:
            result = benchmark_one(cases[size])
            print("RPC_SQL_EXECUTION_MS symbols=" + str(size) + " " +
                  " ".join(f"{key}={value}" for key, value in result.items()))
        print("NOT_CERTIFIED: independent graph, role, extension, side-effect, concurrency and source-custody gates remain")
        return 0
    except (QABlocked, OSError, subprocess.SubprocessError, ValueError) as exc:
        message = str(exc) if isinstance(exc, QABlocked) else "Private QA preflight or fixture failed"
        print("BLOCKED: " + message)
        print("NO FALLBACK TO PRODUCTION OR PUBLIC CI")
        return 2


if __name__ == "__main__":
    sys.exit(main())
