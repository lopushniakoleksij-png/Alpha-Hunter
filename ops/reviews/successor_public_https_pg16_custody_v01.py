"""P0.2 one-shot research: real public quote -> independent PostgreSQL16 custody.

Two fixed unauthenticated HTTPS GETs only. Separate ephemeral runner-local
PostgreSQL16 servers. No Supabase access, paper engine or trading authority.
"""
from datetime import datetime, timezone
from hashlib import sha256
from hmac import new as hmac_new, compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen
from urllib.error import URLError
import json
import os
import secrets
import time

import psycopg

from successor_pg16_tcp_benchmark_v01 import guard_dsn
from successor_dual_pg16_journal_fault_v01 import journal_dsn
from successor_forward_quote_transport_custody_v01 import canonical_json
from successor_public_https_capture_v01 import capture_public_quote

SCHEMA = """
CREATE SCHEMA p02_public_custody;
REVOKE ALL ON SCHEMA p02_public_custody FROM PUBLIC;
CREATE TABLE p02_public_custody.receipts (
 seq integer PRIMARY KEY CHECK(seq IN (1,2)),
 run_id text NOT NULL UNIQUE,
 collected_at timestamptz NOT NULL,
 public_response_sha256 text NOT NULL,
 previous_mac text,
 record jsonb NOT NULL,
 receipt_mac text NOT NULL,
 scientific_pass boolean NOT NULL DEFAULT false CHECK(NOT scientific_pass),
 exchange_authority boolean NOT NULL DEFAULT false CHECK(NOT exchange_authority),
 trade_permission boolean NOT NULL DEFAULT false CHECK(NOT trade_permission),
 source_inventory_authenticated boolean NOT NULL DEFAULT false
   CHECK(NOT source_inventory_authenticated)
);
CREATE FUNCTION p02_public_custody.reject_mutation()
 RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $block$
BEGIN RAISE EXCEPTION 'IMMUTABLE_RECEIPT'; END;
$block$;
CREATE TRIGGER reject_changes BEFORE UPDATE OR DELETE
 ON p02_public_custody.receipts FOR EACH ROW
 EXECUTE FUNCTION p02_public_custody.reject_mutation();
REVOKE ALL ON ALL TABLES IN SCHEMA p02_public_custody FROM PUBLIC;
"""

def sign(key, fields):
    return hmac_new(key, canonical_json(fields).encode("utf-8"), "sha256").hexdigest()

def stored_fields(seq, run, collected, response_sha, previous_mac, record):
    return {"seq":seq,"run_id":run,"collected_at":collected,
            "response_sha256":response_sha,"previous_mac":previous_mac,
            "record":record}

def append(conn, key, seq, run, record, previous_mac):
    fields=stored_fields(seq,run,record["transport_captured_at_utc"],
        record["response_sha256"],previous_mac,record)
    receipt_mac=sign(key,fields)
    with conn.transaction():
        conn.execute("""INSERT INTO p02_public_custody.receipts(
          seq,run_id,collected_at,public_response_sha256,previous_mac,
          record,receipt_mac
        ) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s)""",
        (seq,run,fields["collected_at"],fields["response_sha256"],previous_mac,
         canonical_json(record),receipt_mac))
    return receipt_mac

def verify(conn,key,seq,prior):
    row=conn.execute("""SELECT run_id,collected_at,public_response_sha256,
      previous_mac,record,receipt_mac FROM p02_public_custody.receipts
      WHERE seq=%s""",(seq,)).fetchone()
    if row is None:
        raise AssertionError("INDEPENDENT_RECEIPT_MISSING")
    run,collected,digest,previous_mac,record,stored_mac=row
    if previous_mac!=prior or record.get("response_sha256")!=digest:
        raise AssertionError("SOURCE_CHAIN_MISMATCH")
    if (record.get("tls_host_checked") is not True
       or record.get("venue_price_signature_verified") is not False
       or record.get("source_inventory_authenticated") is not False):
        raise AssertionError("FALSE_SOURCE_AUTHORITY")
    fields=stored_fields(seq,run,collected.astimezone(timezone.utc).isoformat(),
                         digest,previous_mac,record)
    if not compare_digest(stored_mac,sign(key,fields)):
        raise AssertionError("HMAC_RECEIPT_VERIFICATION_FAILED")
    return stored_mac

