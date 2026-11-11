#!/usr/bin/env python3
"""Alpha Hunter Stage 7: preliminary 61-symbol rollback-only latency probe.

Run locally inside the already-created private GitHub Codespace, against
the existing network-disabled PostgreSQL 17 QA container. No production
connections, no commits, no fixtures or SQL exported. Not certification:
ROLLBACK latency excludes durable commit/fsync cost and is not realistic
concurrent-production load. Side-effect completeness needs a separate gate.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys

CONTAINER = "alpha-hunter-private-postgres17-qa"
DATABASE = "ah_authentic_schema_20261110"
BRANCH = "fix/supabase-write-timeout-qa"
FIXTURE = Path.home() / ".alpha-hunter-private-dbqa/bench-fixtures/61.json"
FAMILIES = ("p_parent", "p_children", "p_signals", "p_features", "p_readiness")
TABLES = (
    "alpha_hunter_snapshots",
    "alpha_hunter_symbol_snapshots",
    "alpha_hunter_signals",
    "alpha_hunter_signal_features",
    "alpha_hunter_readiness_observations_v01",
)
EXPECTED = (1, 61, 7, 7, 61)
WARMUPS = 3
SAMPLES = 30


class Blocked(Exception):
    pass


def run(args: list[str], *, stdin: str | None = None, timeout: int = 45) -> str:
    result = subprocess.run(
        args, input=stdin, text=True, capture_output=True, timeout=timeout,
        check=False,
    )
    if result.returncode:
        # Never print private SQL, fixture content, or trigger stack traces.
        raise Blocked("isolated command failed; inspect locally, no production fallback")
    return result.stdout.strip()


def sql(statement: str) -> str:
    return run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-XqAt",
         "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=sqlstate",
         "-U", "postgres", "-d", DATABASE],
        stdin=statement,
    )


def guard_environment() -> None:
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Blocked("private Codespace only; no CI or production fallback")
    if run(["git", "branch", "--show-current"]) != BRANCH:
        raise Blocked("wrong branch; refuse to run on main")
    if run(["docker", "inspect", "-f",
            "{{.State.Running}}|{{.HostConfig.NetworkMode}}", CONTAINER]) != "true|none":
        raise Blocked("offline QA container not running with network=none")
    who = sql("SELECT current_database() || '|' || current_user || '|' || current_setting('server_version_num');")
    if not re.fullmatch(re.escape(DATABASE) + r"\|postgres\|17\d{4}", who):
        raise Blocked("unexpected PostgreSQL identity")


def load_fixture() -> tuple[dict, str]:
    if not FIXTURE.is_file() or FIXTURE.is_symlink():
        raise Blocked("private 61-symbol fixture missing")
    if FIXTURE.stat().st_mode & 0o777 != 0o600:
        raise Blocked("private fixture must have mode 0600")
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if data.get("synthetic_only") is not True:
        raise Blocked("synthetic_only fixture marker missing")
    if any(not isinstance(data.get(k), list) for k in FAMILIES):
        raise Blocked("invalid fixture families")
    if tuple(len(data[k]) for k in FAMILIES) != EXPECTED:
        raise Blocked("fixture family counts differ from 61-symbol baseline")
    if not all(isinstance(row, dict) for k in FAMILIES for row in data[k]):
        raise Blocked("invalid fixture row")
    parent = data["p_parent"][0]
    rid = parent.get("run_id")
    if not isinstance(rid, str) or not re.fullmatch(r"QA_ISOLATED_[a-f0-9]{16}", rid):
        raise Blocked("non-isolated run ID")
    if parent.get("symbol_count") != 61 or parent.get("error_count", 0) != 0:
        raise Blocked("unexpected 61-symbol fixture metadata")
    if any(row.get("run_id") != rid for k in FAMILIES for row in data[k]):
        raise Blocked("cross-run fixture data")
    if any(row.get("trade_permission") is True for k in FAMILIES for row in data[k]):
        raise Blocked("trade permission not allowed in synthetic fixtures")
    return data, rid


def count_sql(rid: str) -> str:
    return "SELECT " + " || ',' || ".join(
        f"(SELECT count(*)::text FROM public.{table} WHERE run_id='{rid}')"
        for table in TABLES
    ) + ";"


def parse_counts(value: str) -> tuple[int, ...]:
    try:
        values = tuple(int(v) for v in value.strip().split(","))
    except ValueError as exc:
        raise Blocked("malformed QA evidence counts") from exc
    if len(values) != len(TABLES):
        raise Blocked("wrong number of core evidence counts")
    return values


def require_empty(rid: str) -> None:
    if parse_counts(sql(count_sql(rid))) != (0, 0, 0, 0, 0):
        raise Blocked("existing QA run evidence; results would be false replay")


def rpc_sql(data: dict) -> str:
    args = []
    for key in FAMILIES:
        encoded = json.dumps(data[key], separators=(",", ":"), ensure_ascii=True)
        args.append("'" + encoded.replace("'", "''") + "'::jsonb")
    return ("SELECT public.alpha_hunter_commit_core_scan_v01("
            + ", ".join(args) + ")")


def measure_once(data: dict, rid: str) -> tuple[float, int, int]:
    prefix = "__AH_STAGE7_CORE_COUNTS__="
    # EXPLAIN ANALYZE executes the candidate and its nested triggers, but
    # ROLLBACK always removes the resulting writes and any trigger side effects.
    body = "\n".join((
        "BEGIN;",
        "SET LOCAL ROLE service_role;",
        "SET LOCAL statement_timeout='12000ms';",
        "SET LOCAL lock_timeout='8000ms';",
        "EXPLAIN (ANALYZE, BUFFERS, WAL, FORMAT JSON) " + rpc_sql(data) + ";",
        "SELECT '" + prefix + "' || (" + count_sql(rid).removeprefix("SELECT ").removesuffix(";") + ");",
        "ROLLBACK;",
    ))
    output = sql(body)
    try:
        decoder = json.JSONDecoder()
        idx = output.index("[")
        plan, used = decoder.raw_decode(output[idx:])
        suffix = output[idx + used:].strip().splitlines()
        rows = [line[len(prefix):] for line in suffix if line.startswith(prefix)]
        if len(rows) != 1 or parse_counts(rows[0]) != EXPECTED:
            raise Blocked("in-transaction core evidence incomplete")
        root = plan[0]
        elapsed_ms = float(root["Execution Time"])
        wal = root.get("Plan", {})
        wal_bytes = int(wal.get("WAL Bytes", 0))
        wal_records = int(wal.get("WAL Records", 0))
        if not math.isfinite(elapsed_ms) or elapsed_ms <= 0 or wal_bytes < 0 or wal_records < 0:
            raise Blocked("invalid EXPLAIN timing or WAL statistics")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise Blocked("EXPLAIN JSON malformed; do not claim a benchmark") from exc
    require_empty(rid)
    return elapsed_ms, wal_bytes, wal_records


def percentile(samples: list[float], p: int) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(len(ordered) * p / 100) - 1)]


def main() -> int:
    try:
        guard_environment()
        data, rid = load_fixture()
        require_empty(rid)
        measured: list[tuple[float, int, int]] = []
        for i in range(WARMUPS + SAMPLES):
            value = measure_once(data, rid)
            if i >= WARMUPS:
                measured.append(value)
        ms = [x[0] for x in measured]
        print("STAGE7_PROBE=PASS")
        print("MODE=ISOLATED_QA_ROLLBACK_ONLY_NOT_CERTIFIED")
        print("SCENARIO=61_SYMBOLS_1_PARENT_7_SIGNALS_7_FEATURES_61_READINESS")
        print(f"WARMUPS={WARMUPS} SAMPLES={SAMPLES}")
        print(f"RPC_P50_MS={percentile(ms, 50):.3f}")
        print(f"RPC_P95_MS={percentile(ms, 95):.3f}")
        print(f"RPC_P99_MS={percentile(ms, 99):.3f}")
        print(f"RPC_MAX_MS={max(ms):.3f}")
        print(f"RPC_MEAN_MS={statistics.mean(ms):.3f}")
        print(f"WAL_BYTES_MEAN={statistics.mean(x[1] for x in measured):.0f}")
        print(f"WAL_BYTES_MAX={max(x[1] for x in measured)}")
        print(f"WAL_RECORDS_MEAN={statistics.mean(x[2] for x in measured):.0f}")
        print("CORE_COUNTS_EACH_TRANSACTION=1,61,7,7,61")
        print("CORE_RECORDS_AFTER=0,0,0,0,0")
        print("PRODUCTION_CONNECTIONS=NONE")
        print("LIMITATIONS=ROLLBACK_NOT_COMMIT;SIDE_EFFECT_COVERAGE_NOT_CERTIFIED;NO_CONCURRENT_LOAD")
        return 0
    except (Blocked, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("STAGE7_PROBE=BLOCKED")
        print("REASON=" + (str(exc) if isinstance(exc, Blocked) else "private QA input or command unavailable"))
        print("NO_PRODUCTION_FALLBACK")
        return 2


if __name__ == "__main__":
    sys.exit(main())
