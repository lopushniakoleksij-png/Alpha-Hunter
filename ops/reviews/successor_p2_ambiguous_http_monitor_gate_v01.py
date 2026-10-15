#!/usr/bin/env python3
"""P2: ambiguous HTTP commit vs independently qualified paper observations.

Runs AFTER existing exact atomic PostgREST HTTP regression, with two EPHEMERAL
PG16 services in GitHub Actions. The local proxy withholds a committed POST
response until the caller actually times out. The result MUST stay UNKNOWN
until independently read back. Parent/child/strategy atomicity is necessary,
but is NOT paper-position monitoring or scientific source authentication.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from hmac import new as hmac_new,compare_digest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread,Event
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
import json,os,socket,time

import psycopg
from psycopg import sql
from successor_pg16_atomic_http_cycle_v01 import (
  DBNAME, URL, make_payload, inspect as inspect_atomic, FINGERPRINT)
from successor_pg16_tcp_benchmark_v01 import guard_dsn,make_conn
from successor_dual_pg16_journal_fault_v01 import journal_dsn
from successor_p03_residual_continuity_v01 import evaluate,sha,utc

PROXY="http://127.0.0.1:3103/atomic"
QUOTE_SOURCE="LOCAL_SYNTHETIC_BOOK_NOT_AUTHENTICATED_BITGET"
SCHEMA="""
CREATE SCHEMA p2_ambiguous;
REVOKE ALL ON SCHEMA p2_ambiguous FROM PUBLIC;
CREATE TABLE p2_ambiguous.position_seals (
 receipt_id text PRIMARY KEY,
 source_run_id text NOT NULL,
 entry_order_id text NOT NULL,
 symbol text NOT NULL,
 observed_at_utc timestamptz NOT NULL,
 quote_source text NOT NULL,
 capture_manifest_sha256 text NOT NULL CHECK(length(capture_manifest_sha256)=64),
 predecessor_receipt_sha256 text NOT NULL,
 record_sha256 text NOT NULL CHECK(length(record_sha256)=64),
 local_hmac_sha256 text NOT NULL CHECK(length(local_hmac_sha256)=64),
 paper_only boolean NOT NULL DEFAULT true CHECK(paper_only),
 exchange_authority boolean NOT NULL DEFAULT false CHECK(NOT exchange_authority),
 trade_permission boolean NOT NULL DEFAULT false CHECK(NOT trade_permission),
 scientific_pass_permitted boolean NOT NULL DEFAULT false CHECK(NOT scientific_pass_permitted),
 UNIQUE(source_run_id,entry_order_id)
);
CREATE FUNCTION p2_ambiguous.deny_mutation() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $body$
BEGIN RAISE EXCEPTION 'P2_AMBIGUOUS_RECEIPT_IMMUTABLE'; END;
$body$;
CREATE TRIGGER deny_update_delete BEFORE UPDATE OR DELETE
 ON p2_ambiguous.position_seals FOR EACH ROW EXECUTE FUNCTION p2_ambiguous.deny_mutation();
