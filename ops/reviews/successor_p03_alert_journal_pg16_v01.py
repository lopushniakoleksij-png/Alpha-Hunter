#!/usr/bin/env python3
"""P0.3 synthetic prospective 35m failure-alert journal on TWO local PG16 hosts.

No production ledger connection, scheduler, source credential, or notification
transport. Durable while the isolated runner lives; not operational continuity.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from json import dumps
import json

import psycopg

from successor_pg16_tcp_benchmark_v01 import guard_dsn
from successor_dual_pg16_journal_fault_v01 import journal_dsn
from successor_p03_residual_continuity_v01 import evaluate,sha

RUN = "p03-isolated-prospective-35m"
CLOCK = datetime(2026,10,15,7,30,0,tzinfo=timezone.utc)
QUOTE_SOURCE = "BITGET_V2_MIX_MARKET_TICKER_SYMBOL_CAPTURE"
FINGERPRINT = "50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834"
SCHEMA = """
CREATE SCHEMA p03_independent_alerts;
REVOKE ALL ON SCHEMA p03_independent_alerts FROM PUBLIC;
CREATE TABLE p03_independent_alerts.outbox (
 event_id text PRIMARY KEY,
 source_run_id text,
 order_id text,
 severity text NOT NULL CHECK(severity IN ('CRITICAL','HIGH')),
 reasons jsonb NOT NULL,
 payload_sha256 text NOT NULL CHECK(length(payload_sha256)=64),
 delivery_status text NOT NULL CHECK(delivery_status='NOT_DISPATCHED'),
 scientific_pass boolean NOT NULL DEFAULT false CHECK(NOT scientific_pass),
 trade_permission boolean NOT NULL DEFAULT false CHECK(NOT trade_permission),
 exchange_authority boolean NOT NULL DEFAULT false CHECK(NOT exchange_authority),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE FUNCTION p03_independent_alerts.reject_edit() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $block$
BEGIN RAISE EXCEPTION 'P03_ALERT_OUTBOX_IMMUTABLE'; END;
$block$;
CREATE TRIGGER immutable_outbox BEFORE UPDATE OR DELETE
 ON p03_independent_alerts.outbox FOR EACH ROW
 EXECUTE FUNCTION p03_independent_alerts.reject_edit();
REVOKE ALL ON ALL TABLES IN SCHEMA p03_independent_alerts FROM PUBLIC;
"""

def fixture():
    positions=[]
    for i in range(32):
        disp="MANAGED_PROTECTED" if i<10 else ("QUARANTINED_NOT_CLOSED" if i<31 else "UNPROTECTED_UNEXPLAINED")
        positions.append({"entry_order_id":f"synthetic-p03-{i:02d}",
            "symbol":("QUSDT" if i<10 else "NMRUSDT"),
            "direction":"LONG","residual_qty":"1.5",
            "disposition":disp,"two_records":i<10})
    inventory={"status":"SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION",
               "positions":positions,"manifest_sha256":sha(positions)}
    scan={"run_id":RUN,"collected_at_utc":CLOCK.isoformat(),
          "validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON",
                                  "scientific_fingerprint_sha256":FINGERPRINT}}
    cap_sha=sha({"synthetic":"p03-local-not-authenticated"})
    quotes=[{"source_run_id":RUN,"symbol":"QUSDT","source":QUOTE_SOURCE,
             "captured_at_utc":CLOCK.isoformat(),"capture_manifest_sha256":cap_sha,
             "bid_price":"1","ask_price":"1.01","bid_size":"50","ask_size":"40"}]
    attempts=[{"attempt_id":"p03-attempt-"+str(i),
       "entry_order_id":p["entry_order_id"],"source_run_id":RUN,"symbol":"QUSDT",
       "direction":"LONG","outcome":"NO_TRIGGER","blockers":[],
       "observed_at_utc":CLOCK.isoformat(),
       "best_bid":"1","best_ask":"1.01","best_bid_size":"50","best_ask_size":"40",
       "evidence":{"quote_source":QUOTE_SOURCE,"capture_manifest_sha256":cap_sha}}
       for i,p in enumerate(positions[:10])]
    prior=[{"entry_order_id":p["entry_order_id"],
            "source_run_id":"synthetic-earlier-receipt",
            "captured_at_utc":(CLOCK-timedelta(minutes=34,seconds=59)).isoformat(),
            "seal_verified":True}
           for p in positions[:10]]
    return inventory,scan,attempts,quotes,prior

def persist(journal,alert):
    event_id=alert["event_id"]
    payload=sha(alert)
    row=journal.execute("""SELECT payload_sha256 FROM p03_independent_alerts.outbox
                         WHERE event_id=%s""",(event_id,)).fetchone()
    if row is not None:
        if row[0]!=payload:
            raise AssertionError("CONFLICTING_DIAGNOSTIC_REPLAY")
        return False
    journal.execute("""INSERT INTO p03_independent_alerts.outbox (
      event_id,source_run_id,order_id,severity,reasons,payload_sha256,delivery_status)
      VALUES (%s,%s,%s,%s,%s::jsonb,%s,'NOT_DISPATCHED')""",
      (event_id,alert["run_id"],alert["entry_order_id"],alert["severity"],
       dumps(alert["reasons"]),payload))
    return True

def main():
    primary_dsn=guard_dsn()
    independent_dsn=journal_dsn()
    inv,scan,attempts,quotes,prior=fixture()
    policy={"approved_sources":frozenset({QUOTE_SOURCE})}
    clean=evaluate(inv,scan,attempts,quotes,prior,**policy)
    assert clean["residual_count"]==32 and clean["locally_observable"]==10
    assert len(clean["alerts"])==22
    assert not clean["scientific_pass_permitted"]
    breach=json.loads(json.dumps(prior))
    for s in breach:
        s["captured_at_utc"]=(CLOCK-timedelta(minutes=35,seconds=1)).isoformat()
    failed=evaluate(inv,scan,attempts,quotes,breach,**policy)
    broken=[x for x in failed["positions"] if "FROZEN_35M_CONTINUITY_BREACH" in x["blockers"]]
    assert len(broken)==10 and failed["locally_observable"]==0
    assert len(failed["alerts"])==32
    absent=evaluate(inv,scan,[],quotes,prior,**policy)
    assert len([x for x in absent["positions"] if "PER_POSITION_ATTEMPT_NOT_EXACTLY_ONE" in x["blockers"]])==10
    bad_source=dict(inv)
    bad_source["status"]="SOURCE_EVIDENCE_UNKNOWN_OR_INVALID"
    unknown=evaluate(bad_source,scan,attempts,quotes,prior,**policy)
    assert "SOURCE_ROWS_NOT_LOCALLY_RECONCILED" in unknown["run_blockers"]
    assert len(unknown["alerts"])>=1
    assert unknown["locally_observable"]==0
    with psycopg.connect(independent_dsn,autocommit=True) as journal:
        assert str(journal.execute("SHOW server_version_num").fetchone()[0]).startswith("16")
        journal.execute(SCHEMA)
        with journal.transaction():
            for a in failed["alerts"]:
                assert persist(journal,a)
        stored=journal.execute("SELECT count(*) FROM p03_independent_alerts.outbox").fetchone()[0]
        assert stored==32
        with journal.transaction():
            for a in failed["alerts"]:
                assert not persist(journal,a)
        assert journal.execute("SELECT count(*) FROM p03_independent_alerts.outbox").fetchone()[0]==32
        # Primary analytics SQL really times out after the independent outbox commits.
        with psycopg.connect(primary_dsn,autocommit=True) as primary:
            try:
                with primary.transaction():
                    primary.execute("SET LOCAL statement_timeout='10ms'")
                    primary.execute("SELECT pg_sleep(0.2)")
            except psycopg.errors.QueryCanceled:
                pass
            else:
                raise AssertionError("PRIMARY_TIMEOUT_NOT_RAISED")
        assert journal.execute("SELECT count(*) FROM p03_independent_alerts.outbox").fetchone()[0]==32
        # Secondary outage leaves no half-committed new outbox records.
        try:
            with journal.transaction():
                one=dict(failed["alerts"][0])
                one["event_id"]=sha({"synthetic":"rollback"})[:32]
                persist(journal,one)
                journal.execute("SET LOCAL statement_timeout='10ms'")
                journal.execute("SELECT pg_sleep(0.2)")
        except psycopg.errors.QueryCanceled:
            pass
        else:
            raise AssertionError("JOURNAL_TIMEOUT_NOT_RAISED")
        assert journal.execute("SELECT count(*) FROM p03_independent_alerts.outbox").fetchone()[0]==32
        try:
            journal.execute("""UPDATE p03_independent_alerts.outbox
              SET delivery_status='NOT_DISPATCHED' WHERE event_id=%s""",
              (failed["alerts"][0]["event_id"],))
        except psycopg.errors.RaiseException:
            pass
        else:
            raise AssertionError("OUTBOX_MUTATION_WAS_PERMITTED")
        assert journal.execute("""SELECT count(*) FROM p03_independent_alerts.outbox
               WHERE delivery_status<>'NOT_DISPATCHED' OR scientific_pass
                  OR exchange_authority OR trade_permission""").fetchone()[0]==0
        print("P03_ALL_RESIDUAL_35M_INDEPENDENT_ALERT_JOURNAL_PASS "+json.dumps({
         "isolated_pg16_primary":"127.0.0.1:5432","isolated_pg16_journal":"127.0.0.1:5433",
         "synthetic_residual_orders":32,"managed":10,"quarantined":21,"unprotected":1,
         "boundary_34m59s_structurally_valid":True,"boundary_35m01s_rejected":True,
         "managed_continuity_breaches_detected":10,"unresolved_residual_incidents":22,
         "durable_independent_diagnostic_events":32,
         "duplicate_alerts_idempotent":True,
         "primary_sql_timeout_secondary_receipts_survived":True,
         "journal_timeout_no_partial_receipts":True,
         "delivery_confirmed":False,"live_inventory_independently_authenticated":False,
         "continuous_real_35m_proven":False,"R10_mutated":False,
         "production_deployed":False,"trade_authority":False},sort_keys=True))
if __name__=="__main__":
    main()
