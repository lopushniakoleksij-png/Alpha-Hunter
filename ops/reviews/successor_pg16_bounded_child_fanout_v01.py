#!/usr/bin/env python3
"""P2 *only isolated* PG16 TCP benchmark: bulk vs bounded, unchanged trigger.

No Supabase calls and no production credentials. Both databases use the
verbatim actual strategy trigger and the full recorded 3 affected-table
schema; all child data synthetic. Separate per-batch commits intentionally
have partial-write risk. Source readback cannot prove paper monitoring.
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import time

import psycopg
from psycopg import sql

from successor_pg16_tcp_benchmark_v01 import (
    guard_dsn, make_conn, BASE_DB, CHILD_INSERT, SCHEMA,
    OBS, EPISODES, synthetic_rows
)
from successor_bounded_child_writer_v01 import (
    persist_and_verify_bounded_children,SuccessorChildStageIncomplete
)

BATCH_DB="ah_bench_bounded_ephemeral"
ITERATIONS=3
SYMBOL_COUNT=63
BATCH_SIZE=12


def initialize(dsn):
    with psycopg.connect(dsn,autocommit=True) as admin:
        if not str(admin.execute("SHOW server_version_num").fetchone()[0]).startswith("16"):
            raise RuntimeError("PG16 ephemeral server required")
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(BATCH_DB)))
    with make_conn(dsn,BATCH_DB) as db:
        db.execute(SCHEMA.read_text())
        count=db.execute("SELECT count(*) FROM pg_trigger WHERE tgname='trg_ah_capture_strategy_observations_v01'").fetchone()[0]
        if count!=1:raise AssertionError("Real trigger missing in batched shadow database")


def insert_parent(dsn,dbname,rid):
    with make_conn(dsn,dbname) as db:
        db.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES(%s) ON CONFLICT DO NOTHING",(rid,))


def project(dsn,dbname,run_id):
    with make_conn(dsn,dbname) as db:
        result={}
        for key,query in (("observations",OBS),("episodes",EPISODES)):
            result[key]=[v[0] for v in db.execute(query,(run_id,))]
        result["symbols"]=[v[0] for v in db.execute(
            "SELECT symbol FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s ORDER BY symbol",(run_id,))]
        return result


def run_bench(dsn,db_name,run_id,rows,chunk_size):
    insert_parent(dsn,db_name,run_id)
    times=[]
    def write(batch):
        began=time.perf_counter()
        with make_conn(dsn,db_name) as db:
            db.execute(CHILD_INSERT,(json.dumps(batch,separators=(",",":")),))
        times.append((time.perf_counter()-began)*1000)
    def read(rid):
        with make_conn(dsn,db_name) as db:
            return [{"symbol":s,"payload":p} for s,p in db.execute(
                "SELECT symbol,payload FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s ORDER BY symbol",(rid,))]
    if chunk_size is None:
        write(rows)
        return {"statement_ms":times,"total_ms":sum(times),"receipt":None}
    start=time.perf_counter()
    proof=persist_and_verify_bounded_children(
        rows,write_batch=write,read_back=read,batch_size=chunk_size)
    return {"statement_ms":times,"total_ms":(time.perf_counter()-start)*1000,
            "receipt":proof}


def check_parity(dsn,run,count):
    baseline=project(dsn,BASE_DB,run)
    alternate=project(dsn,BATCH_DB,run)
    if baseline!=alternate:
        raise AssertionError("BULK_VS_BATCH_EVIDENCE_DIFFERENCE")
    if len(alternate["symbols"])!=count or len(alternate["observations"])!=10*count or len(alternate["episodes"])!=2*count:
        raise AssertionError("BULK_VS_BATCH_SOURCE_EVIDENCE_COUNT_MISMATCH")
    if any(x["trade_permission"] or x["production_permission"] or
           x["production_promotion_permitted"] or x["order_path"]!="NONE"
           for x in alternate["observations"]):
        raise AssertionError("UNEXPECTED_TRADING_PERMISSION")
    return len(alternate["observations"]),len(alternate["episodes"])


def main():
    dsn=guard_dsn()
    initialize(dsn)
    bulk_time=[]
    chunked_time=[]
    chunked_max_statement=[]
    all_obs=all_episodes=0
    for i in range(ITERATIONS):
        rid=f"synthetic-p2-63-children-{i}"
        rows=synthetic_rows(rid,SYMBOL_COUNT)
        # Ensure strict payload identity, as canonical PostgREST children do.
        for row in rows:
            row["payload"]["symbol"]=row["symbol"]
        # Alternate first runner to reduce basic warm-cache advantage.
        sides=[("bulk",BASE_DB,None),("bounded",BATCH_DB,BATCH_SIZE)]
        if i%2:sides.reverse()
        for mode,dbname,size in sides:
            result=run_bench(dsn,dbname,rid,rows,size)
            if mode=="bulk":bulk_time.append(result["total_ms"])
            else:
                assert result["receipt"]["persisted_symbol_count"]==SYMBOL_COUNT
                assert result["receipt"]["trade_permission"] is False
                chunked_time.append(result["total_ms"])
                chunked_max_statement.append(max(result["statement_ms"]))
        obs,episodes=check_parity(dsn,rid,SYMBOL_COUNT)
        all_obs+=obs;all_episodes+=episodes

    # Deliberately fail after the second successful separate commit: NEVER
    # return a success receipt. Repair is candidate-only and NOT atomic.
    rid="synthetic-p2-interrupted-stage"
    rows=synthetic_rows(rid,SYMBOL_COUNT)
    for row in rows:row["payload"]["symbol"]=row["symbol"]
    insert_parent(dsn,BATCH_DB,rid)
    count=0
    def fail_after_2(batch):
        nonlocal count
        if count==2:raise TimeoutError("synthetic postgrest outage after 2 batches")
        with make_conn(dsn,BATCH_DB) as db:
            db.execute(CHILD_INSERT,(json.dumps(batch,separators=(",",":")),))
        count+=1
    def read_back(rid):
        with make_conn(dsn,BATCH_DB) as db:
            return [{"symbol":s,"payload":p} for s,p in db.execute(
                "SELECT symbol,payload FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s ORDER BY symbol",(rid,))]
    try:
        persist_and_verify_bounded_children(rows,write_batch=fail_after_2,
                                           read_back=read_back,batch_size=BATCH_SIZE)
    except SuccessorChildStageIncomplete:
        pass
    else:
        raise AssertionError("PARTIAL_CHILD_WRITE_WRONGLY_CLASSIFIED_COMPLETE")
    partial=project(dsn,BATCH_DB,rid)
    if len(partial["symbols"])!=24 or len(partial["observations"])!=240 or len(partial["episodes"])!=48:
        raise AssertionError("PARTIAL_WRITE_COHERENCE_FAILED")
    # Replaying same deterministic IDs under isolated DB must be idempotent;
    # no historical production backfill is executed or authorized.
    repaired=run_bench(dsn,BATCH_DB,rid,rows,BATCH_SIZE)
    if repaired["receipt"]["status"]!="PERSISTED_SOURCE_CHILD_MANIFEST_VERIFIED_NOT_PAPER_MONITORING":
        raise AssertionError("ISOLATED_RETRY_DID_NOT_VERIFY")
    final=project(dsn,BATCH_DB,rid)
    if (len(final["symbols"]),len(final["observations"]),len(final["episodes"]))!=(63,630,126):
        raise AssertionError("ISOLATED_REPLAY_EVIDENCE_WRONG")

    print("P2_REAL_PG16_BOUNDED_CHILD_FANOUT "+
          json.dumps({
           "scope":"ISOLATED_SYNTHETIC_ONLY_NO_POSTGREST",
           "database_type":"two_independent_ephemeral_PG16_databases_same_VERBATIM_trigger",
           "fresh_63_symbol_runs_per_side":ITERATIONS,
           "strategy_observations_compared":all_obs,
           "strategy_episodes_compared":all_episodes,
           "all_deterministic_child_and_strategy_fields_match":True,
           "bulk_total_latency_ms":[round(v,1) for v in bulk_time],
           "bounded_total_latency_ms":[round(v,1) for v in chunked_time],
           "bounded_worst_statement_ms":[round(v,1) for v in chunked_max_statement],
           "bulk_median_total_ms":round(statistics.median(bulk_time),1),
           "bounded_median_total_ms":round(statistics.median(chunked_time),1),
           "separate_requests_per_full_bounded_run":6,
           "partial_child_write_after_two_committed_batches":24,
           "partial_strategy_observations":240,
           "no_success_receipt_on_failure":True,
           "isolated_replay_idempotent":True,
           "real_postgrest_HTTP_or_resource_contention_reproduced":False,
           "production_timeout_repair_proved":False,
           "protection_35m_proved":False,
           "R10_untouched":True,"exchange_order_authority":False
          },sort_keys=True))
    print("P2_BOUNDED_SYMBOL_WRITE_PARITY_VERIFIED_REVIEW_ONLY")

if __name__=="__main__":
    main()
