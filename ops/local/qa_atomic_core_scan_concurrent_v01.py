#!/usr/bin/env python3
"""Harada E6: two real PostgreSQL sessions collide on one atomic run ID.

Runs only against disposable GitHub Actions postgres:17; never against live DB.
Provides a controlled 3-second nested trigger delay to observe real advisory
lock contention before the first transaction commits.

Not authentic production trigger/lock or latency certification.
"""
import json
import os
import subprocess
import time

EXPECTED = {
    "committed": True,
    "parent_count": 1,
    "symbol_count": 61,
    "signal_count": 61,
    "feature_count": 61,
    "readiness_count": 61,
}

def guard():
    required = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF_NAME": "fix/supabase-write-timeout-qa",
        "PGHOST": "127.0.0.1",
        "PGDATABASE": "isolated_atomic_scan_qa",
        "PGUSER": "postgres",
    }
    for name, value in required.items():
        if os.environ.get(name) != value:
            raise RuntimeError(f"REFUSED: E6 disposable CI guard failed: {name}")
    actual = subprocess.run(
        ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1",
         "-c", "SELECT current_database(),current_user"],
        capture_output=True, text=True, timeout=8, check=True
    ).stdout.strip()
    if actual != "isolated_atomic_scan_qa|postgres":
        raise RuntimeError("REFUSED: isolated database identity mismatch")


def run_psql(sql, name):
    env = dict(os.environ, PGAPPNAME=name)
    return subprocess.Popen(
        ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env
    )


def count(sql):
    p = subprocess.run(
        ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
        text=True, capture_output=True, timeout=5, check=True
    )
    return int(p.stdout.strip())


def wait_observed(sql, label, proc, duration=2.4):
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"{label}: request finished before contention observed")
        if count(sql) > 0:
            return
        time.sleep(0.075)
    raise AssertionError(f"{label}: expected PostgreSQL wait was not observed")


def rpc_sql(case, conflict=False):
    parent = (
        "jsonb_set(parent_rows, '{0,version}', "
        "to_jsonb('qa-CONFLICTING-PARENT'::text))"
        if conflict else "parent_rows"
    )
    return (
        "SELECT public.alpha_hunter_commit_core_scan_v01("
        f"{parent},children_rows,signals_rows,features_rows,readiness_rows)"
        " FROM public.qa_atomic_scale_fixtures_v01 "
        f"WHERE case_name='{case}';"
    )


def parse_receipt(output, title):
    try:
        result = json.loads(output.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{title}: invalid PostgreSQL JSON receipt: {output[:500]}") from exc
    for k, expected in EXPECTED.items():
        if result.get(k) != expected:
            raise AssertionError(f"{title}: expected {k}={expected}, actual={result.get(k)}")
    return result


def case_run(case, case_suffix, conflict):
    first_name = f"AHQA_E6_FIRST_{case_suffix}"
    second_name = f"AHQA_E6_SECOND_{case_suffix}"
    first = run_psql(rpc_sql(case), first_name)
    second = None
    try:
        # Start second RPC while first is *inside* its own nested PG sleep
        # and holding the candidate's per-run transaction-level advisory lock.
        wait_observed(
            "SELECT count(*) FROM pg_stat_activity "
            f"WHERE application_name='{first_name}' AND wait_event='PgSleep';",
            f"{case}: first trigger sleeping", first
        )
        second = run_psql(rpc_sql(case, conflict=conflict), second_name)
        wait_observed(
            "SELECT count(*) FROM pg_locks l "
            "JOIN pg_stat_activity a ON a.pid=l.pid "
            f"WHERE a.application_name='{second_name}' "
            "AND l.locktype='advisory' AND NOT l.granted;",
            f"{case}: second request waiting on advisory lock", second
        )
        first_out, first_err = first.communicate(timeout=18)
        second_out, second_err = second.communicate(timeout=18)
        if first.returncode != 0:
            raise AssertionError(f"{case}: first RPC failed: {first_err[-600:]}")
        first_receipt = parse_receipt(first_out, case + " first")
        if conflict:
            if second.returncode == 0:
                raise AssertionError(f"{case}: conflicting RPC unexpectedly committed")
            if "core scan persisted content mismatch for alpha_hunter_snapshots" not in second_err:
                raise AssertionError(f"{case}: wrong second failure: {second_err[-600:]}")
            print("PASS: conflicting concurrent RPC blocked on advisory lock then rejected differing parent")
        else:
            if second.returncode != 0:
                raise AssertionError(f"{case}: second identical RPC failed: {second_err[-600:]}")
            second_receipt = parse_receipt(second_out, case + " second")
            if first_receipt != second_receipt:
                raise AssertionError(f"{case}: concurrent receipts differ")
            print("PASS: two overlapping identical RPCs serialized and returned equal complete receipts")
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()


def main():
    guard()
    subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-f", "ops/sql/qa_atomic_core_scan_concurrent_setup_v01.sql"],
        check=True, timeout=20
    )
    case_run("SIXTY_ONE_CONCURRENT", "SAME", False)
    case_run("SIXTY_ONE_CONFLICT", "DIFFERENT", True)
    subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-f", "ops/sql/qa_atomic_core_scan_concurrent_verify_v01.sql"],
        check=True, timeout=20
    )
    print("PASS: E6 real concurrent PostgreSQL sessions; one complete scan per run ID; no duplicate side effects")


if __name__ == "__main__":
    main()
