"""P0.2 full-width mixed-concurrency + fail-closed PostgREST stress.

Research on disposable local PG16/17 and local PostgREST ONLY, never Supabase
production, exchange, paper position, original R8/R9/R10 or protected scanner.
All runs are synthetic, parent remains PENDING, trade_permission false.
"""
import json
import math
import os
import pathlib
import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import psycopg

from phase2_real_catalog_http_concurrency_benchmark_v01 import (
    DSN, HIST_ROWS, OUT, insist_local, run_ddl, seed_history, wait_http_schema,
    write_run, test_postgrest_57014_and_ambiguous_ack,
)

CLIENTS = 6
RUNS = 18   # 144 HTTP child batch samples; sample p99 is runner-specific.
SCAN_ROWS = 62
EXPECTED_STRATEGIES_PER_SCAN = 620
EXPECTED_QUOTE_ROWS_PER_SCAN = 310


def local_resource_counters(conn):
    wal = conn.execute("SELECT wal_bytes FROM pg_stat_wal").fetchone()[0]
    stats = conn.execute(
        "SELECT deadlocks,temp_bytes,blks_read,blks_hit FROM pg_stat_database "
        "WHERE datname=current_database()"
    ).fetchone()
    return {
        "wal_bytes":int(wal), "deadlocks":int(stats[0]),
        "temp_bytes":int(stats[1]),"blocks_read":int(stats[2]),
        "blocks_hit":int(stats[3]),
    }


def monitor_db(stop, result):
    """Poll independent local PG connection, never reuse an HTTP worker."""
    with psycopg.connect(DSN,autocommit=True) as conn:
        while not stop.is_set():
            try:
                r=conn.execute("""
                    SELECT
                      count(*) FILTER(WHERE wait_event_type='Lock') AS lock_waiters,
                      count(*) FILTER(WHERE state='active') AS active_backends,
                      count(*) FILTER(WHERE wait_event_type='IO') AS io_waiters
                    FROM pg_stat_activity
                    WHERE datname=current_database()
                      AND pid<>pg_backend_pid()
                """).fetchone()
                result["polls"] += 1
                result["max_lock_waiters"]=max(result["max_lock_waiters"],int(r[0]))
                result["max_active_backends"]=max(result["max_active_backends"],int(r[1]))
                result["max_io_waiters"]=max(result["max_io_waiters"],int(r[2]))
                if r[0]: result["observed_lock_wait_polls"]+=1
            except psycopg.Error as e:
                result["monitor_errors"].append(type(e).__name__)
            stop.wait(.035)


def percentile_nearest_rank(values, pct):
    if not values:raise AssertionError("No samples")
    return sorted(values)[max(0,math.ceil(len(values)*pct/100)-1)]


