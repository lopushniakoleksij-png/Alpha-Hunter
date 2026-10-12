#!/usr/bin/env python3
"""Two physically distinct ephemeral PostgreSQL-16 services, zero prod credentials.

Test: real main ANALYTICS write times out before its commit while an entirely
separate independently addressable journal remains durable. This is only a
failure-detection prototype; it does NOT monitor/exit a real paper position.
Even an independently committed journal ATTEMPT is not a complete source scan.
"""
import json
import os
from hashlib import sha256

import psycopg
from psycopg.conninfo import conninfo_to_dict

from successor_pg16_tcp_benchmark_v01 import (
    guard_dsn, make_conn, BASE_DB
)

JOURNAL_SCHEMA = """
CREATE SCHEMA shadow_journal;
CREATE TABLE shadow_journal.stage_events (
 event_id text PRIMARY KEY,
 run_id text NOT NULL,
 stage text NOT NULL CHECK(stage IN(
  'POSITION_INVENTORY_CAPTURED',
  'MAIN_PARENT_WRITE_STARTED',
  'MAIN_PERSISTENCE_TIMED_OUT',
  'MAIN_CONNECTION_INTERRUPTED',
  'INDEPENDENT_ATTEMPT_OBSERVED',
  'MAIN_CHILD_PERSISTENCE_VERIFIED')),
 source_manifest_sha256 text,
 parent_commit_evidence boolean NOT NULL DEFAULT false CHECK(parent_commit_evidence=false),
 paper_authority boolean NOT NULL DEFAULT false CHECK(paper_authority=false),
 exchange_authority boolean NOT NULL DEFAULT false CHECK(exchange_authority=false),
 trade_permission boolean NOT NULL DEFAULT false CHECK(trade_permission=false),
 source_proof_class text NOT NULL CHECK(source_proof_class=
    'SECONDARY_STAGE_JOURNAL_NOT_SOURCE_COMPLETENESS_PROOF'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(run_id,stage)
);
CREATE FUNCTION shadow_journal.deny_edit() RETURNS trigger LANGUAGE plpgsql
 SECURITY INVOKER SET search_path='' AS $$
BEGIN
 RAISE EXCEPTION 'IMMUTABLE_JOURNAL';
END $$;
CREATE TRIGGER stage_immutable BEFORE UPDATE OR DELETE ON shadow_journal.stage_events
 FOR EACH ROW EXECUTE FUNCTION shadow_journal.deny_edit();
"""


def journal_dsn():
    if os.environ.get("AH_SHADOW_JOURNAL_APPROVED") != "EPHEMERAL_GITHUB_ACTIONS_ONLY":
        raise RuntimeError("second server not independently authorized as ephemeral")
    value = os.environ.get("AH_SHADOW_JOURNAL_DSN","")
    d = conninfo_to_dict(value)
    if (d.get("host"),d.get("port"),d.get("dbname"),d.get("user")) != (
       "127.0.0.1","5433","postgres","journal"):
        raise RuntimeError("Journal must be isolated local server 127.0.0.1:5433/journal")
    return value


def write_journal(cx, run, stage, digest=None):
    with cx.transaction():
        cx.execute("""INSERT INTO shadow_journal.stage_events(
          event_id,run_id,stage,source_manifest_sha256,source_proof_class)
          VALUES(%s,%s,%s,%s,'SECONDARY_STAGE_JOURNAL_NOT_SOURCE_COMPLETENESS_PROOF')""",
          (sha256((run+stage).encode()).hexdigest()[:32],run,stage,digest))


def events(cx,run):
    return [row[0] for row in cx.execute(
        "SELECT stage FROM shadow_journal.stage_events WHERE run_id=%s ORDER BY created_at,stage",
        (run,))]


def parent_count(dsn,run):
    with make_conn(dsn,BASE_DB) as cx:
        return cx.execute(
            "SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id=%s",(run,)
        ).fetchone()[0]