REVOKE ALL ON ALL TABLES IN SCHEMA p2_ambiguous FROM PUBLIC;
"""

class TimeoutProxy(BaseHTTPRequestHandler):
    def do_POST(self):
        count=int(self.headers.get("Content-Length","0"))
        if self.path!="/atomic" or count<1 or count>2_000_000:
            self.send_error(400);return
        data=self.rfile.read(count)
        try:
            with urlopen(Request(URL,data=data,method="POST",headers={
              "Content-Type":"application/json","Accept":"application/json"}),timeout=12) as resp:
                self.server.downstream=(resp.status,resp.read())
        except HTTPError as exc:
            self.server.downstream=(exc.code,exc.read())
        except Exception as exc:
            self.server.downstream=(-1,str(type(exc).__name__).encode())
        finally:
            self.server.forward_done.set()
        # Deliberately withhold even successful HTTP responses past client deadline.
        time.sleep(0.6)
        try:
            self.send_response(self.server.downstream[0])
            self.end_headers()
            self.wfile.write(self.server.downstream[1])
        except (BrokenPipeError,ConnectionResetError):pass
    def log_message(self,*args):pass

def lost_response(payload):
    server=ThreadingHTTPServer(("127.0.0.1",3103),TimeoutProxy)
    server.forward_done=Event()
    server.downstream=None
    th=Thread(target=server.serve_forever,daemon=True)
    th.start()
    try:
        assert PROXY.startswith("http://127.0.0.1:3103/")
        try:
            with urlopen(Request(PROXY,data=json.dumps(payload).encode(),method="POST",
                                headers={"Content-Type":"application/json"}),timeout=0.15) as r:
                raise AssertionError("Lost-response proxy unexpectedly returned: "+str(r.status))
        except (TimeoutError,URLError,ConnectionResetError,socket.timeout):
            pass
        else:
            raise AssertionError("Ambiguous HTTP response was not lost")
        if not server.forward_done.wait(15):raise AssertionError("Backend did not resolve after caller timed out")
        result=server.downstream
        if result is None:raise AssertionError("No independent proxy downstream evidence")
        return result[0]
    finally:
        server.shutdown();server.server_close();th.join(timeout=2)

def make_positions(payload):
    pos=[{"entry_order_id":"synthetic-managed-monitor-"+str(i),
          "symbol":row["symbol"],"direction":"LONG","residual_qty":"1.5",
          "disposition":"MANAGED_PROTECTED","two_records":True}
         for i,row in enumerate(payload["p_rows"])]
    return {"status":"SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION",
            "positions":pos,"manifest_sha256":sha(pos)}

def structural_readback(dsn,run,submitted):
    expected=len(submitted["p_rows"])
    with make_conn(dsn,DBNAME) as c:
        with c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            result=c.execute("""SELECT collected_at_utc,expected_symbols,observed_symbols,
                 expected_observations,actual_observations,expected_episodes,
                 actual_episodes,immutable_child_digest,scientific_pass_permitted
                 FROM successor_shadow.atomic_stage_receipts WHERE run_id=%s""",(run,)).fetchall()
            parents=c.execute("""SELECT count(*) FROM public.alpha_hunter_snapshots
                                 WHERE run_id=%s""",(run,)).fetchone()[0]
            children=c.execute("""SELECT symbol,collected_at_utc,payload,trade_permission
              FROM public.alpha_hunter_symbol_snapshots WHERE run_id=%s ORDER BY symbol""",(run,)).fetchall()
            strategies=c.execute("""SELECT count(*) FROM public.alpha_hunter_strategy_observations_v01
                    WHERE run_id=%s""",(run,)).fetchone()[0]
            episodes=c.execute("""SELECT count(*) FROM public.alpha_hunter_strategy_episodes_v01
                    WHERE first_observation_id IN (
                     SELECT observation_id FROM public.alpha_hunter_strategy_observations_v01
                     WHERE run_id=%s)""",(run,)).fetchone()[0]
    if len(result)!=1 or parents!=1 or len(children)!=expected:
        return False
    t=result[0]
    if (t[1:7]!=(expected,expected,expected*10,strategies,expected*2,episodes)
      or strategies!=expected*10 or episodes!=expected*2 or t[8] is not False):
        return False
    submitted_rows=sorted(submitted["p_rows"],key=lambda r:r["symbol"])
    expected_time=utc(submitted_rows[0]["collected_at_utc"])
    for actual,source in zip(children,submitted_rows):
        if (actual[0]!=source["symbol"] or actual[1]!=expected_time or
           actual[2]!=source["payload"] or actual[3] is not False):
            return False
    return True

def seal_fields(run,order,symbol,when,predecessor,cap):
    return {"source_run_id":run,"entry_order_id":order,"symbol":symbol,
            "observed_at_utc":when,"quote_source":QUOTE_SOURCE,
            "capture_manifest_sha256":cap,"predecessor_receipt_sha256":predecessor}

def canonical(raw):
    return json.dumps(raw,sort_keys=True,separators=(",",":")).encode()

def insert_seal(cx,key,fields):
    record=sha256(canonical(fields)).hexdigest()
    mac=hmac_new(key,record.encode(),"sha256").hexdigest()
    rid=sha256((fields["source_run_id"]+"|"+fields["entry_order_id"]).encode()).hexdigest()[:32]
    cx.execute("""INSERT INTO p2_ambiguous.position_seals
     (receipt_id,source_run_id,entry_order_id,symbol,observed_at_utc,quote_source,
      capture_manifest_sha256,predecessor_receipt_sha256,record_sha256,local_hmac_sha256)
     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
     (rid,fields["source_run_id"],fields["entry_order_id"],fields["symbol"],
      fields["observed_at_utc"],fields["quote_source"],
      fields["capture_manifest_sha256"],fields["predecessor_receipt_sha256"],record,mac))
    return record

def sealed_rows(cx,key,run):
    rows=cx.execute("""SELECT source_run_id,entry_order_id,symbol,observed_at_utc,
      quote_source,capture_manifest_sha256,predecessor_receipt_sha256,
      record_sha256,local_hmac_sha256 FROM p2_ambiguous.position_seals
      WHERE source_run_id=%s ORDER BY entry_order_id""",(run,)).fetchall()
    checked=[]
    for v in rows:
        fields=seal_fields(v[0],v[1],v[2],v[3].isoformat(),v[6],v[5])
        digest=sha256(canonical(fields)).hexdigest()
        assert digest==v[7],"Independent journal receipt digest mismatch"
        assert compare_digest(hmac_new(key,digest.encode(),"sha256").hexdigest(),v[8]),"Wrong local signing key"
        checked.append(dict(fields,record_sha256=digest))
    return checked

