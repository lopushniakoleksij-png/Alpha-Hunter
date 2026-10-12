#!/usr/bin/env python3
"""P2 real PostgREST over HTTP and actual PG16, in GITHUB EPHEMERAL CI ONLY.

Benchmarks two ISOLATED databases with the 2026-10-12 actual 3-table DDL:
baseline: verbatim production AFTER per-row trigger;
candidate: trigger dropped ONLY in disposable DB; same evidence projected in
a separate same-run transaction AFTER HTTP child commit. This architectural
gap is significant and intentionally fail-visible; NO future production plan
may assert monitoring completion on just a child or strategy write.

DOES NOT simulate real Supabase shared tenancy, live 1GB+ data, RLS/pooler,
network location, all feature/readiness/paper stages or 35m quote receipts.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import sys
import statistics
import time
from pathlib import Path
import psycopg
from psycopg import sql
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from successor_pg16_tcp_benchmark_v01 import (
    CANDIDATE, SCHEMA, guard_dsn, make_conn,
    synthetic_rows, do_ingest, extract as projection,
)
# IMPORTANT: pristine DBs separate from the prior contract/receipt test's data.
BASE_DB="ah_pgrst_trigger_fresh_ephemeral"
NEW_DB="ah_pgrst_setbased_fresh_ephemeral"
from successor_bounded_child_writer_v01 import child_manifest_sha256

API = {"baseline": "http://127.0.0.1:3000", "candidate": "http://127.0.0.1:3001"}
PRELOAD_RUNS=24
PRELOAD_SYMBOLS=63
WORKERS_PER_SIDE=3
HTTP_RUNS_PER_SIDE=6
MAX_HTTP_READ_SECONDS=15
CANDIDATE_STATEMENTS=tuple(
    x.strip() for x in CANDIDATE.read_text().split("-- NEXT STATEMENT") if x.strip()
)
assert len(CANDIDATE_STATEMENTS)==2
SAFE_NAME_PREFIX="synthetic-pgrst-p2-"


def only_local_endpoints():
    guard_dsn()
    for host in API.values():
        if not host.startswith("http://127.0.0.1:"):
            raise RuntimeError("Local-only PostgREST enforcement failed")


def pg_candidates_for_local_ci(dsn):
    """Two FRESH identical schema/row-count DBs; add only local bench_api role.

    This fixes the experimental confound from prior tests, which used the
    existing ah_bench* DBs and had different fixture rows by test end.
    """
    with psycopg.connect(dsn,autocommit=True) as admin:
        for name in (BASE_DB,NEW_DB):
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    for dbname in (BASE_DB,NEW_DB):
        with make_conn(dsn,dbname) as cx:
            cx.execute(SCHEMA.read_text())
            if dbname==NEW_DB:
                # ISOLATED candidate only: never a Supabase migration.
                cx.execute("DROP TRIGGER trg_ah_capture_strategy_observations_v01 ON public.alpha_hunter_symbol_snapshots")
            cx.execute("""
                DO $$BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='bench_api') THEN
                    CREATE ROLE bench_api NOLOGIN;
                  END IF;
                END$$;
                GRANT USAGE ON SCHEMA public TO bench_api;
                GRANT SELECT, INSERT, UPDATE ON TABLE
                  public.alpha_hunter_symbol_snapshots TO bench_api;
                ALTER DATABASE """+dbname+""" SET statement_timeout='12s';
            """)


def transform(rows):
    """Use identical payloads as full-schema production-trigger isolated tests."""
    return [dict(row,payload=dict(row["payload"],symbol=row["symbol"])) for row in rows]


def sql_candidate(dsn, run_id):
    with make_conn(dsn,NEW_DB) as cx:
        # Both immutable strategy tables are committed in ONE separate
        # transaction, not atomic with PostgREST symbol table transaction.
        with cx.transaction():
            for statement in CANDIDATE_STATEMENTS:
                query="\n".join(line for line in statement.splitlines()
                                if not line.lstrip().startswith("--"))
                query=query.replace("$1","%s")
                if query.count("%s")!=1:
                    raise AssertionError("Unexpected candidate SQL parameter count")
                cx.execute(query,(run_id,))


def insert_parent(dsn,run_id):
    for name in (BASE_DB,NEW_DB):
        with make_conn(dsn,name) as cx:
            cx.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES (%s) ON CONFLICT DO NOTHING",(run_id,))


def http(method,uri,payload=None):
    req=Request(uri,method=method,headers={
        "Content-Type":"application/json",
        "Accept":"application/json",
        "Prefer":"resolution=merge-duplicates,return=minimal"
    },data=(json.dumps(payload,separators=(",",":")).encode() if payload is not None else None))
    began=time.perf_counter()
    try:
        with urlopen(req,timeout=MAX_HTTP_READ_SECONDS) as response:
            body=response.read()
            status=response.status
    except HTTPError as exc:
        raise RuntimeError(f"ISOLATED_HTTP_{exc.code}: {exc.read(500)!r}") from exc
    except URLError as exc:
        raise RuntimeError(f"ISOLATED_HTTP_TRANSPORT_FAILED: {exc}") from exc
    if status not in (200,201,204):
        raise RuntimeError(f"HTTP_UNEXPECTED_STATUS_{status}")
    return (json.loads(body) if body else None), (time.perf_counter()-began)*1000


def http_write_readback(mode,run_id,rows):
    base=API[mode]+"/alpha_hunter_symbol_snapshots"
    _,write_ms=http("POST",base+"?on_conflict=run_id,symbol",rows)
    params=urlencode({"select":"symbol,payload","run_id":"eq."+run_id,
                     "order":"symbol.asc","limit":"2000"})
    read_rows,read_ms=http("GET",base+"?"+params)
    if not isinstance(read_rows,list) or len(read_rows)!=len(rows):
        raise AssertionError(f"{mode}: CHILD_HTTP_COUNT_INCOMPLETE")
    if any(x["symbol"]!=x["payload"].get("symbol") for x in read_rows):
        raise AssertionError("CHILD_SOURCE_IDENTITY_MISMATCH")
    if child_manifest_sha256(read_rows)!=child_manifest_sha256(rows):
        raise AssertionError("CHILD_SOURCE_PAYLOAD_DIGEST_MISMATCH")
    return write_ms,read_ms


def wait_for_http():
    for mode,base in API.items():
        for _ in range(24):
            try:
                req=Request(base+"/alpha_hunter_symbol_snapshots?select=symbol&limit=1")
                with urlopen(req,timeout=2) as resp:
                    if resp.status==200:break
            except (HTTPError,URLError,TimeoutError):
                time.sleep(.5)
        else:
            raise AssertionError(f"ISOLATED_PGRST_NOT_READY_{mode}")


def exact_comparison(dsn,run_id,expected):
    """Run-local full-row baseline equality, ignoring creation timestamps."""
    left=projection(dsn,BASE_DB,run_id)
    right=projection(dsn,NEW_DB,run_id)
    if left!=right:
        raise AssertionError("BASELINE_CANDIDATE_FULL_STRATEGY_EVIDENCE_MISMATCH")
    if len(left["observations"])!=expected*10 or len(left["episodes"])!=expected*2:
        raise AssertionError("EXACT_SOURCE_STRATEGY_ROW_COUNT_MISMATCH")


def preload(dsn):
    """Both databases same synthetic history/row IDs, candidate projected."""
    start=time.perf_counter()
    for j in range(PRELOAD_RUNS):
        run=SAFE_NAME_PREFIX+f"background-{j}"
        rows=transform(synthetic_rows(run,PRELOAD_SYMBOLS))
        do_ingest(dsn,BASE_DB,run,rows,[])
        do_ingest(dsn,NEW_DB,run,rows,[])
        sql_candidate(dsn,run)
    exact_comparison(dsn,SAFE_NAME_PREFIX+"background-0",PRELOAD_SYMBOLS)
    exact_comparison(dsn,SAFE_NAME_PREFIX+f"background-{PRELOAD_RUNS-1}",PRELOAD_SYMBOLS)
    sizes={}
    for mode,dbname in (("baseline",BASE_DB),("candidate",NEW_DB)):
        with make_conn(dsn,dbname) as cx:
            v=cx.execute("""SELECT
                pg_total_relation_size('public.alpha_hunter_symbol_snapshots'),
                pg_total_relation_size('public.alpha_hunter_strategy_observations_v01'),
                pg_total_relation_size('public.alpha_hunter_strategy_episodes_v01'),
                (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots),
                (SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01)
            """).fetchone()
            sizes[mode]=dict(zip(("symbol_relation_bytes","observation_relation_bytes",
                     "episode_relation_bytes","child_count","strategy_obs_count"),v))
    # Background history MUST have identical cardinality in both DBs.
    for k in ("child_count","strategy_obs_count"):
        if sizes["baseline"][k]!=sizes["candidate"][k]:
            raise AssertionError("UNFAIR_PRELOAD_"+k)
    return sizes,round((time.perf_counter()-start)*1000,1)


def evaluate(mode,run,rows,dsn):
    start=time.perf_counter()
    # The parent stub was created independently in the *two* benchmark DBs.
    child_ms,read_ms=http_write_readback(mode,run,rows)
    projection_ms=0.
    if mode=="candidate":
        began=time.perf_counter()
        sql_candidate(dsn,run)
        projection_ms=(time.perf_counter()-began)*1000
    total_ms=(time.perf_counter()-start)*1000
    return {
        "mode":mode,"run_id":run,"http_child_post_ms":round(child_ms,2),
        "http_child_get_ms":round(read_ms,2),
        "out_of_band_projection_ms":round(projection_ms,2),
        "total_child_to_evidence_ms":round(total_ms,2)
    }


def range_report(values):
    x=sorted(values)
    return {"count":len(x),"p50_ms":round(statistics.median(x),1),
            "observed_p95_ms":round(x[min(len(x)-1,math.ceil(.95*len(x))-1)],1),
            "max_ms":round(x[-1],1)}


def main():
    only_local_endpoints()
    dsn=guard_dsn()
    # The --prepare phase has ALREADY created pristine databases and roles
    # BEFORE the two PostgREST containers started. Never create them twice.
    wait_for_http()
    sizes,preload_ms=preload(dsn)
    runs={}
    for n in range(HTTP_RUNS_PER_SIDE):
        run=SAFE_NAME_PREFIX+f"http-{n}"
        insert_parent(dsn,run)
        runs[run]=transform(synthetic_rows(run,63))

    timings=[]
    # Paired submission and bounded pool: real HTTP and SQL contention,
    # not just serial psycopg statements.
    with ThreadPoolExecutor(max_workers=WORKERS_PER_SIDE*2) as pool:
        future_map={}
        for run,rows in runs.items():
            for mode in ("baseline","candidate"):
                future_map[pool.submit(evaluate,mode,run,rows,dsn)]=(mode,run)
        for f in as_completed(future_map):
            timings.append(f.result())

    for run in runs:
        exact_comparison(dsn,run,63)

    # One idempotent HTTP replay on BOTH versions must not duplicate
    # observations/episodes. The test never replays production run IDs.
    replay=next(iter(runs))
    before=projection(dsn,BASE_DB,replay)
    assert before==projection(dsn,NEW_DB,replay)
    evaluate("baseline",replay,runs[replay],dsn)
    evaluate("candidate",replay,runs[replay],dsn)
    assert before==projection(dsn,BASE_DB,replay)==projection(dsn,NEW_DB,replay)

    # Deliberately fail candidate HTTP connection prior to any strategy
    # projection, with its parent already committed. This MUST be visible as
    # an incomplete stage, NEVER an immutable scientific outcome/quote receipt.
    failed=SAFE_NAME_PREFIX+"http-transport-failure"
    insert_parent(dsn,failed)
    refused=False
    try:
        http("POST","http://127.0.0.1:3999/alpha_hunter_symbol_snapshots",
             transform(synthetic_rows(failed,63)))
    except RuntimeError as exc:
        if "ISOLATED_HTTP_TRANSPORT_FAILED" in str(exc):refused=True
        else:raise
    if not refused:raise AssertionError("Transport fault not detected")
    with make_conn(dsn,NEW_DB) as cx:
        c=cx.execute("SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=%s",(failed,)).fetchone()[0]
        assert c==0

    measurements={}
    for mode in ("baseline","candidate"):
        rows=[t for t in timings if t["mode"]==mode]
        measurements[mode]={
            key:range_report([t[key] for t in rows])
            for key in ("http_child_post_ms","http_child_get_ms",
                        "out_of_band_projection_ms","total_child_to_evidence_ms")
        }
    report={
        "gate":"ISOLATED_PG16_REAL_POSTGREST_API_CONCURRENT_FANOUT_REVIEW_ONLY",
        "clients_per_side":WORKERS_PER_SIDE,
        "http_63_symbol_runs_per_side":HTTP_RUNS_PER_SIDE,
        "strategy_observations_verified":HTTP_RUNS_PER_SIDE*63*10,
        "strategy_episodes_verified":HTTP_RUNS_PER_SIDE*63*2,
        "preloaded_symbol_rows_per_side":PRELOAD_RUNS*PRELOAD_SYMBOLS,
        "pristine_identical_starting_databases":True,
        "preload_elapsed_ms":preload_ms,
        "synthetic_relation_sizes":sizes,
        "measurements":measurements,
        "real_postgrest_http_layer_tested":True,
        "http_client_timeout_s":MAX_HTTP_READ_SECONDS,
        "db_session_statement_timeout_s":12,
        "original_per_row_trigger_unchanged_in_baseline":True,
        "candidate_trigger_suppressed_ONLY_in_isolated_db":True,
        "all_strategy_rows_exact_parity_excluding_generated_created_at":True,
        "same_run_replay_idempotent":True,
        "http_transport_fail_closed_without_strategy_projection":True,
        "candidate_post_http_projection_is_non_atomic_with_child_write":True,
        "production_postgrest_pooler_or_1GB_scale_reproduced":False,
        "independent_paper_position_receipt_or_35m_proved":False,
        "successor_deployment_authorized":False,
        "production_changed":False,"live_order_authority":False
    }
    print("P2_REAL_POSTGREST_CONTENTION_SHADOW "+json.dumps(report,sort_keys=True))
    print("P2_HTTP_STRATEGY_PARITY_PASS_STILL_NOT_PRODUCTION_SAFE")

if __name__=="__main__":
    if len(sys.argv)==2 and sys.argv[1]=="--prepare":
        only_local_endpoints()
        pg_candidates_for_local_ci(guard_dsn())
        print("P2_LOCAL_DB_HTTP_ROLE_PREP_PASS")
    elif len(sys.argv)==1:
        main()
    else:
        raise SystemExit("Only --prepare or no arguments are permitted")
