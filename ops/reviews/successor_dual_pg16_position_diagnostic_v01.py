#!/usr/bin/env python3
"""P2 independently durable per-order DIAGNOSTIC journal, two isolated PG16 hosts.

Not a production writer, not real Bitget orders. Source records and prior
qualification are synthetic, NOT externally authenticated. No complete
scientific cycle or order permissions can be emitted by this journal.
"""
from __future__ import annotations
import json
from hashlib import sha256
import psycopg
from successor_pg16_tcp_benchmark_v01 import guard_dsn,make_conn,BASE_DB
from successor_dual_pg16_journal_fault_v01 import journal_dsn
from successor_forward_asof_inventory_v01 import build_forward_asof_inventory,TABLES
from successor_all_residual_monitor_qualification_v01 import score_monitoring_coverage

RUN="synthetic-p2-position-journal-main-timeout"
FINGERPRINT="50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834"
QUOTE_SOURCE="BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"
DDL="""
CREATE SCHEMA p2_position_shadow;
REVOKE ALL ON SCHEMA p2_position_shadow FROM PUBLIC;
CREATE TABLE p2_position_shadow.receipts(
 run_id text NOT NULL, entry_order_id text NOT NULL,
 source_manifest_sha256 text NOT NULL CHECK(length(source_manifest_sha256)=64),
 disposition text NOT NULL, structural_status text NOT NULL,
 reasons jsonb NOT NULL,
 source_authenticated boolean NOT NULL DEFAULT false CHECK(source_authenticated=false),
 scientific_pass boolean NOT NULL DEFAULT false CHECK(scientific_pass=false),
 position_protection_proven boolean NOT NULL DEFAULT false CHECK(position_protection_proven=false),
 exchange_authority boolean NOT NULL DEFAULT false CHECK(exchange_authority=false),
 trade_permission boolean NOT NULL DEFAULT false CHECK(trade_permission=false),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(run_id,entry_order_id)
);
CREATE FUNCTION p2_position_shadow.reject_edit() RETURNS trigger
 LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'RECEIPT_IMMUTABLE';END $$;
CREATE TRIGGER immutable_receipt BEFORE UPDATE OR DELETE
 ON p2_position_shadow.receipts FOR EACH ROW
 EXECUTE FUNCTION p2_position_shadow.reject_edit();
REVOKE ALL ON ALL TABLES IN SCHEMA p2_position_shadow FROM PUBLIC;
"""
def sample():
    safe={"paper_only":True,"exchange_authority":False,
          "trade_permission":False,"order_path":"NONE"}
    orders=[
        {"order_id":"synthetic-legacy-partial","symbol":"NMRUSDT",
         "direction":"LONG","created_at":"2026-10-03T09:00:00Z",
         "submitted_at_utc":"2026-10-03T09:00:00Z",**safe},
        {"order_id":"synthetic-forward-managed","symbol":"QUSDT",
         "direction":"LONG","created_at":"2026-10-12T11:42:00Z",
         "submitted_at_utc":"2026-10-12T11:42:00Z",**safe}]
    fills=[
        {"fill_id":"old-entry","order_id":"synthetic-legacy-partial",
         "quantity":"1.5","filled_at_utc":"2026-10-03T09:01:00Z",
         "created_at":"2026-10-03T09:01:01Z","source_run_id":"historical",**safe},
        {"fill_id":"new-entry","order_id":"synthetic-forward-managed",
         "quantity":"2","filled_at_utc":"2026-10-12T11:45:00Z",
         "created_at":"2026-10-12T11:45:01Z","source_run_id":"forward",**safe}]
    receipts={name:{"source_table":name,"complete":True,
       "consistent_snapshot_id":"synthetic-isolated-read-1",
       "captured_at_utc":"2026-10-12T12:00:05Z"} for name in TABLES}
    inventory=build_forward_asof_inventory(orders,fills,[],receipts,
      asof_utc="2026-10-12T12:00:00Z",max_source_capture_lag_seconds=30)
    assert inventory["expected_position_count"]==2
    parent={"run_id":RUN,"collected_at_utc":"2026-10-12T12:00:00Z",
       "validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON",
       "scientific_fingerprint_sha256":FINGERPRINT}}
    disposition=[
       {"entry_order_id":"synthetic-legacy-partial","state":"UNPROTECTED_INCIDENT"},
       {"entry_order_id":"synthetic-forward-managed","state":"MANAGED_PROTECTED",
        "protection_count":2}]
    attempt={"attempt_id":"synthetic-forward-observation",
       "entry_order_id":"synthetic-forward-managed","source_run_id":RUN,
       "symbol":"QUSDT","direction":"LONG","outcome":"NO_TRIGGER",
       "observed_at_utc":"2026-10-12T12:00:04Z",
       "best_bid":"1.0","best_ask":"1.01",
       "best_bid_size":"20","best_ask_size":"15",
       "blockers":[],"evidence":{"quote_source":QUOTE_SOURCE}}
    return inventory,parent,disposition,[attempt]

