#!/usr/bin/env python3
"""P0 prospective SOURCE SNAPSHOT contract in isolated actual PostgreSQL 16.

Only accepts explicitly whitelisted localhost ephemeral GitHub Actions DB.
A single READ ONLY REPEATABLE READ transaction captures ALL three physical
source tables; a concurrent separate transaction cannot contaminate that
snapshot. The existing pure all-cohort fill-minus-exit scorer then calculates
the manifest. This is NOT live Supabase, independently authenticated custody,
an R10 scientific PASS, or permission to trade / deploy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json

import psycopg
from psycopg.rows import dict_row

from successor_pg16_tcp_benchmark_v01 import BASE_DB, guard_dsn, make_conn
from successor_forward_asof_inventory_v01 import build_forward_asof_inventory, TABLES

PREFIX = "synthetic-isolated-source-"
BASE_TS = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=8)
SCHEMA = """
CREATE SCHEMA source_fixture;
-- Minimal PHYSICAL source structures, not copies of full production DDL.
CREATE TABLE source_fixture.orders (
 order_id text PRIMARY KEY, symbol text NOT NULL, direction text NOT NULL,
 submitted_at_utc timestamptz NOT NULL, created_at timestamptz NOT NULL,
 paper_only boolean NOT NULL, exchange_authority boolean NOT NULL,
 trade_permission boolean NOT NULL, order_path text NOT NULL
);
CREATE TABLE source_fixture.entry_fills (
 fill_id text PRIMARY KEY, order_id text NOT NULL REFERENCES source_fixture.orders,
 filled_at_utc timestamptz NOT NULL,created_at timestamptz NOT NULL,
 source_run_id text NOT NULL,quantity numeric NOT NULL,
 paper_only boolean NOT NULL,exchange_authority boolean NOT NULL,
 trade_permission boolean NOT NULL,order_path text NOT NULL
);
CREATE TABLE source_fixture.exit_fills (
 exit_fill_id text PRIMARY KEY,entry_order_id text NOT NULL REFERENCES source_fixture.orders,
 symbol text NOT NULL,direction text NOT NULL,
 filled_at_utc timestamptz NOT NULL,created_at timestamptz NOT NULL,
 source_run_id text NOT NULL,quantity numeric NOT NULL,
 paper_only boolean NOT NULL,exchange_authority boolean NOT NULL,
 trade_permission boolean NOT NULL,order_path text NOT NULL
);
"""
SELECTS = (
 """SELECT order_id,symbol,direction,submitted_at_utc,created_at,
  paper_only,exchange_authority,trade_permission,order_path
  FROM source_fixture.orders
  WHERE created_at<=%s AND submitted_at_utc<=%s ORDER BY order_id""",
 """SELECT fill_id,order_id,filled_at_utc,created_at,source_run_id,quantity,
  paper_only,exchange_authority,trade_permission,order_path
  FROM source_fixture.entry_fills
  WHERE filled_at_utc<=%s AND created_at<=%s ORDER BY fill_id""",
 """SELECT exit_fill_id,entry_order_id,symbol,direction,filled_at_utc,created_at,
  source_run_id,quantity,paper_only,exchange_authority,trade_permission,order_path
  FROM source_fixture.exit_fills
  WHERE filled_at_utc<=%s AND created_at<=%s ORDER BY exit_fill_id""",
)
SAFE = (True,False,False,'NONE')

def insert_order(cx, oid, symbol, direction, age_seconds=360):
    created=BASE_TS+timedelta(seconds=age_seconds)
    cx.execute("""INSERT INTO source_fixture.orders
       (order_id,symbol,direction,submitted_at_utc,created_at,
        paper_only,exchange_authority,trade_permission,order_path)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
       (oid,symbol,direction,created,created,*SAFE))

def insert_entry(cx, fill, oid, qty, age_seconds=365):
    created=BASE_TS+timedelta(seconds=age_seconds)
    cx.execute("""INSERT INTO source_fixture.entry_fills
       (fill_id,order_id,filled_at_utc,created_at,source_run_id,quantity,
        paper_only,exchange_authority,trade_permission,order_path)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
       (fill,oid,created,created,'synthetic-source-run',qty,*SAFE))

def insert_exit(cx, fill, oid, symbol, direction, qty, age_seconds=375):
    created=BASE_TS+timedelta(seconds=age_seconds)
    cx.execute("""INSERT INTO source_fixture.exit_fills
       (exit_fill_id,entry_order_id,symbol,direction,filled_at_utc,created_at,
        source_run_id,quantity,paper_only,exchange_authority,trade_permission,order_path)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
       (fill,oid,symbol,direction,created,created,
        'synthetic-source-run',qty,*SAFE))

