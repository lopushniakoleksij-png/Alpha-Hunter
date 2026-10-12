#!/usr/bin/env python3
"""REAL PostgreSQL 16 over TCP, ephemeral GitHub Actions service only.

SAFETY: no production URL / creds, no runtime imports or trading authority.
This is a scoped parity and cost/latency comparison on exact observed affected
3-table DDL/constraints/indexes and verbatim strategy trigger. Parent is a stub.
Not a Supabase/PostgREST/full-R10 monitoring simulation or production perf proof.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "tests/postgres/successor-full-production-schema-fixture.sql"
CANDIDATE = ROOT / "ops/reviews/successor_full_schema_set_based_candidate_v01.sql"
CLOCK = "2026-10-12T12:00:00+00:00"
BASE_DB = "ah_bench_trigger_ephemeral"
NEW_DB = "ah_bench_setbased_ephemeral"
TEST_SIZES = (16, 48, 64, 64, 64)
CONCURRENT_WORKERS = 3
CONCURRENT_ITERATIONS = 3

CHILD_INSERT = """
INSERT INTO public.alpha_hunter_symbol_snapshots(
  run_id,symbol,collected_at_utc,payload,trade_permission,state)
SELECT r.run_id,r.symbol,r.collected_at_utc,r.payload,false,'WATCH'
FROM jsonb_to_recordset(%s::jsonb)
  AS r(run_id text,symbol text,collected_at_utc timestamptz,payload jsonb)
