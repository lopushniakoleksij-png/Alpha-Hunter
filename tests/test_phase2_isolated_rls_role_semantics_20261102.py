"""Isolated PostgreSQL role/RLS checks for P0 source evidence custody.

Never touches Supabase production. Requires an ephemeral local PG16/17 service
with synthetic roles and synthetic data only. PostgreSQL superuser is used
only for fixture schema setup, not for client role assertions.
"""
import os
import pytest

psycopg = pytest.importorskip("psycopg")


@pytest.fixture(scope="module")
def pg():
    if os.getenv("AH_LOCAL_RLS_ONLY") != "1":
        pytest.skip("explicit isolated PostgreSQL RLS acceptance is not enabled")
    dsn=os.getenv("AH_ISOLATED_RLS_PG_DSN","")
    if "host=127.0.0.1" not in dsn or "dbname=postgres" not in dsn:
        pytest.fail("refusing any connection other than local ephemeral PostgreSQL")
    with psycopg.connect(dsn, autocommit=True) as conn:
        # Explicit isolated names, never production object names or secrets.
        conn.execute("CREATE ROLE ah_test_anon NOLOGIN")
        conn.execute("CREATE ROLE ah_test_authenticated NOLOGIN")
        conn.execute("""
          CREATE TABLE public.ah_test_sensitive_monitor_receipt(
             receipt_id text PRIMARY KEY, source_run_id text NOT NULL,
             entry_order_id text NOT NULL, quoted_bid numeric
          )
        """)
        conn.execute("""
          INSERT INTO public.ah_test_sensitive_monitor_receipt
          VALUES ('receipt-x','run-x','position-x',42)
        """)
        conn.execute("""
          ALTER TABLE public.ah_test_sensitive_monitor_receipt
          ENABLE ROW LEVEL SECURITY
        """)
        conn.execute("""
          GRANT SELECT,INSERT
          ON public.ah_test_sensitive_monitor_receipt
          TO ah_test_anon,ah_test_authenticated
        """)
        conn.execute("""
          CREATE VIEW public.ah_test_sensitive_monitor_receipt_invoker
            WITH (security_invoker=true,security_barrier=true)
          AS SELECT receipt_id, source_run_id, entry_order_id
          FROM public.ah_test_sensitive_monitor_receipt
        """)
        conn.execute("""
          GRANT SELECT
          ON public.ah_test_sensitive_monitor_receipt_invoker
          TO ah_test_anon,ah_test_authenticated
        """)
        try:
            yield conn
        finally:
            conn.execute("RESET ROLE")
            conn.execute("DROP VIEW IF EXISTS public.ah_test_sensitive_monitor_receipt_invoker")
            conn.execute("DROP TABLE IF EXISTS public.ah_test_sensitive_monitor_receipt")
            conn.execute("DROP ROLE IF EXISTS ah_test_authenticated")
            conn.execute("DROP ROLE IF EXISTS ah_test_anon")


@pytest.mark.parametrize("role",["ah_test_anon","ah_test_authenticated"])
def test_public_roles_cannot_read_row_through_underlying_grant(pg, role):
    try:
        pg.execute("SET ROLE "+role)
        # Even with GRANT SELECT metadata, zero RLS policies denies rows.
        assert pg.execute(
            "SELECT receipt_id FROM public.ah_test_sensitive_monitor_receipt"
        ).fetchall() == []
        # Owner-privileged view bypass is explicitly avoided by security_invoker.
        assert pg.execute(
            "SELECT receipt_id FROM public.ah_test_sensitive_monitor_receipt_invoker"
        ).fetchall() == []
    finally:
        pg.execute("RESET ROLE")


@pytest.mark.parametrize("role",["ah_test_anon","ah_test_authenticated"])
def test_public_roles_cannot_insert_receipts_without_rls_policy(pg, role):
    try:
        pg.execute("SET ROLE "+role)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            pg.execute("""
              INSERT INTO public.ah_test_sensitive_monitor_receipt
              VALUES ('forged','fake-run','fake-position',999)
            """)
    finally:
        pg.execute("RESET ROLE")
    assert pg.execute(
        "SELECT count(*) FROM public.ah_test_sensitive_monitor_receipt"
    ).fetchone()[0] == 1


def test_privileged_fixture_access_is_not_public_role_access(pg):
    assert pg.execute(
        "SELECT receipt_id FROM public.ah_test_sensitive_monitor_receipt"
    ).fetchall() == [("receipt-x",)]
