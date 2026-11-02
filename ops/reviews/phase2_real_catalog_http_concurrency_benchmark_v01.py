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
    if os.getenv("AH_P0_PARENT_LEDGER_COMPLETE")=="1":
        addendum=REPO/"tests/fixtures/p0_catalog_parent_ledger_protection_addendum_20261102.sql"
        rr=subprocess.run(["psql","-v","ON_ERROR_STOP=1","-f",str(addendum)],
            env=env,capture_output=True,text=True,timeout=90)
        if rr.returncode:
            raise RuntimeError("Catalog parent/ledger addendum failed: "+rr.stderr[-2400:])


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
                             "newest_trade_timestamp_ms":1793619000000}}}
    # Payload min width dictated by 10x strategy ~1KB; never truncate
    # meaningful trigger input to attain an artificial target.
    if not isinstance(root, dict) or not isinstance(root.get('multi_strategy_engine'),dict):
        raise AssertionError('payload JSON must be an object, never a tuple/list')
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
            'S'||mod(g,10)::text,'WATCH','NO_SAFE_TRADE','SHORT',
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
    """Require both parent and child endpoints stable across 4 GET probes."""
    stable=0
    for _ in range(90):
        try:
            codes=[
                requests.get(BASE+"/"+table,
                             params={"select":"run_id","limit":"1"},
                             timeout=2).status_code
                for table in ("alpha_hunter_snapshots","alpha_hunter_symbol_snapshots")
            ]
        except requests.RequestException:
            codes=[]
        if codes==[200,200]:
            stable+=1
            if stable>=4:
                return
        else:
            stable=0
        time.sleep(0.3)
    raise RuntimeError("PostgREST parent/child schema cache never stabilized")


def write_run(run):
    parent={"run_id":run,"collected_at_utc":"2026-11-02T11:30:00Z",
            "version":"synthetic-shape","product_type":"usdt-futures",
            "symbol_count":SCAN_SYMBOLS,"error_count":0,
            "payload":{"_canonical_publication_state":"PENDING",
                       "validation_identity":{"run_source":"RENDER_CRON",
                       "scientific_fingerprint_sha256":"synthetic-only"}}}
    if os.getenv("AH_P0_PARENT_LEDGER_COMPLETE")=="1":
        parent["payload"]["private_account"]={
            "status":"CONNECTED",
            "accounts":[{"margin_coin":"USDT","account_equity":"1000",
                         "available":"950","unrealized_pl":"-10","locked":"50"}],
            "open_position_count":1,
            "open_positions":[{"symbol":"TESTUSDT","hold_side":"short","total":"2",
                "open_price_avg":"100","mark_price":"101","unrealized_pl":"-2",
                "take_profit":None,"stop_loss":None,
                "protection_observation_status":"DATA_INSUFFICIENT",
                "protection_orders":[]}],
            "protection_observation_status":"DATA_INSUFFICIENT"}
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



