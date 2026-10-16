#!/usr/bin/env python3
"""DRAFT ONLY. Actual PG16 57014 + all-cohort partial-fill monitor proof.

Runs ONLY inside GitHub Actions against a disposable localhost PG16 database.
Synthetic accounting includes 10 managed, 21 quarantined, one NMR-like partial
unprotected (1.5 of ordered 3.2). Source truth is ENTRY minus EXIT for EVERY
order, not the protection-only view. The atomic successor cycle must never
seal unless its child evidence, ALL expected positive residual IDs, verified
protected position observations and absence of quarantined/unprotected
residuals are independently read back in the SAME transaction.

Real Postgres statement_timeout SQLSTATE 57014 is injected into child INSERT
trigger. No real Supabase, Bitget, SMTP, R10, or main deployment access.
"""
from __future__ import annotations
import json
import os
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from successor_pg16_tcp_benchmark_v01 import guard_dsn

DB = "ah_p0_partial_atomic_only_ephemeral"
FROZEN_35M_SECONDS = 2100
SCHEMA = """
CREATE SCHEMA p0_shadow;
CREATE TABLE p0_shadow.orders(
 order_id text PRIMARY KEY, original_quantity numeric NOT NULL CHECK(original_quantity>0),
 paper_only bool NOT NULL DEFAULT true CHECK(paper_only),
 trade_permission bool NOT NULL DEFAULT false CHECK(NOT trade_permission)
);
CREATE TABLE p0_shadow.entry_fills(
 fill_id text PRIMARY KEY, order_id text NOT NULL REFERENCES p0_shadow.orders,
 qty numeric NOT NULL CHECK(qty>0)
);
CREATE TABLE p0_shadow.exit_fills(
 fill_id text PRIMARY KEY, entry_order_id text NOT NULL REFERENCES p0_shadow.orders,
 qty numeric NOT NULL CHECK(qty>0)
);
CREATE TABLE p0_shadow.protective_orders(
 entry_order_id text REFERENCES p0_shadow.orders,
 leg text CHECK(leg IN ('STOP','TP')),
 PRIMARY KEY(entry_order_id,leg)
);
CREATE TABLE p0_shadow.quarantine(
 order_id text PRIMARY KEY REFERENCES p0_shadow.orders,
 incident text NOT NULL
);
CREATE VIEW p0_shadow.all_positive_residuals AS
 WITH entries AS (
    SELECT order_id,sum(qty) qty FROM p0_shadow.entry_fills GROUP BY order_id
 ), exits AS (
    SELECT entry_order_id AS order_id,sum(qty) qty
    FROM p0_shadow.exit_fills GROUP BY entry_order_id
 )
 SELECT o.order_id,o.original_quantity,coalesce(en.qty,0) entry_quantity,
        coalesce(ex.qty,0) exit_quantity,
        coalesce(en.qty,0)-coalesce(ex.qty,0) residual_quantity,
        (SELECT count(*) FROM p0_shadow.protective_orders p
          WHERE p.entry_order_id=o.order_id) protective_leg_count,
        (q.order_id IS NOT NULL) quarantined,
        CASE WHEN q.order_id IS NOT NULL THEN 'QUARANTINED'
          WHEN EXISTS(SELECT 1 FROM p0_shadow.protective_orders p
            WHERE p.entry_order_id=o.order_id AND leg='STOP')
           AND EXISTS(SELECT 1 FROM p0_shadow.protective_orders p
            WHERE p.entry_order_id=o.order_id AND leg='TP') THEN 'MANAGED'
          ELSE 'UNPROTECTED' END disposition
 FROM p0_shadow.orders o
 LEFT JOIN entries en ON en.order_id=o.order_id
 LEFT JOIN exits ex ON ex.order_id=o.order_id
 WHERE coalesce(en.qty,0)-coalesce(ex.qty,0)>0;

CREATE TABLE p0_shadow.source_symbols(
 symbol text PRIMARY KEY CHECK(symbol LIKE '%USDT')
);
CREATE TABLE p0_shadow.parents(
 run_id text PRIMARY KEY CHECK(run_id LIKE 'synthetic-p0-%'),
 expected_symbols integer NOT NULL CHECK(expected_symbols>0)
);
CREATE TABLE p0_shadow.children(
 run_id text REFERENCES p0_shadow.parents,
 symbol text NOT NULL,
 PRIMARY KEY(run_id,symbol)
);
CREATE TABLE p0_shadow.monitor_attempts(
 run_id text REFERENCES p0_shadow.parents,
 order_id text REFERENCES p0_shadow.orders,
 evidence_type text NOT NULL CHECK(evidence_type='SYNTHETIC_LOCAL_RECEIPT_ONLY'),
 PRIMARY KEY(run_id,order_id)
);
CREATE TABLE p0_shadow.cycle_seals(
 run_id text PRIMARY KEY REFERENCES p0_shadow.parents,
 source_residual_count integer NOT NULL CHECK(source_residual_count>0),
 observed_monitor_count integer NOT NULL CHECK(observed_monitor_count=source_residual_count),
 observed_child_count integer NOT NULL CHECK(observed_child_count>0),
 no_live_source_authentication boolean NOT NULL DEFAULT true CHECK(no_live_source_authentication),
 scientific_pass_permitted boolean NOT NULL DEFAULT false CHECK(NOT scientific_pass_permitted),
 trade_permission boolean NOT NULL DEFAULT false CHECK(NOT trade_permission)
);
CREATE FUNCTION p0_shadow.immutable_seal() RETURNS trigger LANGUAGE plpgsql
 SET search_path='' AS $body$ BEGIN
 RAISE EXCEPTION 'P0_RECEIPT_IMMUTABLE';
END $body$;
CREATE TRIGGER immutable_seal BEFORE UPDATE OR DELETE
 ON p0_shadow.cycle_seals FOR EACH ROW EXECUTE FUNCTION p0_shadow.immutable_seal();

CREATE FUNCTION p0_shadow.accept_cycle(
 p_run text,p_expected_symbols integer,p_children jsonb,p_attempt_ids jsonb
) RETURNS text LANGUAGE plpgsql SET search_path='' AS $body$
DECLARE n_residual integer; n_managed integer; n_child integer; n_attempt integer;
BEGIN
 IF current_database()<>'ah_p0_partial_atomic_only_ephemeral'
    OR p_run IS NULL OR p_run NOT LIKE 'synthetic-p0-%'
 THEN RAISE EXCEPTION 'EPHEMERAL_ONLY'; END IF;
 IF p_expected_symbols<1 OR p_expected_symbols>128
   OR pg_catalog.jsonb_typeof(p_children)<>'array'
   OR pg_catalog.jsonb_typeof(p_attempt_ids)<>'array'
 THEN RAISE EXCEPTION 'INVALID_REQUEST'; END IF;
 -- "parent present" does not mean a completed cycle.
 INSERT INTO p0_shadow.parents(run_id,expected_symbols)
 VALUES(p_run,p_expected_symbols);
 INSERT INTO p0_shadow.children(run_id,symbol)
 SELECT p_run,elem#>>'{}'
 FROM pg_catalog.jsonb_array_elements(p_children) elem;
 INSERT INTO p0_shadow.monitor_attempts(run_id,order_id,evidence_type)
 SELECT p_run,elem#>>'{}','SYNTHETIC_LOCAL_RECEIPT_ONLY'
 FROM pg_catalog.jsonb_array_elements(p_attempt_ids) elem;

 SELECT count(*) INTO n_child FROM p0_shadow.children WHERE run_id=p_run;
 SELECT count(*) INTO n_attempt FROM p0_shadow.monitor_attempts WHERE run_id=p_run;
 SELECT count(*) INTO n_residual FROM p0_shadow.all_positive_residuals;
 SELECT count(*) INTO n_managed FROM p0_shadow.all_positive_residuals
    WHERE disposition='MANAGED' AND protective_leg_count=2;
 IF n_residual=0 OR n_child<>p_expected_symbols
    OR (SELECT count(*) FROM p0_shadow.source_symbols)<>p_expected_symbols
    OR EXISTS(
      SELECT 1 FROM p0_shadow.source_symbols source
      LEFT JOIN p0_shadow.children saved
        ON saved.symbol=source.symbol AND saved.run_id=p_run
      WHERE saved.symbol IS NULL
    ) OR EXISTS(
      SELECT 1 FROM p0_shadow.children saved
      LEFT JOIN p0_shadow.source_symbols source ON source.symbol=saved.symbol
      WHERE saved.run_id=p_run AND source.symbol IS NULL
    )
 THEN RAISE EXCEPTION 'P0_CHILD_OR_SOURCE_INCOMPLETE'; END IF;
 -- Even if SOME position IDs are monitored, compare full source ledger.
 -- NMR-like partially filled order absent from the managed-only view must
 -- cause a hard reject. Quarantine is INCIDENT, never a valid monitor receipt.
 IF n_managed<>n_residual OR n_attempt<>n_residual
 OR EXISTS(
   SELECT 1 FROM p0_shadow.all_positive_residuals r
   LEFT JOIN p0_shadow.monitor_attempts a ON a.order_id=r.order_id
     AND a.run_id=p_run
   WHERE r.disposition<>'MANAGED' OR a.order_id IS NULL
 ) OR EXISTS(
   SELECT 1 FROM p0_shadow.monitor_attempts a
   LEFT JOIN p0_shadow.all_positive_residuals r ON r.order_id=a.order_id
   WHERE a.run_id=p_run AND r.order_id IS NULL
 )
 THEN RAISE EXCEPTION 'P0_PARTIAL_OR_MONITOR_MANIFEST_INCOMPLETE'; END IF;
 -- All stages remain uncommitted until a source-set/readback verified seal.
 INSERT INTO p0_shadow.cycle_seals(
  run_id,source_residual_count,observed_monitor_count,observed_child_count
 ) VALUES(p_run,n_residual,n_attempt,n_child);
 RETURN 'LOCAL_ONLY_ATOMIC_STRUCTURE_NOT_REAL_MONITORING';
END $body$;
"""

