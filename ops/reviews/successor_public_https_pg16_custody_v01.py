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
from pathlib import Path

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
    first, raw_first = capture_public_quote(root+"-1", include_raw_bytes=True)
    second, raw_second = capture_public_quote(root+"-2", include_raw_bytes=True)
    assert sha256(raw_first).hexdigest() == first["response_sha256"]
    assert sha256(raw_second).hexdigest() == second["response_sha256"]
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
        # A GitHub-hosted artifact provides a second bounded-retention copy
        # outside Supabase. It is NOT an independently administered append-only
        # journal, guaranteed durable delivery, or venue-signed price feed.
        export = os.getenv("AH_P02_EXPORT_PUBLIC_QUOTE_PROOF")
        if export is not None and export != "EPHEMERAL_CI_ARTIFACT_ONLY":
            raise AssertionError("UNAPPROVED_PUBLIC_PROOF_EXPORT")
        if export == "EPHEMERAL_CI_ARTIFACT_ONLY":
            proof_dir = Path("p02-public-quote-ci-proof")
            proof_dir.mkdir(exist_ok=True)
            for n, raw in enumerate((raw_first, raw_second), start=1):
                if len(raw) > 65536 or not raw:
                    raise AssertionError("RAW_PUBLIC_RESPONSE_INVALID")
                (proof_dir / f"public-ticker-{n}.json").write_bytes(raw)
            manifest = {
                "proof_scope": "ONE_SHOT_PUBLIC_HTTPS_ONLY_NO_POSITION_SOURCE",
                "source_host": "api.bitget.com",
                "endpoint": "/api/v2/mix/market/ticker",
                "product_type": "USDT-FUTURES",
                "symbol": "BTCUSDT",
                "captures": [
                    { "sequence": n, "run_id": q["source_run_id"],
                      "raw_filename": f"public-ticker-{n}.json",
                      "raw_response_sha256": q["response_sha256"],
                      "quote_row_sha256": q["raw_response_row_sha256"],
                      "capture_manifest_sha256": q["capture_manifest_sha256"],
                      "capture_utc": q["transport_captured_at_utc"],
                      "request_id": q["request_id"],
                      "exchange_timestamp_ms": q["exchange_timestamp_ms"] }
                    for n, q in enumerate((first, second), start=1)
                ],
                "ephemeral_independent_pg16_commit_readback_passed": True,
                "bounded_ci_retention_not_permanent": True,
                "actual_paper_inventory_authenticated": False,
                "authenticated_venue_signed_prices": False,
                "persistent_independent_journal": False,
                "real_alert_delivery": False,
                "operational_monitoring_35m_proven": False,
                "scientific_pass_permitted": False,
                "production_mutated": False,
                "trade_permission": False,
                "exchange_authority": False,
            }
            (proof_dir / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                encoding="utf-8"
            )
            for row in manifest["captures"]:
                saved = (proof_dir / row["raw_filename"]).read_bytes()
                if sha256(saved).hexdigest() != row["raw_response_sha256"]:
                    raise AssertionError("RAW_PUBLIC_PROOF_READBACK_HASH_MISMATCH")

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
