"""P0 isolated PostgreSQL/PostgREST catalog-chain, realistic-width/concurrency study.

- Requires local container postgres and PostgREST; explicit flag and exact local host.
- Reconstitutes catalog-derived table types, constraints, indexes, and 10 active
  trigger paths. 7 related production trigger functions not yet represented.
- Seeds synthetic historical strategy rows (not real trading data), times three
  concurrent 62-symbol scans via actual HTTP. No production or exchange access.
- Research diagnostic only, NEVER a release/signoff and never trades.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import random
import re
import statistics
import subprocess
import time
import requests
import psycopg
from psycopg.types.json import Jsonb

REPO = Path(__file__).resolve().parents[2]
BASE="http://127.0.0.1:3000"
DSN="host=127.0.0.1 port=5432 dbname=postgres user=postgres password=isolated-only"
OUT=Path("catalog_chain_http_results")
HIST_ROWS=int(os.getenv("AH_P0_HISTORY_ROWS","1640424"))
SCAN_SYMBOLS=62
STRATEGY_IDS=tuple("S"+str(i) for i in range(10))
FIXTURE=REPO/"tests/fixtures/p0_production_catalog_trigger_chain_20261102.sql"


def insist_local():
    if os.getenv("AH_P0_ISOLATED_ONLY")!="1":
        raise RuntimeError("No explicit isolated confirmation")
    if os.getenv("SUPABASE_URL") or os.getenv("BITGET_API_KEY"):
        raise RuntimeError("No production/exchange credentials permitted")
    if HIST_ROWS<1000 or HIST_ROWS>1640424:
        raise RuntimeError("Bounded history rows must be 1000..1640424")
    if not FIXTURE.is_file():
        raise RuntimeError("Exact-schema fixture missing")


def run_ddl():
    env=os.environ.copy()
    env.update({"PGHOST":"127.0.0.1","PGPORT":"5432","PGDATABASE":"postgres",
                "PGUSER":"postgres","PGPASSWORD":"isolated-only"})
    result=subprocess.run(
        ["psql","-v","ON_ERROR_STOP=1","-f",str(FIXTURE)],
        env=env,capture_output=True,text=True,timeout=90)
    if result.returncode:
        raise RuntimeError("Catalog fixture failed: "+result.stderr[-2400:])


def json_noise(seed, n):
    # Distinct deterministic hashes prevent artificial repeated-string
    # compressibility. No private source records enter the fixture.
    return "".join(sha256((str(seed)+":"+str(j)).encode()).hexdigest()
                   for j in range((n+63)//64))[:n]


def sample_strategy(r, s, i):
    # ~1 KB uncompressed strategy JSON, similar to observed 1069-byte
    # pg_column_size strategy_payload sample.
    return {
        "strategy_id":s,"strategy_name":s,"engine_version":"synthetic-v0",
        "status":"SHADOW_CANDIDATE" if int(s[1:])%2 else "WATCH",
        "action":"NO_SAFE_TRADE","direction":"LONG" if i%2 else "SHORT",
        "signal_score":0.1,"score_is_calibrated":False,
        "entry":100.0,"stop":97.0,"target":115.0,"risk":3.0,
        "reward":15.0,"rr":5.0,"geometry_valid":True,
        "persistence":{"strategy_instance_id":f"{r}-{i}-{s}",
                       "first_seen_at_utc":"2026-11-02T11:30:00Z",
                       "state":"WATCH","consecutive_scans":1},
        "evidence":{"synthetic_noise":json_noise(f"{r}:{i}:{s}",660)},
        "checks":{},"reasons":[]}


def payload_for(run, idx, target_width=8421):
    st=[sample_strategy(run,s,idx) for s in STRATEGY_IDS]
    root={
        "symbol":f"TEST{idx:03d}USDT","last_price":100.0,
        "market_phase":"UNKNOWN","opportunity_timing":"NONE",
        "state":"NEUTRAL","trade_permission":False,
        "multi_strategy_engine":{"strategies":st},
        "microstructure":{
            "status":"COMPLETE","source_skew_ms":200,
            "order_book":{"best_bid":99.9,"best_ask":100.1,"midpoint":100.0,
                          "spread_pct":0.2,"depth_imbalance":0.0,
                          "exchange_timestamp_ms":1793619000000},
            "recent_trades":{"trade_imbalance":0.0,
                             "newest_trade_timestamp_ms":1793619000000}}},
    # Payload min width dictated by 10x strategy ~1KB; never truncate
    # meaningful trigger input to attain an artificial target.
    initial=len(json.dumps(root))
    if initial<target_width:
        root["synthetic_padding"]=json_noise((run,idx),target_width-initial)
    return root


def seed_history(conn, rows):
    if rows==0: return
    # Historical synthetic data is loaded without executing downstream
    # decision triggers per historic row; new scan triggers remain enabled.
    conn.execute("""
       ALTER TABLE public.alpha_hunter_strategy_observations_v01
       DISABLE TRIGGER trg_ah_capture_shadow_decision_quote_v01
    """)
    try:
        # Limit seed statement to <=150s; never run this outside local PG.
        conn.execute("SET statement_timeout='150000ms'")
        # Use distinct MD5 blocks to avoid unrealistic repeated-string TOAST.
        conn.execute("""
          INSERT INTO public.alpha_hunter_strategy_observations_v01
            (observation_id,run_id,symbol,observed_at_utc,strategy_id,
             status,action,direction,strategy_payload,evidence)
          SELECT 'h-'||g::text,'historical-run-'||g::text,
            'HISTUSDT',timestamptz '2026-10-01 00:00:00+00'
               +(g*interval '1 second'),
            'S'||(g%10)::text,'WATCH','NO_SAFE_TRADE','SHORT',
            jsonb_build_object('synthetic_noise',
               (SELECT string_agg(md5(g::text||':'||i::text),'')
                FROM generate_series(1,34) i)),
            jsonb_build_object('synthetic_noise',
               (SELECT string_agg(md5(g::text||':e:'||i::text),'')
                FROM generate_series(1,18) i))
          FROM generate_series(1,%s) g
        """,(rows,))
    finally:
        conn.execute("""
            ALTER TABLE public.alpha_hunter_strategy_observations_v01
            ENABLE TRIGGER trg_ah_capture_shadow_decision_quote_v01
        """)
    conn.execute("ANALYZE public.alpha_hunter_strategy_observations_v01")
    conn.execute("SET statement_timeout='15000ms'")


def wait_http_schema():
    for _ in range(90):
        try:
            r=requests.get(BASE+"/alpha_hunter_symbol_snapshots",
                           params={"select":"run_id","limit":"1"},timeout=2)
            if r.status_code==200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError("PostgREST schema cache never loaded")


def write_run(run):
    parent={"run_id":run,"collected_at_utc":"2026-11-02T11:30:00Z",
            "version":"synthetic-shape","product_type":"usdt-futures",
            "symbol_count":SCAN_SYMBOLS,"error_count":0,
            "payload":{"_canonical_publication_state":"PENDING",
                       "validation_identity":{"run_source":"RENDER_CRON",
                       "scientific_fingerprint_sha256":"synthetic-only"}}}
    r=requests.post(BASE+"/alpha_hunter_snapshots",json=parent,
                    headers={"Prefer":"resolution=merge-duplicates,return=minimal"},
                    timeout=10)
    if r.status_code not in (200,201,204):
        raise RuntimeError("parent HTTP "+str(r.status_code)+" "+r.text[:300])
    durations=[]
    for k in range(0,SCAN_SYMBOLS,8):
        rows=[{"run_id":run,"symbol":f"TEST{i:03d}USDT",
               "collected_at_utc":"2026-11-02T11:30:00Z",
               "state":"NEUTRAL","trade_permission":False,
               "last_price":100.0,"payload":payload_for(run,i)}
              for i in range(k,min(k+8,SCAN_SYMBOLS))]
        t=time.perf_counter()
        r=requests.post(BASE+"/alpha_hunter_symbol_snapshots",
                        params={"on_conflict":"run_id,symbol"},json=rows,
                        headers={"Prefer":"resolution=merge-duplicates,return=minimal"},
                        timeout=(3,15))
        durations.append(round(1000*(time.perf_counter()-t),2))
        if r.status_code not in (200,201,204):
            raise RuntimeError("child HTTP "+str(r.status_code)+" "+r.text[:650])
    return run,durations


def main():
    insist_local()
    OUT.mkdir(parents=True,exist_ok=True)
    run_ddl()
    with psycopg.connect(DSN,autocommit=True) as conn:
        ver=int(conn.execute("SHOW server_version_num").fetchone()[0])//10000
        if ver not in (16,17):
            raise RuntimeError("Wrong PostgreSQL major")
        # Exact catalog indexes are present; two independent percentile
        # index variants and full live physical distribution are NOT certified.
        started=time.perf_counter()
        seed_history(conn,HIST_ROWS)
        seed_seconds=round(time.perf_counter()-started,2)
        conn.execute("NOTIFY pgrst,'reload schema'")
        counts={"history":conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01"
        ).fetchone()[0]}
        size_history=conn.execute(
            "SELECT pg_total_relation_size('public.alpha_hunter_strategy_observations_v01')"
        ).fetchone()[0]
    wait_http_schema()
    runs=["test-http-a","test-http-b","test-http-c"]
    started=time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as executor:
        written=list(executor.map(write_run,runs))
    wall_seconds=round(time.perf_counter()-started,3)
    durations=[x for _,times in written for x in times]
    with psycopg.connect(DSN,autocommit=True) as conn:
        totals={}
        for run in runs:
            n=conn.execute("SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s",(run,)).fetchone()[0]
            if n!=62:raise AssertionError("Missing child run "+run)
            totals[run]=n
        obs=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=ANY(%s)",
            (runs,)).fetchone()[0]
        ep=conn.execute("SELECT count(*) FROM public.alpha_hunter_strategy_episodes_v01").fetchone()[0]
        queue=conn.execute("SELECT count(*) FROM private.alpha_hunter_strategy_24h_outcome_queue_v01").fetchone()[0]
        quotes=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_shadow_decision_quotes_v01"
        ).fetchone()[0]
        if (obs,ep,queue,quotes)!=(len(runs)*620,len(runs)*620,len(runs)*620,len(runs)*310):
            raise AssertionError(f"Real trigger census wrong {(obs,ep,queue,quotes)}")
        # Preserve exact physical row width evidence; never fake a pass
        # merely because count is correct.
        sample=conn.execute(
            "SELECT pg_column_size(payload) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s ORDER BY symbol LIMIT 62",
            (runs[0],)).fetchall()
        widths=[v[0] for v in sample]
    report={"status":"CATALOG_TRIGGER_SUBSET_RESEARCH_ONLY",
        "exact_catalog_functions_reused":5,
        "trigger_functions_not_yet_reconstituted":7,
        "postgres_major":ver,"historical_strategy_rows_seeded":counts["history"],
        "history_total_size_bytes":size_history,"history_seed_seconds":seed_seconds,
        "concurrent_clients":3,"runs":totals,"new_observations":obs,
        "episodes":ep,"queued_24h_outcomes":queue,"shadow_quotes":quotes,
        "http_8_row_calls":len(durations),
        "http_batch_p50_ms":round(statistics.median(durations),2),
        "http_batch_p95_ms":round(sorted(durations)[int(.95*(len(durations)-1))],2),
        "http_batch_max_ms":max(durations),"wall_seconds":wall_seconds,
        "symbol_payload_p50_bytes":statistics.median(widths),
        "symbol_payload_p95_bytes":sorted(widths)[int(.95*(len(widths)-1))],
        "catalog_full_chain_complete":False,
        "live_profitability_claim":False,"production_equivalent":False,
        "production_mutation":False,"deployment_authorized":False,
        "trade_permission":False}
    (OUT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))
    print("FULL production trigger-chain and DBA approval remain BLOCKED.")


if __name__=="__main__":
    main()
