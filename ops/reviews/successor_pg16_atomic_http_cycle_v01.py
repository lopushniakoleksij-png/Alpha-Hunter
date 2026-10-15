#!/usr/bin/env python3
"""P2 DRAFT-ONLY: synthetic atomic PostgREST RPC, NEVER production SQL.

Single PostgreSQL-function statement commits parent, exact child manifest,
all projected observations + episodes, then structural stage receipt together.
Only disposable local PG16 DB with guard_dsn, never production URL/credentials.
A structural receipt does NOT prove paper positions were monitored, an R10
scientific pass, 35m continuity, profitability or real-order authority.
"""
from __future__ import annotations
import concurrent.futures
import json
import math
import statistics
import sys
import time
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

import psycopg
from psycopg import sql

from successor_pg16_tcp_benchmark_v01 import (
    SCHEMA,CANDIDATE,BASE_DB,guard_dsn,make_conn,synthetic_rows,do_ingest,extract
)

DBNAME="ah_p2_atomic_only_ephemeral"
URL="http://127.0.0.1:3002/rpc/atomic_accept_scan"
VERSION="ATOMIC_SOURCE_AND_STRATEGY_ONLY_NOT_PAPER_MONITORING"
POSTGRES15MS=12000
HTTP_SECONDS=15
FINGERPRINT="50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834"

def candidate_statements():
    x=[]
    for part in CANDIDATE.read_text().split("-- NEXT STATEMENT"):
        stmt="\n".join(line for line in part.strip().splitlines()
                       if not line.lstrip().startswith("--")).strip()
        if stmt:
            if stmt.count("$1")!=1:
                raise AssertionError("Unexpected unparameterized candidate projection")
            x.append(stmt.replace("$1","p_run_id").rstrip(";")+";")
    if len(x)!=2:raise AssertionError("Full fidelity strategy observations AND episodes required")
    return x

