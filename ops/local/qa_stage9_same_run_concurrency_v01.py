#!/usr/bin/env python3
"""Stage 9: three concurrent same-run durable RPC attempts, QA only.

Runs only via the existing reversible QA cron-quiescence controller against a
fresh physical TEMPLATE disposable clone in a network-isolated Codespace.
Reuses an exact Git-blob-verified Stage 7 single-commit probe for all helpers.
No production, no reference writes, no new external infrastructure.
One three-client race is a correctness probe, NOT throughput/p99 certification.
"""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading

N = "alpha-hunter-private-postgres17-qa"
BASE = "ah_authentic_schema_20261110"
BRANCH = "fix/supabase-write-timeout-qa"
SINGLE_BLOB = "f04bb2a33e04bf98a0df65f8f649f5c494400318"
WORKERS = 3


class Blocked(Exception):
    pass


def command(args, timeout=25):
    process = subprocess.run(args, capture_output=True, text=True,
                             timeout=timeout, check=False)
    if process.returncode:
        raise Blocked("offline QA command failed; stderr withheld")
    return process.stdout.strip()


def load_verified_single_probe():
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("private Codespace required")
    if command(["git", "branch", "--show-current"], timeout=15) != BRANCH:
        raise Blocked("wrong repair branch")
    ident = command([
        "docker", "inspect", "-f",
        "{{.State.Running}}|{{.HostConfig.NetworkMode}}", N,
    ], timeout=15)
    if ident != "true|none":
        raise Blocked("wrong network-isolated QA container")
    name = os.environ.get("AH_STAGE7_SINGLE_PROBE", "")
    path = Path(name)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise Blocked("verified single-run QA probe missing")
    if path.stat().st_mode & 0o077:
        raise Blocked("private probe permissions too open")
    if command(["git", "hash-object", str(path)], timeout=15) != SINGLE_BLOB:
        raise Blocked("verified single-run probe Git blob differs")
    spec = importlib.util.spec_from_file_location("ah_stage7_verified", path)
    if spec is None or spec.loader is None:
        raise Blocked("verified probe cannot be imported")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    if probe.N != N or probe.BASE != BASE or probe.BRANCH != BRANCH:
        raise Blocked("probe identity mismatch")
    return probe


def bounded_race(probe, db, args):
    barrier = threading.Barrier(WORKERS, timeout=15)

    def attempt(_):
        barrier.wait(timeout=15)
        return probe.rpc(db, args)

    # Each RPC creates its own isolated local psql connection.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(attempt, range(WORKERS)))
    return results


def verify_clone(probe, db, rid):
    if probe.sql(db, "SELECT current_database()") != db:
        raise Blocked("disposable database identity mismatch")
    if probe.sql(db, "SELECT to_regclass('cron.job') IS NOT NULL") != "t":
        raise Blocked("disposable cron-dependent schema absent")
    if probe.sql(db, "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_cron')") != "t":
        raise Blocked("disposable pg_cron extension absent")
    if probe.sql(db, "SELECT count(*) FROM cron.job") != "0":
        raise Blocked("disposable cron jobs unexpectedly present")
    verified_callbacks = (
        "SELECT count(*) FROM pg_trigger t "
        "JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_proc p ON p.oid=t.tgfoid "
        "JOIN pg_namespace pn ON pn.oid=p.pronamespace "
        "WHERE n.nspname='public' AND pn.nspname='private' "
        "AND c.relname IN ('alpha_hunter_snapshots',"
        "'alpha_hunter_symbol_snapshots','alpha_hunter_signals',"
        "'alpha_hunter_signal_features',"
        "'alpha_hunter_readiness_observations_v01') "
        "AND NOT t.tgisinternal "
        "AND p.proowner='postgres'::regrole::oid "
        "AND p.prosecdef"
    )
    if probe.sql(db, verified_callbacks) != "5":
        raise Blocked("expected five nested QA callbacks not retained")
    if probe.counts(db, rid) != (0, 0, 0, 0, 0):
        raise Blocked("prior synthetic run evidence in disposable clone")