def check_no_misleading_success(journal, run,main_parent_rows):
    records=set(events(journal,run))
    assert main_parent_rows==0, "Unexpected committed main parent"
    assert "POSITION_INVENTORY_CAPTURED" in records
    assert "INDEPENDENT_ATTEMPT_OBSERVED" in records
    assert "MAIN_CHILD_PERSISTENCE_VERIFIED" not in records
    assert "MAIN_PERSISTENCE_TIMED_OUT" in records or "MAIN_CONNECTION_INTERRUPTED" in records
    assert journal.execute("""SELECT count(*) FROM shadow_journal.stage_events
             WHERE run_id=%s AND (parent_commit_evidence OR paper_authority OR
                                  exchange_authority OR trade_permission)""",
             (run,)).fetchone()[0]==0
    # There is intentionally NO completed/scientific-PASS column or "complete"
    # status in the independent journal: presence of a signal is not execution.
    return "UNKNOWN_MAIN_PERSISTENCE_FAILED_WITH_INDEPENDENT_DIAGNOSTIC_EVIDENCE"


def main():
    main_dsn=guard_dsn()
    separate_dsn=journal_dsn()
    with psycopg.connect(separate_dsn, autocommit=True) as journal:
        journal.execute(JOURNAL_SCHEMA)
        # A previously captured inventory manifest comes from a synthetic,
        # explicitly non-authentic forward AS-OF ledger. It will not provide
        # proof of live source completeness, even if mirrored safely here.
        digest=sha256(json.dumps([
          {"entry_order_id":"synthetic-paper-1","symbol":"QUSDT",
           "residual_qty":"1.5","direction":"LONG"}
        ],sort_keys=True).encode()).hexdigest()
        run="synthetic-main-supabase-timeout"
        write_journal(journal,run,"POSITION_INVENTORY_CAPTURED",digest)
        write_journal(journal,run,"MAIN_PARENT_WRITE_STARTED",digest)
        try:
            with make_conn(main_dsn,BASE_DB) as main_cx:
                with main_cx.transaction():
                    main_cx.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES (%s)",
                                    (run,))
                    main_cx.execute("SET LOCAL statement_timeout='10ms'")
                    main_cx.execute("SELECT pg_sleep(0.15)")
        except psycopg.errors.QueryCanceled:
            write_journal(journal,run,"MAIN_PERSISTENCE_TIMED_OUT",digest)
        else:
            raise AssertionError("Injected main PostgreSQL timeout should abort")
        write_journal(journal,run,"INDEPENDENT_ATTEMPT_OBSERVED",digest)
        assert check_no_misleading_success(journal,run,parent_count(main_dsn,run)).startswith("UNKNOWN")

        run2="synthetic-main-connection-killed"
        write_journal(journal,run2,"POSITION_INVENTORY_CAPTURED",digest)
        write_journal(journal,run2,"MAIN_PARENT_WRITE_STARTED",digest)
        try:
            with make_conn(main_dsn,BASE_DB) as main_cx:
                with main_cx.transaction():
                    main_cx.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES (%s)",
                                    (run2,))
                    main_cx.execute("SELECT pg_terminate_backend(pg_backend_pid())")
        except (psycopg.OperationalError, psycopg.InterfaceError):
            write_journal(journal,run2,"MAIN_CONNECTION_INTERRUPTED",digest)
        else:
            raise AssertionError("Simulated severed main DB connection must abort")
        write_journal(journal,run2,"INDEPENDENT_ATTEMPT_OBSERVED",digest)
        assert check_no_misleading_success(journal,run2,parent_count(main_dsn,run2)).startswith("UNKNOWN")
        assert len(events(journal,run))==4 and len(events(journal,run2))==4
        # Real standalone journal server persists while the separate primary
        # server aborts its own transactions; successful journal writes still
        # cannot assert monitoring completeness without source/quote evidence.
        print("P0_DUAL_PG16_JOURNAL_FAULT_INJECTION_PASS "+
            json.dumps({"isolated_main_service":"127.0.0.1:5432",
                        "isolated_journal_service":"127.0.0.1:5433",
                        "main_timeout_caused_full_transaction_rollback":True,
                        "main_connection_kill_caused_full_transaction_rollback":True,
                        "journal_survived_both_independent_failures":True,
                        "journal_stages_written":8,"false_complete_seals":0,
                        "asof_inventory_genuine_external_authenticity":False,
                        "independent_paper_position_monitoring_operational":False,
                        "R10_touched":False,"live_trading_authority":False},
                       sort_keys=True))


if __name__=="__main__":
    main()
