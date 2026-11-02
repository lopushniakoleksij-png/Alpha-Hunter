#!/usr/bin/env python3
"""P2 ISOLATED HTTP collector -> independent PG16 append-only quote custody.

This executes ONLY against an in-process 127.0.0.1 mock Bitget API and two
ephemeral localhost PostgreSQL16 databases in GitHub Actions. It is NOT the
real Bitget venue, a trusted live collector, an authenticated paper-ledger
snapshot, operational 35-minute monitoring or a paper/real order authority.

An independent journal receipt MUST commit before main analytics is attempted.
A main DB timeout cannot silently erase a prior journal diagnostic. If the
journal is down, the receipt fails CLOSED and no scientific PASS is produced.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from urllib.request import Request,urlopen
from urllib.parse import urlsplit,parse_qs
import json
import secrets

import psycopg

from successor_pg16_tcp_benchmark_v01 import guard_dsn,make_conn,BASE_DB
from successor_dual_pg16_journal_fault_v01 import journal_dsn
from successor_dual_pg16_position_diagnostic_v01 import sample
from successor_forward_quote_transport_custody_v01 import (
    build_transport_quote_capture,build_shadow_quote_attempt,canonical_json,
    QuoteCustodyIncomplete,
)

URL_PATH="/api/v2/mix/market/ticker"
RUN="synthetic-p2-custody-primary-timeout"
PRIOR_RUN="synthetic-p2-custody-prior"
SYMBOL="QUSDT"
ORDER_ID="synthetic-forward-managed"
QUARANTINE_ORDER="synthetic-legacy-partial"
DDL="""
CREATE SCHEMA p2_http_custody;
REVOKE ALL ON SCHEMA p2_http_custody FROM PUBLIC;
CREATE TABLE p2_http_custody.receipts(
 run_id text NOT NULL,
 entry_order_id text NOT NULL,
 source_manifest_sha256 text NOT NULL CHECK(source_manifest_sha256~'^[0-9a-f]{64}$'),
 event_type text NOT NULL CHECK(event_type IN ('QUOTE_CAPTURE_LOCAL_ONLY','UNPROTECTED_INCIDENT')),
 source_endpoint text,
 captured_at_utc timestamptz NOT NULL,
 capture_sha256 text,
 previous_mac text,
 record jsonb NOT NULL,
 receipt_mac text NOT NULL CHECK(receipt_mac~'^[0-9a-f]{64}$'),
 source_authentication boolean NOT NULL DEFAULT false CHECK(source_authentication=false),
 paper_continuity_proven boolean NOT NULL DEFAULT false CHECK(paper_continuity_proven=false),
 trade_permission boolean NOT NULL DEFAULT false CHECK(trade_permission=false),
 exchange_authority boolean NOT NULL DEFAULT false CHECK(exchange_authority=false),
 scientific_pass boolean NOT NULL DEFAULT false CHECK(scientific_pass=false),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(run_id,entry_order_id)
);
CREATE FUNCTION p2_http_custody.reject_modifications()
 RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $block$
BEGIN RAISE EXCEPTION 'IMMUTABLE_P2_CUSTODY_RECEIPT'; END;
$block$;
CREATE TRIGGER no_update_delete BEFORE UPDATE OR DELETE
 ON p2_http_custody.receipts FOR EACH ROW
 EXECUTE FUNCTION p2_http_custody.reject_modifications();