def atomic_ddl():
    observations,episodes=candidate_statements()
    return """
CREATE SCHEMA successor_shadow;
REVOKE ALL ON SCHEMA successor_shadow FROM PUBLIC;
CREATE TABLE successor_shadow.atomic_stage_receipts(
 run_id text PRIMARY KEY REFERENCES public.alpha_hunter_snapshots(run_id),
 collected_at_utc timestamptz NOT NULL,
 expected_symbols integer NOT NULL CHECK(expected_symbols>0),
 observed_symbols integer NOT NULL CHECK(observed_symbols=expected_symbols),
 expected_observations integer NOT NULL CHECK(expected_observations>=0),
 actual_observations integer NOT NULL CHECK(actual_observations=expected_observations),
 expected_episodes integer NOT NULL CHECK(expected_episodes>=0),
 actual_episodes integer NOT NULL CHECK(actual_episodes=expected_episodes),
 immutable_child_digest text NOT NULL CHECK(immutable_child_digest ~ '^[0-9a-f]{64}$'),
 research_only text NOT NULL DEFAULT 'LOCAL_ATOMIC_STRUCTURE_ONLY_NOT_POSITION_MONITORING'
   CHECK(research_only='LOCAL_ATOMIC_STRUCTURE_ONLY_NOT_POSITION_MONITORING'),
 scientific_pass_permitted boolean NOT NULL DEFAULT false CHECK(scientific_pass_permitted=false),
 trade_permission boolean NOT NULL DEFAULT false CHECK(trade_permission=false),
 exchange_authority boolean NOT NULL DEFAULT false CHECK(exchange_authority=false),
 order_path text NOT NULL DEFAULT 'NONE' CHECK(order_path='NONE'),
 sealed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE FUNCTION successor_shadow.immutable_row() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $body$
BEGIN RAISE EXCEPTION 'SUCCESSOR_ATOMIC_RESEARCH_RECEIPT_IMMUTABLE'; END;
$body$;
CREATE TRIGGER no_receipt_mutation BEFORE UPDATE OR DELETE
 ON successor_shadow.atomic_stage_receipts FOR EACH ROW
 EXECUTE FUNCTION successor_shadow.immutable_row();
CREATE FUNCTION successor_shadow.atomic_accept_scan(
 p_run_id text,
 p_rows jsonb,
 p_expected_symbols integer,
 p_expected_observations integer,
 p_expected_episodes integer,
 p_fingerprint text,
 p_fault text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $body$
DECLARE
 v_actual_symbols integer;
 v_actual_observations integer;
 v_actual_episodes integer;
 v_intent_observations integer;
 v_intent_episodes integer;
 v_sha text;
 v_time timestamptz;
 v_prev successor_shadow.atomic_stage_receipts%ROWTYPE;
BEGIN
 -- Refuse ANY production host/DB even if someone accidentally copies this
 -- test SQL. No production Supabase project is named or reachable.
 IF current_database()<>'ah_p2_atomic_only_ephemeral'
   OR p_run_id IS NULL OR p_run_id NOT LIKE 'synthetic-p2-atomic-%'
   OR p_fingerprint<>'50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834'
 THEN RAISE EXCEPTION 'EPHEMERAL_TEST_ONLY'; END IF;
 IF p_fault IS NOT NULL AND p_fault NOT IN
  ('AFTER_CHILDREN','AFTER_OBSERVATIONS','BEFORE_RECEIPT','TIMEOUT')
 THEN RAISE EXCEPTION 'INVALID_FAULT_MODE'; END IF;
 IF p_expected_symbols IS NULL OR p_expected_symbols NOT BETWEEN 1 AND 128
  OR jsonb_typeof(p_rows)<>'array'
  OR jsonb_array_length(p_rows)<>p_expected_symbols
 THEN RAISE EXCEPTION 'EXPECTED_SYMBOL_MANIFEST_INVALID'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(
   pg_catalog.hashtextextended(p_run_id,0));
 v_sha:=pg_catalog.encode(pg_catalog.sha256(
   pg_catalog.convert_to(p_rows::text,'UTF8')),'hex');
 SELECT * INTO v_prev FROM successor_shadow.atomic_stage_receipts
   WHERE run_id=p_run_id;
 IF FOUND THEN
   IF v_prev.immutable_child_digest<>v_sha
      OR v_prev.expected_symbols<>p_expected_symbols
      OR v_prev.expected_observations<>p_expected_observations
      OR v_prev.expected_episodes<>p_expected_episodes
   THEN RAISE EXCEPTION 'SEALED_RETRY_PAYLOAD_CONFLICT'; END IF;
   RETURN pg_catalog.jsonb_build_object(
     'stage','ALREADY_ATOMICALLY_COMMITTED_LOCAL_ONLY',
     'run_id',p_run_id,'symbol_count',v_prev.observed_symbols,
     'strategy_count',v_prev.actual_observations,
     'episode_count',v_prev.actual_episodes,
     'child_sha256',v_sha,
     'scientific_pass_permitted',false,'trade_permission',false,
     'exchange_authority',false,'monitoring_verified',false);
 END IF;
 IF EXISTS(SELECT 1 FROM public.alpha_hunter_snapshots WHERE run_id=p_run_id)
    OR EXISTS(SELECT 1 FROM public.alpha_hunter_symbol_snapshots WHERE run_id=p_run_id)
 THEN RAISE EXCEPTION 'UNSEALED_PRIOR_PARENT_OR_CHILD_REFUSE_BACKFILL'; END IF;
 SELECT count(DISTINCT item->>'symbol'),
   count(*) FILTER(WHERE jsonb_typeof(item)<>'object'
     OR item->>'run_id' IS DISTINCT FROM p_run_id
     OR item->>'symbol' IS NULL
     OR item->>'symbol' !~ '^[A-Z0-9]+USDT$'
     OR item->'payload'->>'symbol' IS DISTINCT FROM item->>'symbol'
     OR jsonb_typeof(item->'payload')<>'object'
     OR jsonb_typeof(item->'payload'->'multi_strategy_engine'->'strategies')<>'array')
 INTO v_actual_symbols,v_intent_observations
 FROM pg_catalog.jsonb_array_elements(p_rows) AS item;
 IF v_actual_symbols<>p_expected_symbols OR v_intent_observations<>0
 THEN RAISE EXCEPTION 'MALFORMED_DUPLICATE_OR_MIXED_SOURCE_MANIFEST'; END IF;
 SELECT min((item->>'collected_at_utc')::timestamptz) INTO v_time
 FROM pg_catalog.jsonb_array_elements(p_rows) item;
 IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(p_rows) item
  WHERE (item->>'collected_at_utc')::timestamptz<>v_time)
 THEN RAISE EXCEPTION 'MIXED_SCAN_COLLECTION_TIMES'; END IF;
 SELECT coalesce(sum(jsonb_array_length(
    item->'payload'->'multi_strategy_engine'->'strategies')),0)::integer,
   coalesce(sum((
     SELECT count(*) FROM pg_catalog.jsonb_array_elements(
       item->'payload'->'multi_strategy_engine'->'strategies') strategy
     WHERE coalesce(strategy->'persistence'->>'strategy_instance_id','')<>''
   )),0)::integer
 INTO v_intent_observations,v_intent_episodes
 FROM pg_catalog.jsonb_array_elements(p_rows) item;
 IF v_intent_observations<>p_expected_observations
   OR v_intent_episodes<>p_expected_episodes
 THEN RAISE EXCEPTION 'DECLARED_STRATEGY_MANIFEST_MISMATCH'; END IF;
 INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES(p_run_id);
 INSERT INTO public.alpha_hunter_symbol_snapshots(
     run_id,symbol,collected_at_utc,payload,trade_permission,state)
 SELECT x.run_id,x.symbol,x.collected_at_utc,x.payload,false,'WATCH'
 FROM pg_catalog.jsonb_to_recordset(p_rows)
 AS x(run_id text,symbol text,collected_at_utc timestamptz,payload jsonb);
 IF p_fault='AFTER_CHILDREN' THEN RAISE EXCEPTION 'INJECTED_FAULT_AFTER_CHILDREN'; END IF;
 IF p_fault='TIMEOUT' THEN
    PERFORM pg_catalog.set_config('statement_timeout','40ms',true);
    PERFORM pg_catalog.pg_sleep(0.18);
 END IF;
 """+observations+"""
 IF p_fault='AFTER_OBSERVATIONS' THEN
   RAISE EXCEPTION 'INJECTED_FAULT_AFTER_OBSERVATIONS'; END IF;
 """+episodes+"""
 SELECT count(*) INTO v_actual_symbols
   FROM public.alpha_hunter_symbol_snapshots WHERE run_id=p_run_id;
 SELECT count(*) INTO v_actual_observations
   FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=p_run_id;
 SELECT count(*) INTO v_actual_episodes
   FROM public.alpha_hunter_strategy_episodes_v01
   WHERE first_observation_id IN (
    SELECT observation_id FROM public.alpha_hunter_strategy_observations_v01
    WHERE run_id=p_run_id);
 IF v_actual_symbols<>p_expected_symbols
   OR v_actual_observations<>p_expected_observations
   OR v_actual_episodes<>p_expected_episodes
 THEN RAISE EXCEPTION 'INCOMPLETE_ATOMIC_STRATEGY_EVIDENCE'; END IF;
 -- Verify DB-persisted child payload identity, not only a count or a digest
 -- computed from the submitted HTTP request. This query is in the SAME
 -- pending transaction, so any readback failure aborts ALL five stages.
 IF EXISTS(
  SELECT 1 FROM pg_catalog.jsonb_to_recordset(p_rows)
    req(run_id text,symbol text,collected_at_utc timestamptz,payload jsonb)
  LEFT JOIN public.alpha_hunter_symbol_snapshots saved
    ON saved.run_id=req.run_id AND saved.symbol=req.symbol
  WHERE saved.run_id IS NULL
    OR saved.payload IS DISTINCT FROM req.payload
    OR saved.collected_at_utc IS DISTINCT FROM req.collected_at_utc
    OR saved.trade_permission IS DISTINCT FROM false
 ) THEN RAISE EXCEPTION 'ATOMIC_CHILD_SOURCE_READBACK_MISMATCH'; END IF;
 IF p_fault='BEFORE_RECEIPT' THEN
   RAISE EXCEPTION 'INJECTED_FAULT_BEFORE_RECEIPT'; END IF;
 INSERT INTO successor_shadow.atomic_stage_receipts(
   run_id,collected_at_utc,expected_symbols,observed_symbols,
   expected_observations,actual_observations,expected_episodes,actual_episodes,
   immutable_child_digest)
 VALUES(p_run_id,v_time,p_expected_symbols,v_actual_symbols,
        p_expected_observations,v_actual_observations,
        p_expected_episodes,v_actual_episodes,v_sha);
 RETURN pg_catalog.jsonb_build_object(
   'stage','ATOMIC_SOURCE_STRATEGY_COMMITTED_LOCAL_ONLY',
   'run_id',p_run_id,'symbol_count',v_actual_symbols,
   'strategy_count',v_actual_observations,'episode_count',v_actual_episodes,
   'child_sha256',v_sha,
   'scientific_pass_permitted',false,'trade_permission',false,
   'exchange_authority',false,'monitoring_verified',false);
END;
$body$;
REVOKE ALL ON ALL TABLES IN SCHEMA successor_shadow FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA successor_shadow FROM PUBLIC;
GRANT USAGE ON SCHEMA successor_shadow TO bench_api;
GRANT EXECUTE ON FUNCTION successor_shadow.atomic_accept_scan(
 text,jsonb,integer,integer,integer,text,text) TO bench_api;
GRANT SELECT,INSERT ON TABLE
 public.alpha_hunter_snapshots,public.alpha_hunter_symbol_snapshots,
 public.alpha_hunter_strategy_observations_v01,
 public.alpha_hunter_strategy_episodes_v01 TO bench_api;
GRANT INSERT,SELECT ON successor_shadow.atomic_stage_receipts TO bench_api;
"""

