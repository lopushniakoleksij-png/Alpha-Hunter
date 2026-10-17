"""True HTTP/PostgREST canonical publication integration, local ephemeral services only.

Real PostgreSQL foreign keys, real HTTP upserts with PostgREST and synthetic
SQLSTATE 57014 statement-cancel errors. Never connects to production Supabase.
"""
import os
import time

import pytest
import requests

psycopg = pytest.importorskip("psycopg")

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError

BASE = "http://127.0.0.1:3000"


class LocalPostgrestSession(requests.Session):
    """Rewrite Supabase gateway prefix for the direct isolated PostgREST endpoint."""

    def request(self, method, url, *args, **kwargs):
        assert url.startswith(BASE + "/rest/v1/")
        return super().request(
            method, url.replace(BASE + "/rest/v1/", BASE + "/", 1),
            *args, **kwargs,
        )


class LocalPostgrestWriter(SupabaseStorage):
    @property
    def headers(self):
        # Direct PostgREST anonymous role in this isolated test needs no JWT.
        return {
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }


def scanner_payload(n=57):
    return {
        "version": "test-v0",
        "product_type": "usdt-futures",
        "collected_at_utc": "2026-10-17T09:40:00Z",
        "validation_identity": {"run_source": "RENDER_CRON"},
        "symbols": [{
            "symbol": f"TEST{i:03d}USDT",
            "last_price": 100.0 + i,
            "state": "NEUTRAL",
            "trade_permission": False,
            "execution_setup": {},
        } for i in range(n)],
    }


@pytest.fixture
def real_http_db(monkeypatch):
    if os.getenv("AH_LOCAL_POSTGREST_ONLY") != "1":
        pytest.skip("PostgREST acceptance is not enabled")
    dsn = os.getenv("AH_LOCAL_PG_DSN", "")
    if "host=127.0.0.1" not in dsn or "dbname=postgres" not in dsn:
        pytest.fail("Non-local PostgreSQL connection forbidden")
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS public.alpha_hunter_symbol_snapshots")
        connection.execute("DROP TABLE IF EXISTS public.alpha_hunter_snapshots")
        connection.execute("DROP FUNCTION IF EXISTS public.ah_test_forced_cancel()")
        connection.execute("""
            CREATE TABLE public.alpha_hunter_snapshots (
                run_id text PRIMARY KEY,
                collected_at_utc timestamptz,
                version text,
                product_type text,
                symbol_count integer,
                error_count integer,
                payload jsonb NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE public.alpha_hunter_symbol_snapshots (
                run_id text NOT NULL REFERENCES public.alpha_hunter_snapshots(run_id),
                symbol text NOT NULL,
                collected_at_utc timestamptz,
                state text,
                previous_state text,
                state_changed boolean,
                trade_permission boolean,
                direction text,
                reward_risk numeric,
                last_price numeric,
                open_interest numeric,
                funding_rate numeric,
                data_integrity_score numeric,
                error text,
                payload jsonb NOT NULL,
                PRIMARY KEY (run_id, symbol)
            )
        """)
        connection.execute("NOTIFY pgrst, 'reload schema'")
        # A newly started PostgREST container may respond while its schema
        # cache is still reloading. Require BOTH tables to be stable across
        # successive checks before attempting the first real HTTP write.
        stable = 0
        for _ in range(80):
            try:
                statuses = [
                    requests.get(
                        BASE + "/" + table,
                        params={"select": "run_id", "limit": "1"},
                        timeout=2,
                    ).status_code
                    for table in (
                        "alpha_hunter_snapshots",
                        "alpha_hunter_symbol_snapshots",
                    )
                ]
            except requests.RequestException:
                statuses = []
            if statuses == [200, 200]:
                stable += 1
                if stable >= 4:
                    break
            else:
                stable = 0
            time.sleep(0.3)
        else:
            pytest.fail("Local PostgREST schema cache did not stabilize")
        storage = LocalPostgrestWriter(
            SupabaseConfig(url=BASE, key="ISOLATED_ONLY",
                           retry_backoff_seconds=0, max_retries=2),
            session=LocalPostgrestSession(),
        )
        # Test only parent and child HTTP path. Existing regressions independently
        # cover signals, immutable paper rows and entry/exit reconciliation.
        actual_upsert = storage._upsert

        def limited_upsert(table, rows, key):
            if table in (storage.settings.snapshot_table, storage.settings.symbol_table):
                return actual_upsert(table, rows, key)

        monkeypatch.setattr(storage, "_upsert", limited_upsert)
        monkeypatch.setattr(storage, "_insert_immutable", lambda *a, **kw: None)
        monkeypatch.setattr(storage, "_reconcile_paper_stages", lambda *a, **kw: None)
        try:
            yield storage, connection
        finally:
            connection.execute("DROP TABLE IF EXISTS public.alpha_hunter_symbol_snapshots")
            connection.execute("DROP TABLE IF EXISTS public.alpha_hunter_snapshots")
            connection.execute("DROP FUNCTION IF EXISTS public.ah_test_forced_cancel()")
            connection.execute("NOTIFY pgrst, 'reload schema'")


def read_state(conn, run_id):
    return conn.execute(
        "select payload->>'_canonical_publication_state' from public.alpha_hunter_snapshots where run_id=%s",
        (run_id,),
    ).fetchone()[0]


def read_child_count(conn, run_id):
    return conn.execute(
        "select count(*) from public.alpha_hunter_symbol_snapshots where run_id=%s",
        (run_id,),
    ).fetchone()[0]


def test_real_http_57_rows_publish_only_after_complete_readback(real_http_db):
    storage, conn = real_http_db
    value = scanner_payload()
    run_id = storage.save_snapshot(value)
    assert read_child_count(conn, run_id) == 57
    assert read_state(conn, run_id) == "VERIFIED"
    # A repeated deterministic HTTP upsert cannot produce duplicate children.
    assert storage.save_snapshot(value) == run_id
    assert read_child_count(conn, run_id) == 57
    assert read_state(conn, run_id) == "VERIFIED"


def test_real_http_third_chunk_57014_then_idempotent_recovery(real_http_db):
    storage, conn = real_http_db
    conn.execute("""
        CREATE FUNCTION public.ah_test_forced_cancel()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.symbol='TEST032USDT' THEN
            RAISE EXCEPTION 'synthetic statement timeout (isolated test)' USING ERRCODE='57014';
          END IF;
          RETURN NEW;
        END $$
    """)
    conn.execute("""
        CREATE TRIGGER ah_test_forced_cancel_trigger
        BEFORE INSERT ON public.alpha_hunter_symbol_snapshots
        FOR EACH ROW EXECUTE FUNCTION public.ah_test_forced_cancel()
    """)
    value = scanner_payload()
    with pytest.raises(SupabaseStorageError, match="upsert failed for alpha_hunter_symbol_snapshots"):
        storage.save_snapshot(value)
    run_id = value["run_id"]
    assert read_state(conn, run_id) == "PENDING"
    assert read_child_count(conn, run_id) == 32

    conn.execute("DROP TRIGGER ah_test_forced_cancel_trigger ON public.alpha_hunter_symbol_snapshots")
    assert storage.save_snapshot(value) == run_id
    assert read_state(conn, run_id) == "VERIFIED"
    assert read_child_count(conn, run_id) == 57
