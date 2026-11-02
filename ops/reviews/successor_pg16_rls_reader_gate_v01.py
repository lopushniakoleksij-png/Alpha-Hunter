#!/usr/bin/env python3
"""P2 isolated PostgreSQL 16 role/RLS access proof. NEVER production SQL.

Runs ONLY inside ephemeral GitHub Actions PG16 on 127.0.0.1 with no Supabase,
Bitget, Render or outbound-email credentials. Recreates a synthetic read-only
source role and checks granted-column SELECT, RLS coverage and rejection of
writes/privilege escalation. It is NOT a live source-reader qualification.
"""
from __future__ import annotations

import json
import os
import secrets

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from successor_pg16_tcp_benchmark_v01 import guard_dsn

DB = "ah_p2_rls_only_ephemeral"
ROLE = "ah_p2_ephemeral_source_reader"
TABLES = ("p2_source_orders", "p2_source_entry_fills", "p2_source_exit_fills")
COLUMNS = {
    "p2_source_orders": "order_id,symbol,paper_only,exchange_authority,trade_permission,order_path",
    "p2_source_entry_fills": "fill_id,order_id,quantity,source_run_id",
    "p2_source_exit_fills": "exit_fill_id,entry_order_id,quantity,source_run_id",
}
SCHEMA = """
CREATE TABLE public.p2_source_orders(
 order_id text PRIMARY KEY, symbol text NOT NULL,
 paper_only boolean NOT NULL, exchange_authority boolean NOT NULL,
 trade_permission boolean NOT NULL, order_path text NOT NULL,
 restricted_notes text NOT NULL
);
CREATE TABLE public.p2_source_entry_fills(
 fill_id text PRIMARY KEY, order_id text NOT NULL,
 quantity numeric NOT NULL, source_run_id text NOT NULL
);
CREATE TABLE public.p2_source_exit_fills(
 exit_fill_id text PRIMARY KEY, entry_order_id text NOT NULL,
 quantity numeric NOT NULL, source_run_id text NOT NULL
);
CREATE TABLE public.p2_other_project_private(
 secret text NOT NULL
);
INSERT INTO public.p2_source_orders VALUES
 ('legacy-partial','NMRUSDT',true,false,false,'NONE','UNAPPROVED_INTERNAL'),
 ('new-paper','QUSDT',true,false,false,'NONE','UNAPPROVED_INTERNAL');
INSERT INTO public.p2_source_entry_fills VALUES
 ('f1','legacy-partial',1.5,'synthetic-legacy'),
 ('f2','new-paper',2.0,'synthetic-current');
INSERT INTO public.p2_source_exit_fills VALUES
 ('x1','new-paper',1.0,'synthetic-current');
INSERT INTO public.p2_other_project_private VALUES ('must-never-be-readable');
ALTER TABLE public.p2_source_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.p2_source_entry_fills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.p2_source_exit_fills ENABLE ROW LEVEL SECURITY;
"""

def setup():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Refuse non-CI environment, even if local credentials look acceptable")
    dsn=guard_dsn()
    pw=secrets.token_urlsafe(24)
    with psycopg.connect(dsn,autocommit=True) as root:
        assert str(root.execute("SHOW server_version_num").fetchone()[0]).startswith("16")
        root.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(
             sql.Identifier(ROLE),sql.Literal(pw)))
        root.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB)))
    own=make_conninfo(dsn,dbname=DB)
    with psycopg.connect(own,autocommit=True) as admin:
        admin.execute(SCHEMA)
        admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DB),sql.Identifier(ROLE)))
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)))
        for tab in TABLES:
            admin.execute(sql.SQL("GRANT SELECT ({}) ON {} TO {}").format(
                sql.SQL(COLUMNS[tab]),sql.Identifier("public",tab),sql.Identifier(ROLE)))
    limited=make_conninfo(dsn,dbname=DB,user=ROLE,password=pw)
    return own,limited