def guarded_setup():
    dsn=guard_dsn()
    with psycopg.connect(dsn,autocommit=True) as admin:
        ver=admin.execute("SHOW server_version_num").fetchone()[0]
        if not str(ver).startswith("16"):raise AssertionError("isolated PG16 only")
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DBNAME)))
    with make_conn(dsn,DBNAME) as cx:
        cx.execute(SCHEMA.read_text())
        cx.execute("""DROP TRIGGER trg_ah_capture_strategy_observations_v01
            ON public.alpha_hunter_symbol_snapshots""")
        cx.execute("""DO $$BEGIN
          IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='bench_api') THEN
             CREATE ROLE bench_api NOLOGIN;
          END IF; END$$;
          GRANT USAGE ON SCHEMA public TO bench_api""")
        cx.execute(atomic_ddl())
        cx.execute("ALTER DATABASE ah_p2_atomic_only_ephemeral SET statement_timeout='12s'")
    print("P2_ISOLATED_ATOMIC_RESEARCH_SETUP_READY")

def make_payload(n,run):
    rows=synthetic_rows(run,n)
    for row in rows:
        row["payload"]["symbol"]=row["symbol"]
    return {"p_run_id":run,
       "p_rows":rows,
       "p_expected_symbols":n,
       "p_expected_observations":n*10,
       "p_expected_episodes":n*2,
       "p_fingerprint":FINGERPRINT,
       "p_fault":None}

