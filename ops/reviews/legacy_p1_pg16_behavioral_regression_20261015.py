#!/usr/bin/env python3
"""P1 REAL PostgreSQL16 behavioral regression of exact unchanged PR337 SELECTs.

Disposable LOCAL CI DB ONLY. Synthetic records with same-shaped table names
cannot authenticate/repair real production history. No production imports,
credentials, network venues, migrations, writes to Supabase, or orders.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
COVERAGE = ROOT / "ops/reviews/legacy_residual_coverage_readonly_20261012.sql"
BALANCE = ROOT / "ops/reviews/legacy_ledger_balance_readonly_20261012.sql"
DSN = "postgresql://p1review:p1review@127.0.0.1:5441/postgres"
AUTH = "EPHEMERAL_GITHUB_ACTIONS_ONLY"

DDL = """
CREATE TABLE public.alpha_hunter_paper_orders_v02 (
  order_id text PRIMARY KEY,decision_id text NOT NULL UNIQUE,symbol text NOT NULL,
  direction text NOT NULL,submitted_at_utc timestamptz NOT NULL,quantity numeric NOT NULL);
CREATE TABLE public.alpha_hunter_paper_fills_v02 (
  fill_id text PRIMARY KEY,order_id text NOT NULL,quantity numeric NOT NULL);
CREATE TABLE public.alpha_hunter_paper_exit_fills_v04 (
  exit_fill_id text PRIMARY KEY,entry_order_id text NOT NULL,quantity numeric NOT NULL);
CREATE TABLE public.alpha_hunter_paper_protective_orders_v03 (
  protective_order_id text PRIMARY KEY,entry_order_id text NOT NULL,
  protection_type text NOT NULL);
CREATE TABLE public.alpha_hunter_paper_lifecycle_current_v01 (
  decision_id text PRIMARY KEY,state text NOT NULL);
CREATE TABLE public.alpha_hunter_paper_entry_quarantine_v06 (
  order_id text PRIMARY KEY,reason text);
CREATE TABLE public.alpha_hunter_paper_exit_quarantine_v04 (
  entry_order_id text PRIMARY KEY,reason text);
CREATE TABLE public.alpha_hunter_paper_reconciliation_quarantine_v04 (
  order_id text PRIMARY KEY,reason text);
CREATE TABLE public.alpha_hunter_paper_protection_open_v04 (
  entry_order_id text PRIMARY KEY);
CREATE TABLE public.alpha_hunter_paper_reconciliation_inventory_v08 (
  order_id text PRIMARY KEY);