def seed(dsn):
    with make_conn(dsn,BASE_DB) as cx:
        cx.execute(SCHEMA)
        insert_order(cx,PREFIX+'nmr','NMRUSDT','LONG')
        insert_entry(cx,PREFIX+'nmr-entry',PREFIX+'nmr','1.5')
        insert_order(cx,PREFIX+'q','QUSDT','LONG')
        insert_entry(cx,PREFIX+'q-entry',PREFIX+'q','5.0')
        insert_exit(cx,PREFIX+'q-partial',PREFIX+'q','QUSDT','LONG','1.25')
        insert_order(cx,PREFIX+'eth','ETHUSDT','SHORT')
        insert_entry(cx,PREFIX+'eth-entry',PREFIX+'eth','.4')
        insert_exit(cx,PREFIX+'eth-exit',PREFIX+'eth','ETHUSDT','SHORT','.4')
        cx.commit()

def _serialize_row(row):
    def encode(v):
        if isinstance(v,datetime): return v.isoformat()
        if isinstance(v,dict): return {k:encode(i) for k,i in v.items()}
        if isinstance(v,list): return [encode(i) for i in v]
        return str(v) if not isinstance(v,(str,bool,int,type(None))) else v
    return encode(row)

def capture_one_actual_snapshot(dsn,asof,after_orders=None):
    """Capture immutable source rows from ONE actual PG repeatable-read snapshot.

    The caller cannot pass `complete=True` or `consistent_snapshot_id`; both
    are generated after reading the tables. The PG snapshot string is a local
    concurrency proof, not a cryptographic credential or external attestation.
    """
    with make_conn(dsn,BASE_DB) as cx:
        cx.row_factory=dict_row
        with cx.transaction():
            cx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            snap=cx.execute("SELECT pg_current_snapshot()::text AS token").fetchone()['token']
            values=[]
            for i,statement in enumerate(SELECTS):
                rows=cx.execute(statement,(asof,asof)).fetchall()
                values.append([_serialize_row(row) for row in rows])
                if i==0 and after_orders is not None:
                    after_orders()
            snap_after=cx.execute("SELECT pg_current_snapshot()::text AS token").fetchone()['token']
            if snap!=snap_after:
                raise AssertionError("Source snapshot changed inside repeatable read")
        captured=datetime.now(timezone.utc)
        receipts={name:dict(source_table=name,complete=True,
          consistent_snapshot_id=snap,captured_at_utc=captured.isoformat())
          for name in TABLES}
    asof_utc=asof.isoformat()
    manifest=build_forward_asof_inventory(
        *values,receipts,asof_utc=asof_utc,
        max_source_capture_lag_seconds=35)
    if manifest["status"]!="SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION":
        raise AssertionError("Source evidence fail-closed: "+repr(manifest["blockers"]))
    return manifest, values, snap

def main():
    dsn=guard_dsn()
    seed(dsn)
    asof=datetime.now(timezone.utc)
    # A second independent writer commits a BACKDATED fourth order+fill after
    # transaction A establishes its snapshot, between the three source SELECTs.
    # The first manifest must remain consistent (2 residuals); a fresh snapshot
    # sees the newer commit and cannot pretend the two inventories are equal.
    def race_writer():
        with make_conn(dsn,BASE_DB) as writer:
            insert_order(writer,PREFIX+'race','INJUSDT','SHORT')
            insert_entry(writer,PREFIX+'race-entry',PREFIX+'race','2.0')
            writer.commit()
    first,all_rows,snap1=capture_one_actual_snapshot(dsn,asof,after_orders=race_writer)
    assert len(all_rows[0])==3 and len(all_rows[1])==3 and len(all_rows[2])==2
    assert first["expected_position_count"]==2
    assert {r['symbol'] for r in first['positions']}=={'NMRUSDT','QUSDT'}
    assert [r['residual_qty'] for r in first['positions']]==['1.5','3.75']
    later,more_rows,snap2=capture_one_actual_snapshot(dsn,asof)
    assert len(more_rows[0])==4 and len(more_rows[1])==4
    assert later["expected_position_count"]==3
    assert {r['symbol'] for r in later['positions']}=={'NMRUSDT','QUSDT','INJUSDT'}
    assert first["manifest_sha256"]!=later["manifest_sha256"]
    assert snap1!=snap2

    # If the actual source query itself times out after reading one table,
    # there is no returned partial/complete source manifest.
    def failed_capture():
        raise psycopg.errors.QueryCanceled("synthetic failure before all three source tables")
    try:
        capture_one_actual_snapshot(dsn,asof,after_orders=failed_capture)
    except psycopg.errors.QueryCanceled:
        pass
    else:
        raise AssertionError("Partially read sources incorrectly completed")
    print("P0_REAL_PG16_SOURCE_SNAPSHOT_RACE_PASS "+json.dumps({
        "isolation":"REAL_REPEATABLE_READ_READ_ONLY_PG16",
        "source_tables":3,
        "initial_expected_residual_positions":first["expected_position_count"],
        "later_expected_residual_positions":later["expected_position_count"],
        "concurrent_backdated_writer_detected_on_next_snapshot":True,
        "initial_snapshot_did_not_mix_three_table_versions":True,
        "partial_source_read_returned_no_manifest":True,
        "source_capture_isolation_verified":True,
        "external_production_database_authority_verified":False,
        "independent_journal_operational_for_real_positions":False,
        "scientific_pass_permitted":False,
        "R10_touched":False,
        "order_authority":False,
    },sort_keys=True))

if __name__=="__main__":
    main()