def main():
    db = None
    status = 0
    probe = None
    try:
        probe = load_verified_single_probe()
        fixture, run_id = probe.guard()
        if probe.sql(BASE, "SELECT current_setting('cron.database_name')") != "postgres":
            raise Blocked("QA cron launcher not redirected")
        if probe.sql(BASE, "SELECT count(*) FROM cron.job") != "0":
            raise Blocked("reference has scheduled jobs")
        if probe.sql(
            "postgres", "SELECT count(*) FROM pg_stat_activity WHERE datname='" + BASE + "'"
        ) != "0":
            raise Blocked("reference database still has active sessions")
        db = "ah_stage7_ephemeral_qa_" + secrets.token_hex(6)
        if probe.sql("postgres", "SELECT EXISTS(SELECT 1 FROM pg_database "
                     "WHERE datname='" + db + "')") != "f":
            raise Blocked("disposable database name collision")
        try:
            probe.sql("postgres", "CREATE DATABASE " + db + " TEMPLATE " + BASE
                      + " OWNER supabase_admin;",
                      role="supabase_admin", timeout=90)
        except probe.Stop:
            raise Blocked("physical QA clone failed; private SQL withheld")
        verify_clone(probe, db, run_id)
        before = probe.downstream(db, run_id)
        args = ",".join(
            "'" + json.dumps(fixture[k], separators=(",", ":"),
                             ensure_ascii=True).replace("'", "''") + "'::jsonb"
            for k in probe.K
        )
        try:
            race = bounded_race(probe, db, args)
        except (threading.BrokenBarrierError, Exception) as err:
            # Do not expose private SQL and per-connection error details.
            raise Blocked("concurrent same-run RPC attempts did not all succeed") from None
        if len(race) != WORKERS:
            raise Blocked("wrong concurrent RPC receipt count")
        elapsed = []
        for receipt, duration in race:
            if receipt.get("run_id") != run_id:
                raise Blocked("concurrent RPC receipt run identity mismatch")
            if tuple(receipt.get(k) for k in (
                "parent_count", "symbol_count", "signal_count",
                "feature_count", "readiness_count"
            )) != probe.EXPECTED or receipt.get("committed") is not True:
                raise Blocked("concurrent RPC evidence counts incomplete")
            if not math.isfinite(duration) or not 0 < duration < 45000:
                raise Blocked("concurrent RPC timing invalid")
            elapsed.append(duration)
        if probe.counts(db, run_id) != probe.EXPECTED:
            raise Blocked("core records duplicated or incomplete after race")
        after = probe.downstream(db, run_id)
        if after[probe.SIDE[0]] != before[probe.SIDE[0]] + 1:
            raise Blocked("concurrent scan private snapshot not exactly once")
        if any(after[k] < before[k] for k in probe.SIDE):
            raise Blocked("concurrent scan reduced side effects")
        replay_receipt, retry_elapsed = probe.rpc(db, args)
        if replay_receipt.get("run_id") != run_id:
            raise Blocked("post-race retry receipt run identity changed")
        if probe.counts(db, run_id) != probe.EXPECTED:
            raise Blocked("post-race retry changed core records")
        if probe.downstream(db, run_id) != after:
            raise Blocked("post-race retry duplicated side effects")
        print("SAME_RUN_RACE_STATUS=PASS")
        print("SAME_RUN_CONCURRENT_CLIENTS=3")
        print("SAME_RUN_ALL_RECEIPTS=PASS")
        print("SAME_RUN_CORE_COUNTS=1,61,7,7,61")
        print("SAME_RUN_PRIVATE_SNAPSHOT_ONCE=PASS")
        print("SAME_RUN_POST_RACE_RETRY=PASS")
        print("SAME_RUN_MAX_CLIENT_WALL_MS=%.3f" % max(elapsed))
        print("SAME_RUN_RETRY_CLIENT_WALL_MS=%.3f" % retry_elapsed)
        print("STAGE7_PHYSICAL_CLONE_COMMIT=PASS")
        print("COMMITTED_CORE_COUNTS=1,61,7,7,61")
        print("RETRY_NO_DUPLICATES=PASS")
        print("PRODUCTION_CONNECTIONS=NONE")
        print("REFERENCE_DATABASE_WRITES=NONE")
        print("LIMITATION=ONE_THREE_CLIENT_SAME_RUN_RACE;SYNTHETIC_61_SYMBOLS;NO_DIFFERENT_RUN_CONCURRENCY;NO_INJECTED_FAILURE;NOT_PRODUCTION_CERTIFIED")
    except (Blocked, OSError, ValueError, subprocess.TimeoutExpired) as error:
        status = 2
        print("SAME_RUN_RACE_STATUS=BLOCKED")
        print("REASON=" + (str(error) if isinstance(error, Blocked)
                           else "private QA race input unavailable"))
        print("NO_PRODUCTION_FALLBACK")
    finally:
        if db is not None and probe is not None:
            try:
                probe.drop_disposable(db)
                print("DISPOSABLE_DB_REMOVED=PASS")
            except (probe.Stop, OSError, subprocess.TimeoutExpired):
                status = 3
                print("DISPOSABLE_DB_REMOVED=NOT_VERIFIED")
                print("QA_MANUAL_DISPOSABLE_CLEANUP_REQUIRED=YES")
    return status


if __name__ == "__main__":
    sys.exit(main())