def classify(dsn,journal,key,source,inventory,*,allow_journal=True):
    run=source["p_run_id"]
    if not structural_readback(dsn,run,source):
        return "INCOMPLETE_OR_AMBIGUOUS_PARENT_CHILD_OR_STRATEGY"
    if not allow_journal:
        return "INDEPENDENT_JOURNAL_UNKNOWN"
    rows=sealed_rows(journal,key,run)
    if len(rows)!=len(inventory["positions"]):
        return "MANAGED_RECEIPTS_MISSING"
    previous=sealed_rows(journal,key,"synthetic-p2-atomic-prior-monitor")
    prev_by_id={r["entry_order_id"]:r for r in previous}
    cur_by_id={r["entry_order_id"]:r for r in rows}
    if set(cur_by_id)!=set(p["entry_order_id"] for p in inventory["positions"]):
        return "MANAGED_RECEIPTS_UNMATCHED"
    scan={"run_id":run,"collected_at_utc":source["p_rows"][0]["collected_at_utc"]}
    prior=[];attempts=[];quotes=[]
    for i,p in enumerate(inventory["positions"]):
        prev=prev_by_id.get(p["entry_order_id"])
        cur=cur_by_id[p["entry_order_id"]]
        if (prev is None or cur["symbol"]!=p["symbol"] or
           cur["predecessor_receipt_sha256"]!=prev["record_sha256"]):
            return "PRIOR_SEAL_LINKAGE_MISSING"
        prior.append({"entry_order_id":p["entry_order_id"],"source_run_id":prev["source_run_id"],
                      "captured_at_utc":prev["observed_at_utc"],"seal_verified":True})
        quote={"source_run_id":run,"symbol":p["symbol"],"source":cur["quote_source"],
               "capture_manifest_sha256":cur["capture_manifest_sha256"],
               "captured_at_utc":cur["observed_at_utc"],
               "bid_price":"1","ask_price":"1.01","bid_size":"10","ask_size":"10"}
        quotes.append(quote)
        attempts.append({"source_run_id":run,"entry_order_id":p["entry_order_id"],
          "symbol":p["symbol"],"direction":"LONG","attempt_id":"synthetic-attempt-"+str(i),
          "observed_at_utc":cur["observed_at_utc"],"outcome":"NO_TRIGGER","blockers":[],
          "best_bid":"1","best_ask":"1.01","best_bid_size":"10","best_ask_size":"10",
          "evidence":{"quote_source":cur["quote_source"],
                      "capture_manifest_sha256":cur["capture_manifest_sha256"]}})
    result=evaluate(inventory,scan,attempts,quotes,prior,approved_sources=frozenset({QUOTE_SOURCE}))
    if result["locally_observable"]!=len(inventory["positions"]) or result["alerts"]:
        return "POSITION_OBSERVATION_NOT_QUALIFIED"
    assert result["scientific_pass_permitted"] is False
    assert result["independent_source_authentication_verified"] is False
    return "LOCAL_STRUCTURAL_RECEIPTS_VERIFIED_NOT_SCIENTIFIC_COMPLETE"