REVOKE ALL ON ALL TABLES IN SCHEMA p2_http_custody FROM PUBLIC;
"""
class MockTickerHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        parts=urlsplit(self.path)
        query=parse_qs(parts.query)
        if parts.path!=URL_PATH or query.get("symbol")!=[SYMBOL]:
            self.send_error(404,"NOT_AN_APPROVED_MOCK_VENUE_ROUTE");return
        row={"symbol":SYMBOL,
             "ts":str(int(datetime.now(timezone.utc).timestamp()*1000)),
             "bidPr":"0.90","askPr":"0.91",
             "bidSz":"12","askSz":"11"}
        data=json.dumps({"code":"00000","data":[row]}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

@contextmanager
def mock_http():
    server=ThreadingHTTPServer(("127.0.0.1",0),MockTickerHandler)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()

def fetch_from_local_collector(url,run):
    """Instrumented transport wrapper; no arbitrary external URL accepted."""
    endpoint=urlsplit(url)
    if endpoint.hostname!="127.0.0.1" or endpoint.path!=URL_PATH:
        raise QuoteCustodyIncomplete("EPHEMERAL_TRANSPORT_HOST_NOT_APPROVED")
    if parse_qs(endpoint.query)!={"symbol":[SYMBOL]}:
        raise QuoteCustodyIncomplete("CAPTURE_SYMBOL_REQUEST_NOT_EXACT")
    transport_id=secrets.token_hex(12)
    with urlopen(Request(url,headers={"Accept":"application/json"}),timeout=3) as resp:
        if resp.status!=200:raise QuoteCustodyIncomplete("HTTP_CAPTURE_FAILED")
        body=json.loads(resp.read())
        captured_at=datetime.now(timezone.utc).isoformat()
    if body.get("code")!="00000" or len(body.get("data",[]))!=1:
        raise QuoteCustodyIncomplete("VENUE_RESPONSE_SHAPE_UNVERIFIED")
    capture=build_transport_quote_capture(
        endpoint=URL_PATH,requested_symbol=SYMBOL,observed_at_utc=captured_at,
        transport_request_id=transport_id,raw_response_row=body["data"][0],
        upstream_call_succeeded=True,run_id=run,
    )
    # Transport chain consists of a local mock HTTP response and exact bound
    # source row. It has NO venue TLS/response-signature or identity assurance.
    assert capture["source_authentication"]=="SUPPLIED_TRANSPORT_METADATA_NOT_INDEPENDENTLY_VERIFIED"
    return capture

def signed_fields(inv_sha,run,order,status,at,cap_digest,previous_mac,record):
    return {"source_manifest_sha256":inv_sha,"run_id":run,
      "entry_order_id":order,"event_type":status,
      "captured_at_utc":at,
      "capture_sha256":cap_digest,"previous_mac":previous_mac,
      "record":record}

def mac_for(key,fields):
    return hmac_new(key,canonical_json(fields).encode(),"sha256").hexdigest()

def store_receipt(conn,key,fields):
    digest=mac_for(key,fields)
    with conn.transaction():
        conn.execute("""INSERT INTO p2_http_custody.receipts(
          run_id,entry_order_id,source_manifest_sha256,event_type,
          source_endpoint,captured_at_utc,capture_sha256,previous_mac,
          record,receipt_mac)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",(
          fields["run_id"],fields["entry_order_id"],
          fields["source_manifest_sha256"],fields["event_type"],
          fields["record"].get("source_endpoint"),
          fields["captured_at_utc"],fields["capture_sha256"],
          fields["previous_mac"],canonical_json(fields["record"]),digest))
    return digest

def read_exact(conn,key,run,order):
    row=conn.execute("""SELECT source_manifest_sha256,event_type,
       captured_at_utc,capture_sha256,previous_mac,record,receipt_mac
       FROM p2_http_custody.receipts
       WHERE run_id=%s AND entry_order_id=%s""",(run,order)).fetchone()
    if row is None:raise AssertionError("MISSING_DURABLE_SECONDARY_RECEIPT")
    inv,status,at,cap,prior,record,mac=row
    fields=signed_fields(inv,run,order,status,at.astimezone(timezone.utc).isoformat(),cap,prior,record)
    if not compare_digest(mac,mac_for(key,fields)):
        raise AssertionError("JOURNAL_RECEIPT_HMAC_INVALID")
    return fields,mac