def test_postgrest_57014_and_ambiguous_ack():
    """Real disposable PostgREST failure injection and exact database custody.

    Separate synthetic run IDs keep these tests entirely distinct from
    paper positions and frozen R8-R10 science.
    """
    def parent(run):
        r=requests.post(BASE+"/alpha_hunter_snapshots",json={
            "run_id":run,"collected_at_utc":"2026-11-02T11:30:00Z",
            "version":"synthetic-failure","product_type":"usdt-futures",
            "symbol_count":62,"error_count":0,
            "payload":{"_canonical_publication_state":"PENDING",
                       "validation_identity":{"run_source":"RENDER_CRON",
                                              "scientific_fingerprint_sha256":"synthetic-only"}}},
            headers={"Prefer":"resolution=merge-duplicates,return=minimal"},
            timeout=10)
        if r.status_code not in (200,201,204):
            raise RuntimeError("synthetic parent failed "+r.text[:400])

    def rows(run, indices):
        return [{
            "run_id":run,"symbol":f"TEST{i:03d}USDT",
            "collected_at_utc":"2026-11-02T11:30:00Z",
            "state":"NEUTRAL","trade_permission":False,
            "last_price":100.0,"payload":payload_for(run,i)}
            for i in indices]

    def put(run, indices, *, timeout=(3,15)):
        return requests.post(BASE+"/alpha_hunter_symbol_snapshots",
            params={"on_conflict":"run_id,symbol"},
            json=rows(run,indices),
            headers={"Prefer":"resolution=merge-duplicates,return=minimal"},
            timeout=timeout)

    with psycopg.connect(DSN,autocommit=True) as conn:
        parent("synthetic-57014")
        conn.execute("""
          CREATE FUNCTION public.ah_local_cancel_57014()
          RETURNS trigger LANGUAGE plpgsql AS $p0$
          BEGIN
            IF NEW.run_id='synthetic-57014'
               AND NEW.symbol='TEST032USDT' THEN
              RAISE EXCEPTION 'local cancellation test only' USING ERRCODE='57014';
            END IF;
            RETURN NEW;
          END; $p0$
        """)
        conn.execute("""
          CREATE TRIGGER ah_local_cancel_57014 BEFORE INSERT OR UPDATE
          ON public.alpha_hunter_symbol_snapshots
          FOR EACH ROW EXECUTE FUNCTION public.ah_local_cancel_57014()
        """)
        try:
            for k in range(0,32,8):
                r=put("synthetic-57014",range(k,k+8))
                if r.status_code not in (200,201,204):
                    raise AssertionError("unexpected pre-cancel HTTP failure")
            r=put("synthetic-57014",range(32,40))
            if r.status_code<400 or "57014" not in r.text:
                raise AssertionError("PostgREST failed to expose SQLSTATE 57014")
            partial=conn.execute(
                "SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s",
                ("synthetic-57014",)).fetchone()[0]
            if partial!=32:
                raise AssertionError("failed PostgREST chunk incorrectly committed")
            state=conn.execute(
                "SELECT payload->>'_canonical_publication_state' FROM public.alpha_hunter_snapshots WHERE run_id=%s",
                ("synthetic-57014",)).fetchone()[0]
            if state!="PENDING":
                raise AssertionError("incomplete parent incorrectly published")
        finally:
            conn.execute("DROP TRIGGER ah_local_cancel_57014 ON public.alpha_hunter_symbol_snapshots")
            conn.execute("DROP FUNCTION public.ah_local_cancel_57014()")

        # Exact retry of the same run; replaying 32 successful child writes
        # cannot create duplicated strategy observations or episodes.
        write_run("synthetic-57014")
        child=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s",
            ("synthetic-57014",)).fetchone()[0]
        obs=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=%s",
            ("synthetic-57014",)).fetchone()[0]
        if (child,obs)!=(62,620):
            raise AssertionError(f"PostgREST 57014 retry failed: {child},{obs}")

        parent("synthetic-unknown-ack")
        conn.execute("""
          CREATE FUNCTION public.ah_local_slow_ack()
          RETURNS trigger LANGUAGE plpgsql AS $p0$
          BEGIN
            IF NEW.run_id='synthetic-unknown-ack'
               AND NEW.symbol='TEST000USDT' THEN
              PERFORM pg_sleep(0.6);
            END IF;
            RETURN NEW;
          END; $p0$
        """)
        conn.execute("""
          CREATE TRIGGER ah_local_slow_ack BEFORE INSERT
          ON public.alpha_hunter_symbol_snapshots
          FOR EACH ROW EXECUTE FUNCTION public.ah_local_slow_ack()
        """)
        try:
            timed_out=False
            try:
                put("synthetic-unknown-ack",[0],timeout=(3,0.05))
            except requests.exceptions.ReadTimeout:
                timed_out=True
            if not timed_out:
                raise AssertionError("read-timeout injection failed")
            time.sleep(0.9)
            observed=conn.execute(
                "SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s",
                ("synthetic-unknown-ack",)).fetchone()[0]
            if observed not in (0,1):
                raise AssertionError("ambiguous HTTP write created duplicate rows")
        finally:
            conn.execute("DROP TRIGGER ah_local_slow_ack ON public.alpha_hunter_symbol_snapshots")
            conn.execute("DROP FUNCTION public.ah_local_slow_ack()")
        r=put("synthetic-unknown-ack",[0])
        if r.status_code not in (200,201,204):
            raise AssertionError("ambiguous ACK retry failed "+r.text[:400])
        final=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s",
            ("synthetic-unknown-ack",)).fetchone()[0]
        final_obs=conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=%s",
            ("synthetic-unknown-ack",)).fetchone()[0]
        if (final,final_obs)!=(1,10):
            raise AssertionError("ambiguous ACK exact readback failed")
        return {
            "injected_postgrest_SQLSTATE_57014":"PASS",
            "partial_chunk_after_cancel":partial,
            "postgrest_cancel_replay_children":child,
            "postgrest_cancel_replay_strategy_observations":obs,
            "injected_client_read_timeout":"PASS",
            "ambiguous_ack_observed_before_retry":observed,
            "ambiguous_ack_final_children":final,
            "ambiguous_ack_final_strategy_observations":final_obs,
            "all_synthetic_parents_stay_PENDING":True}

