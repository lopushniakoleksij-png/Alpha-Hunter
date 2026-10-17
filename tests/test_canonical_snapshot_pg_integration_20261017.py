"""PostgreSQL 16/17 ephemeral acceptance of canonical parent/child publication.

All connections are hard restricted to a localhost GitHub Actions service.
This never reads or writes Alpha Hunter production Supabase.
"""
import json
import os

import pytest
import requests

# Full production CI deliberately does not install the isolated PG client.
# Only the dedicated PostgreSQL 16/17 acceptance job needs this dependency.
psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


@pytest.fixture
def isolated_pg():
    if os.getenv("ALPHA_HUNTER_ISOLATED_POSTGRES_ACCEPTANCE") != "1":
        pytest.skip("isolated PostgreSQL service not requested")
    dsn = os.getenv("AH_ISOLATED_PG_DSN", "")
    if "host=127.0.0.1" not in dsn or "dbname=postgres" not in dsn:
        pytest.fail("Refusing any non-local or unidentified PostgreSQL connection")

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS ah_test_child")
        conn.execute("DROP TABLE IF EXISTS ah_test_parent")
        conn.execute("""
            CREATE TABLE ah_test_parent (
                run_id text PRIMARY KEY,
                symbol_count integer NOT NULL,
                payload jsonb NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE ah_test_child (
                run_id text NOT NULL REFERENCES ah_test_parent(run_id) ON DELETE CASCADE,
                symbol text NOT NULL,
                payload jsonb NOT NULL,
                PRIMARY KEY (run_id, symbol)
            )
        """)
        try:
            yield conn
        finally:
            conn.execute("DROP TABLE IF EXISTS ah_test_child")
            conn.execute("DROP TABLE IF EXISTS ah_test_parent")


def snapshot():
    return {
        "collected_at_utc": "2026-10-17T08:40:00+00:00",
        "version": "v-test",
        "product_type": "usdt-futures",
        "validation_identity": {"run_source": "RENDER_CRON"},
        "symbols": [
            {"symbol": sym, "state": "NEUTRAL", "last_price": px,
             "trade_permission": False, "execution_setup": {}}
            for sym, px in (("BTCUSDT", 80000), ("ETHUSDT", 2400))
        ],
    }


def writer_for_db(monkeypatch, conn, *, simulate_lost_child_ack=False):
    writer = SupabaseStorage(SupabaseConfig(
        url="https://not-a-real-supabase.invalid", key="isolated-test-only",
    ))
    state = {"lost_ack": simulate_lost_child_ack, "child_timeout": False}

    def persist(table, rows, on_conflict):
        if table == writer.settings.snapshot_table:
            for row in rows:
                conn.execute("""
                    INSERT INTO ah_test_parent (run_id,symbol_count,payload)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (run_id) DO UPDATE
                    SET symbol_count=EXCLUDED.symbol_count,payload=EXCLUDED.payload
                """, (row["run_id"], row["symbol_count"], Jsonb(row["payload"])))
        elif table == writer.settings.symbol_table:
            for row in rows:
                if state["child_timeout"]:
                    conn.execute("SET statement_timeout='50ms'")
                try:
                    conn.execute("""
                        INSERT INTO ah_test_child (run_id,symbol,payload)
                        VALUES (%s,%s,%s)
                        ON CONFLICT (run_id,symbol) DO UPDATE SET payload=EXCLUDED.payload
                    """, (row["run_id"], row["symbol"], Jsonb(row["payload"])))
                finally:
                    if state["child_timeout"]:
                        conn.execute("RESET statement_timeout")
            if state["lost_ack"]:
                state["lost_ack"] = False
                raise requests.ReadTimeout("synthetic lost HTTP response after DB commit")
        # Other evidence tables are intentionally out of scope in this isolated
        # FK/publication contract; existing reconciliation regressions cover them.

    def select(table, params):
        run_id = params["run_id"][3:]
        if table == writer.settings.symbol_table:
            return [
                {"symbol": symbol, "payload": payload}
                for symbol, payload in conn.execute(
                    "SELECT symbol,payload FROM ah_test_child WHERE run_id=%s ORDER BY symbol",
                    (run_id,),
                ).fetchall()
            ]
        if table == writer.settings.snapshot_table:
            return [
                {"run_id": rid, "symbol_count": n, "payload": payload}
                for rid, n, payload in conn.execute(
                    "SELECT run_id,symbol_count,payload FROM ah_test_parent WHERE run_id=%s",
                    (run_id,),
                ).fetchall()
            ]
        pytest.fail(f"Unexpected isolated select {table}")

    monkeypatch.setattr(writer, "_upsert", persist)
    monkeypatch.setattr(writer, "_select_json", select)
    monkeypatch.setattr(writer, "_insert_immutable", lambda *a, **kw: None)
    monkeypatch.setattr(writer, "_reconcile_paper_stages", lambda *a, **kw: None)
    return writer, state


