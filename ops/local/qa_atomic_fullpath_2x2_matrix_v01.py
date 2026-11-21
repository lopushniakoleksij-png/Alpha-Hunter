#!/usr/bin/env python3
"""Alpha Hunter P0: isolated 2x2 real PG17 transaction-boundary comparison.

A = five separately committed SQL transactions; existing-style index
B = five separately committed SQL transactions; candidate partial index
C = one atomic RPC + existing-style index (from prior measured fixture)
D = one atomic RPC + candidate partial index (from prior measured fixture)

Do not confuse these SQL transactions with real HTTP/PostgREST calls.
Sequential fixture copies previously committed synthetic rows; payload build
and SELECT-copy overhead are not fully matched with the atomic function.
Synthetic private trigger analogue ONLY, never a production acceptance claim.
"""
import json
import os
import statistics
import subprocess
import time

STAGES = ("parent", "symbols", "signals", "features", "readiness")
SIZES = (30, 50, 61)
N = 20
DB = "isolated_atomic_scan_qa"

def check_env():
    for key, value in {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF_NAME": "fix/supabase-write-timeout-qa",
        "PGHOST": "127.0.0.1",
        "PGUSER": "postgres",
        "PGDATABASE": DB,
    }.items():
        if os.environ.get(key) != value:
            raise RuntimeError("REFUSED: disposable PG17 CI guard failed: " + key)
    if query("SELECT current_database()||'|'||current_user") != DB + "|postgres":
        raise RuntimeError("REFUSED: database/role mismatch")

def run_cmd(cmd, *, expected_success=True, timeout=40):
    env = dict(os.environ)
    env["PGOPTIONS"] = "-c statement_timeout=12s -c lock_timeout=8s"
    result = subprocess.run(
        cmd, text=True, capture_output=True, timeout=timeout, env=env,
    )
    if expected_success and result.returncode:
        raise RuntimeError("QA_COMMAND_FAILED: " + result.stderr[-1400:])
    return result