def verify():
    assert os.environ.get("GITHUB_ACTIONS")=="true"
    for k in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","DATABASE_URL",
              "BITGET_API_KEY","BITGET_SECRET_KEY","BITGET_API_PASSPHRASE"):
        assert not os.environ.get(k), "Unexpected privileged source variable"
    dsn,jdsn=guard_dsn(),journal_dsn()
    source=make_payload(2,"synthetic-p2-atomic-ambiguous-committed")
    failed=make_payload(2,"synthetic-p2-atomic-ambiguous-rolledback")
    failed["p_fault"]="AFTER_CHILDREN"
    inv=make_positions(source)
    # Real HTTP response withheld after successful downstream RPC commit.
    assert lost_response(source)==200
    assert inspect_atomic(dsn,source["p_run_id"])==(1,2,20,4,1)
    with psycopg.connect(jdsn,autocommit=True) as journal:
        assert str(journal.execute("SHOW server_version_num").fetchone()[0]).startswith("16")
        journal.execute(SCHEMA)
        key=os.urandom(32) # Ephemeral ONLY: no independent long-lived source authority.
        assert classify(dsn,journal,key,source,inv)=="MANAGED_RECEIPTS_MISSING"
        # Parent + 0 children, even with a parent persisted, is never COMPLETE.
        bare="synthetic-p2-atomic-parent-only"
        with make_conn(dsn,DBNAME) as db:
            db.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES (%s)",(bare,))
        bogus=make_payload(2,bare)
        assert classify(dsn,journal,key,bogus,make_positions(bogus))=="INCOMPLETE_OR_AMBIGUOUS_PARENT_CHILD_OR_STRATEGY"
        # Lost response after REAL rollback: the identical HTTP outcome must
        # NOT be treated as a successful source run.
        assert lost_response(failed) in (400,409)
        assert inspect_atomic(dsn,failed["p_run_id"])==(0,0,0,0,0)
        assert classify(dsn,journal,key,failed,make_positions(failed))=="INCOMPLETE_OR_AMBIGUOUS_PARENT_CHILD_OR_STRATEGY"
        # Genuine committed SECOND DB records. Simulated quote data remains unauthenticated.
        obs=utc(source["p_rows"][0]["collected_at_utc"])
        first=(obs-timedelta(minutes=34,seconds=59)).isoformat()
        when=obs.isoformat()
        for i,p in enumerate(inv["positions"]):
            cap=sha({"local_synthetic_quote":p["symbol"]})
            prev=seal_fields("synthetic-p2-atomic-prior-monitor",p["entry_order_id"],p["symbol"],first,"GENESIS_LOCAL_ONLY",cap)
            predecessor=insert_seal(journal,key,prev)
            if i==0:
                curr=seal_fields(source["p_run_id"],p["entry_order_id"],p["symbol"],when,predecessor,cap)
                insert_seal(journal,key,curr)
        assert classify(dsn,journal,key,source,inv)=="MANAGED_RECEIPTS_MISSING"
        # Separate journal connection outage must never be a safety PASS.
        assert classify(dsn,journal,key,source,inv,allow_journal=False)=="INDEPENDENT_JOURNAL_UNKNOWN"
        second=inv["positions"][1]
        cap=sha({"local_synthetic_quote":second["symbol"]})
        parent_sha=next(x for x in sealed_rows(journal,key,"synthetic-p2-atomic-prior-monitor")
                        if x["entry_order_id"]==second["entry_order_id"])["record_sha256"]
        insert_seal(journal,key,seal_fields(source["p_run_id"],second["entry_order_id"],second["symbol"],when,parent_sha,cap))
        assert classify(dsn,journal,key,source,inv)=="LOCAL_STRUCTURAL_RECEIPTS_VERIFIED_NOT_SCIENTIFIC_COMPLETE"
        try:
            sealed_rows(journal,b"wrong-key",source["p_run_id"])
        except AssertionError:pass
        else:raise AssertionError("Tampered/wrong signing key was accepted")
        # Immutable custody cannot silently rewrite a misleading observation.
        try:
            journal.execute("""UPDATE p2_ambiguous.position_seals SET symbol='FAKEUSDT'
              WHERE source_run_id=%s""",(source["p_run_id"],))
        except psycopg.errors.RaiseException:pass
        else:raise AssertionError("Journal edit was permitted")
        count=journal.execute("""SELECT count(*) FROM p2_ambiguous.position_seals""").fetchone()[0]
        assert count==4
        assert journal.execute("""SELECT count(*) FROM p2_ambiguous.position_seals
          WHERE NOT paper_only OR exchange_authority OR trade_permission OR scientific_pass_permitted""").fetchone()[0]==0
    print("P2_AMBIGUOUS_HTTP_COMMIT_FAIL_CLOSED_PASS "+json.dumps({
      "real_postgrest_http_response_timeout_after_commit":True,
      "actual_server_success_commit_independently_read":True,
      "real_http_response_timeout_after_rollback":True,
      "rollback_left_no_parent_child_or_receipt":True,
      "parent_only_rejected":True,
      "source_children_and_strategies_exactly_read_back":True,
      "managed_positions_synthetically_required":2,
      "missing_one_sealed_monitor_receipt_rejected":True,
      "separate_pg16_prior_receipt_chains_verified":True,
      "wrong_key_rejected":True,"append_only_journal_rejected_mutation":True,
      "independent_journal_outage_fails_closed":True,
      "boundary_34m59s_research_only":True,
      "replay_creates_no_qualified_live_observation":True,
      "independent_live_inventory_authenticated":False,
      "independent_live_quote_authenticated":False,
      "live_35m_monitoring_proven":False,
      "scientific_pass_permitted":False,
      "primary_hourly_modified":False,"production_database_mutated":False,
      "render_deployment":False,"trade_permission":False},sort_keys=True))

if __name__=="__main__":verify()