def source_check(reader):
    # Reject unverified RLS grants and empty physical source paths, not merely
    # a SELECT returning zero rows. No RLS-filtered "zero exposure" success.
    with reader.transaction():
        reader.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        policy_rows=reader.execute(
            """SELECT tablename,count(*) FROM pg_policies
             WHERE schemaname='public' AND tablename=ANY(%s)
             GROUP BY tablename""",(list(TABLES),)).fetchall()
        if len(policy_rows)!=len(TABLES) or any(n<1 for _,n in policy_rows):
            return "ACCESS_INCOMPLETE_POLICY_MISSING"
        orders=reader.execute(
            """SELECT order_id,symbol,paper_only,exchange_authority,trade_permission,order_path
               FROM public.p2_source_orders ORDER BY order_id""").fetchall()
        entries=reader.execute(
            "SELECT order_id,sum(quantity) FROM public.p2_source_entry_fills GROUP BY order_id ORDER BY order_id").fetchall()
        exits=reader.execute(
            "SELECT entry_order_id,sum(quantity) FROM public.p2_source_exit_fills GROUP BY entry_order_id").fetchall()
        snap=reader.execute("SELECT pg_current_snapshot()::text").fetchone()[0]
        if len(orders)!=2 or len(entries)!=2 or len(exits)!=1 or not snap:
            return "ACCESS_INCOMPLETE_SOURCE_ROWS"
        if any(row[2:]!=(True,False,False,"NONE") for row in orders):
            return "SOURCE_FLAGS_INVALID"
        if {r[0]:r[1] for r in entries}["legacy-partial"]!=1.5:
            return "LEGACY_PARTIAL_NOT_VISIBLE"
        if {r[0]:r[1] for r in exits}["new-paper"]!=1:
            return "EXIT_NOT_VISIBLE"
    return "LOCAL_ROLE_SOURCE_PROOF_ONLY"

def must_deny(reader,statement):
    try:
        reader.execute(statement)
    except psycopg.errors.InsufficientPrivilege:
        return True
    raise AssertionError("Synthetic reader unexpectedly allowed: "+statement)

def verify():
    own,limited=setup()
    with psycopg.connect(limited,autocommit=True) as reader:
        role=reader.execute(
            "SELECT rolcanlogin,rolsuper,rolbypassrls,rolinherit,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user").fetchone()
        assert role==(True,False,False,False,False,False)
        # Granted SELECT but no reader-specific RLS policy is EMPTY, not proof
        # that the real full paper ledger contains no residual positions.
        raw=reader.execute("SELECT order_id FROM public.p2_source_orders").fetchall()
        assert raw==[], "RLS absent-policy default deny failed"
        assert source_check(reader)=="ACCESS_INCOMPLETE_POLICY_MISSING"
    with psycopg.connect(own,autocommit=True) as admin:
        # Reader-specific ALL-ROWS *SELECT only* policies. An RLS filter based
        # on paper_only could hide anomalous source rows and is forbidden.
        for tab in TABLES:
            admin.execute(sql.SQL(
                "CREATE POLICY {} ON {} FOR SELECT TO {} USING (true)").format(
                  sql.Identifier(tab+"_p2_read"),sql.Identifier("public",tab),sql.Identifier(ROLE)))
    with psycopg.connect(limited,autocommit=True) as reader:
        assert source_check(reader)=="LOCAL_ROLE_SOURCE_PROOF_ONLY"
        # Column-scoped GRANT does not imply SELECT * or secret-column read.
        must_deny(reader,"SELECT restricted_notes FROM public.p2_source_orders")
        must_deny(reader,"SELECT * FROM public.p2_source_orders")
        must_deny(reader,"SELECT * FROM public.p2_other_project_private")
        must_deny(reader,"INSERT INTO public.p2_source_orders (order_id,symbol,paper_only,exchange_authority,trade_permission,order_path,restricted_notes) VALUES ('injected','NMRUSDT',true,false,false,'NONE','bad')")
        must_deny(reader,"UPDATE public.p2_source_entry_fills SET quantity=100")
        must_deny(reader,"DELETE FROM public.p2_source_exit_fills")
        must_deny(reader,"CREATE TABLE public.p2_malicious_write(x int)")
        must_deny(reader,"CREATE ROLE p2_escalated_reader BYPASSRLS")
        must_deny(reader,"SET ROLE bench")
        assert reader.execute(
          "SELECT has_table_privilege(current_user,'public.p2_source_orders','INSERT')").fetchone()[0] is False
        assert reader.execute(
          "SELECT has_table_privilege(current_user,'public.p2_other_project_private','SELECT')").fetchone()[0] is False
    with psycopg.connect(own,autocommit=True) as admin:
        assert admin.execute("SELECT count(*) FROM public.p2_source_orders").fetchone()[0]==2
        assert admin.execute("SELECT count(*) FROM public.p2_other_project_private").fetchone()[0]==1
    print("P2_REAL_PG16_RLS_READER_ONLY_GATE_PASS "+json.dumps({
       "postgres_16_real_tcp":True,
       "all_relations_ephemeral_only":True,
       "source_tables_scoped":3,
       "rls_missing_policy_not_confused_with_zero_exposure":True,
       "select_policy_role_specific_all_source_rows":True,
       "older_partial_fill_visible":True,
       "secret_column_and_other_project_denied":True,
       "insert_update_delete_ddl_role_escalation_denied":True,
       "repeatable_read_read_only_transaction_verified":True,
       "live_supabase_role_or_policy_activated":False,
       "live_72h_observer_authorized":False,
       "production_main_or_r10_changed":False,
       "real_alert_delivered":False,
       "spend_authorized":False
    },sort_keys=True))

if __name__=="__main__":
    verify()