def postgrest(payload):
    if not URL.startswith("http://127.0.0.1:3002/"):
        raise AssertionError("non-ephemeral host")
    req=Request(URL,method="POST",headers={
       "Content-Type":"application/json","Accept":"application/json"},
       data=json.dumps(payload,separators=(",",":")).encode())
    start=time.perf_counter()
    try:
        with urlopen(req,timeout=HTTP_SECONDS) as resp:
            result=json.loads(resp.read())
            if resp.status not in (200,201):
                raise AssertionError("unexpected RPC HTTP response "+str(resp.status))
    except HTTPError as e:
        return {"error_http":e.code,"body":e.read(2000).decode()},            (time.perf_counter()-start)*1000
    except URLError as e:
        raise AssertionError("isolated local PostgREST unavailable") from e
    return result,(time.perf_counter()-start)*1000

def inspect(dsn,run):
    with make_conn(dsn,DBNAME) as db:
        parent=db.execute("SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id=%s",(run,)).fetchone()[0]
        child=db.execute("SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s",(run,)).fetchone()[0]
        obs=db.execute("SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=%s",(run,)).fetchone()[0]
        ep=db.execute("""SELECT count(*) FROM public.alpha_hunter_strategy_episodes_v01
          WHERE first_observation_id IN(SELECT observation_id
          FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=%s)""",(run,)).fetchone()[0]
        receipt=db.execute("SELECT count(*) FROM successor_shadow.atomic_stage_receipts WHERE run_id=%s",(run,)).fetchone()[0]
        return (parent,child,obs,ep,receipt)

