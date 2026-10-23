#!/usr/bin/env python3
"""Isolated PostgreSQL 16/17 *full source-scope* RLS negative regression.

Reconstructs 12 named paper-ledger physical relations plus the security-invoker
protection view from approved-column excerpts of live pg_catalog. All data is
synthetic. NEVER connects to Supabase or provisions a live role, sender,
worker, journal or R10 scanner. This is NOT 72h monitoring evidence.
"""
from __future__ import annotations

import json
import os
import secrets

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from successor_pg16_tcp_benchmark_v01 import guard_dsn

DB="ah_p2_full_scope_only_ephemeral"
ROLE="ah_p2_full_scope_ephemeral_reader"

# Exact names of all currently observed source base relations, not a narrower
# managed-view-only allowlist. Each is a LOCAL PG16/17 synthetic subset of columns.
DDL={
 "alpha_hunter_paper_orders_v02": """(
   order_id text PRIMARY KEY, decision_id text, submitted_at_utc timestamptz,
   symbol text, direction text, quantity numeric, paper_only boolean,
   exchange_authority boolean, trade_permission boolean, order_path text,
   restricted_internal text NOT NULL DEFAULT 'DO_NOT_GRANT')""",
 "alpha_hunter_paper_fills_v02": """(
   fill_id text PRIMARY KEY, order_id text, filled_at_utc timestamptz,
   created_at timestamptz, quantity numeric, source_run_id text,
   paper_only boolean)""",
 "alpha_hunter_paper_exit_fills_v04": """(
   exit_fill_id text PRIMARY KEY, entry_order_id text, filled_at_utc timestamptz,
   created_at timestamptz, quantity numeric, source_run_id text)""",
 "alpha_hunter_paper_exit_attempts_v04": """(
   attempt_id text PRIMARY KEY, entry_order_id text, source_run_id text,
   observed_at_utc timestamptz, symbol text, direction text, evidence jsonb)""",
 "alpha_hunter_paper_protective_orders_v03": """(
   protective_order_id text PRIMARY KEY, entry_order_id text,
   protection_type text, trigger_price numeric, created_at_utc timestamptz)""",
 "alpha_hunter_paper_events_v01": """(
   event_id text PRIMARY KEY, decision_id text, sequence integer,
   state text, occurred_at_utc timestamptz)""",
 "alpha_hunter_paper_exit_activation_v04": """(
   activation_id text PRIMARY KEY, activated_at_utc timestamptz)""",
 "alpha_hunter_paper_entry_quarantine_v06": """(
   order_id text PRIMARY KEY, quarantined_at_utc timestamptz, reason text)""",
 "alpha_hunter_paper_exit_quarantine_v04": """(
   entry_order_id text PRIMARY KEY, quarantined_at_utc timestamptz, reason text)""",
 "alpha_hunter_paper_reconciliation_quarantine_v04": """(
   order_id text PRIMARY KEY, quarantined_at_utc timestamptz, reason text)""",
 "alpha_hunter_snapshots": """(
   run_id text PRIMARY KEY, collected_at_utc timestamptz,
   symbol_count integer, payload jsonb)""",
 "alpha_hunter_symbol_snapshots": """(
   run_id text, symbol text, collected_at_utc timestamptz, payload jsonb,
   trade_permission boolean, PRIMARY KEY(run_id,symbol))""",
}
# This list is an upper-bound scope of data required for the test's
# synthetic consistency model, NOT a final production migration. Exclude
# restricted_internal to exercise column-wise denials. Restrict JSON at source
# after field-by-field privacy review before any live authorisation.
COLUMNS={
 "alpha_hunter_paper_orders_v02": "order_id,decision_id,submitted_at_utc,symbol,direction,quantity,paper_only,exchange_authority,trade_permission,order_path",
 "alpha_hunter_paper_fills_v02": "fill_id,order_id,filled_at_utc,created_at,quantity,source_run_id,paper_only",
 "alpha_hunter_paper_exit_fills_v04": "exit_fill_id,entry_order_id,filled_at_utc,created_at,quantity,source_run_id",
 "alpha_hunter_paper_exit_attempts_v04": "attempt_id,entry_order_id,source_run_id,observed_at_utc,symbol,direction,evidence",
 "alpha_hunter_paper_protective_orders_v03": "protective_order_id,entry_order_id,protection_type,trigger_price,created_at_utc",
 "alpha_hunter_paper_events_v01": "event_id,decision_id,sequence,state,occurred_at_utc",
 "alpha_hunter_paper_exit_activation_v04": "activation_id,activated_at_utc",
 "alpha_hunter_paper_entry_quarantine_v06": "order_id,quarantined_at_utc,reason",
 "alpha_hunter_paper_exit_quarantine_v04": "entry_order_id,quarantined_at_utc,reason",
 "alpha_hunter_paper_reconciliation_quarantine_v04": "order_id,quarantined_at_utc,reason",
 "alpha_hunter_snapshots": "run_id,collected_at_utc,symbol_count,payload",
 "alpha_hunter_symbol_snapshots": "run_id,symbol,collected_at_utc,payload,trade_permission",
}
assert set(DDL)==set(COLUMNS) and len(DDL)==12
VIEW="""CREATE VIEW public.alpha_hunter_paper_protection_open_v04
 WITH (security_invoker=true, security_barrier=true) AS
 SELECT o.order_id AS entry_order_id,o.symbol,
        count(DISTINCT p.protective_order_id)::integer AS protection_count
 FROM public.alpha_hunter_paper_orders_v02 o
 JOIN public.alpha_hunter_paper_fills_v02 f ON f.order_id=o.order_id
 JOIN public.alpha_hunter_paper_protective_orders_v03 p ON p.entry_order_id=o.order_id
 JOIN public.alpha_hunter_paper_events_v01 e ON e.decision_id=o.decision_id
 CROSS JOIN public.alpha_hunter_paper_exit_activation_v04 a
 LEFT JOIN public.alpha_hunter_paper_exit_fills_v04 xf ON xf.entry_order_id=o.order_id
 LEFT JOIN public.alpha_hunter_paper_exit_quarantine_v04 xq ON xq.entry_order_id=o.order_id
 WHERE f.quantity>=o.quantity AND e.state='FILLED'
   AND p.created_at_utc>=a.activated_at_utc
   AND xf.entry_order_id IS NULL AND xq.entry_order_id IS NULL
 GROUP BY o.order_id,o.symbol"""

