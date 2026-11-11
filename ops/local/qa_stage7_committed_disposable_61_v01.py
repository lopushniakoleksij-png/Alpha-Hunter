#!/usr/bin/env python3
"""Stage 7 disposable committed persistence and retry probe.
ONLY in existing private Codespace + network-isolated QA PostgreSQL 17.
The restored reference database is logically dumped into an empty temporary database; only
that disposable copy receives durable synthetic writes. Never production.
One commit/retry does NOT establish p95/p99 or full end-to-end readiness.
"""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

N = "alpha-hunter-private-postgres17-qa"
BASE = "ah_authentic_schema_20261110"
BRANCH = "fix/supabase-write-timeout-qa"
P = Path.home() / ".alpha-hunter-private-dbqa/bench-fixtures/61.json"
K = ("p_parent", "p_children", "p_signals", "p_features", "p_readiness")
T = ("alpha_hunter_snapshots", "alpha_hunter_symbol_snapshots",
     "alpha_hunter_signals", "alpha_hunter_signal_features",
     "alpha_hunter_readiness_observations_v01")
EXPECTED = (1, 61, 7, 7, 61)
SIDE = ("private.alpha_hunter_snapshot_slim_v01",
        "public.alpha_hunter_account_ledger_materialization_events",
        "public.alpha_hunter_account_state_snapshots")

class Stop(Exception):
    pass

def run(args, payload=None, timeout=45):
    r = subprocess.run(args, input=payload, text=True, capture_output=True,
                       timeout=timeout)
    if r.returncode:
        error = next((s.strip() for s in r.stderr.splitlines()
                      if "ERROR:" in s or "FATAL:" in s), "")
        raise Stop("local QA command failed: " + error[:180])
    return r.stdout.strip()

def sql(db, q, role="postgres", timeout=45):
    assert role in ("postgres", "supabase_admin")
    return run(["docker", "exec", "-i", N, "psql", "-XqAt",
                "-v", "ON_ERROR_STOP=1", "-U", role, "-d", db],
               q, timeout)

def counts(db, rid):
    q = "SELECT " + " || ',' || ".join(
        f"(SELECT count(*)::text FROM public.{t} WHERE run_id='{rid}')"
        for t in T)
    return tuple(int(v) for v in sql(db, q).split(","))

def downstream(db, rid):
    out = {}
    for qualified in SIDE:
        schema, table = qualified.split(".")
        if sql(db, f"SELECT to_regclass('{qualified}') IS NOT NULL") != "t":
            raise Stop("missing expected QA side-effect table " + qualified)
        has_run_id = sql(db, f"SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='{schema}' AND table_name='{table}' AND column_name='run_id')") == "t"
        clause = f" WHERE run_id='{rid}'" if has_run_id else ""
        out[qualified] = int(sql(db, f"SELECT count(*) FROM {qualified}{clause}"))
    return out

def guard():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Stop("private Codespace required")
    if run(["git", "branch", "--show-current"]) != BRANCH:
        raise Stop("wrong branch")
    if run(["docker", "inspect", "-f",
            "{{.State.Running}}|{{.HostConfig.NetworkMode}}", N]) != "true|none":
        raise Stop("QA container must be running with network=none")
    ident = sql(BASE, "SELECT current_database()||'|'||current_user||'|'||current_setting('server_version_num')")
    if not re.fullmatch(re.escape(BASE) + r"\|postgres\|17\d{4}", ident):
        raise Stop("wrong source database identity")
    if not P.is_file() or P.is_symlink() or P.stat().st_mode & 0o777 != 0o600:
        raise Stop("private fixture absent or insecure")
    d = json.loads(P.read_text())
    if d.get("synthetic_only") is not True or any(not isinstance(d.get(k), list) for k in K):
        raise Stop("invalid synthetic-only fixture")
    if tuple(len(d[k]) for k in K) != EXPECTED:
        raise Stop("wrong fixture family counts")
    if any(not isinstance(row, dict) for k in K for row in d[k]):
        raise Stop("invalid fixture rows")
    rid = d["p_parent"][0].get("run_id")
    if not isinstance(rid, str) or not re.fullmatch(r"QA_ISOLATED_[a-f0-9]{16}", rid):
        raise Stop("unexpected run_id")
    if d["p_parent"][0].get("symbol_count") != 61:
        raise Stop("unexpected symbol count")
    if any(row.get("run_id") != rid or row.get("trade_permission") is True
           for k in K for row in d[k]):
        raise Stop("run identity/trading safety mismatch")
    if counts(BASE, rid) != (0, 0, 0, 0, 0):
        raise Stop("existing fixture ID in restored reference database")
    if int(sql("postgres", f"SELECT pg_database_size('{BASE}')")) > 400_000_000:
        raise Stop("QA reference exceeds disposable-copy size limit")
    if sql(BASE, "SELECT has_function_privilege('service_role','public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)','EXECUTE')") != "t":
        raise Stop("service_role cannot execute candidate RPC")
    return d, rid