ON CONFLICT(run_id,symbol) DO UPDATE SET payload=excluded.payload
"""
OBS = """SELECT to_jsonb(o)-'created_at' item
 FROM public.alpha_hunter_strategy_observations_v01 o WHERE o.run_id=%s
 ORDER BY observation_id"""
EPISODES = """SELECT to_jsonb(e)-'created_at' item
 FROM public.alpha_hunter_strategy_episodes_v01 e
 WHERE first_observation_id IN (
  SELECT observation_id FROM public.alpha_hunter_strategy_observations_v01
  WHERE run_id=%s) ORDER BY episode_id"""


def guard_dsn() -> str:
    if os.environ.get("AH_SHADOW_POSTGRES_APPROVED") != "EPHEMERAL_GITHUB_ACTIONS_ONLY":
        raise RuntimeError("This synthetic bench is disabled without explicit ephemeral CI opt-in")
    dsn = os.environ.get("AH_SHADOW_PG_DSN", "")
    parts = conninfo_to_dict(dsn)
    if (
        parts.get("host") != "127.0.0.1"
        or parts.get("port") != "5432"
        or parts.get("dbname") != "postgres"
        or parts.get("user") != "bench"
    ):
        raise RuntimeError("Refuse any host/account/DB except 127.0.0.1:5432/postgres as bench")
    if any(os.environ.get(k) for k in ("SUPABASE_SERVICE_ROLE_KEY", "BITGET_API_KEY", "BITGET_SECRET_KEY")):
        raise RuntimeError("Do not run this test with production exchange/Supabase credentials present")
    return dsn


def synthetic_entropy(label: str, size: int) -> str:
    # Irregular deterministic SHA strings; avoids unrealistic 100%-compressible 'x' data.
    return "".join(hashlib.sha256(f"{label}|{n}".encode()).hexdigest()
                   for n in range(math.ceil(size / 64)))[:size]


def sample_payload(run_id: str, i: int) -> dict:
    return {
        "last_price": str(1.5 + i / 1000),
        "market_phase": "IGNITION" if i % 2 else "PRE_MOVE",
        "opportunity_timing": "EARLY",
        "timeframes": {
            "15m": {"trend": "UP", "evidence": synthetic_entropy(f"{run_id}|tf|{i}", 2048)},
            "1H": {"trend": "UP", "support": .88, "resistance": 1.21},
            "4H": {"trend": "RANGE"},
        },
        "multi_strategy_engine": {
            "strategies": [
                {
                    "strategy_id": f"S{j+1}", "strategy_name": f"synthetic S{j+1}",
                    "engine_version": "benchmark-only-v0.1",
                    "status": "WATCH" if j == 0 else "SHADOW_CANDIDATE" if j == 1 else "NO_SAFE_TRADE",
                    "action": "WAIT_FOR_TRIGGER" if j < 2 else "NO_SAFE_TRADE",
                    "direction": "LONG" if j % 2 == 0 else "SHORT",
                    "signal_score": float(j + 1.125),
                    "score_is_calibrated": bool(j % 2),
                    "entry": "1.5", "stop": "1.4", "target": "1.8",
                    "risk": "0.1", "reward": "0.3", "rr": "3.0",
                    "distance_to_entry_pct": "0.22",
                    "geometry_valid": j % 2 == 0,
                    "evidence": {"study": "none", "synthetic": synthetic_entropy(f"{run_id}|{i}|{j}", 950)},
                    "checks": {"source": "SYNTHETIC_NOT_MARKET"}, "reasons": [] if j < 2 else ["NO_SIGNAL"],
                    "persistence": {
                        "state": "SEEN" if j < 2 else "NONE",
                        "strategy_instance_id": f"{run_id}|{i}|{j}" if j < 2 else "",
                        "first_seen_at_utc": CLOCK if j < 2 else "",
                        "consecutive_scans": "2" if j < 2 else "0",
                    },
                } for j in range(10)
            ]
        },
    }


def synthetic_rows(run_id: str, count: int) -> list[dict]:
    return [{
        "run_id": run_id,
        "symbol": f"SYNTH{i:04d}USDT",
        "collected_at_utc": CLOCK,
        "payload": sample_payload(run_id, i),
    } for i in range(count)]


def make_conn(dsn: str, dbname: str) -> psycopg.Connection:
    cx = psycopg.connect(make_conninfo(dsn, dbname=dbname), connect_timeout=6)
    # Mirrors production service-role PostgreSQL timeout WITHOUT modifying DB role.
    cx.execute("SET statement_timeout = '12s'")
    cx.commit()
    return cx


def setup(dsn: str, candidate: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as admin:
        version = admin.execute("SHOW server_version_num").fetchone()[0]
        if not str(version).startswith("16"):
            raise RuntimeError(f"Expected isolated PG16 server, found {version}")
        for name in (BASE_DB, NEW_DB):
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    fixture = SCHEMA.read_text()
    for name in (BASE_DB, NEW_DB):
        with make_conn(dsn, name) as cx:
            cx.execute(fixture)
            if name == NEW_DB:
                cx.execute("DROP TRIGGER trg_ah_capture_strategy_observations_v01 ON public.alpha_hunter_symbol_snapshots")
    if candidate.upper().count("INSERT INTO") != 2:
        raise AssertionError("Candidate should only have two explicit INSERT SELECT statements")


def do_ingest(dsn: str, dbname: str, run_id: str, records: list[dict],
              statements: list[str], *, invalid_direction: bool = False) -> float:
    # A single transaction spans parent stub, child write and both strategy tables.
    if invalid_direction:
        records = json.loads(json.dumps(records))
        records[0]["payload"]["multi_strategy_engine"]["strategies"][0]["direction"] = "INVALID"
    with make_conn(dsn, dbname) as cx:
        start = time.perf_counter()
        with cx.transaction():
            cx.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES (%s) ON CONFLICT DO NOTHING", (run_id,))
            cx.execute(CHILD_INSERT, (json.dumps(records, separators=(",", ":")),))
            for statement in statements:
                cx.execute(statement.replace("$1", "%s"), (run_id,))
        return (time.perf_counter()-start)*1000


def extract(dsn: str, dbname: str, run_id: str) -> dict:
    with make_conn(dsn, dbname) as cx:
        return {
            "observations": [row[0] for row in cx.execute(OBS, (run_id,))],
            "episodes": [row[0] for row in cx.execute(EPISODES, (run_id,))],
        }


def has_no_orphans(dsn: str, dbname: str, run_id: str) -> None:
    with make_conn(dsn, dbname) as cx:
        for table in ("alpha_hunter_snapshots", "alpha_hunter_symbol_snapshots",
                      "alpha_hunter_strategy_observations_v01"):
            n = cx.execute(sql.SQL("SELECT count(*) FROM public.{} WHERE run_id=%s").format(
                sql.Identifier(table)), (run_id,)).fetchone()[0]
            if n != 0:
                raise AssertionError(f"Failed rollback: {table} contains {n} rows")


def exact_comparison(dsn: str, run_id: str, count: int) -> None:
    base = extract(dsn, BASE_DB, run_id)
    new = extract(dsn, NEW_DB, run_id)
    if base != new:
        for k in ("observations", "episodes"):
            if base[k] != new[k]:
                for n, (x, y) in enumerate(zip(base[k], new[k])):
                    if x != y:
                        raise AssertionError(f"{k} row {n} mismatched: {set(x) ^ set(y)}")
                raise AssertionError(f"{k} cardinality mismatch")
    if len(base["observations"]) != count*10 or len(base["episodes"]) != count*2:
        raise AssertionError(f"Missing expected immutable records at {run_id}")
    if any(row["trade_permission"] or row["production_permission"]
           or row["production_promotion_permitted"] or row["order_path"] != "NONE"
           for row in base["observations"]):
        raise AssertionError("Unexpected trade permissions in synthetic evidence")


def distribution(vals: list[float]) -> dict:
    ordered = sorted(vals)
    return {"count":len(vals), "min_ms":round(ordered[0],1),
            "p50_ms":round(statistics.median(ordered),1),
            "observed_p95_ms":round(ordered[min(len(ordered)-1, math.ceil(.95*len(ordered))-1)],1),
            "max_ms":round(ordered[-1],1)}


def side_sizes(dsn: str, dbname: str) -> dict:
    with make_conn(dsn, dbname) as cx:
        avg = cx.execute("""SELECT count(*),round(avg(pg_column_size(payload)))::bigint,
                    pg_total_relation_size('public.alpha_hunter_symbol_snapshots'::regclass)
                    FROM public.alpha_hunter_symbol_snapshots""").fetchone()
        counts = cx.execute("""SELECT (SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01),
              (SELECT count(*) FROM public.alpha_hunter_strategy_episodes_v01)""").fetchone()
        return {"symbols":avg[0],"mean_pg_column_size_payload_bytes":avg[1],
                "symbol_table_total_bytes":avg[2],
                "strategy_observations":counts[0],"strategy_episodes":counts[1]}


def main() -> None:
    dsn=guard_dsn()
    text=CANDIDATE.read_text()
    statements=[s.strip() for s in text.split("-- NEXT STATEMENT") if s.strip()]
    if len(statements)!=2: raise AssertionError("Expected exactly two set-based SQL statements")
    setup(dsn,text)
    results: dict[str,list[float]]={"baseline_serial":[],"candidate_serial":[],
                                   "baseline_concurrent":[],"candidate_concurrent":[]}
    original_run_ids=[]
    for i,n in enumerate(TEST_SIZES):
        run_id=f"pg16-shadow-serial-{i}"
        records=synthetic_rows(run_id,n)
        # Alternate warm vs challenger order to reduce biased cache advantage.
        order=[(BASE_DB,[],"baseline_serial"),(NEW_DB,statements,"candidate_serial")]
        if i%2: order.reverse()
        for dbname,sqls,k in order:
            results[k].append(do_ingest(dsn,dbname,run_id,records,sqls))
        exact_comparison(dsn,run_id,n)
        original_run_ids.append((run_id,records))
    run_id,records=original_run_ids[-1]
    before=extract(dsn,BASE_DB,run_id)
    do_ingest(dsn,BASE_DB,run_id,records,[])
    do_ingest(dsn,NEW_DB,run_id,records,statements)
    if extract(dsn,BASE_DB,run_id)!=before or extract(dsn,NEW_DB,run_id)!=before:
        raise AssertionError("Duplicate replay mutated immutable strategy evidence")
    for dbname,statements_for_db in [(BASE_DB,[]),(NEW_DB,statements)]:
        failed_run=f"pg16-shadow-forced-rollback-{dbname}"
        try:
            do_ingest(dsn,dbname,failed_run,synthetic_rows(failed_run,2),
                      statements_for_db,invalid_direction=True)
        except psycopg.errors.CheckViolation:
            pass
        else:
            raise AssertionError("Did not reject invalid strategy direction")
        has_no_orphans(dsn,dbname,failed_run)

    def work(w: int, i: int, dbname: str, sqls: list[str], key: str):
        run_id=f"pg16-shadow-concurrent-{w}-{i}"
        rows=synthetic_rows(run_id,64)
        duration=do_ingest(dsn,dbname,run_id,rows,sqls)
        return (run_id, duration,key)
    tasks=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS*2) as pool:
        # Different run IDs per worker/iteration; write no production data.
        for i in range(CONCURRENT_ITERATIONS):
            for w in range(CONCURRENT_WORKERS):
                tasks.append(pool.submit(work,w,i,BASE_DB,[],"baseline_concurrent"))
                tasks.append(pool.submit(work,w,i,NEW_DB,statements,"candidate_concurrent"))
        for future in concurrent.futures.as_completed(tasks):
            rid,duration,key=future.result()
            results[key].append(duration)
    for i in range(CONCURRENT_ITERATIONS):
        for w in range(CONCURRENT_WORKERS):
            exact_comparison(dsn,f"pg16-shadow-concurrent-{w}-{i}",64)
    sizes={side:side_sizes(dsn,dbname) for side,dbname in
           [("baseline",BASE_DB),("candidate",NEW_DB)]}
    if sizes["baseline"]!=sizes["candidate"]:
        # TOAST/index physical relation size may vary due to access/replay;
        # compare row counts and payload averages, not physical file size.
        if any(sizes["baseline"][k]!=sizes["candidate"][k] for k in
               ("symbols","mean_pg_column_size_payload_bytes","strategy_observations","strategy_episodes")):
            raise AssertionError("Storage/parity mismatch across compared databases")
    report={
        "gate":"REAL_POSTGRES_16_TCP_FULL_AFFECTED_TABLES_SYNTHETIC",
        "scientific_status":"REVIEW_ONLY_NOT_A_LIVE_MONITORING_OR_PRODUCTION_THROUGHPUT_PASS",
        "host":"isolated-GitHub-Actions-postgres-16-service",
        "statement_timeout":"12s_connection_local_only",
        "real_postgres_wal_toast_indexes":True,
        "postgres_to_postgrest_http":False,
        "production_scale_or_multi_tenant_contention":False,
        "exact_source_trigger_and_affected_columns":True,
        "parent_schema":"STUB_FK_ONLY",
        "strategy_columns_identical_except_created_at":True,
        "repeat_idempotency":True,
        "forced_transaction_rollback":True,
        "synthetic_serial_sizes":list(TEST_SIZES),
        "concurrent_writes_per_side":CONCURRENT_WORKERS*CONCURRENT_ITERATIONS,
        "timings":{key:distribution(value) for key,value in results.items()},
        "resulting_rows":sizes,
        "frozen_R10_touched":False,
        "production_DDL_touched":False,
        "real_order_authority":False,
    }
    print("P0_REAL_PG16_SHADOW_BENCHMARK "+json.dumps(report,sort_keys=True))
    if not all(v["max_ms"]<12000 for v in report["timings"].values()):
        raise AssertionError("Isolated 12s statement-time-budget proxy exceeded")
    print("ISOLATED_PARITY_AND_ROLLBACK_VERIFIED_NOT_PRODUCTION_AUTHORIZED")


if __name__=="__main__":
    main()