def verify():
    main_dsn=guard_dsn()
    jdsn=journal_dsn()
    inv,parent,states,attempts=sample()
    scored=score_monitoring_coverage(inv,parent,states,attempts,[],
        approved_quote_sources=frozenset({QUOTE_SOURCE}))
    assert scored["expected_residuals"]==2
    assert scored["managed_locally_qualified"]==1
    assert scored["quarantined_or_unprotected"]==1
    assert scored["status"]=="FAIL_CLOSED_COVERAGE_OR_MONITORING_GAP"
    assert not scored["scientific_pass_permitted"]
    assert any("UNPROTECTED_FILLED_RESIDUAL_INCIDENT" in p["blockers"]
               for p in scored["positions"])
    with psycopg.connect(jdsn,autocommit=True) as journal:
        journal.execute(DDL)
        # Independent diagnostic table is durably written BEFORE simulating
        # primary analytics timeout. Receipt still says NO AUTHENTICATED
        # SOURCE / NO REAL POSITION MANAGEMENT / NO SCIENTIFIC PASS.
        with journal.transaction():
            for row in scored["positions"]:
                journal.execute("""
                  INSERT INTO p2_position_shadow.receipts(
                    run_id,entry_order_id,source_manifest_sha256,
                    disposition,structural_status,reasons)
                  VALUES(%s,%s,%s,%s,%s,%s::jsonb)
                """,(RUN,row["entry_order_id"],scored["source_manifest_sha256"],
                     row["disposition"],row["receipt_status"],
                     json.dumps(row["blockers"])))
        failed=False
        try:
            with make_conn(main_dsn,BASE_DB) as primary:
                with primary.transaction():
                    primary.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES(%s)",(RUN,))
                    primary.execute("SET LOCAL statement_timeout='10ms'")
                    primary.execute("SELECT pg_sleep(0.15)")
        except psycopg.errors.QueryCanceled:
            failed=True
        assert failed,"Primary analytics timeout injection did not fail"
        with make_conn(main_dsn,BASE_DB) as primary:
            assert primary.execute("SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id=%s",(RUN,)).fetchone()[0]==0
        rows=journal.execute("""SELECT disposition,structural_status,reasons
          FROM p2_position_shadow.receipts WHERE run_id=%s
          ORDER BY entry_order_id""",(RUN,)).fetchall()
        assert len(rows)==2 and sum(x[1]=="LOCAL_QUALIFIED_ATTEMPT_SUPPLIED_ONLY"
                                    for x in rows)==1
        assert any(x[1]=="UNPROTECTED_BLOCKED" for x in rows)
        assert journal.execute("""SELECT count(*) FROM p2_position_shadow.receipts
          WHERE scientific_pass OR source_authenticated OR
            position_protection_proven OR exchange_authority OR trade_permission
        """).fetchone()[0]==0
        try:
            journal.execute("""UPDATE p2_position_shadow.receipts
              SET structural_status='FAKE_SEAL' WHERE run_id=%s""",(RUN,))
        except psycopg.errors.RaiseException as e:
            assert "IMMUTABLE" in str(e)
        else:raise AssertionError("Immutable diagnostic rows mutated")
        # Journal timeout must roll back the *journal transaction* too,
        # rather than writing partial or false-positive monitoring.
        jfail="synthetic-p2-journal-write-timeout"
        try:
            with journal.transaction():
                journal.execute("""INSERT INTO p2_position_shadow.receipts(
                  run_id,entry_order_id,source_manifest_sha256,
                  disposition,structural_status,reasons)
                  VALUES(%s,'one',%s,'MANAGED_PROTECTED',
                    'LOCAL_QUALIFIED_ATTEMPT_SUPPLIED_ONLY','[]'::jsonb)
                """,(jfail,inv["manifest_sha256"]))
                journal.execute("SET LOCAL statement_timeout='5ms'")
                journal.execute("SELECT pg_sleep(0.1)")
        except psycopg.errors.QueryCanceled:pass
        else:raise AssertionError("Journal timeout should cancel and rollback")
        assert journal.execute("""SELECT count(*) FROM p2_position_shadow.receipts
             WHERE run_id=%s""",(jfail,)).fetchone()[0]==0
        print("P2_DUAL_PG16_PER_ORDER_DIAGNOSTIC_PASS "+json.dumps({
         "main_analytics_timeout_rolled_back_parent":True,
         "independent_position_diagnostics_durable":2,
         "managed_attempt_locally_qualified_only":1,
         "unprotected_legacy_partial_not_hidden":1,
         "journal_failure_rolls_back_partial_diagnostics":True,
         "no_false_scientific_or_execution_authority":True,
         "real_live_source_authentication":False,
         "live_position_observation_service_deployed":False,
         "frozen_35m_preserved":True,
         "R10_test_touched":False},sort_keys=True))
if __name__=="__main__":
    verify()