def query(sql):
    return run_cmd(["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql]).stdout.strip()

def source_fixture_check():
    # Measured atomic trials from earlier in this same disposable CI job.
    rows = int(query(
        "SELECT count(*) FROM public.qa_fullpath_request_latency "
        "WHERE phase IN ('baseline','candidate') "
        "AND size IN (30,50,61);"
    ))
    if rows != 120:
        raise AssertionError(f"Expected 120 atomic RPC source measurements; got {rows}")

def percentile(items, q):
    v = sorted(items)
    idx = (len(v)-1)*q
    low = int(idx)
    return v[low] + (v[min(low+1, len(v)-1)]-v[low])*(idx-low)

def summarize(values, indexing, architecture, size):
    if len(values) != N:
        raise AssertionError("QA_2x2_INCOMPLETE_SAMPLE")
    out = {
        "indexing": indexing, "architecture": architecture,
        "symbols": size, "n": len(values),
        "p50_sql_ms": round(percentile(values, .5), 2),
        "p95_sql_ms": round(percentile(values, .95), 2),
        "p99_sql_ms": round(percentile(values, .99), 2),
        "max_sql_ms": round(max(values), 2),
        "average_sql_ms": round(statistics.mean(values), 2),
        "exceeded_12000ms": sum(x >= 12000 for x in values),
        "data_source": "synthetic-505569-outcomes",
        "trigger_graph": "synthetic-7-sink-analogue-not-authentic",
    }
    print("QA_2X2_MEASUREMENT " + json.dumps(out, sort_keys=True), flush=True)
    return out

def stage(indexing, size, trial, stage_name):
    sql = (
        "SELECT public.qa_fullpath_sequential_stage_v01("
        f"'{indexing}',{size},{trial},'{stage_name}');"
    )
    result = json.loads(query(sql))
    if (result.get("stage") != stage_name or
       result.get("stage_count") != (1 if stage_name == "parent" else size) or
       result.get("qa_only") is not True or
       float(result.get("elapsed_sql_ms", 0)) <= 0):
        raise AssertionError("QA_2x2_STAGE_RECEIPT_MISMATCH")
    return float(result["elapsed_sql_ms"])

def index_config(indexing):
    if indexing == "baseline":
        query("DROP INDEX IF EXISTS public.idx_ah_payoff_geometry_percentiles_candidate_v01;")
    else:
        result = run_cmd([
            "psql","-X","-v","ON_ERROR_STOP=1",
            "-f","ops/sql/strategy_payoff_percentile_hotpath_index_candidate_v01.sql"],
            timeout=45,
        )
        if result.returncode:
            raise RuntimeError(result.stderr[-1000:])
    query("ANALYZE public.alpha_hunter_strategy_forward_outcomes_v01;")

def sequential_trial(indexing, size, trial):
    start = time.perf_counter()
    stage_sql_ms = sum(stage(indexing,size,trial,s) for s in STAGES)
    wall_ms = 1000*(time.perf_counter()-start)
    query("SELECT public.qa_fullpath_assert_sequential_v01("
          f"'{indexing}',{size},{trial});")
    query("INSERT INTO public.qa_fullpath_2x2_latency "
          "(indexing,architecture,size,trial,sql_ms,client_wall_ms,stage_count) "
          f"VALUES ('{indexing}','sequential',{size},{trial},"
          f"{stage_sql_ms:.8f},{wall_ms:.8f},5);")
    return stage_sql_ms

def atomic_record(indexing, size, trial):
    q = query(
        "SELECT elapsed_ms FROM public.qa_fullpath_request_latency "
        f"WHERE phase='{indexing}' AND size={size} AND trial={trial};"
    )
    ms = float(q)
    query("INSERT INTO public.qa_fullpath_2x2_latency "
          "(indexing,architecture,size,trial,sql_ms,client_wall_ms,stage_count) "
          f"VALUES ('{indexing}','atomic',{size},{trial},{ms:.8f},{ms:.8f},1);")
    return ms

def fault_demonstration():
    source = "QA_FULLPATH_BASELINE_30_1"
    target = "QA_FULLPATH_SEQ_FAIL_DEMO"
    # Parent commits on its own client connection before symbol transaction.
    query(
        "INSERT INTO public.alpha_hunter_snapshots "
        "SELECT (jsonb_populate_record(NULL::public.alpha_hunter_snapshots,"
        f"to_jsonb(src)||jsonb_build_object('run_id','{target}'))).* "
        "FROM public.alpha_hunter_snapshots src "
        f"WHERE src.run_id='{source}';"
    )
    # Symbol insert fails at symbol 30 by explicit QA-only SQLSTATE injection.
    sql = (
        "INSERT INTO public.alpha_hunter_symbol_snapshots "
        "SELECT (jsonb_populate_record(NULL::public.alpha_hunter_symbol_snapshots,"
        f"to_jsonb(src)||jsonb_build_object('run_id','{target}'))).* "
        "FROM public.alpha_hunter_symbol_snapshots src "
        f"WHERE src.run_id='{source}';"
    )
    failed = run_cmd(
        ["psql","-X","-v","ON_ERROR_STOP=1","-v","VERBOSITY=verbose","-c",sql],
        expected_success=False,
    )
    if failed.returncode == 0 or "57014" not in failed.stderr or "QA_SEQUENCE_INJECTED_57014" not in failed.stderr:
        raise AssertionError("QA_SEQUENTIAL_FAULT_NOT_INJECTED_AS_EXPECTED: " + failed.stderr[-400:])
    counts = query(
        "SELECT (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id='QA_FULLPATH_SEQ_FAIL_DEMO')"
        "||','||(SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id='QA_FULLPATH_SEQ_FAIL_DEMO')"
        "||','||(SELECT count(*) FROM public.qa_fullpath_strategy_observations WHERE run_id='QA_FULLPATH_SEQ_FAIL_DEMO')"
        "||','||(SELECT count(*) FROM public.qa_fullpath_payoff_geometry WHERE run_id='QA_FULLPATH_SEQ_FAIL_DEMO');"
    )
    if counts != "1,0,0,0":
        raise AssertionError("QA_SEQUENTIAL_UNEXPECTED_POST_ERROR_COUNTS: " + counts)
    print("PASS: real separate SQL commits expose parent-only 1/0 after injected failed symbols transaction", flush=True)
    print("NOTE: 57014 fault code was deliberately injected, NOT a measured 12s stall", flush=True)

def main():
    check_env()
    source_fixture_check()
    run_cmd(["psql","-X","-v","ON_ERROR_STOP=1",
             "-f","ops/sql/qa_atomic_fullpath_2x2_sequential_v01.sql"])
    results = []
    for indexing in ("baseline","candidate"):
        index_config(indexing)
        for size in SIZES:
            serial_times = []
            atomic_times = []
            for trial in range(1,N+1):
                serial_times.append(sequential_trial(indexing,size,trial))
                atomic_times.append(atomic_record(indexing,size,trial))
            results.append(summarize(serial_times,indexing,"sequential",size))
            results.append(summarize(atomic_times,indexing,"atomic",size))
    fault_demonstration()
    # Re-assert synthetic percentile parity and complete downstream row counts
    # for every source index configuration (not just per one specimen).
    run_cmd(["psql","-X","-v","ON_ERROR_STOP=1",
             "-f","ops/sql/qa_atomic_fullpath_2x2_verify_v01.sql"])
    print("PASS: all four architecture/index configurations, 30/50/61, 20 trials each;"
          " sequential parent-only fault modeled",flush=True)

if __name__=="__main__":
    main()
