"""Integrated successor failure-injection acceptance on disposable PostgreSQL/PostgREST.

Tests the real draft storage writer (PR #371) together with read-back of
synthetic position receipts and the separate Phase II continuity validator.
Never contacts production; no live order path. Database fixture from the
existing PR #371 HTTP suite is deliberately reused.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import requests

from test_canonical_snapshot_postgrest_http_20261017 import (
    BASE, real_http_db, scanner_payload, read_state, read_child_count,
    insert_local_position, insert_local_receipt,
)
from alpha_hunter.storage import SupabaseStorageError

FILE = (Path(__file__).resolve().parents[1] /
        "ops/reviews/phase2_successor_integrity_gate_v01.py")
spec = spec_from_file_location("phase2_integrated_gate", FILE)
gate = module_from_spec(spec)
spec.loader.exec_module(gate)


def create_nested_trigger_chain(conn):
    """Isolated representation of symbol -> strategy -> payoff evaluation."""
    conn.execute("""
      CREATE TABLE public.ah_test_payoff_outcomes (
          episode integer PRIMARY KEY, strategy_id text NOT NULL,
          horizon_hours integer NOT NULL,
          direction text NOT NULL, qualified boolean NOT NULL,
          max_adverse_excursion_pct double precision
      )
    """)
    conn.execute("""
      INSERT INTO public.ah_test_payoff_outcomes
      SELECT g, CASE WHEN g%2=0 THEN 'S2' ELSE 'S4' END,
             24, CASE WHEN g%2=0 THEN 'LONG' ELSE 'SHORT' END,
             g%91=0, (g%1100)::double precision/1000
      FROM generate_series(1,6000) AS g
    """)
    conn.execute("""
      CREATE FUNCTION public.ah_test_payoff_health()
      RETURNS double precision LANGUAGE plpgsql AS $$
      DECLARE p double precision;
      BEGIN
        SELECT percentile_cont(0.5) WITHIN GROUP
               (ORDER BY max_adverse_excursion_pct)
          INTO p FROM public.ah_test_payoff_outcomes
         WHERE horizon_hours=24 AND qualified
           AND strategy_id='S2' AND direction='LONG';
        RETURN p;
      END $$;
    """)
    conn.execute("""
      CREATE FUNCTION public.ah_test_trigger_capture()
      RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        PERFORM public.ah_test_payoff_health();
        IF NEW.symbol='TEST032USDT' THEN
          RAISE EXCEPTION 'isolated nested AFTER trigger statement cancellation'
            USING ERRCODE='57014';
        END IF;
        RETURN NEW;
      END $$;
    """)
    conn.execute("""
      CREATE TRIGGER ah_test_nested_capture
      AFTER INSERT OR UPDATE OF payload
      ON public.alpha_hunter_symbol_snapshots
      FOR EACH ROW EXECUTE FUNCTION public.ah_test_trigger_capture();
    """)


def remove_nested_trigger_chain(conn):
    conn.execute("""
      DROP TRIGGER IF EXISTS ah_test_nested_capture
      ON public.alpha_hunter_symbol_snapshots
    """)
    conn.execute("DROP FUNCTION IF EXISTS public.ah_test_trigger_capture()")
    conn.execute("DROP FUNCTION IF EXISTS public.ah_test_payoff_health()")
    conn.execute("DROP TABLE IF EXISTS public.ah_test_payoff_outcomes")


def write_prior_receipt_over_http(run_id, observed_at):
    """Explicitly persisted earlier synthetic observation, not an invented fill."""
    payload = {
        "entry_order_id": "isolated-position-1",
        "source_run_id": run_id,
        "decision_id": "isolated-decision-1",
        "symbol": "TEST000USDT",
        "direction": "LONG",
        "observed_at_utc": observed_at,
        "outcome": "NO_TRIGGER",
        "blockers": [],
        "paper_only": True,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }
    response = requests.post(
        BASE + "/alpha_hunter_paper_exit_attempts_v04",
        json=payload,
        headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        timeout=10,
    )
    assert response.status_code in (200,201,204), response.text[:300]


def verdict_using_persisted_http_rows(storage, *, run_id, prior_run_id):
    """No fabricated child or monitoring evidence enters the gate."""
    children = storage._select_json(
        "alpha_hunter_symbol_snapshots",
        {"select":"symbol", "run_id":f"eq.{run_id}", "limit":"1000"},
    )
    current = storage._select_json(
        "alpha_hunter_paper_exit_attempts_v04",
        {"select":"*", "source_run_id":f"eq.{run_id}", "limit":"1000"},
    )
    prior = storage._select_json(
        "alpha_hunter_paper_exit_attempts_v04",
        {"select":"*", "source_run_id":f"eq.{prior_run_id}", "limit":"1000"},
    )
    assert len(prior) == 1
    return gate.evaluate_scan(
        run_id=run_id,
        collected_at_utc="2026-10-17T09:40:00Z",
        expected_symbols=[f"TEST{i:03d}USDT" for i in range(61)],
        persisted_symbols=[x["symbol"] for x in children],
        positions=[{
            "entry_order_id":"isolated-position-1",
            "decision_id":"isolated-decision-1",
            "symbol":"TEST000USDT",
            "direction":"LONG",
            "prior_observed_at_utc":prior[0]["observed_at_utc"],
        }],
        receipts=current,
        expected_fingerprint="synthetic-frozen-successor",
        observed_fingerprint="synthetic-frozen-successor",
        expected_source="RENDER_CRON",
        observed_source="RENDER_CRON",
        monitoring_limit_minutes=35,
    )


def test_integrated_trigger_57014_recovery_and_monitoring_continuity(real_http_db):
    storage, conn = real_http_db
    value = scanner_payload(n=61)
    value["run_id"] = "9"*32
    insert_local_position(conn)
    create_nested_trigger_chain(conn)
    try:
        # Actual HTTP/PostgREST handles a PostgreSQL AFTER-trigger exception.
        with pytest.raises(SupabaseStorageError, match="upsert failed for alpha_hunter_symbol_snapshots"):
            storage.save_snapshot(value)
        assert read_state(conn, value["run_id"]) == "PENDING"
        assert read_child_count(conn, value["run_id"]) == 32
        assert conn.execute(
            "SELECT count(*) FROM public.alpha_hunter_paper_exit_attempts_v04 "
            "WHERE source_run_id=%s", (value["run_id"],),
        ).fetchone()[0] == 0

        # Fixing the synthetic timeout is not sufficient. Without the per-position
        # receipt the parent must remain PENDING even if all 61 children persisted.
        conn.execute("""
          DROP TRIGGER ah_test_nested_capture
          ON public.alpha_hunter_symbol_snapshots
        """)
        with pytest.raises(SupabaseStorageError, match="durable monitoring evidence"):
            storage.save_snapshot(value)
        assert read_state(conn, value["run_id"]) == "PENDING"
        assert read_child_count(conn, value["run_id"]) == 61

        insert_local_receipt(conn, value["run_id"])
        assert storage.save_snapshot(value) == value["run_id"]
        assert read_state(conn, value["run_id"]) == "VERIFIED"
        assert read_child_count(conn, value["run_id"]) == 61

        # A last-good receipt does not erase a 40-minute gap. PR #371 alone
        # currently publishes; independent Phase II scientific gate rejects it.
        write_prior_receipt_over_http("prior-gap", "2026-10-17T09:00:00Z")
        failed = verdict_using_persisted_http_rows(
            storage, run_id=value["run_id"], prior_run_id="prior-gap",
        )
        assert failed["operational_evidence_complete"] is False
        assert "MONITORING_GAP_OVER_FROZEN_LIMIT" in failed["blockers"]
        assert failed["scientific_eligible"] is False
        assert failed["trade_permission"] is False

        # An independently stored previous receipt within 20 minutes is eligible
        # for local evidence review, but *still* never enables trading.
        write_prior_receipt_over_http("prior-ok", "2026-10-17T09:20:00Z")
        passed = verdict_using_persisted_http_rows(
            storage, run_id=value["run_id"], prior_run_id="prior-ok",
        )
        assert passed["operational_evidence_complete"] is True
        assert passed["scientific_eligible"] is True
        assert passed["trade_permission"] is False
        assert passed["production_promotion_permitted"] is False
    finally:
        remove_nested_trigger_chain(conn)


def test_same_scan_complete_children_with_missing_receipt_never_publish(real_http_db):
    storage, conn = real_http_db
    insert_local_position(conn)
    value = scanner_payload(n=61)
    value["run_id"] = "8"*32
    with pytest.raises(SupabaseStorageError, match="durable monitoring evidence"):
        storage.save_snapshot(value)
    assert read_child_count(conn, value["run_id"]) == 61
    assert read_state(conn, value["run_id"]) == "PENDING"
