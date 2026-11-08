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


def ensure_offline_clone() -> None:
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
    if not re.fullmatch(r"alpha_hunter_private_qa\\|postgres\\|17[0-9]{4}", identity):
        raise QABlocked("Offline database name, role or PG17 server identity mismatched")
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


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    low = int(index)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (index - low)


def benchmark_one(fixture: dict) -> dict:
    sql = ("BEGIN; SET LOCAL ROLE service_role; "
           "SET LOCAL statement_timeout = '12000ms'; "
           "SET LOCAL lock_timeout = '8000ms'; "
           + statement_for_fixture(fixture) + " ROLLBACK;")
    times = []
    for trial in range(WARMUPS + REPEATS):
        output = psql(sql)
        try:
            plan = json.loads(output)
            elapsed_ms = float(plan[0]["Execution Time"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise QABlocked("Offline EXPLAIN output missing execution time") from exc
        if elapsed_ms < 0:
            raise QABlocked("Invalid offline EXPLAIN latency")
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
        ensure_offline_clone()
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
