#!/usr/bin/env python3
"""Only a disposable GitHub Actions PG16: test temporary SET ROLE lifecycle.

Synthetic DDL, never original V2 or proposed V3 production migration.
Creates its own DB and isolated roles; no private connection/credentials.
A non-superuser CREATEROLE migrator must not be mistaken for superuser.
"""
import json
import os
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from successor_pg16_tcp_benchmark_v01 import guard_dsn

DB="ah_r1_setrole_lifecycle_ephemeral"
MIG="ah_r1_life_migrator"
OWNER="ah_r1_life_projection_owner"
READER="ah_r1_life_readonly"
SCHEMA="ah_r1_life_ro"

def members(cx):
    return cx.execute("""SELECT a.rolname,m.admin_option,m.set_option,m.inherit_option
    FROM pg_auth_members m
    JOIN pg_roles a ON a.oid=m.member
    JOIN pg_roles b ON b.oid=m.roleid
    WHERE b.rolname=%s ORDER BY a.rolname""",(OWNER,)).fetchall()

def verify():
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise AssertionError("CI localhost disposable only")
    dsn=guard_dsn()
    with psycopg.connect(dsn,autocommit=True) as root:
        if not str(root.execute("SHOW server_version_num").fetchone()[0]).startswith("16"):
            raise AssertionError("PG16 isolated only")
        root.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB)))
        for role,extra in ((MIG,"CREATEROLE"),(READER,"NOCREATEROLE")):
            root.execute(sql.SQL(
                "CREATE ROLE {} NOLOGIN NOINHERIT NOBYPASSRLS NOSUPERUSER "
                "NOCREATEDB NOREPLICATION {}").format(sql.Identifier(role),sql.SQL(extra)))
    own=make_conninfo(dsn,dbname=DB)
    with psycopg.connect(own,autocommit=True) as cx:
        cx.execute("CREATE TABLE public.synthetic_snapshots (id text PRIMARY KEY,payload jsonb NOT NULL)")
        cx.execute("""INSERT INTO public.synthetic_snapshots VALUES
            ('partial','{"validation_identity":{"run_source":"RENDER_CRON","secret":"hidden"}}'),
            ('no_identity','{"other":"none"}')""")
        cx.execute("ALTER TABLE public.synthetic_snapshots ENABLE ROW LEVEL SECURITY")
        # Do not grant prospective owner base privileges through PUBLIC.
        cx.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
            sql.Identifier(DB),sql.Identifier(MIG)))
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIG)))
        cx.execute(sql.SQL(
            "CREATE ROLE {} NOLOGIN NOINHERIT NOBYPASSRLS NOSUPERUSER "
            "NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(OWNER)))
        auto=members(cx)
        assert auto==[(MIG,True,False,False)],auto
        # Escalate TEMPORARILY, with explicit SET and no INHERIT.
        cx.execute(sql.SQL("GRANT {} TO {} WITH SET TRUE, INHERIT FALSE").format(
            sql.Identifier(OWNER),sql.Identifier(MIG)))
        assert cx.execute("SELECT pg_has_role(current_user,%s,'SET')",(OWNER,)).fetchone()[0]
        elevated=members(cx)
        # PG16 can record multiple role grants with different grantors:
        # auto ADMIN SET FALSE and a separate explicit SET TRUE edge.
        assert len(elevated)>=2 and any(x[1] and not x[2] for x in elevated) \
            and any(x[2] and not x[3] for x in elevated),elevated
        cx.execute(sql.SQL("RESET ROLE"))
        # Superuser owned base source grants use administrative operator.
        cx.execute(sql.SQL("GRANT SELECT (id,payload) ON public.synthetic_snapshots TO {}").format(
            sql.Identifier(OWNER)))
        cx.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(OWNER)))
        cx.execute(sql.SQL(
            "CREATE POLICY synthetic_projection_read ON public.synthetic_snapshots "
            "FOR SELECT TO {} USING (true)").format(sql.Identifier(OWNER)))
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIG)))
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER)))
        assert cx.execute("SELECT current_user").fetchone()[0]==OWNER
        # No CREATE-on-DATABASE grant to the NOLOGIN owner: migrator has
        # CREATE DATABASE permission and verified temporary SET permission.
        cx.execute("RESET ROLE")
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIG)))
        cx.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
            sql.Identifier(SCHEMA),sql.Identifier(OWNER)))
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER)))
        cx.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(SCHEMA)))
        cx.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(SCHEMA),sql.Identifier(READER)))
        cx.execute(sql.SQL("""CREATE VIEW {}.parent_v WITH
            (security_barrier=true,security_invoker=false) AS
            SELECT id,payload #>> '{{validation_identity,run_source}}' AS run_source
            FROM public.synthetic_snapshots""").format(sql.Identifier(SCHEMA)))
        cx.execute(sql.SQL("REVOKE ALL ON {}.parent_v FROM PUBLIC").format(sql.Identifier(SCHEMA)))
        cx.execute(sql.SQL("GRANT SELECT ON {}.parent_v TO {}").format(
            sql.Identifier(SCHEMA),sql.Identifier(READER)))
        owns=cx.execute("""SELECT pg_get_userbyid(c.relowner)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relname='parent_v'""",(SCHEMA,)).fetchone()[0]
        assert owns==OWNER,owns
        cx.execute("RESET ROLE")
        assert cx.execute("SELECT current_user").fetchone()[0]=="bench"
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIG)))
        cx.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(OWNER),sql.Identifier(MIG)))
        # Revoking the temporary SET edge retains automatic ADMIN-only
        # membership with SET FALSE, INHERIT FALSE.
        assert members(cx)==[(MIG,True,False,False)],members(cx)
        assert cx.execute("SELECT pg_has_role(current_user,%s,'SET')",(OWNER,)).fetchone()[0] is False
        cx.execute("RESET ROLE")
        # Simulate reader (NOLOGIN) in synthetic *privilege context* only.
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(READER)))
        got=cx.execute(sql.SQL("SELECT id,run_source FROM {}.parent_v ORDER BY id").format(
            sql.Identifier(SCHEMA))).fetchall()
        assert got==[("no_identity",None),("partial","RENDER_CRON")],got
        for stmt in (
            "SELECT payload FROM public.synthetic_snapshots",
            "SELECT * FROM public.synthetic_snapshots",
            "UPDATE public.synthetic_snapshots SET payload='{}'",
            ):
            try: cx.execute(stmt)
            except psycopg.errors.InsufficientPrivilege:pass
            else:raise AssertionError("R1_READER_PERMISSION_BYPASS: "+stmt)
        cx.execute("RESET ROLE")

        # Can a non-superuser migrator regain membership to perform *later* rollback?
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIG)))
        can_regrant=False
        try:
            cx.execute(sql.SQL("GRANT {} TO {} WITH SET TRUE, INHERIT FALSE").format(
                sql.Identifier(OWNER),sql.Identifier(MIG)))
            can_regrant=True
        except psycopg.errors.InsufficientPrivilege:
            pass
        # If regrant works, rollback must remove privilege when done. If
        # not, operator must arrange a separately authorized DBA grant.
        cx.execute("RESET ROLE")
        if not can_regrant:
            # Separate external DBA provision as *synthetic* test administrator.
            cx.execute(sql.SQL("GRANT {} TO {} WITH SET TRUE, INHERIT FALSE").format(
                sql.Identifier(OWNER),sql.Identifier(MIG)))
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIG)))
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER)))
        cx.execute(sql.SQL("REVOKE SELECT ON {}.parent_v FROM {}").format(
            sql.Identifier(SCHEMA),sql.Identifier(READER)))
        cx.execute(sql.SQL("DROP VIEW {}.parent_v RESTRICT").format(sql.Identifier(SCHEMA)))
        cx.execute(sql.SQL("REVOKE USAGE ON SCHEMA {} FROM {}").format(
            sql.Identifier(SCHEMA),sql.Identifier(READER)))
        cx.execute(sql.SQL("DROP SCHEMA {} RESTRICT").format(sql.Identifier(SCHEMA)))
        cx.execute("RESET ROLE")
        cx.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(OWNER),sql.Identifier(MIG)))
        cx.execute("RESET ROLE")
        assert members(cx)==[(MIG,True,False,False)],members(cx)
        assert cx.execute("SELECT to_regnamespace(%s)",(SCHEMA,)).fetchone()[0] is None
        before=cx.execute("SELECT count(*) FROM public.synthetic_snapshots").fetchone()[0]
        assert before==2
        cx.execute(sql.SQL("DROP POLICY synthetic_projection_read ON public.synthetic_snapshots"))
        cx.execute(sql.SQL("REVOKE SELECT (id,payload) ON public.synthetic_snapshots FROM {}").format(sql.Identifier(OWNER)))
        cx.execute(sql.SQL("REVOKE USAGE ON SCHEMA public FROM {}").format(sql.Identifier(OWNER)))
        # The original automatic ADMIN grant permits role teardown
        # by the non-superuser CREATEROLE migrator.
        cx.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIG)))
        cx.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(OWNER)))
        cx.execute("RESET ROLE")
        assert members(cx)==[]
        assert cx.execute("SELECT count(*) FROM public.synthetic_snapshots").fetchone()[0]==2
    print("R1_ISOLATED_PG16_TEMPORARY_SETROLE_FORWARD_ROLLBACK_PASS "+json.dumps({
      "non_superuser_migration":True,
      "role_set_privilege_temporary_only":True,
      "projection_view_owned_by_no_login_non_bypass_role":True,
      "reader_raw_payload_rejected":True,
      "missing_identity_kept_null":True,
      "source_rows_unchanged":2,
      "automatic_admin_membership_during_restricted_operation":"ADMIN_TRUE_SET_FALSE_INHERIT_FALSE",
      "view_owner_dropped_by_non_superuser_migrator":True,
      "unprivileged_migrator_can_regrant_after_revocation":can_regrant,
      "exact_V2_or_V3_production_SQL_executed":False,
      "postgres_server":"ephemeral GitHub Action PG16 only",
      "production_mutation":False,"external_DBA_signoff":False,
      "trade_authority":False},sort_keys=True))
if __name__=="__main__":verify()
