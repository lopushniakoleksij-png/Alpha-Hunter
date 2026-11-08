#!/usr/bin/env python3
"""Harada C6/C7: full atomic RPC synthetic trigger-chain PG17 benchmark.

Database: disposable 505,569-row simulated payoff outcomes + 5-step nested
trigger analogue including a calibrated-order side branch. Actual private
production functions are NOT used; no external DB connection or real orders.

Keep the p50/p95/p99 as exploratory synthetic performance measurements ONLY.
"""
import concurrent.futures
import json
import os
import statistics
import subprocess
from pathlib import Path

EXPECTED_DB = "isolated_atomic_scan_qa"
EXPECTED_BRANCH = "fix/supabase-write-timeout-qa"
RUNS_EACH = 20

def safe():
    guard = dict(
        GITHUB_ACTIONS="true",
        GITHUB_REF_NAME=EXPECTED_BRANCH,
        PGHOST="127.0.0.1",
        PGUSER="postgres",
        PGDATABASE=EXPECTED_DB,
    )
    for k, v in guard.items():
        if os.environ.get(k) != v:
            raise RuntimeError("REFUSED: ephemeral QA guard failed: " + k)
    x = subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At",
         "-c", "SELECT current_database()||'|'||current_user"],
        check=True, text=True, capture_output=True, timeout=10,
    ).stdout.strip()
    if x != EXPECTED_DB + "|postgres":
        raise RuntimeError("REFUSED: unexpected DB and role identity")

def psql_file(path):
    x = subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-f", path],
        check=True, text=True, capture_output=True, timeout=120,
    )
    for line in x.stderr.splitlines():
        if "NOTICE:" in line and ("PASS:" in line or "QA_FULLPATH" in line):
            print(line.strip())
    return x.stdout

def sql_query(text, timeout=30):
    env = dict(os.environ)
    env["PGOPTIONS"] = "-c statement_timeout=12s -c lock_timeout=8s"
    return subprocess.run(
        ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", text],
        check=True, text=True, capture_output=True, timeout=timeout, env=env,
    ).stdout.strip()

def bench_one(phase, size, n):
    result = json.loads(sql_query(
        "SELECT public.qa_fullpath_run(" +
        "'"+phase+"',"+str(size)+","+str(n)+");"
    ))
    if (result.get("committed") is not True
       or result.get("symbols") != size
       or result.get("qa_only") is not True
       or float(result["elapsed_ms"]) <= 0
       or result.get("historical_rows_sum", 0) <= 0):
        raise RuntimeError("QA_FULLPATH_MALFORMED_OR_INCOMPLETE_RECEIPT")
    return float(result["elapsed_ms"])

def percentile_linear(values, fraction):
    sorted_vals = sorted(values)
    index = (len(sorted_vals)-1)*fraction
    lower = int(index)
    upper = min(lower+1, len(sorted_vals)-1)
    return sorted_vals[lower]+(sorted_vals[upper]-sorted_vals[lower])*(index-lower)

def stats(phase, size, times):
    values = list(times)
    assert len(values) > 0
    out = {
        "phase": phase, "symbols": size, "n": len(values),
        "p50_ms": round(percentile_linear(values, .50), 2),
        "p95_ms": round(percentile_linear(values, .95), 2),
        "p99_ms": round(percentile_linear(values, .99), 2),
        "max_ms": round(max(values), 2),
        "mean_ms": round(statistics.mean(values), 2),
        "exceed_12000ms": sum(v >= 12000 for v in values),
        "scientific_equivalence": "synthetic-only",
        "trigger_equivalence": "not-authentic-private",
    }
    print("QA_FULLPATH_MEASUREMENT " + json.dumps(out, sort_keys=True), flush=True)
    return out

def main():
    safe()
    psql_file("ops/sql/qa_atomic_fullpath_505k_benchmark_setup_v01.sql")
    # A: Existing synthetic access paths, not target index.
    # This index was installed earlier by the legacy QA percentile test.
    sql_query("DROP INDEX IF EXISTS public.idx_ah_payoff_geometry_percentiles_candidate_v01;")
    sql_query("ANALYZE public.alpha_hunter_strategy_forward_outcomes_v01;")
    summaries = []
    for size in (30, 50, 61):
        values = [bench_one("baseline", size, n) for n in range(1, RUNS_EACH+1)]
        summaries.append(stats("baseline", size, values))

    # B: Proposed index, in disposable DB only. Never production.
    psql_file("ops/sql/strategy_payoff_percentile_hotpath_index_candidate_v01.sql")
    sql_query("ANALYZE public.alpha_hunter_strategy_forward_outcomes_v01;")
    for size in (30, 50, 61):
        values = [bench_one("candidate", size, n) for n in range(1, RUNS_EACH+1)]
        summaries.append(stats("candidate", size, values))

    # Short real concurrent PG sessions with the candidate index enabled.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        jobs = [executor.submit(bench_one, "candidate_concurrent", 61, n)
                for n in range(1, 7)]
        concurrent_values = [job.result(timeout=60) for job in jobs]
    summaries.append(stats("candidate_concurrent", 61, concurrent_values))

    psql_file("ops/sql/qa_atomic_fullpath_505k_benchmark_verify_v01.sql")
    # Store measured results as ephemeral runner artifact, NOT production evidence.
    target = Path("/tmp/alpha_hunter_fullpath_qa_505k.json")
    target.write_text(json.dumps({
        "scope": "SYNTHETIC_NOT_AUTHENTIC_PRIVATE_TRIGGER_GRAPH",
        "outcome_rows": 505569,
        "isolated_db": EXPECTED_DB,
        "rows": summaries,
    }, indent=2), encoding="utf-8")
    print("PASS: simulated 505,569-outcome full-RPC and nested trigger workload;",
          "30/50/61, baseline/candidate and concurrent 61, all receipts verified")

if __name__ == "__main__":
    main()