def require_ci():
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise AssertionError("Only ephemeral GitHub Actions may create synthetic PG16")
    dsn=guard_dsn()
    if "127.0.0.1" not in dsn:
        raise AssertionError("Explicit localhost PostgreSQL only")
    return dsn

def count(conn,run):
    return tuple(conn.execute(
      f"SELECT count(*) FROM p0_shadow.{tab} WHERE run_id=%s",(run,)).fetchone()[0]
      for tab in ("parents","children","monitor_attempts","cycle_seals"))

def invoke(conn,run,children,ids):
    return conn.execute(
      "SELECT p0_shadow.accept_cycle(%s,%s,%s::jsonb,%s::jsonb)",
      (run,3,json.dumps(children),json.dumps(ids))).fetchone()[0]

def expected_failure(dsn,run,children,ids,expected_marker):
    with psycopg.connect(make_conninfo(dsn,dbname=DB),autocommit=True) as db:
        try:
            with db.transaction():
                invoke(db,run,children,ids)
        except psycopg.errors.RaiseException as exc:
            if expected_marker not in str(exc):
                raise
        else:
            raise AssertionError("Expected fail closed for "+run)
        if count(db,run)!=(0,0,0,0):
            raise AssertionError("Partial atomic commit leaked for "+run)

def verify():
    dsn=require_ci()
    with psycopg.connect(dsn,autocommit=True) as root:
        assert str(root.execute("SHOW server_version_num").fetchone()[0]).startswith("16")
        root.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB)))
    dbinfo=make_conninfo(dsn,dbname=DB)
    with psycopg.connect(dbinfo,autocommit=True) as db:
        db.execute(SCHEMA)
        db.execute("INSERT INTO p0_shadow.source_symbols VALUES ('BTCUSDT'),('ETHUSDT'),('NMRUSDT')")
        db.execute("ALTER DATABASE "+DB+" SET statement_timeout = '12s'")
        for i in range(10):
            oid=f"synthetic-managed-{i}"
            db.execute("INSERT INTO p0_shadow.orders VALUES(%s,1,true,false)",(oid,))
            db.execute("INSERT INTO p0_shadow.entry_fills VALUES(%s,%s,1)",(oid+"-f",oid))
            db.execute("INSERT INTO p0_shadow.protective_orders VALUES(%s,'STOP'),(%s,'TP')",(oid,oid))
        for i in range(21):
            oid=f"synthetic-quarantine-{i}"
            db.execute("INSERT INTO p0_shadow.orders VALUES(%s,1,true,false)",(oid,))
            db.execute("INSERT INTO p0_shadow.entry_fills VALUES(%s,%s,1)",(oid+"-f",oid))
            db.execute("INSERT INTO p0_shadow.quarantine VALUES(%s,'SYNTHETIC_UNRESOLVED_INCIDENT')",(oid,))
        db.execute("INSERT INTO p0_shadow.orders VALUES('synthetic-NMRUSDT-LONG',3.2,true,false)")
        db.execute("INSERT INTO p0_shadow.entry_fills VALUES('synthetic-NMR-partial-f','synthetic-NMRUSDT-LONG',1.5)")
        db.execute("INSERT INTO p0_shadow.orders VALUES('synthetic-closed-NMR',9.8,true,false)")
        db.execute("INSERT INTO p0_shadow.entry_fills VALUES('synthetic-closed-NMR-f','synthetic-closed-NMR',9.8)")
        db.execute("INSERT INTO p0_shadow.exit_fills VALUES('synthetic-closed-NMR-x','synthetic-closed-NMR',9.8)")
        summary=db.execute("""SELECT disposition,count(*) FROM p0_shadow.all_positive_residuals
           GROUP BY disposition ORDER BY disposition""").fetchall()
        assert dict(summary)=={"MANAGED":10,"QUARANTINED":21,"UNPROTECTED":1},summary
        partial=db.execute("""SELECT original_quantity,entry_quantity,exit_quantity,
           residual_quantity,protective_leg_count,quarantined
           FROM p0_shadow.all_positive_residuals
           WHERE order_id='synthetic-NMRUSDT-LONG'""").fetchone()
        assert tuple(map(str,partial[:4]))==("3.2","1.5","0","1.5"),partial
        assert partial[4:]==(0,False),partial
        assert db.execute("SELECT count(*) FROM p0_shadow.all_positive_residuals").fetchone()[0]==32
    managed_ids=[f"synthetic-managed-{i}" for i in range(10)]
    children=["BTCUSDT","ETHUSDT","NMRUSDT"]
    expected_failure(dsn,"synthetic-p0-nmr-excluded",children,managed_ids,
                     "P0_PARTIAL_OR_MONITOR_MANIFEST_INCOMPLETE")
    # No false improvement if caller injects a fabricated NMR attempt:
    # no STOP/TP protection and 21 quarantines remain unqualified.
    expected_failure(dsn,"synthetic-p0-faked-nmr-attempt",children,
                     managed_ids+["synthetic-NMRUSDT-LONG"],
                     "P0_PARTIAL_OR_MONITOR_MANIFEST_INCOMPLETE")
    expected_failure(dsn,"synthetic-p0-missing-child",children[:2],managed_ids,
                     "P0_CHILD_OR_SOURCE_INCOMPLETE")
    expected_failure(dsn,"synthetic-p0-wrong-child",
                     ["BTCUSDT","ETHUSDT","FAKEUSDT"],managed_ids,
                     "P0_CHILD_OR_SOURCE_INCOMPLETE")
    # Prove true SQLSTATE 57014 by a 100ms INSERT trigger and 35ms SQL budget
    # on an ephemeral connection. This is NOT an increase of the frozen 12s
    # production statement ceiling.
    with psycopg.connect(dbinfo,autocommit=True) as db:
        db.execute("""CREATE FUNCTION p0_shadow.slow_test_child() RETURNS trigger
         LANGUAGE plpgsql SET search_path='' AS $b$
         BEGIN PERFORM pg_catalog.pg_sleep(0.10); RETURN NEW; END $b$""")
        db.execute("""CREATE TRIGGER only_injected_slow_child
         BEFORE INSERT ON p0_shadow.children FOR EACH ROW
         EXECUTE FUNCTION p0_shadow.slow_test_child()""")
        try:
            with db.transaction():
                db.execute("SET LOCAL statement_timeout = '35ms'")
                invoke(db,"synthetic-p0-actual-57014",children,managed_ids)
        except psycopg.errors.QueryCanceled as exc:
            assert exc.sqlstate=="57014",exc
        else:
            raise AssertionError("Actual PostgreSQL timeout was not raised")
        assert count(db,"synthetic-p0-actual-57014")==(0,0,0,0)
        db.execute("DROP TRIGGER only_injected_slow_child ON p0_shadow.children")
        db.execute("DROP FUNCTION p0_shadow.slow_test_child()")
        # Quarantines and unprotected NMR STILL block after SQL recovers.
        expected_failure(dsn,"synthetic-p0-after-57014",children,managed_ids,
                         "P0_PARTIAL_OR_MONITOR_MANIFEST_INCOMPLETE")
        # Entirely separate LOCAL safe-case fixture: all residuals protected.
        # No historical production data or real NMR status is changed.
        db.execute("TRUNCATE p0_shadow.entry_fills, p0_shadow.exit_fills CASCADE")
        db.execute("TRUNCATE p0_shadow.quarantine,p0_shadow.protective_orders, p0_shadow.orders CASCADE")
        for i in range(2):
            oid=f"synthetic-clean-managed-{i}"
            db.execute("INSERT INTO p0_shadow.orders VALUES(%s,1,true,false)",(oid,))
            db.execute("INSERT INTO p0_shadow.entry_fills VALUES(%s,%s,1)",(oid+"-f",oid))
            db.execute("INSERT INTO p0_shadow.protective_orders VALUES(%s,'STOP'),(%s,'TP')",(oid,oid))
        expected_failure(dsn,"synthetic-p0-clean-missing-position",children,
                         ["synthetic-clean-managed-0"],
                         "P0_PARTIAL_OR_MONITOR_MANIFEST_INCOMPLETE")
        with db.transaction():
            verdict=invoke(db,"synthetic-p0-clean-pass",children,[
                "synthetic-clean-managed-0","synthetic-clean-managed-1"])
            assert verdict=="LOCAL_ONLY_ATOMIC_STRUCTURE_NOT_REAL_MONITORING"
        assert count(db,"synthetic-p0-clean-pass")==(1,3,2,1)
        # A parent-only old record is explicitly NOT a sealed cycle.
        db.execute("INSERT INTO p0_shadow.parents VALUES('synthetic-p0-parent-only',3)")
        assert count(db,"synthetic-p0-parent-only")==(1,0,0,0)
        assert db.execute("""SELECT count(*) FROM p0_shadow.cycle_seals
               WHERE run_id='synthetic-p0-parent-only'""").fetchone()[0]==0
        try:
            db.execute("UPDATE p0_shadow.cycle_seals SET observed_monitor_count=99 WHERE run_id='synthetic-p0-clean-pass'")
        except psycopg.errors.RaiseException:
            pass
        else:
            raise AssertionError("A sealed completion receipt was mutable")
    print("P0_REAL_PG16_PARTIAL_ATOMIC_57014_FAIL_CLOSED_PASS "+json.dumps({
      "source_inventory_synthetic_positive_residuals":32,
      "managed":10,"quarantined":21,"unprotected_partial_nmr":1,
      "nmr_original_order_qty":3.2,"nmr_partial_fill_qty":1.5,
      "nmr_never_hidden_by_managed_view":True,
      "nmr_unprotected_false_attempt_rejected":True,
      "parent_child_monitor_same_transaction_required":True,
      "incomplete_child_rolls_back_parent":True,
      "same_count_wrong_child_identity_rejected":True,
      "missing_clean_position_observation_rolls_back":True,
      "real_postgresql_statement_timeout_sqlstate":"57014",
      "timeout_rolls_back_parent_child_attempt_seal":True,
      "parent_only_not_sealed":True,
      "clean_independent_synthetic_control_case":True,
      "source_all_residuals_continuous_35m_proven":False,
      "real_paper_protection_activated":False,
      "scientific_pass_permitted":False,
      "trade_permission":False,
      "production_deployment":False,"r10_modified":False,"new_spend_usd":0,
      "production_sql_limit_seconds_unchanged":12,
      "production_http_limit_seconds_unchanged":15,
      "frozen_monitor_maximum_seconds":FROZEN_35M_SECONDS},sort_keys=True))

if __name__=="__main__":
    verify()
