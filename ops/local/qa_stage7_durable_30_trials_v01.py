#!/usr/bin/env python3
"""Thirty independent durable commit/retry trials in an isolated QA environment.

Each trial executes the already verified single-commit probe against a fresh
disposable physical TEMPLATE clone. No changes to the private reference, CI,
production scanner, production DB, trading authority or GitHub main.
Intended to run only inside the reversible cron-quiescence QA controller.

Latency includes local docker/psql client round trips and commit completion,
not HTTP, Render, production concurrency, or real workload data.
"""
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys

N = "alpha-hunter-private-postgres17-qa"
BASE = "ah_authentic_schema_20261110"
BRANCH = "fix/supabase-write-timeout-qa"
SINGLE_PROBE_BLOB = "f04bb2a33e04bf98a0df65f8f649f5c494400318"
TRIALS = 30
EXPECTED = {
    "STAGE7_PHYSICAL_CLONE_COMMIT": "PASS",
    "COMMITTED_CORE_COUNTS": "1,61,7,7,61",
    "RETRY_NO_DUPLICATES": "PASS",
    "PRIVATE_SNAPSHOT_SIDE_EFFECT": "PASS",
    "CRON_DEPENDENT_VIEW_PRESERVED_BY_TEMPLATE": "PASS",
    "CRON_REDIRECTED_DURING_DISPOSABLE_TEST": "YES",
    "PRODUCTION_CONNECTIONS": "NONE",
    "REFERENCE_DATABASE_WRITES": "NONE",
    "DISPOSABLE_DB_REMOVED": "PASS",
}
SIDE_KEYS = (
    "SIDE_EFFECT_COUNT_PRIVATE_ALPHA_HUNTER_SNAPSHOT_SLIM_V01",
    "SIDE_EFFECT_COUNT_PUBLIC_ALPHA_HUNTER_ACCOUNT_LEDGER_MATERIALIZATION_EVENTS",
    "SIDE_EFFECT_COUNT_PUBLIC_ALPHA_HUNTER_ACCOUNT_STATE_SNAPSHOTS",
)


class Blocked(Exception):
    pass


def run(args, timeout=40):
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        raise Blocked("isolated QA command failed (private stderr withheld)")
    return proc.stdout.strip()


def query(db, statement):
    proc = subprocess.run(
        ["docker", "exec", "-i", N, "psql", "-XqAt", "-v",
         "ON_ERROR_STOP=1", "-U", "postgres", "-d", db],
        input=statement, capture_output=True, text=True, timeout=30,
    )
    if proc.returncode:
        raise Blocked("isolated QA query failed (private stderr withheld)")
    return proc.stdout.strip()


def percentile_ms(xs, p):
    if not xs or not all(math.isfinite(x) and x > 0 for x in xs):
        raise Blocked("invalid finite latency samples")
    return sorted(xs)[max(0, math.ceil(len(xs) * p / 100) - 1)]


def parse_trial(stdout):
    data = {}
    for line in stdout.splitlines():
        if "=" in line:
            name, value = line.strip().split("=", 1)
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", name) and name not in data:
                data[name] = value
            elif name in data:
                raise Blocked("duplicate probe evidence field")
    for field, expected in EXPECTED.items():
        if data.get(field) != expected:
            raise Blocked("incomplete durable commit/retry or cleanup evidence")
    signature = []
    for field in SIDE_KEYS:
        value = data.get(field, "")
        if not value.isdecimal():
            raise Blocked("missing side-effect counts")
        signature.append(int(value))
    if signature[0] != 1 or signature[1] < 1 or signature[2] < 1:
        raise Blocked("incomplete downstream side effects")
    ms = []
    for field in ("FIRST_TRANSACTION_CLIENT_WALL_MS",
                  "RETRY_TRANSACTION_CLIENT_WALL_MS"):
        try:
            value = float(data[field])
        except (KeyError, ValueError):
            raise Blocked("missing transaction duration") from None
        if not math.isfinite(value) or not 0 < value < 45000:
            raise Blocked("invalid transaction client wall duration")
        ms.append(value)
    return ms[0], ms[1], tuple(signature)


