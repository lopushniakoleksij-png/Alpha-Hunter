#!/usr/bin/env python3
"""P2 draft-only source/quote incident -> separate PG16 journal re-open test.

Two independent *ephemeral* localhost PG16 services under existing GitHub CI.
The signed mock source and mock recipient proof is sourced solely from the
unit-test fixture. No actual external quote, production database, email, or
persistent cross-failure-domain infrastructure is accessed. NEVER promote.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
import psycopg
from psycopg import errors
from successor_pg16_tcp_benchmark_v01 import guard_dsn
from successor_dual_pg16_journal_fault_v01 import journal_dsn

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests"))
from test_successor_p2_incident_delivery_lineage_v01 import sample,verify

SCHEMA="""
CREATE SCHEMA p2_lineage_ephemeral;
REVOKE ALL ON SCHEMA p2_lineage_ephemeral FROM PUBLIC;
CREATE TABLE p2_lineage_ephemeral.incident_receipts(
 record_id text PRIMARY KEY,
 event_id text NOT NULL UNIQUE,
 incident_digest text NOT NULL CHECK(length(incident_digest)=64),
 evidence_bundle_digest text NOT NULL CHECK(length(evidence_bundle_digest)=64),
 paper_only boolean NOT NULL DEFAULT true CHECK(paper_only),
 trade_permission boolean NOT NULL DEFAULT false CHECK(NOT trade_permission),
 exchange_authority boolean NOT NULL DEFAULT false CHECK(NOT exchange_authority),
 scientific_pass_permitted boolean NOT NULL DEFAULT false CHECK(NOT scientific_pass_permitted),
 committed_at_utc timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE FUNCTION p2_lineage_ephemeral.reject_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $body$
BEGIN
 RAISE EXCEPTION 'ISOLATED_INCIDENT_RECEIPT_IMMUTABLE';
END;
$body$;
CREATE TRIGGER immutable_receipt BEFORE UPDATE OR DELETE
ON p2_lineage_ephemeral.incident_receipts FOR EACH ROW
EXECUTE FUNCTION p2_lineage_ephemeral.reject_mutation();
REVOKE ALL ON ALL TABLES IN SCHEMA p2_lineage_ephemeral FROM PUBLIC;
"""

def readback(dsn, record_id):
    # Separate connection with no pending writer transaction.
    with psycopg.connect(dsn,connect_timeout=5,autocommit=True) as cx:
        row=cx.execute("""SELECT record_id,event_id,incident_digest,
            evidence_bundle_digest FROM p2_lineage_ephemeral.incident_receipts
            WHERE record_id=%s""",(record_id,)).fetchone()
        return dict(zip(("record_id","event_id","incident_digest",
                         "evidence_bundle_digest"),row)) if row else None

def main():
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise AssertionError("Only disposable CI PostgreSQL may run this")
    for key in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","DATABASE_URL",
                "BITGET_API_KEY","BITGET_SECRET_KEY","BITGET_API_PASSPHRASE"):
        if os.environ.get(key):
            raise AssertionError("Real credentials are prohibited")
    _=guard_dsn() # guard existing isolated primary localhost 5432
    dsn=journal_dsn() # guard separate ephemeral localhost 5433
    x=sample()
    original=x["recovered_row"]
    with psycopg.connect(dsn,connect_timeout=5,autocommit=True) as cx:
        if not str(cx.execute("SHOW server_version_num").fetchone()[0]).startswith("16"):
            raise AssertionError("Disposable PostgreSQL 16 only")
        cx.execute(SCHEMA)
        cx.execute("""INSERT INTO p2_lineage_ephemeral.incident_receipts
           (record_id,event_id,incident_digest,evidence_bundle_digest)
           VALUES (%s,%s,%s,%s)""",(
            original["record_id"],original["event_id"],
            original["incident_digest"],original["evidence_bundle_digest"]))
    recovered=readback(dsn,original["record_id"])
    assert recovered==original
    assert verify(x,recovered_row=recovered)["status"]=="OFFLINE_INCIDENT_TO_MOCK_INBOX_LINKED_NOT_LIVE"
    assert verify(x,recovered_row=None)["status"]=="FAIL_CLOSED_EVIDENCE_LINKAGE_UNKNOWN"
    wrong=dict(recovered,incident_digest="a"*64)
    assert verify(x,recovered_row=wrong)["status"]=="FAIL_CLOSED_EVIDENCE_LINKAGE_UNKNOWN"
    with psycopg.connect(dsn,connect_timeout=5,autocommit=True) as cx:
        try:
            cx.execute("""UPDATE p2_lineage_ephemeral.incident_receipts
              SET incident_digest=%s WHERE record_id=%s""",
              ("f"*64,original["record_id"]))
        except errors.RaiseException as exc:
            assert "ISOLATED_INCIDENT_RECEIPT_IMMUTABLE" in str(exc)
        else:
            raise AssertionError("Immutable incident audit row was changed")
        try:
            cx.execute("""INSERT INTO p2_lineage_ephemeral.incident_receipts
              (record_id,event_id,incident_digest,evidence_bundle_digest)
              VALUES (%s,%s,%s,%s)""",(
              original["record_id"],original["event_id"],
              "f"*64,original["evidence_bundle_digest"]))
        except errors.UniqueViolation:
            pass
        else:
            raise AssertionError("Conflicting incident replay bypassed PK constraint")
        assert cx.execute("SELECT count(*) FROM p2_lineage_ephemeral.incident_receipts").fetchone()[0]==1
        assert cx.execute("""SELECT count(*) FROM p2_lineage_ephemeral.incident_receipts
          WHERE NOT paper_only OR trade_permission OR exchange_authority
                OR scientific_pass_permitted""").fetchone()[0]==0
    assert readback(dsn,original["record_id"])==original
    print("P2_EPHEMERAL_SECOND_DB_INCIDENT_OUTBOX_LINKAGE_PASS "+json.dumps({
        "source_quote_position_incident_mock_recipient_linked":True,
        "journal_server":"second localhost PG16 service, not long-term durable",
        "new_connection_after_commit_readback":True,
        "missing_or_mismatched_readback_fails_closed":True,
        "conflicting_duplicate_rejected":True,
        "journal_record_mutation_rejected":True,
        "recipient_confirmation":"signed synthetic fixture ONLY",
        "production_source_authenticated":False,
        "venue_quote_price_signed":False,
        "real_alert_delivered":False,
        "real_long_term_custody_proven":False,
        "live_monitoring_proven":False,
        "scientific_pass_permitted":False,
        "trade_permission":False,
        "production_mutation":False,
        "new_spend_usd":0,
    },sort_keys=True))

if __name__=="__main__":main()