def setup():
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise RuntimeError("Refuse outside isolated GitHub Actions")
    dsn=guard_dsn()
    # Completely disposable new test database and test-only LOGIN role.
    # Never runs DDL on live Supabase, the R10 cohort or the main service.
    password=secrets.token_urlsafe(24)
    with psycopg.connect(dsn,autocommit=True) as root:
        pg_major=int(root.execute("SHOW server_version_num").fetchone()[0])//10000
        assert pg_major in (16,17), "EPHEMERAL_POSTGRES_16_OR_17_REQUIRED"
        root.execute(sql.SQL(
            "CREATE ROLE {} LOGIN NOINHERIT NOBYPASSRLS NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION PASSWORD {}"
        ).format(sql.Identifier(ROLE),sql.Literal(password)))
        root.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB)))
    admindsn=make_conninfo(dsn,dbname=DB)
    with psycopg.connect(admindsn,autocommit=True) as admin:
        for table,fields in DDL.items():
            admin.execute(sql.SQL("CREATE TABLE public.{} {}").format(
                sql.Identifier(table),sql.SQL(fields)))
            admin.execute(sql.SQL("ALTER TABLE public.{} ENABLE ROW LEVEL SECURITY").format(sql.Identifier(table)))
        admin.execute(VIEW)
        now="2026-10-16T00:00:00Z"
        admin.execute("""INSERT INTO public.alpha_hunter_paper_orders_v02
          (order_id,decision_id,submitted_at_utc,symbol,direction,quantity,
           paper_only,exchange_authority,trade_permission,order_path)
          VALUES ('nmr-legacy','d-old',%s,'NMRUSDT','LONG',3,true,false,false,'NONE'),
                 ('q-current','d-q',%s,'QUSDT','LONG',2,true,false,false,'NONE'),
                 ('anomalous-flag','d-bad',%s,'OTHERUSDT','SHORT',1,false,false,false,'NONE')""",
          (now,now,now))
        admin.execute("""INSERT INTO public.alpha_hunter_paper_fills_v02
          (fill_id,order_id,filled_at_utc,created_at,quantity,source_run_id,paper_only)
          VALUES ('f-nmr','nmr-legacy',%s,%s,1.5,'old-source',true),
                 ('f-q','q-current',%s,%s,2,'new-source',true)""",
          (now,now,now,now))
        admin.execute("""INSERT INTO public.alpha_hunter_paper_exit_fills_v04
           (exit_fill_id,entry_order_id,filled_at_utc,created_at,quantity,source_run_id)
           VALUES ('xf-nmr','nmr-legacy',%s,%s,0,'old-source')""",
           (now,now))
        admin.execute("""INSERT INTO public.alpha_hunter_paper_exit_attempts_v04
            (attempt_id,entry_order_id,source_run_id,observed_at_utc,symbol,direction,evidence)
            VALUES ('at-q','q-current','run1',%s,'QUSDT','LONG',
              '{"quote_source":"LOCAL_SYNTHETIC_NOT_EXCHANGE_VERIFIED"}'::jsonb)""",(now,))
        admin.execute("""INSERT INTO public.alpha_hunter_paper_protective_orders_v03
          (protective_order_id,entry_order_id,protection_type,trigger_price,created_at_utc)
          VALUES ('q-stop','q-current','STOP_LOSS',1,%s),
                 ('q-target','q-current','TAKE_PROFIT',2,%s)""",(now,now))
        admin.execute("""INSERT INTO public.alpha_hunter_paper_events_v01
          (event_id,decision_id,sequence,state,occurred_at_utc)
          VALUES ('evt-q','d-q',1,'FILLED',%s)""",(now,))
        admin.execute("""INSERT INTO public.alpha_hunter_paper_exit_activation_v04
          (activation_id,activated_at_utc) VALUES ('activation-test','2026-10-15T23:00:00Z')""")
        admin.execute("""INSERT INTO public.alpha_hunter_paper_entry_quarantine_v06
          (order_id,quarantined_at_utc,reason) VALUES ('old-elsewhere',%s,'synthetic')""",(now,))
        admin.execute("""INSERT INTO public.alpha_hunter_paper_reconciliation_quarantine_v04
          (order_id,quarantined_at_utc,reason) VALUES ('legacy-other',%s,'synthetic')""",(now,))
        admin.execute("""INSERT INTO public.alpha_hunter_snapshots
          (run_id,collected_at_utc,symbol_count,payload) VALUES
          ('run1',%s,1,'{"validation_identity":{"run_source":"RENDER_CRON"}}'::jsonb)""",(now,))
        admin.execute("""INSERT INTO public.alpha_hunter_symbol_snapshots
          (run_id,symbol,collected_at_utc,payload,trade_permission)
          VALUES ('run1','QUSDT',%s,'{"symbol":"QUSDT"}'::jsonb,false)""",(now,))
        admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DB),sql.Identifier(ROLE)))
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)))
        for table,columns in COLUMNS.items():
            admin.execute(sql.SQL("GRANT SELECT ({}) ON public.{} TO {}").format(
                sql.SQL(columns),sql.Identifier(table),sql.Identifier(ROLE)))
        admin.execute(sql.SQL("GRANT SELECT ON public.alpha_hunter_paper_protection_open_v04 TO {}").format(sql.Identifier(ROLE)))
    return admindsn,make_conninfo(dsn,dbname=DB,user=ROLE,password=password)