def main():
    insist_local()
    OUT.mkdir(parents=True,exist_ok=True)
    # Fail fast before multi-gigabyte seeding if synthetic JSON has changed shape.
    sample=payload_for('shape-canary',0)
    if (not isinstance(sample,dict)
            or len(sample['multi_strategy_engine']['strategies'])!=10
            or not isinstance(sample['microstructure'],dict)):
        raise AssertionError('synthetic shape preflight failed')
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
    parent_extra={}
    if os.getenv("AH_P0_PARENT_LEDGER_COMPLETE")=="1":
        with psycopg.connect(DSN,autocommit=True) as check:
            p=check.execute("""
                SELECT m.run_id,m.status,s.connection_status,s.complete,s.trade_permission
                FROM public.alpha_hunter_account_ledger_materialization_events m
                JOIN public.alpha_hunter_account_state_snapshots s
                  ON s.account_snapshot_id=m.account_snapshot_id
                WHERE m.run_id=ANY(%s) ORDER BY m.run_id
            """,(runs,)).fetchall()
            if len(p)!=3 or any(x[1:]!=("MATERIALIZED_CONNECTED","CONNECTED_READ_ONLY",True,False)
                                for x in p):
                raise AssertionError(f"Concurrent parent ledger evidence invalid: {p}")
            prot=check.execute("""
                SELECT count(*),count(*) FILTER(WHERE trade_permission=false)
                FROM public.alpha_hunter_protection_reconciliation_events_v01
            """).fetchone()
            pos=check.execute("""
                SELECT count(*) FROM public.alpha_hunter_open_position_snapshots
                WHERE trade_permission=false
            """).fetchone()[0]
            if pos!=3 or prot[0]<3 or prot[0]!=prot[1]:
                raise AssertionError(f"Concurrent protection events invalid: {prot} positions={pos}")
            parent_extra={"parent_account_events":len(p),
                "connected_positions":pos,"protective_reconciliation_events":prot[0],
                "all_paper_only":True}
    report={"status":"CATALOG_TRIGGER_SUBSET_RESEARCH_ONLY",
        "exact_catalog_functions_reused":(12 if parent_extra else 5),
        "parent_account_protection_extra":parent_extra,
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
    report["postgrest_failure_injection"]=(
        test_postgrest_57014_and_ambiguous_ack()
        if os.getenv("AH_P0_FAILURE_PROBES")=="1" else "NOT_RUN_IN_THIS_JOB")
    (OUT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))
    print("FULL production trigger-chain and DBA approval remain BLOCKED.")


if __name__=="__main__":
    main()