def compare_baseline(dsn,run,payload):
    # Baseline uses the ORIGINAL production per-row trigger, atomic PG16 TCP.
    # Benchmarking here measures semantics, NOT production PostgREST p99.
    rows=payload["p_rows"]
    do_ingest(dsn,BASE_DB,run,rows,[])
    a=extract(dsn,BASE_DB,run)
    b=extract(dsn,DBNAME,run)
    if a!=b:
        raise AssertionError("ATOMIC_RPC_STRATEGY_PARITY_FAILED")
    return (len(a["observations"]),len(a["episodes"]))

def wait_for_postgrest_schema_cache():
    """Do not treat a fresh container's PGRST002 schema-cache 503 as a code regression.

    Wait only for the isolated localhost API health route. No POST, no retries
    of an unknown production order, no production service or DB access.
    """
    for _ in range(40):
        try:
            with urlopen("http://127.0.0.1:3002/",timeout=2) as response:
                if response.status==200:
                    return
        except (HTTPError,URLError,TimeoutError):
            time.sleep(.35)
    raise AssertionError("ISOLATED_POSTGREST_SCHEMA_CACHE_NOT_READY")

def verify():
    dsn=guard_dsn()
    wait_for_postgrest_schema_cache()
    durations=[]
    for i in range(3):
        run=f"synthetic-p2-atomic-clean-{i}"
        p=make_payload(63,run)
        response,ms=postgrest(p)
        if response.get("stage")!="ATOMIC_SOURCE_STRATEGY_COMMITTED_LOCAL_ONLY":
            raise AssertionError(f"Atomic HTTP rejected normal run: {response}")
        if response.get("trade_permission") or response.get("monitoring_verified"):
            raise AssertionError("unsafe authority claim")
        if inspect(dsn,run)!=(1,63,630,126,1):
            raise AssertionError("atomic count/receipt mismatch")
        compare_baseline(dsn,run,p)
        durations.append(ms)
    # Full-size idempotent HTTP retry represents ambiguous 15s client read.
    p=make_payload(63,"synthetic-p2-atomic-clean-0")
    repeated,_=postgrest(p)
    if repeated.get("stage")!="ALREADY_ATOMICALLY_COMMITTED_LOCAL_ONLY"        or inspect(dsn,p["p_run_id"])!=(1,63,630,126,1):
        raise AssertionError("Retry duplicated or changed committed evidence")
    mutated=make_payload(63,"synthetic-p2-atomic-clean-0")
    mutated["p_rows"][0]["payload"]["last_price"]="50000"
    conflict,_=postgrest(mutated)
    if conflict.get("error_http") not in (400,409):
        raise AssertionError("Mutated retry falsely accepted")

    failed=[]
    for kind in ("AFTER_CHILDREN","AFTER_OBSERVATIONS","BEFORE_RECEIPT"):
        run="synthetic-p2-atomic-fail-"+kind.lower()
        p=make_payload(63,run)
        p["p_fault"]=kind
        reply,_=postgrest(p)
        if reply.get("error_http") not in (400,409):
            raise AssertionError("Injected rollback not detected "+str(reply))
        if inspect(dsn,run)!=(0,0,0,0,0):
            raise AssertionError("Partial durable evidence leaked after "+kind)
        failed.append(kind)
    # Source manifest mismatch fails BEFORE the transaction can write parent.
    malformed=make_payload(63,"synthetic-p2-atomic-identity-reject")
    malformed["p_rows"][0]["payload"]["symbol"]="WRONGUSDT"
    response,_=postgrest(malformed)
    if response.get("error_http") not in (400,409)        or inspect(dsn,malformed["p_run_id"])!=(0,0,0,0,0):
        raise AssertionError("Mismatched source accepted")
    invalid=make_payload(2,"synthetic-p2-atomic-invalid-strategy")
    invalid["p_rows"][0]["payload"]["multi_strategy_engine"]["strategies"][0]["direction"]="INVALID"
    response,_=postgrest(invalid)
    if response.get("error_http") not in (400,409)        or inspect(dsn,invalid["p_run_id"])!=(0,0,0,0,0):
        raise AssertionError("Bad scientific geometry bypassed immutable constraints")

    # Deliberately mutate a source payload through an isolated BEFORE INSERT
    # trigger: equal row COUNTS are not enough; exact persisted readback must
    # reject the whole transaction and leave zero durable rows.
    forged=make_payload(2,"synthetic-p2-atomic-persisted-payload-different")
    with make_conn(dsn,DBNAME) as db:
        db.execute("""
          CREATE FUNCTION successor_shadow.synthetic_mutate_child()
          RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
          SET search_path='' AS $mut$
          BEGIN
            NEW.payload=pg_catalog.jsonb_set(
              NEW.payload,'{last_price}','\"98765\"'::jsonb,true);
            RETURN NEW;
          END;
          $mut$;
          CREATE TRIGGER synthetic_child_payload_mutation
          BEFORE INSERT ON public.alpha_hunter_symbol_snapshots
          FOR EACH ROW EXECUTE FUNCTION successor_shadow.synthetic_mutate_child();
        """)
    try:
        response,_=postgrest(forged)
        if response.get("error_http") not in (400,409) or (
            "ATOMIC_CHILD_SOURCE_READBACK_MISMATCH"
            not in response.get("body","")):
            raise AssertionError("Corrupted persisted payload was not refused "+str(response))
    finally:
        with make_conn(dsn,DBNAME) as db:
            db.execute("""DROP TRIGGER synthetic_child_payload_mutation
              ON public.alpha_hunter_symbol_snapshots;
              DROP FUNCTION successor_shadow.synthetic_mutate_child()""")
    if inspect(dsn,forged["p_run_id"])!=(0,0,0,0,0):
        raise AssertionError("Corrupted source payload left committed partial rows")

    # Unsealed previous parent cannot be overwritten or 'fixed up' as history.
    prior="synthetic-p2-atomic-prior-unsealed"
    with make_conn(dsn,DBNAME) as db:
        db.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES(%s)",(prior,))
    response,_=postgrest(make_payload(2,prior))
    if response.get("error_http") not in (400,409)        or inspect(dsn,prior)!=(1,0,0,0,0):
        raise AssertionError("Prior partially persisted run was backfilled")

    # A REAL PG statement cancellation (far shorter ONLY in ephemeral test)
    # must roll back the entire function call including any attempted parent,
    # child, strategy observation/episode and structural receipt.
    timeout_payload=make_payload(63,"synthetic-p2-atomic-sql-timeout")
    timed_out=False
    with make_conn(dsn,DBNAME) as db:
        db.execute("SET ROLE bench_api")
        db.execute("SET statement_timeout = '25ms'")
        db.commit()
        try:
            db.execute("""SELECT successor_shadow.atomic_accept_scan(
                %s,%s::jsonb,%s,%s,%s,%s,%s)""",(
                timeout_payload["p_run_id"],json.dumps(timeout_payload["p_rows"]),
                63,630,126,FINGERPRINT,None))
        except psycopg.errors.QueryCanceled:
            timed_out=True
            db.rollback()
        if not timed_out:
            raise AssertionError("Atomic function did not hit injected local SQL timeout")
    if inspect(dsn,timeout_payload["p_run_id"])!=(0,0,0,0,0):
        raise AssertionError("SQL cancellation retained a partial receipt or child write")

    # Reproduce the exact PostgREST/Supabase SQL timeout response shape seen
    # on the live missing-child scan: HTTP 500, PostgreSQL SQLSTATE 57014.
    # The fault runs ONLY inside our disposable local PostgreSQL/PostgREST.
    pg_cancel=make_payload(2,"synthetic-p2-atomic-http-57014")
    pg_cancel["p_fault"]="TIMEOUT"
    cancelled_reply,_=postgrest(pg_cancel)
    if (cancelled_reply.get("error_http")!=500
        or '"code":"57014"' not in cancelled_reply.get("body","").replace(" ","")
        or "statement timeout" not in cancelled_reply.get("body","").lower()):
        raise AssertionError("Expected actual PostgREST HTTP 500 / 57014, not "+str(cancelled_reply))
    if inspect(dsn,pg_cancel["p_run_id"])!=(0,0,0,0,0):
        raise AssertionError("57014 left a falsely completed parent, child, strategy or receipt")
    # A request that timed out must be UNKNOWN until an independent readback.
    # Retrying the same prospective payload after the injected fault is removed
    # may commit once; further identical retries must never create duplicates.
    pg_cancel["p_fault"]=None
    recovered,_=postgrest(pg_cancel)
    if (recovered.get("stage")!="ATOMIC_SOURCE_STRATEGY_COMMITTED_LOCAL_ONLY"
        or inspect(dsn,pg_cancel["p_run_id"])!=(1,2,20,4,1)):
        raise AssertionError("Prospective 57014 recovery failed exact durable reconciliation")
    repeated,_=postgrest(pg_cancel)
    if (repeated.get("stage")!="ALREADY_ATOMICALLY_COMMITTED_LOCAL_ONLY"
        or inspect(dsn,pg_cancel["p_run_id"])!=(1,2,20,4,1)):
        raise AssertionError("Retried 57014 success duplicated or changed evidence")
    conflict=make_payload(2,pg_cancel["p_run_id"])
    conflict["p_rows"][0]["payload"]["last_price"]="123456"
    blocked,_=postgrest(conflict)
    if blocked.get("error_http") not in (400,409):
        raise AssertionError("Altered post-57014 replay overwrote committed source")
    if inspect(dsn,pg_cancel["p_run_id"])!=(1,2,20,4,1):
        raise AssertionError("Post-57014 conflicting retry changed durable counts")

    # Multiple exact HTTP retries racing on the SAME run may create precisely
    # ONE run + ONE sealed receipt. A mutated concurrent retry cannot replace
    # an already locked/committed run.
    race=make_payload(63,"synthetic-p2-atomic-racing-retries")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        replies=[f.result()[0] for f in [
          pool.submit(postgrest,race) for _ in range(3)]]
    assert sorted(r["stage"] for r in replies)==[
       "ALREADY_ATOMICALLY_COMMITTED_LOCAL_ONLY",
       "ALREADY_ATOMICALLY_COMMITTED_LOCAL_ONLY",
       "ATOMIC_SOURCE_STRATEGY_COMMITTED_LOCAL_ONLY"]
    if inspect(dsn,race["p_run_id"])!=(1,63,630,126,1):
        raise AssertionError("Same-run concurrent retries produced duplicate evidence")
    compare_baseline(dsn,race["p_run_id"],race)

    # Close client connection cannot be taken as monitoring evidence.
    with make_conn(dsn,DBNAME) as db:
        gated=db.execute("""SELECT count(*) FROM successor_shadow.atomic_stage_receipts
           WHERE scientific_pass_permitted OR trade_permission OR exchange_authority
              OR order_path<>'NONE'""").fetchone()[0]
        if gated:raise AssertionError("Unexpected paper or real order authority")
    print("P2_REAL_PG16_HTTP_ATOMIC_CYCLE_PASS "+
          json.dumps({"3_full_63_symbol_runs":3,"observations_checked":1890,
            "episodes_checked":378,"http_atomic_latency_ms":[round(x,1) for x in durations],
            "median_atomic_ms":round(statistics.median(durations),1),
            "negative_rollback_points":failed,
            "all_parent_child_observation_episode_receipt_rows_rollback":True,
            "ambiguous_http_retry_idempotent":True,
            "true_pg_statement_cancellation_rolls_back_all_stages":timed_out,
            "persisted_payload_mutation_detected_and_rolled_back":True,
            "three_same_run_http_retries_have_one_receipt":True,
            "conflicting_retry_refused":True,"historic_parent_backfill_refused":True,
            "production_scan_monitored_positions":False,
            "paper_35m_continuity_verified":False,
            "deployed":False,"R10_mutated":False,"exchange_authority":False},
            sort_keys=True))
    print("P2_ATOMIC_HTTP_STRATEGY_PARITY_AND_ROLLBACK_PASS_DEPLOYMENT_UNAPPROVED")

if __name__=="__main__":
    if len(sys.argv)==2 and sys.argv[1]=="--prepare":guarded_setup()
    elif len(sys.argv)==1:verify()
    else:raise SystemExit("Usage --prepare or no args")