def read_source(reader):
    """Fail closed on missing role-specific policies; views never substitute for full source."""
    with reader.transaction():
        reader.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        records=reader.execute("""SELECT tablename,roles,cmd,qual
          FROM pg_policies WHERE schemaname='public'
            AND tablename=ANY(%s)""",(list(DDL),)).fetchall()
        policies={tab for tab,roles,cmd,qual in records
                  if roles==[ROLE] and cmd=="SELECT" and qual=="true"}
        if policies!=set(DDL):
            return "UNKNOWN_POLICY_SCOPE_OR_MISSING_SOURCE",len(policies)
        orders=reader.execute("""SELECT order_id,paper_only FROM public.alpha_hunter_paper_orders_v02
              ORDER BY order_id""").fetchall()
        fills=reader.execute("""SELECT order_id,quantity FROM public.alpha_hunter_paper_fills_v02""").fetchall()
        exits=reader.execute("""SELECT entry_order_id,quantity FROM public.alpha_hunter_paper_exit_fills_v04""").fetchall()
        protection=reader.execute("SELECT entry_order_id,protection_count FROM public.alpha_hunter_paper_protection_open_v04").fetchall()
        scan=reader.execute("SELECT run_id,symbol_count FROM public.alpha_hunter_snapshots").fetchall()
        symbols=reader.execute("SELECT run_id,symbol FROM public.alpha_hunter_symbol_snapshots").fetchall()
        evidence=reader.execute("SELECT entry_order_id,evidence FROM public.alpha_hunter_paper_exit_attempts_v04").fetchall()
        snapshot=reader.execute("SELECT pg_current_snapshot()::text").fetchone()[0]
        if not snapshot or len(orders)!=3 or len(fills)!=2 or len(exits)!=1 or len(scan)!=1 or len(symbols)!=1 or len(evidence)!=1:
            return "UNKNOWN_SOURCE_ROWS_MISSING",len(policies)
        if set(orders)!={("nmr-legacy",True),("q-current",True),("anomalous-flag",False)}:
            return "UNKNOWN_ANOMALOUS_FLAG_HIDDEN",len(policies)
        ff=dict(fills);xx=dict(exits)
        if ff.get("nmr-legacy")-xx.get("nmr-legacy",0)!=1.5 or ff.get("q-current")!=2:
            return "UNKNOWN_PARTIAL_FILL_HIDDEN",len(policies)
        # Managed-only security-invoker view omits NMR, as does real view; this
        # does NOT authorize dropping NMR from full-ledger residual inventory.
        if protection!=[("q-current",2)]:
            return "UNKNOWN_PROTECTION_VIEW_DEPENDENCY",len(policies)
        if scan!=[("run1",1)] or symbols!=[("run1","QUSDT")]:
            return "UNKNOWN_PARENT_CHILD_MISMATCH",len(policies)
    return "LOCAL_SYNTHETIC_SCOPE_CONSISTENT_NOT_AUTHENTICATED",len(policies)