def rpc(db, args):
    q = ("BEGIN;\nSET LOCAL ROLE service_role;\n"
         "SET LOCAL statement_timeout='12000ms';\n"
         "SET LOCAL lock_timeout='8000ms';\n"
         "SELECT public.alpha_hunter_commit_core_scan_v01(" + args + ");\n"
         "COMMIT;")
    start = time.perf_counter()
    output = sql(db, q, timeout=45)
    elapsed = (time.perf_counter()-start)*1000
    json_rows = [x for x in output.splitlines() if x.startswith("{")]
    if len(json_rows) != 1:
        raise Stop("RPC response missing or ambiguous")
    obj = json.loads(json_rows[0])
    if obj.get("committed") is not True or tuple(obj.get(k) for k in
            ("parent_count", "symbol_count", "signal_count",
             "feature_count", "readiness_count")) != EXPECTED:
        raise Stop("RPC evidence count mismatch")
    return obj, elapsed

def drop_disposable(db):
    if not re.fullmatch(r"ah_stage7_ephemeral_qa_[0-9a-f]{12}", db):
        raise Stop("disposable cleanup name mismatch")
    sql("postgres", "DROP DATABASE IF EXISTS " + db + " WITH (FORCE);",
        role="supabase_admin", timeout=70)
    if sql("postgres", f"SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='{db}')") != "f":
        raise Stop("disposable cleanup unverified")

def main():
    db = None
    status = 0
    try:
        d, rid = guard()
        db = "ah_stage7_ephemeral_qa_" + secrets.token_hex(6)
        if sql("postgres", f"SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='{db}')") != "f":
            raise Stop("disposable DB name collision")
        # TEMPLATE BASE requires zero other sessions, which isn't a valid
        # assumption in a shared Codespace. Create a brand-new empty DB from
        # template0 then logically copy the *isolated QA reference* over a
        # local, in-container pipe. No network, production connection, or
        # intermediate SQL archive; pg_dump uses a consistent snapshot.
        sql("postgres",
            "CREATE DATABASE " + db + " TEMPLATE template0 OWNER supabase_admin;",
            role="supabase_admin", timeout=90)
        stream = (
            "set -euo pipefail; "
            "pg_dump -U supabase_admin -d " + BASE + " -Fc "
            "| pg_restore -U supabase_admin -d " + db
            + " --single-transaction --exit-on-error"
        )
        run(["docker", "exec", N, "bash", "-c", stream], timeout=180)
        if sql(db, "SELECT current_database()") != db:
            raise Stop("disposable clone identity mismatch")
        # The prior Stage 6 reconciliation is required in the scratch copy.
        verify = (
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
        if sql(db, verify) != "5":
            raise Stop("disposable copy failed five-callback owner/security baseline")
        if counts(db, rid) != (0, 0, 0, 0, 0):
            raise Stop("existing fixture ID in disposable clone")
        side_before = downstream(db, rid)
        args = ",".join(
            "'" + json.dumps(d[k], separators=(",", ":"), ensure_ascii=True).replace("'", "''") + "'::jsonb"
            for k in K)
        result1, first_ms = rpc(db, args)
        if result1.get("run_id") != rid or counts(db, rid) != EXPECTED:
            raise Stop("post-COMMIT core evidence incomplete")
        side_after = downstream(db, rid)
        if side_after[SIDE[0]] != side_before[SIDE[0]] + 1:
            raise Stop("private snapshot trigger side effect missing")
        if any(side_after[t] < side_before[t] for t in SIDE):
            raise Stop("side-effect evidence count decreased")
        result2, retry_ms = rpc(db, args)
        if result2.get("run_id") != rid or counts(db, rid) != EXPECTED:
            raise Stop("post-RETRY core evidence changed")
        if downstream(db, rid) != side_after:
            raise Stop("retry replayed downstream side effects")
        print("STAGE7_DISPOSABLE_COMMIT=PASS")
        print("COMMITTED_CORE_COUNTS=1,61,7,7,61")
        print("RETRY_NO_DUPLICATES=PASS")
        print("PRIVATE_SNAPSHOT_SIDE_EFFECT=PASS")
        for t in SIDE:
            print("SIDE_EFFECT_COUNT_" + t.upper().replace(".", "_") + "=" + str(side_after[t]))
        print(f"FIRST_TRANSACTION_CLIENT_WALL_MS={first_ms:.3f}")
        print(f"RETRY_TRANSACTION_CLIENT_WALL_MS={retry_ms:.3f}")
        print("LIMITATION=ONE_COMMIT_RETRY_NO_P95_P99_OR_CONCURRENT_LOAD")
        print("PRODUCTION_CONNECTIONS=NONE")
    except (Stop, OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        status = 2
        print("STAGE7_DISPOSABLE_COMMIT=BLOCKED")
        print("REASON=" + (str(e) if isinstance(e, Stop) else "private QA input unavailable"))
        print("NO_PRODUCTION_FALLBACK")
    finally:
        if db is not None:
            try:
                drop_disposable(db)
                print("DISPOSABLE_DB_REMOVED=PASS")
            except (Stop, OSError, subprocess.TimeoutExpired):
                status = 3
                print("DISPOSABLE_DB_REMOVED=NOT_VERIFIED")
                print("CLEANUP_ATTENTION_REQUIRED=" + db)
    return status

if __name__ == "__main__":
    sys.exit(main())