def publication(conn, run_id):
    return conn.execute(
        "SELECT payload->>'_canonical_publication_state' FROM ah_test_parent WHERE run_id=%s",
        (run_id,),
    ).fetchone()[0]


def test_real_foreign_key_rejects_child_before_parent(isolated_pg):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        isolated_pg.execute("""
            INSERT INTO ah_test_child VALUES
            ('not-yet-parent','BTCUSDT','{"symbol":"BTCUSDT"}'::jsonb)
        """)


def test_persisted_children_then_verified_parent(isolated_pg, monkeypatch):
    writer, _ = writer_for_db(monkeypatch, isolated_pg)
    run_id = writer.save_snapshot(snapshot())
    assert publication(isolated_pg, run_id) == "VERIFIED"
    assert isolated_pg.execute(
        "SELECT count(*) FROM ah_test_child WHERE run_id=%s", (run_id,),
    ).fetchone()[0] == 2


def test_statement_timeout_leaves_pending_parent_not_false_verified(isolated_pg, monkeypatch):
    isolated_pg.execute("""
        CREATE FUNCTION ah_test_child_delay() RETURNS trigger AS $$
        BEGIN PERFORM pg_sleep(0.25); RETURN NEW; END
        $$ LANGUAGE plpgsql
    """)
    isolated_pg.execute("""
        CREATE TRIGGER ah_test_child_delay_trigger BEFORE INSERT ON ah_test_child
        FOR EACH ROW EXECUTE FUNCTION ah_test_child_delay()
    """)
    writer, state = writer_for_db(monkeypatch, isolated_pg)
    state["child_timeout"] = True
    row = snapshot()
    with pytest.raises(psycopg.errors.QueryCanceled):
        writer.save_snapshot(row)
    run_id = row["run_id"]
    assert publication(isolated_pg, run_id) == "PENDING"
    assert isolated_pg.execute(
        "SELECT count(*) FROM ah_test_child WHERE run_id=%s", (run_id,),
    ).fetchone()[0] == 0


def test_lost_write_ack_requires_recovery_before_publication(isolated_pg, monkeypatch):
    writer, _ = writer_for_db(monkeypatch, isolated_pg, simulate_lost_child_ack=True)
    row = snapshot()
    with pytest.raises(requests.ReadTimeout, match="lost HTTP response"):
        writer.save_snapshot(row)
    run_id = row["run_id"]
    assert publication(isolated_pg, run_id) == "PENDING"
    assert isolated_pg.execute(
        "SELECT count(*) FROM ah_test_child WHERE run_id=%s", (run_id,),
    ).fetchone()[0] == 2
    assert writer.save_snapshot(row) == run_id
    assert publication(isolated_pg, run_id) == "VERIFIED"
    assert isolated_pg.execute(
        "SELECT count(*) FROM ah_test_child WHERE run_id=%s", (run_id,),
    ).fetchone()[0] == 2