"""
# These IDs are SYNTHETIC and cannot be confused with real ledger primary keys.
NMR = "synthetic-p1-partial-pre-r8"
MANAGED = "synthetic-p1-managed"
QUARANTINE = "synthetic-p1-quarantine"
GAP = "synthetic-p1-stoptp-not-managed"
CLOSED = "synthetic-p1-closed"
UNFILLED = "synthetic-p1-unfilled"
OVERFILL = "synthetic-p1-overfill"
OVEREXIT = "synthetic-p1-overexit"
ORPHAN = "synthetic-p1-orphan-fill"
ORPHAN_EXIT = "synthetic-p1-orphan-exit"

def guard():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "No local/manual production use"
    assert os.environ.get("AH_P1_ISOLATED_APPROVED") == AUTH, "Explicit ephemeral gate required"
    assert os.environ.get("AH_P1_ISOLATED_PG_DSN") == DSN, "Only exact disposable loopback PG16"
    for env in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","DATABASE_URL",
                "AH_SHADOW_PG_DSN","AH_SHADOW_JOURNAL_DSN",
                "BITGET_API_KEY","BITGET_SECRET_KEY","BITGET_API_PASSPHRASE"):
        assert not os.environ.get(env), "Production or exchange credentials forbidden: "+env

def exact_sql(path):
    raw = path.read_text(encoding="utf-8")
    stripped = "\n".join(x.split("--",1)[0] for x in raw.splitlines()).strip()
    import re
    assert re.match(r"(?is)^with\s",stripped)
    assert re.search(r"(?i)\bselect\b",stripped)
    assert not re.search(r"(?i)\b(insert|update|delete|create|alter|drop|truncate|grant|revoke|call|execute|copy|vacuum|do|merge)\b",stripped)
    return stripped.rstrip(";")

def load(cx):
    def order(oid,qty,state="FILLED",date="2026-10-10T10:00:00+00:00"):
        cx.execute("""INSERT INTO public.alpha_hunter_paper_orders_v02
          VALUES (%s,%s,%s,'LONG',%s,%s)""",(oid,"decision-"+oid,"NMRUSDT" if oid==NMR else "QUSDT",date,qty))
        cx.execute("""INSERT INTO public.alpha_hunter_paper_lifecycle_current_v01
           VALUES(%s,%s)""",("decision-"+oid,state))
    def entry(oid,qty):
        cx.execute("INSERT INTO public.alpha_hunter_paper_fills_v02 VALUES (%s,%s,%s)",("fill-"+oid,oid,qty))
    def exit_(oid,qty):
        cx.execute("INSERT INTO public.alpha_hunter_paper_exit_fills_v04 VALUES (%s,%s,%s)",("exit-"+oid,oid,qty))
    def protects(oid,kind):
        cx.execute("INSERT INTO public.alpha_hunter_paper_protective_orders_v03 VALUES (%s,%s,%s)",("protect-"+kind+oid,oid,kind))
    order(NMR,"3.2","PARTIALLY_FILLED","2026-10-02T22:04:12+00:00")
    entry(NMR,"1.5")  # real NMR balances, but only synthetic fixture
    order(MANAGED,"5")
    entry(MANAGED,"5")
    protects(MANAGED,"STOP_LOSS"); protects(MANAGED,"TAKE_PROFIT")
    cx.execute("INSERT INTO public.alpha_hunter_paper_protection_open_v04 VALUES (%s)",(MANAGED,))
    order(QUARANTINE,"10","PARTIALLY_FILLED");entry(QUARANTINE,"4")
    cx.execute("INSERT INTO public.alpha_hunter_paper_entry_quarantine_v06 VALUES(%s,'historical')",(QUARANTINE,))
    order(GAP,"10","PARTIALLY_FILLED");entry(GAP,"8");exit_(GAP,"3")
    protects(GAP,"STOP_LOSS");protects(GAP,"TAKE_PROFIT")
    order(CLOSED,"3");entry(CLOSED,"3");exit_(CLOSED,"3")
    order(UNFILLED,"2","SUBMITTED")
    order(OVERFILL,"1");entry(OVERFILL,"2")
    order(OVEREXIT,"2");entry(OVEREXIT,"1");exit_(OVEREXIT,"2")
    cx.execute("INSERT INTO public.alpha_hunter_paper_fills_v02 VALUES ('synthetic-orphan-fill',%s,1)",(ORPHAN,))
    cx.execute("INSERT INTO public.alpha_hunter_paper_exit_fills_v04 VALUES ('synthetic-orphan-exit',%s,1)",(ORPHAN_EXIT,))

def coverage(cx,query):
    return {r["order_id"]:r for r in cx.execute(query).fetchall()}

def balanced(cx,query):
    return {r["ledger_state"]:(r["order_count"],r["positive_residual_orders"])
            for r in cx.execute(query).fetchall()}

def main():
    guard()
    cov_sql,bal_sql=exact_sql(COVERAGE),exact_sql(BALANCE)
    with psycopg.connect(DSN,row_factory=dict_row) as cx:
        version=int(cx.execute("SHOW server_version_num").fetchone()["server_version_num"])
        assert 160000<=version<170000, "Must run actual PostgreSQL 16"
        cx.execute(DDL)
        load(cx)
        cx.commit()
        # Actual PostgreSQL READ ONLY session; no pseudo SQL interpreter.
        with cx.transaction():
            cx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            rows=coverage(cx,cov_sql)
            balance=balanced(cx,bal_sql)
        assert set(rows)=={NMR,MANAGED,QUARANTINE,GAP,OVERFILL}
        assert rows[NMR]["audit_status"]=="UNPROTECTED_RESIDUAL_REVIEW_REQUIRED"
        assert rows[NMR]["lifecycle_state"]=="PARTIALLY_FILLED"
        assert str(rows[NMR]["filled_quantity"])=="1.5"
        assert str(rows[NMR]["residual_quantity"])=="1.5"
        assert rows[NMR]["stop_records"]==rows[NMR]["target_records"]==0
        assert rows[NMR]["in_managed_protection"] is False
        assert rows[NMR]["in_reconciliation_inventory"] is False
        assert rows[MANAGED]["audit_status"]=="MANAGED_PROTECTION_RECORDS_PRESENT"
        assert rows[QUARANTINE]["audit_status"]=="QUARANTINED_RESIDUAL_PRESERVE_EVIDENCE"
        assert rows[GAP]["audit_status"]=="PROTECTION_COVERAGE_GAP_REVIEW_REQUIRED"
        assert str(rows[GAP]["residual_quantity"])=="5"
        assert CLOSED not in rows and UNFILLED not in rows and OVEREXIT not in rows
        assert balance["FILLED_GREATER_THAN_ORDERED"]==(1,1)
        assert balance["EXIT_GREATER_THAN_FILLED"]==(1,0)
        assert balance["ORPHAN_FILL_OR_EXIT"]==(2,1)
        assert balance["POSITIVE_RESIDUAL_REQUIRES_COVERAGE_AUDIT"]==(4,4)
        assert balance["BALANCED_OR_UNFILLED"]==(2,0)
        # A falsely terminal lifecycle cannot erase actual positive residual.
        with cx.transaction():
            cx.execute("""UPDATE public.alpha_hunter_paper_lifecycle_current_v01
                          SET state='CANCELLED' WHERE decision_id=%s""",("decision-"+NMR,))
        assert coverage(cx,cov_sql)[NMR]["residual_quantity"]==rows[NMR]["residual_quantity"]
        # One stop alone is NOT both protective legs.
        with cx.transaction():
            cx.execute("""INSERT INTO public.alpha_hunter_paper_protective_orders_v03
                          VALUES ('synthetic-stop-nmr',%s,'STOP_LOSS')""",(NMR,))
        assert coverage(cx,cov_sql)[NMR]["audit_status"]=="UNPROTECTED_RESIDUAL_REVIEW_REQUIRED"
        # Even both recorded STOP and TP without managed inventory membership:
        # never certify manager coverage.
        with cx.transaction():
            cx.execute("""INSERT INTO public.alpha_hunter_paper_protective_orders_v03
                          VALUES ('synthetic-target-nmr',%s,'TAKE_PROFIT')""",(NMR,))
        assert coverage(cx,cov_sql)[NMR]["audit_status"]=="PROTECTION_COVERAGE_GAP_REVIEW_REQUIRED"
        # Rewinding mutable synthetic fixture does NOT change real source evidence.
        with cx.transaction():
            cx.execute("""DELETE FROM public.alpha_hunter_paper_protective_orders_v03
                          WHERE entry_order_id=%s""",(NMR,))
            cx.execute("""INSERT INTO public.alpha_hunter_paper_exit_fills_v04
                          VALUES ('synthetic-nmr-fully-exited',%s,1.5)""",(NMR,))
        assert NMR not in coverage(cx,cov_sql)
        assert balanced(cx,bal_sql)["BALANCED_OR_UNFILLED"]==(3,0)
        print("P1_REAL_PG16_PARTIAL_FILL_REGRESSION_PASS "+json.dumps({
            "source_sql_executed_unchanged":True,"postgres_major":16,
            "synthetic_initial_positive_residuals":5,
            "unprotected_nmr_partial_1_5_visible":True,
            "unfilled_remainder_1_7_not_counted_as_residual":True,
            "quarantine_not_closed":True,
            "dual_stop_target_without_managed_membership_blocked":True,
            "single_leg_no_coverage":True,
            "terminal_lifecycle_does_not_hide_positive_residual":True,
            "overfill_overexit_orphans_fail_visible":True,
            "synthetic_exit_only_drops_fixture_not_live_nmr":True,
            "live_nmr_remediated":False,"production_db_touched":False,
            "paper_or_live_orders_authorised":False,"deploy":False},sort_keys=True))

if __name__=="__main__":
    main()
