#!/usr/bin/env python3
"""Isolated local PostgreSQL 16 runtime proof of successor per-position seal.

Runs after successor_pg16_tcp_benchmark_v01.py in the SAME disposable Actions
postgres service. NO Supabase/Bitget connection, no production roles or DDL.
"""
from __future__ import annotations

from pathlib import Path

import psycopg

from successor_pg16_tcp_benchmark_v01 import BASE_DB, guard_dsn, make_conn

CONTRACT = (Path(__file__).resolve().parents[2] /
            "tests/postgres/successor-monitoring-cycle-seal-schema.sql")
FINGERPRINT = "50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834"
SYMBOLS = ("QUSDT", "NMRUSDT")
POSITIONS = (("one", "QUSDT", "LONG"), ("two", "QUSDT", "LONG"),
             ("three", "NMRUSDT", "SHORT"))
COLLECTED = "2026-10-12T12:00:00Z"
CAPTURE = "2026-10-12T12:00:04Z"


def seed(cx: psycopg.Connection, name: str, *,
         captured: str = CAPTURE, collected: str = COLLECTED,
         children: bool = True, attempts: bool = True, monitored_orders=POSITIONS,
         basis_kind: str = "FILL_ATTESTED",
         basis_source_id: str = "synthetic-independent-fill",
         basis_at: str = "2026-10-12T11:45:00Z") -> None:
    asof = "2026-10-12T11:59:00Z" if collected == COLLECTED else "2026-10-12T12:19:00Z"
    # One atomic staged test fixture. Source child rows use the EXACT copied
    # production public alpha_hunter_symbol_snapshots schema and its trigger.
    with cx.transaction():
        cx.execute("INSERT INTO public.alpha_hunter_snapshots(run_id) VALUES (%s)", (name,))
        cx.execute("""INSERT INTO successor_shadow.cycles(
            run_id,collected_at_utc,run_source,runtime_role,fingerprint,
            expected_symbol_count,expected_position_count,symbol_manifest_source,
            position_inventory_source,position_inventory_asof_utc,
            position_inventory_attested_complete,source_policy_id,
            approved_quote_sources,max_quote_offset_seconds)
            VALUES (%s,%s,'RENDER_CRON','RENDER_CRON',%s,2,%s,
            'synthetic-independent-canonical-source',
            'synthetic-independent-position-manifest',%s,true,
            'synthetic-source-policy',ARRAY['BITGET_PUBLIC_ALL_TICKERS'],30)
        """,(name,collected,FINGERPRINT,len(monitored_orders),asof))
        for sym in SYMBOLS:
            cx.execute("INSERT INTO successor_shadow.expected_symbols(run_id,symbol) VALUES (%s,%s)",
                       (name,sym))
            if children:
                cx.execute("""INSERT INTO public.alpha_hunter_symbol_snapshots(
                    run_id,symbol,collected_at_utc,payload) VALUES (%s,%s,%s,'{}')""",
                           (name,sym,collected))
                cx.execute("""INSERT INTO successor_shadow.committed_symbols(
                    run_id,symbol,source_row_id) VALUES (%s,%s,%s)""",
                           (name,sym,"isolated-canonical-source-child:"+name+":"+sym))
        for oid,sym,direction in monitored_orders:
            cx.execute("""INSERT INTO successor_shadow.expected_positions(
                run_id,entry_order_id,symbol,direction,basis_kind,basis_source_id,
                basis_qualified_at_utc) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                       (name,oid,sym,direction,basis_kind,basis_source_id,basis_at))
            if attempts:
                cx.execute("""INSERT INTO successor_shadow.position_monitoring(
                    run_id,entry_order_id,attempt_id,source_run_id,symbol,direction,
                    outcome,quote_source,captured_at_utc,bid,ask,bid_size,ask_size)
                    VALUES (%s,%s,%s,%s,%s,%s,'NO_TRIGGER',
                    'BITGET_PUBLIC_ALL_TICKERS',%s,1,1.01,10,7)""",
                           (name,oid,name+":"+oid,name,sym,direction,captured))


def seal(cx, name):
    return cx.execute("SELECT successor_shadow.try_seal_cycle(%s)",(name,)).fetchone()[0]


def count(cx, name):
    return cx.execute("SELECT count(*) FROM successor_shadow.completed_cycles WHERE run_id=%s",
                      (name,)).fetchone()[0]


def main() -> None:
    dsn=guard_dsn()
    with make_conn(dsn,BASE_DB) as cx:
        cx.execute(CONTRACT.read_text())
        seed(cx,"pg16-cycle-clean")
        assert seal(cx,"pg16-cycle-clean")=="SEALED_LOCAL_STRUCTURAL_ONLY"
        assert seal(cx,"pg16-cycle-clean")=="ALREADY_SEALED_STRUCTURAL_ONLY"
        assert count(cx,"pg16-cycle-clean")==1

        seed(cx,"pg16-cycle-parent-only",children=False,attempts=False)
        assert seal(cx,"pg16-cycle-parent-only")=="UNKNOWN_OR_INCOMPLETE_SYMBOL_STAGE"
        assert count(cx,"pg16-cycle-parent-only")==0

        seed(cx,"pg16-cycle-missing-attempt",attempts=False)
        assert seal(cx,"pg16-cycle-missing-attempt")=="UNKNOWN_OR_INCOMPLETE_POSITION_COUNT"
        assert count(cx,"pg16-cycle-missing-attempt")==0

        seed(cx,"pg16-cycle-gap",basis_at="2026-10-12T11:20:00Z")
        assert seal(cx,"pg16-cycle-gap")=="UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP"
        assert count(cx,"pg16-cycle-gap")==0

        seed(cx,"pg16-cycle-next",collected="2026-10-12T12:20:00Z",
             captured="2026-10-12T12:20:04Z",
             basis_kind="PRIOR_SEALED_CYCLE",
             basis_source_id="pg16-cycle-clean",basis_at=CAPTURE)
        assert seal(cx,"pg16-cycle-next")=="SEALED_LOCAL_STRUCTURAL_ONLY"
        assert count(cx,"pg16-cycle-next")==1

        # Source child receipts require actual committed symbol rows; the
        # live production schema's composite (run_id,symbol) FK enforces this.
        try:
            with cx.transaction():
                cx.execute("""INSERT INTO successor_shadow.committed_symbols(
                    run_id,symbol,source_row_id)
                    VALUES ('pg16-cycle-missing-attempt','FAKEUSDT','missing')""")
        except psycopg.errors.ForeignKeyViolation:
            pass
        else:
            raise AssertionError("Missing real source child was incorrectly accepted")

        # An immutable final cycle cannot be modified. Keep the failed
        # transaction confined to its own SAVEPOINT rather than abort session.
        try:
            with cx.transaction():
                cx.execute("""INSERT INTO successor_shadow.expected_positions(
                    run_id,entry_order_id,symbol,direction,basis_kind,
                    basis_source_id,basis_qualified_at_utc)
                    VALUES('pg16-cycle-clean','fake-new-position','QUSDT',
                    'LONG','FILL_ATTESTED','fake','2026-10-12T11:59:00Z')""")
        except psycopg.errors.RaiseException as e:
            assert "ALREADY_SEALED" in str(e)
        else:
            raise AssertionError("Mutation after completed cycle accepted")

        assert count(cx,"pg16-cycle-clean")==1
        assert cx.execute("""SELECT count(*) FROM successor_shadow.completed_cycles
            WHERE scientific_pass_permitted OR exchange_authority OR paper_authority""").fetchone()[0]==0
    print("P0_REAL_PG16_ISOLATED_CYCLE_SEAL_PASS "
          '{"cases":5,"sealed":2,"incomplete":3,"historic_backfill":false,'
          '"parent_only_cannot_seal":true,"all_position_attempts_required":true,'
          '"frozen_35min_bound":true,"real_source_child_fk":true,'
          '"prior_seal_chain_checked":true,"new_order_authority":false,'
          '"production_migration":false}')


if __name__ == "__main__":
    main()