def socket_read_timeout():
    """Force an actual OS socket read timeout; not an injected Python exception."""
    class Slow(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            time.sleep(.15)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"late")
            except (BrokenPipeError,ConnectionResetError): pass
    server=ThreadingHTTPServer(("127.0.0.1",0),Slow)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        try:
            urlopen("http://127.0.0.1:"+str(server.server_port)+"/slow",
                    timeout=.02).read()
        except (TimeoutError,URLError,OSError):
            return True
        raise AssertionError("SOCKET_TIMEOUT_NOT_DETECTED")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

def run():
    if os.getenv("AH_P02_ONE_SHOT_APPROVAL")!="EPHEMERAL_CI_PUBLIC_GET_ONLY":
        raise RuntimeError("P02_CI_ONLY")
    for k in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","BITGET_API_KEY",
              "BITGET_SECRET_KEY","BITGET_API_PASSPHRASE","DATABASE_URL"):
        if os.getenv(k):
            raise RuntimeError("NO_PRODUCTION_CREDENTIALS_ALLOWED")
    main=guard_dsn()
    independent=journal_dsn()
    assert socket_read_timeout()
    root="p02-synthetic-"+secrets.token_hex(8)
    first=capture_public_quote(root+"-1")
    second=capture_public_quote(root+"-2")
    gap=(datetime.fromisoformat(second["transport_captured_at_utc"])
         -datetime.fromisoformat(first["transport_captured_at_utc"])).total_seconds()
    if gap < 0 or gap > 2100:
        raise AssertionError("FROZEN_35MIN_GAP_BREACH")
    key=secrets.token_bytes(32)  # Temporary test key, not approved key custody.
    with psycopg.connect(independent,autocommit=True) as secondary:
        if not str(secondary.execute("SHOW server_version_num").fetchone()[0]).startswith("16"):
            raise AssertionError("ISOLATED_PG16_REQUIRED")
        secondary.execute(SCHEMA)
        one=append(secondary,key,1,root+"-1",first,None)
        assert verify(secondary,key,1,None)==one
        two=append(secondary,key,2,root+"-2",second,one)
        assert verify(secondary,key,2,one)==two
        try:
            verify(secondary,b"wrong-test-key",2,one)
        except AssertionError as exc:
            assert "HMAC" in str(exc)
        else:
            raise AssertionError("BAD_MAC_ACCEPTED")
        with psycopg.connect(main,autocommit=True) as primary:
            try:
                with primary.transaction():
                    primary.execute("SET LOCAL statement_timeout='10ms'")
                    primary.execute("SELECT pg_sleep(0.25)")
            except psycopg.errors.QueryCanceled:
                pass
            else:
                raise AssertionError("PRIMARY_TIMEOUT_NOT_TRIGGERED")
        assert verify(secondary,key,2,one)==two
        try:
            with secondary.transaction():
                secondary.execute("SET LOCAL statement_timeout='10ms'")
                secondary.execute("SELECT pg_sleep(0.25)")
        except psycopg.errors.QueryCanceled:
            pass
        else:
            raise AssertionError("JOURNAL_TIMEOUT_NOT_TRIGGERED")
        assert secondary.execute("SELECT COUNT(*) FROM p02_public_custody.receipts").fetchone()[0]==2
        try:
            with secondary.transaction():
                secondary.execute("UPDATE p02_public_custody.receipts SET run_id='invalid' WHERE seq=1")
        except psycopg.errors.RaiseException:
            pass
        else:
            raise AssertionError("MUTABLE_JOURNAL_NOT_ACCEPTABLE")
        forbidden=secondary.execute("""SELECT COUNT(*) FROM p02_public_custody.receipts
            WHERE scientific_pass OR trade_permission OR exchange_authority
              OR source_inventory_authenticated""").fetchone()[0]
        assert forbidden==0
        print("P02_PUBLIC_HTTPS_AND_INDEPENDENT_PG16_CUSTODY_PASS "+json.dumps({
            "genuine_bitget_https_captures":2,
            "tls_hostname_ca_checked":True,
            "exchange_signed_quote":False,
            "independent_receipts":2,
            "primary_database_timeout_tested":True,
            "secondary_database_timeout_tested":True,
            "real_socket_timeout_tested":True,
            "hmac_chain_verified":True,
            "live_paper_inventory_authenticated":False,
            "full_35m_continuity_proven":False,
            "trading_authority":False,
            "prod_deployment":False,
            "observed_capture_gap_seconds":round(gap,3),
        },sort_keys=True))

if __name__=="__main__":
    run()