def must_deny(reader,statement):
    try:
        reader.execute(statement)
    except psycopg.errors.InsufficientPrivilege:
        return
    raise AssertionError("Unauthorized synthetic reader action unexpectedly permitted: "+statement)

def verify():
    admindsn,reader_dsn=setup()
    with psycopg.connect(reader_dsn,autocommit=True) as reader:
        assert reader.execute("SELECT count(*) FROM public.alpha_hunter_paper_orders_v02").fetchone()[0]==0
        assert read_source(reader)==("UNKNOWN_POLICY_SCOPE_OR_MISSING_SOURCE",0)
    with psycopg.connect(admindsn,autocommit=True) as admin:
        for tab in DDL:
            if tab=="alpha_hunter_paper_events_v01":
                continue
            admin.execute(sql.SQL("CREATE POLICY {} ON public.{} FOR SELECT TO {} USING (true)").format(
                sql.Identifier("scope_"+tab),sql.Identifier(tab),sql.Identifier(ROLE)))
    with psycopg.connect(reader_dsn,autocommit=True) as reader:
        assert read_source(reader)==("UNKNOWN_POLICY_SCOPE_OR_MISSING_SOURCE",11)
        # SECURITY INVOKER cannot see the FILLED event when its base-table
        # policy is missing. No empty managed view can certify zero exposure.
        assert reader.execute("SELECT count(*) FROM public.alpha_hunter_paper_protection_open_v04").fetchone()[0]==0
    with psycopg.connect(admindsn,autocommit=True) as admin:
        admin.execute(sql.SQL("""CREATE POLICY p2_events_scope ON public.alpha_hunter_paper_events_v01
                           FOR SELECT TO {} USING (true)""").format(sql.Identifier(ROLE)))
    with psycopg.connect(reader_dsn,autocommit=True) as reader:
        assert read_source(reader)==("LOCAL_SYNTHETIC_SCOPE_CONSISTENT_NOT_AUTHENTICATED",12)
        assert reader.execute("SELECT rolbypassrls,rolinherit,rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone()==(False,False,False)
        for statement in (
            "SELECT restricted_internal FROM public.alpha_hunter_paper_orders_v02",
            "SELECT * FROM public.alpha_hunter_paper_orders_v02",
            "INSERT INTO public.alpha_hunter_paper_exit_fills_v04(exit_fill_id) VALUES('forged')",
            "UPDATE public.alpha_hunter_paper_fills_v02 SET quantity=100",
            "DELETE FROM public.alpha_hunter_paper_fills_v02",
            "CREATE TABLE public.p2_reader_unapproved(x integer)",
            "CREATE ROLE p2_reader_elevated BYPASSRLS",
            "SET ROLE bench",
        ):
            must_deny(reader,statement)
    with psycopg.connect(admindsn,autocommit=True) as admin:
        # A later missing policy on a previously approved table causes UNKNOWN,
        # not a retroactive PASS. All ephemeral changes are local to runner.
        admin.execute("DROP POLICY scope_alpha_hunter_symbol_snapshots ON public.alpha_hunter_symbol_snapshots")
    with psycopg.connect(reader_dsn,autocommit=True) as reader:
        assert read_source(reader)==("UNKNOWN_POLICY_SCOPE_OR_MISSING_SOURCE",11)
    print("P2_ISOLATED_FULL_12_TABLE_RLS_SOURCE_SCOPE_PASS "+json.dumps({
       "synthetic_12_base_tables":12,
       "security_invoker_protection_view_7_dependencies_tested":True,
       "rls_default_deny_not_zero_exposure":True,
       "missing_event_policy_and_later_dropped_child_policy_fail_closed":True,
       "legacy_partial_fill_outside_managed_view_visible":True,
       "anomalous_paper_flag_visible_not_filtered":True,
       "read_only_repeatable_read_same_snapshot":True,
       "column_exclusion_write_ddl_and_role_escalation_denied":True,
       "live_rls_grants_created":False,
       "live_72h_proven":False,
       "real_email_sent_or_delivered":False,
       "r10_modified":False,
       "trade_permission":False,
       "new_spending":0
    },sort_keys=True))

if __name__=="__main__":
    verify()