def main():
    insist_local()
    if os.getenv("AH_P0_STRESS_EXPLICIT")!="1":
        raise RuntimeError("Requires P0.2 stress-specific local opt-in")
    if HIST_ROWS!=1640424:
        raise RuntimeError("Refuse non-production-count history for P0.2")
    if os.getenv("AH_P0_PARENT_LEDGER_COMPLETE")!="1":
        raise RuntimeError("Parent/account/protection trigger addendum required")
    if any(os.getenv(k) for k in ("SUPABASE_SERVICE_ROLE_KEY","BITGET_SECRET_KEY",
                                  "RENDER_API_KEY","SUPABASE_URL")):
        raise RuntimeError("Production credentials forbidden")
    OUT.mkdir(parents=True,exist_ok=True)
    run_ddl()
    with psycopg.connect(DSN,autocommit=True) as conn:
        pg_major=int(conn.execute("SHOW server_version_num").fetchone()[0])//10000
        if pg_major not in (16,17):raise RuntimeError("PG16/17 only")
        seed_at=time.perf_counter()
        seed_history(conn,HIST_ROWS)
        seed_secs=round(time.perf_counter()-seed_at,2)
        conn.execute("NOTIFY pgrst,'reload schema'")
        actual_history=conn.execute("SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01").fetchone()[0]
        physical_bytes=conn.execute("SELECT pg_total_relation_size('public.alpha_hunter_strategy_observations_v01')").fetchone()[0]
        if actual_history!=HIST_ROWS or not (3000000000<=physical_bytes<=7000000000):
            raise AssertionError("Full-width seed not within production-shaped 3–7GB acceptance band")
    wait_http_schema()

    with psycopg.connect(DSN,autocommit=True) as conn:
        before=local_resource_counters(conn)
        baseline_db_size=int(conn.execute("SELECT pg_database_size(current_database())").fetchone()[0])

    names=[f"p0-stress-{i:03d}" for i in range(RUNS)]
    poll={"polls":0,"max_lock_waiters":0,"max_active_backends":0,
          "max_io_waiters":0,"observed_lock_wait_polls":0,"monitor_errors":[]}
    stop=threading.Event()
    watcher=threading.Thread(target=monitor_db,args=(stop,poll),daemon=True)
    watcher.start()
    started=time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=CLIENTS) as pool:
            runs=list(pool.map(write_run,names))
    finally:
        stop.set()
        watcher.join(timeout=6)
    elapsed=round(time.perf_counter()-started,3)
    if watcher.is_alive() or poll["monitor_errors"]:
        raise AssertionError("DB monitor incomplete or failed")
    samples=[ms for name,times in runs for ms in times]
    if len(samples)!=RUNS*8:
        raise AssertionError("Insufficient samples for p99")
    with psycopg.connect(DSN,autocommit=True) as conn:
        after=local_resource_counters(conn)
        size_after=int(conn.execute("SELECT pg_database_size(current_database())").fetchone()[0])
        rows=conn.execute("""
            SELECT p.run_id,
                   (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots c
                    WHERE c.run_id=p.run_id) child_count,
                   (SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01 o
                    WHERE o.run_id=p.run_id) observation_count,
                   (SELECT count(*) FROM public.alpha_hunter_shadow_decision_quotes_v01 q
                    WHERE q.run_id=p.run_id) quotes_count,
                   p.payload->>'_canonical_publication_state' publication_state
            FROM public.alpha_hunter_snapshots p
            WHERE p.run_id=ANY(%s) ORDER BY p.run_id
        """,(names,)).fetchall()
        if len(rows)!=RUNS:
            raise AssertionError("Parent census incomplete")
        for run,child,obs,quotes,state in rows:
            if (child,obs,quotes,state)!=(SCAN_ROWS,EXPECTED_STRATEGIES_PER_SCAN,
                                           EXPECTED_QUOTE_ROWS_PER_SCAN,"PENDING"):
                raise AssertionError(f"{run}: partial/false VERIFIED evidence {child,obs,quotes,state}")
        ep=conn.execute("SELECT count(*) FROM public.alpha_hunter_strategy_episodes_v01").fetchone()[0]
        queue=conn.execute("SELECT count(*) FROM private.alpha_hunter_strategy_24h_outcome_queue_v01").fetchone()[0]
        positions=conn.execute("SELECT count(*) FROM public.alpha_hunter_open_position_snapshots").fetchone()[0]
        protections=conn.execute(
            "SELECT count(*),count(*) FILTER(WHERE trade_permission=false) "
            "FROM public.alpha_hunter_protection_reconciliation_events_v01").fetchone()
        m=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_account_ledger_materialization_events "
            "WHERE run_id=ANY(%s)",(names,)).fetchone()[0]
        if (ep,queue,positions,protections[0],protections[1],m)!=(RUNS*620,RUNS*620,
                                                                     RUNS,RUNS,RUNS,RUNS):
            raise AssertionError(f"Bad downstream, position or protection custody {(ep,queue,positions,protections,m)}")
        if int(conn.execute("SELECT count(*) FROM public.alpha_hunter_profitability_test_activations_v01").fetchone()[0]):
            raise AssertionError("Unintended cohort activation")
        # Test database must be exclusively synthetic; no real orders possible.
        safe=conn.execute("""
            SELECT count(*) FROM public.alpha_hunter_symbol_snapshots
            WHERE trade_permission=true OR run_id=ANY(%s)
              AND payload->>'trade_permission'='true'
        """,(names,)).fetchone()[0]
        if safe:raise AssertionError("Any real-trading path or trade_permission")
    # Failure matrix is executed AFTER full-size and stressed 18-run writes,
    # on the SAME DB, with production-count history still present.
    with psycopg.connect(DSN,autocommit=True) as conn:
        faults_before=local_resource_counters(conn)
    failure=test_postgrest_57014_and_ambiguous_ack()
    with psycopg.connect(DSN,autocommit=True) as conn:
        faults_after=local_resource_counters(conn)
        all_still_pending=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_snapshots "
            "WHERE payload->>'_canonical_publication_state'='VERIFIED'").fetchone()[0]
        if all_still_pending:
            raise AssertionError("False canonical VERIFIED after failure recovery")
        final_obs=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01 "
            "WHERE run_id='synthetic-57014'").fetchone()[0]
        if final_obs!=620:raise AssertionError("Failure retry observation lineage invalid")
    diffs={k:after[k]-before[k] for k in ("wal_bytes","deadlocks","temp_bytes",
                                           "blocks_read","blocks_hit")}
    fault_diff={k:faults_after[k]-faults_before[k] for k in ("wal_bytes","deadlocks","temp_bytes")}
    if diffs["wal_bytes"]<=0 or diffs["deadlocks"]!=0 or fault_diff["deadlocks"]!=0:
        raise AssertionError("WAL missing or observed unexpected deadlock")
    result={
        "status":"PASS_RESEARCH_ONLY_FULL_WIDTH_STRESS_AND_TRANSPORT_FAULTS",
        "pg_major":pg_major,
        "live_production_equivalent":False,
        "exact_all_production_triggers_installed":False,
        "actual_supabase_rls_gateway_tested":False,
        "all_real_trading_authority":False,
        "production_mutation":False,
        "original_cohort_reclassification":False,
        "historical_rows":actual_history,
        "historical_table_bytes":physical_bytes,
        "seed_seconds":seed_secs,
        "concurrent_clients":CLIENTS,"synthetic_scans":RUNS,
        "child_rows":RUNS*62,"strategy_observations":RUNS*620,
        "shadow_quotes":RUNS*310,"protective_reconciliation_events":RUNS,
        "http_child_batches":len(samples),
        "http_batch_p50_ms":percentile_nearest_rank(samples,50),
        "http_batch_p95_ms":percentile_nearest_rank(samples,95),
        "http_batch_p99_ms":percentile_nearest_rank(samples,99),
        "http_batch_max_ms":max(samples),
        "wall_seconds":elapsed,
        "monitor":poll,
        "wal_and_db_activity_delta":diffs,
        "db_size_delta_bytes":size_after-baseline_db_size,
        "failure_matrix":failure,
        "failure_wal_and_deadlocks_delta":fault_diff,
        "false_verified_snapshots":0,
        "independent_DBA_approval":False,
        "independent_security_approval":False,
        "deployment_authorized":False,
        "trade_permission":False
    }
    (OUT/"stress_p0_2_report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,sort_keys=True))
    print("P0.2 research scope PASSED. Real production release remains NO-GO.")

if __name__=="__main__":
    main()
