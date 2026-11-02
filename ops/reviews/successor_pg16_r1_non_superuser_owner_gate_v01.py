#!/usr/bin/env python3
"""R1 design blocker reproduction ONLY on ephemeral GitHub Actions PostgreSQL16.

Synthetic NON-superuser CREATEROLE migration principal creates a NOLOGIN
view owner. Verify PostgreSQL's automatic ADMIN membership has SET=FALSE and
cannot change ownership to that role without a separately reviewed privilege
transition. This is NOT the exact V2 forward/rollback SQL integration test.
Never connects to production or acquires real credentials.
"""
from __future__ import annotations
import json
import os
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from successor_pg16_tcp_benchmark_v01 import guard_dsn

DB="ah_r1_owner_gate_ephemeral"
MIGRATOR="ah_r1_ephem_migrator"
OWNER="ah_r1_ephem_projection_owner"

def negative(db,statement):
    try:
        db.execute(statement)
    except psycopg.errors.InsufficientPrivilege:
        return True
    raise AssertionError("NON_SUPERUSER_OWNER_BOUNDARY_UNEXPECTEDLY_ALLOWED: "+statement)

def verify():
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise AssertionError("Only an already provisioned ephemeral CI runner is allowed")
    dsn=guard_dsn() # exactly bench@127.0.0.1:5432/postgres, no live keys
    with psycopg.connect(dsn,autocommit=True) as root:
        version=root.execute("SHOW server_version_num").fetchone()[0]
        if not str(version).startswith("16"):
            raise AssertionError("Only ephemeral PostgreSQL16")
        root.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB)))
        root.execute(sql.SQL(
            "CREATE ROLE {} NOLOGIN CREATEROLE NOINHERIT NOBYPASSRLS NOSUPERUSER "
            "NOCREATEDB NOREPLICATION").format(sql.Identifier(MIGRATOR)))
    with psycopg.connect(make_conninfo(dsn,dbname=DB),autocommit=True) as db:
        # Production-like migrator is not a superuser.
        db.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
            sql.Identifier(DB),sql.Identifier(MIGRATOR)))
        db.execute(sql.SQL("CREATE TABLE public.ah_r1_ephem_public_source (id integer)"))
        db.execute(sql.SQL("GRANT SELECT ON public.ah_r1_ephem_public_source TO {}").format(
            sql.Identifier(MIGRATOR)))
        db.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIGRATOR)))
        got=db.execute("SELECT current_user,(SELECT rolsuper FROM pg_roles WHERE rolname=current_user)").fetchone()
        if got!=(MIGRATOR,False):
            raise AssertionError("Non-superuser migration role not actually active")
        db.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT NOBYPASSRLS "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(OWNER)))
        member=db.execute(
            "SELECT m.admin_option,m.set_option,m.inherit_option "
            "FROM pg_auth_members m "
            "JOIN pg_roles a ON a.oid=m.member JOIN pg_roles b ON b.oid=m.roleid "
            "WHERE a.rolname=%s AND b.rolname=%s",(MIGRATOR,OWNER)).fetchone()
        if member!=(True,False,False):
            raise AssertionError("Expected PG16 automatic ADMIN TRUE SET FALSE INHERIT FALSE: "+str(member))
        set_allowed=db.execute("SELECT pg_has_role(current_user,%s,'SET')",(OWNER,)).fetchone()[0]
        if set_allowed:
            raise AssertionError("Source migration review incorrectly assumed SET ROLE")
        # The original V2 forward needs a schema owned by the NOLOGIN
        # projection role and two ALTER VIEW ... OWNER TO changes.
        denied_schema=negative(db,sql.SQL(
            "CREATE SCHEMA {} AUTHORIZATION {}").format(
                sql.Identifier("ah_r1_ephem_owned_schema"),sql.Identifier(OWNER)))
        db.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
            sql.Identifier("ah_r1_ephem_migrator_schema"),sql.Identifier(MIGRATOR)))
        db.execute("CREATE VIEW ah_r1_ephem_migrator_schema.v AS "
                   "SELECT id FROM public.ah_r1_ephem_public_source")
        denied_transfer=negative(db,sql.SQL(
            "ALTER VIEW ah_r1_ephem_migrator_schema.v OWNER TO {}").format(sql.Identifier(OWNER)))
        remains=db.execute("SELECT pg_get_userbyid(c.relowner) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='ah_r1_ephem_migrator_schema' AND c.relname='v'").fetchone()[0]
        if remains!=MIGRATOR:
            raise AssertionError("Failed owner transfer must not silently change owner")
        db.execute("RESET ROLE")
    print("R1_EPHEMERAL_PG16_NON_SUPERUSER_OWNERSHIP_BLOCKER_CONFIRMED "+json.dumps({
        "non_superuser_role_creation":True,
        "auto_admin_membership":True,
        "auto_set_false":True,
        "auto_inherit_false":True,
        "unauthorized_create_owned_schema_denied":denied_schema,
        "unauthorized_view_owner_transfer_denied":denied_transfer,
        "view_owner_after_rejection":remains,
        "original_v2_sql_executed":False,
        "R1_migration_approved":False,
        "production_database_mutated":False,
        "production_timeout_changed":False,
        "production_trade_authority":False
    },sort_keys=True))

if __name__=="__main__":
    verify()