def verify():
    main_dsn=guard_dsn()
    independent_dsn=journal_dsn()
    key=secrets.token_bytes(32)  # ephemeral CI-only key, not persisted or prod usable.
    inv,parent,dispositions,_=sample()
    assert len(inv["positions"])==2 and inv["expected_position_count"]==2
    assert {d["entry_order_id"] for d in dispositions}=={
      ORDER_ID,QUARANTINE_ORDER}
    with mock_http() as host:
        first=fetch_from_local_collector(
          host+URL_PATH+"?symbol="+SYMBOL,PRIOR_RUN)
        current=fetch_from_local_collector(
          host+URL_PATH+"?symbol="+SYMBOL,RUN)
        assert current["capture_manifest_sha256"]!=first["capture_manifest_sha256"]

    prior_attempt=build_shadow_quote_attempt(first,
      entry_order_id=ORDER_ID,symbol=SYMBOL,direction="LONG",
      source_run_id=PRIOR_RUN,
      scan_collected_at_utc=first["transport_captured_at_utc"])
    current_attempt=build_shadow_quote_attempt(current,
      entry_order_id=ORDER_ID,symbol=SYMBOL,direction="LONG",
      source_run_id=RUN,
      scan_collected_at_utc=current["transport_captured_at_utc"])
    first_time=datetime.fromisoformat(first["transport_captured_at_utc"])
    second_time=datetime.fromisoformat(current["transport_captured_at_utc"])
    seconds=(second_time-first_time).total_seconds()
    assert 0<=seconds<2100
    assert not prior_attempt["exchange_authority"]
    assert not current_attempt["scientific_pass_permitted"]

    with psycopg.connect(independent_dsn,autocommit=True) as journal:
        journal.execute(DDL)
        prior_fields=signed_fields(
           inv["manifest_sha256"],PRIOR_RUN,ORDER_ID,"QUOTE_CAPTURE_LOCAL_ONLY",
           first["transport_captured_at_utc"],first["capture_manifest_sha256"],
           None,first)
        previous_mac=store_receipt(journal,key,prior_fields)
        # Check PREVIOUS custody via the actual immutable second-store row,
        # instead of accepting externally supplied 'seal_verified=true'.
        prev_data,prev_verified=read_exact(journal,key,PRIOR_RUN,ORDER_ID)
        assert prev_verified==previous_mac
        assert prev_data["capture_sha256"]==first["capture_manifest_sha256"]

        current_fields=signed_fields(
           inv["manifest_sha256"],RUN,ORDER_ID,"QUOTE_CAPTURE_LOCAL_ONLY",
           current["transport_captured_at_utc"],
           current["capture_manifest_sha256"],previous_mac,current)
        current_mac=store_receipt(journal,key,current_fields)
        unprotected_fields=signed_fields(
           inv["manifest_sha256"],RUN,QUARANTINE_ORDER,
           "UNPROTECTED_INCIDENT",second_time.isoformat(),None,None,
           {"symbol":"NMRUSDT","direction":"LONG",
            "incident":"SYNTHETIC_LEGACY_RESIDUAL_WITHOUT_ACTIVE_PROTECTION",
            "paper_only":True})
        store_receipt(journal,key,unprotected_fields)
        current_data,mac=read_exact(journal,key,RUN,ORDER_ID)
        assert mac==current_mac
        assert current_data["previous_mac"]==previous_mac
        # A wrong key cannot validate a genuine journal row. In production
        # key custody must survive restarts and have distinct operator scope.
        try:read_exact(journal,secrets.token_bytes(32),RUN,ORDER_ID)
        except AssertionError as e:assert "HMAC_INVALID" in str(e)
        else:raise AssertionError("Incorrect verifier key accepted")

        # Simulate primary analytics write failure AFTER independently
        # committing quote + incident evidence to a separate PG16 host.
        main_cancel=False
        try:
            with make_conn(main_dsn,BASE_DB) as primary:
                with primary.transaction():
                    primary.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES(%s)",(RUN,))
                    primary.execute("SET LOCAL statement_timeout='10ms'")
                    primary.execute("SELECT pg_sleep(0.2)")
        except psycopg.errors.QueryCanceled:
            main_cancel=True
        assert main_cancel
        with make_conn(main_dsn,BASE_DB) as primary:
            assert primary.execute(
                "SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id=%s",
                (RUN,)).fetchone()[0]==0
        assert read_exact(journal,key,RUN,ORDER_ID)[1]==current_mac
        assert read_exact(journal,key,RUN,QUARANTINE_ORDER)[0]["event_type"]=="UNPROTECTED_INCIDENT"

        # Can't change a journal row to fabricate scientific PASS or a
        # different quote; immutable trigger rejects DELETE and UPDATE.
        try:
            journal.execute("""UPDATE p2_http_custody.receipts
               SET scientific_pass=true WHERE run_id=%s""",(RUN,))
        except psycopg.errors.RaiseException:pass
        else:raise AssertionError("Journal source was mutable")
        assert journal.execute(
            """SELECT count(*) FROM p2_http_custody.receipts
              WHERE source_authentication OR paper_continuity_proven
              OR trade_permission OR exchange_authority OR scientific_pass
            """).fetchone()[0]==0

        # Failed second-store commit is not a receipt. Force a DB statement
        # timeout after inserting a NEW row, before transaction completes.
        broken_run="synthetic-p2-journal-secondary-timeout"
        aborted=False
        try:
            with journal.transaction():
                fields=signed_fields(inv["manifest_sha256"],broken_run,
                    ORDER_ID,"QUOTE_CAPTURE_LOCAL_ONLY",
                    current["transport_captured_at_utc"],
                    current["capture_manifest_sha256"],None,current)
                journal.execute("""INSERT INTO p2_http_custody.receipts(
                   run_id,entry_order_id,source_manifest_sha256,event_type,
                   captured_at_utc,capture_sha256,previous_mac,
                   record,receipt_mac) VALUES
                   (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",(
                   broken_run,ORDER_ID,inv["manifest_sha256"],
                   "QUOTE_CAPTURE_LOCAL_ONLY",
                   current["transport_captured_at_utc"],
                   current["capture_manifest_sha256"],None,
                   canonical_json(current),mac_for(key,fields)))
                journal.execute("SET LOCAL statement_timeout='5ms'")
                journal.execute("SELECT pg_sleep(0.08)")
        except psycopg.errors.QueryCanceled:
            aborted=True
        assert aborted
        assert journal.execute("""SELECT count(*) FROM p2_http_custody.receipts
           WHERE run_id=%s""",(broken_run,)).fetchone()[0]==0
        # Exact same run/position duplicate insertion cannot create two
        # receipts. A conflicting replay must be refused.
        try:store_receipt(journal,key,current_fields)
        except psycopg.errors.UniqueViolation:pass
        else:raise AssertionError("Duplicate receipt accepted")

        count=journal.execute("SELECT count(*) FROM p2_http_custody.receipts").fetchone()[0]
        assert count==3
        print("P2_SIMULATED_HTTP_COLLECTOR_INDEPENDENT_CUSTODY_PASS "+
          json.dumps({
           "venue_source":"LOCAL_MOCK_HTTP_NOT_AUTHENTICATED_BITGET",
           "source_manifest_claim":"SUPPLIED_ONLY",
           "independent_durable_receipts":count,
           "current_managed_receipt":1,
           "legacy_unprotected_visible":1,
           "prior_receipt_read_from_separate_pg16":True,
           "second_store_hmac_key_ephemeral":True,
           "captured_observation_interval_seconds":round(seconds,3),
           "live_35m_continuity_proven":False,
           "main_sql_timeout_after_journal_commit":True,
           "journal_timeout_no_partial_seal":True,
           "tamper_and_wrong_key_rejected":True,
           "existing_positions_modified":False,
           "scientific_pass":False,"exchange_authority":False,
           "prod_deployment":False},sort_keys=True))
if __name__=="__main__":
    verify()