def guard():
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("private Codespace only")
    if run(["git", "branch", "--show-current"], timeout=15) != BRANCH:
        raise Blocked("wrong repair branch")
    if run(["docker", "inspect", "-f",
            "{{.State.Running}}|{{.HostConfig.NetworkMode}}", N],
           timeout=15) != "true|none":
        raise Blocked("network-isolated QA container unavailable")
    identity = query(
        BASE, "SELECT current_database()||'|'||current_user||'|'||"
              "current_setting('server_version_num')"
    )
    if not re.fullmatch(re.escape(BASE) + r"\|postgres\|17\d{4}", identity):
        raise Blocked("QA identity or PostgreSQL version mismatch")
    if query("postgres", "SELECT current_setting('cron.database_name')") != "postgres":
        raise Blocked("cron launcher must be temporarily redirected")
    if query(BASE, "SELECT count(*) FROM cron.job") != "0":
        raise Blocked("reference has scheduled cron jobs")
    if query("postgres", "SELECT count(*) FROM pg_stat_activity WHERE datname='" + BASE + "'") != "0":
        raise Blocked("reference database has sessions")
    if int(query("postgres", "SELECT pg_database_size('" + BASE + "')")) > 400_000_000:
        raise Blocked("reference size exceeds QA guard")
    src = os.environ.get("AH_STAGE7_SINGLE_PROBE", "")
    path = Path(src)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise Blocked("private verified single-trial probe absent")
    if path.stat().st_mode & 0o077:
        raise Blocked("single-trial probe permissions too open")
    if run(["git", "hash-object", str(path)], timeout=15) != SINGLE_PROBE_BLOB:
        raise Blocked("single-trial probe fingerprint mismatch")
    return path


def main():
    completed = 0
    try:
        path = guard()
        commits, retries, side_prev = [], [], None
        for index in range(1, TRIALS + 1):
            result = subprocess.run(
                [sys.executable, str(path)],
                capture_output=True, text=True, timeout=140,
            )
            if result.returncode != 0:
                if "DISPOSABLE_DB_REMOVED=NOT_VERIFIED" in result.stdout:
                    print("QA_MANUAL_DISPOSABLE_CLEANUP_REQUIRED=YES")
                raise Blocked("single-trial commit/retry or cleanup failed")
            commit_ms, retry_ms, side = parse_trial(result.stdout)
            if side_prev is not None and side != side_prev:
                raise Blocked("downstream side effects differed across clones")
            side_prev = side
            commits.append(commit_ms)
            retries.append(retry_ms)
            completed = index

        if len(commits) != TRIALS or len(retries) != TRIALS:
            raise Blocked("insufficient durable trials")
        print("DURABLE_TRIAL_STATUS=PASS")
        print("DURABLE_TRIALS_COMPLETED=30")
        print("DURABLE_FRESH_DISPOSABLE_CLONES=30")
        print("DURABLE_COMMIT_P50_MS=%.3f" % percentile_ms(commits, 50))
        print("DURABLE_COMMIT_P95_MS=%.3f" % percentile_ms(commits, 95))
        print("DURABLE_COMMIT_P99_MS=%.3f" % percentile_ms(commits, 99))
        print("DURABLE_COMMIT_MAX_MS=%.3f" % max(commits))
        print("DURABLE_COMMIT_MEAN_MS=%.3f" % statistics.mean(commits))
        print("DURABLE_RETRY_P50_MS=%.3f" % percentile_ms(retries, 50))
        print("DURABLE_RETRY_P95_MS=%.3f" % percentile_ms(retries, 95))
        print("DURABLE_RETRY_P99_MS=%.3f" % percentile_ms(retries, 99))
        print("DURABLE_RETRY_MAX_MS=%.3f" % max(retries))
        print("DURABLE_RETRY_MEAN_MS=%.3f" % statistics.mean(retries))
        print("DURABLE_SIDE_EFFECTS_STABLE=PASS")
        print("DURABLE_ALL_DISPOSABLE_DATABASES_REMOVED=PASS")
        print("STAGE7_PHYSICAL_CLONE_COMMIT=PASS")
        print("COMMITTED_CORE_COUNTS=1,61,7,7,61")
        print("RETRY_NO_DUPLICATES=PASS")
        print("DISPOSABLE_DB_REMOVED=PASS")
        print("PRODUCTION_CONNECTIONS=NONE")
        print("REFERENCE_DATABASE_WRITES=NONE")
        print("LIMITATION=30_INDEPENDENT_QA_CLONES;SAME_SYNTHETIC_61_SYMBOL_FIXTURE;NO_CONCURRENT_LOAD;NO_HTTP_OR_PRODUCTION_P99;NO_DBA_SECURITY_APPROVAL")
        return 0
    except (Blocked, OSError, subprocess.TimeoutExpired, ValueError) as error:
        print("DURABLE_TRIAL_STATUS=BLOCKED")
        print("DURABLE_TRIALS_COMPLETED=" + str(completed))
        print("REASON=" + (str(error) if isinstance(error, Blocked)
                           else "private QA test command unavailable"))
        print("NO_PRODUCTION_FALLBACK")
        return 2


if __name__ == "__main__":
    sys.exit(main())
