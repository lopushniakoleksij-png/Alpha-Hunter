"""P0 live HTTP/PostgREST publication test on disposable PostgreSQL 16/17 only.

Exercises the ACTUAL SupabaseStorage.save_snapshot() source implementation for
parent, immutable 61-symbol batches, signals, features and readiness via HTTP.
Only the unrelated paper execution/reconciliation stage is stubbed out.
Never uses production Supabase, Bitget, Render, exchanges or real credentials.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
import requests

from alpha_hunter import storage as storage_module
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError

BASE = "http://127.0.0.1:3000"
TABLES = (
    "alpha_hunter_snapshots",
    "alpha_hunter_symbol_snapshots",
    "alpha_hunter_signals",
    "alpha_hunter_signal_features",
    "alpha_hunter_readiness_observations_v01",
)
KEYS = {
    "alpha_hunter_snapshots": ("run_id",),
    "alpha_hunter_symbol_snapshots": ("run_id", "symbol"),
    "alpha_hunter_signals": ("signal_id",),
    "alpha_hunter_signal_features": ("signal_id",),
    "alpha_hunter_readiness_observations_v01": ("run_id", "symbol"),
}
TIMESTAMPS = {"collected_at_utc", "detected_at_utc", "captured_at_utc", "observed_at_utc"}
BOOLEAN = {"trade_permission", "state_changed", "v7_trade_ready"}
TEXT = {"run_id", "symbol", "signal_id", "state", "error", "direction", "version", "product_type"}
NUMERIC = {"symbol_count", "error_count"}


def assert_disposable() -> str:
    if os.getenv("AH_P0_LOCAL_POSTGREST_ONLY") != "1":
        raise RuntimeError("Refusing non-isolated run")
    if any(os.getenv(k) for k in (
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "BITGET_API_KEY",
        "BITGET_SECRET_KEY", "RENDER_API_KEY"
    )):
        raise RuntimeError("Production credentials are forbidden")
    dsn = os.environ.get("AH_P0_PG_DSN", "")
    if "host=127.0.0.1" not in dsn or "dbname=isolated_research" not in dsn:
        raise RuntimeError("Only isolated local PostgreSQL is supported")
    return dsn


def snapshot(run_id: str, size: int = 61) -> dict:
    return {
        "run_id": run_id,
        "version": "synthetic-p0-test",
        "product_type": "usdt-futures",
        "collected_at_utc": "2026-11-05T03:40:00+00:00",
        "validation_identity": {"run_source": "RENDER_CRON"},
        "symbols": [
            {
                "symbol": f"TEST{i:03d}USDT",
                "state": "WATCH",
                "trade_permission": False,
                "last_price": round(1.0 + i / 100, 4),
                "execution_setup": {"direction": "LONG", "rr": 1.2},
                "intelligence": {"huge_rr_score": 10.0},
                "timeframes": {},
            } for i in range(size)
        ],
    }


class LocalSession(requests.Session):
    def request(self, method, url, *args, **kwargs):
        if not url.startswith(BASE + "/rest/v1/"):
            raise AssertionError("Refusing non-local PostgREST URL")
        resolved = url.replace(BASE + "/rest/v1/", BASE + "/", 1)
        response = super().request(method, resolved, *args, **kwargs)
        if response.status_code >= 400:
            print(
                "LOCAL_HTTP_DIAGNOSTIC",
                method, response.url, response.status_code,
                repr(response.text[:500]),
                flush=True,
            )
        return response


class LostAckSession(LocalSession):
    """The HTTP server really commits; simulate responses lost in transit."""
    def __init__(self):
        super().__init__()
        self.dropped = 0

    def post(self, url, **kwargs):
        reply = super().post(url, **kwargs)
        if (
            url.endswith("/alpha_hunter_symbol_snapshots")
            and self.dropped < 3
        ):
            assert reply.status_code in (200, 201, 204), reply.text[:300]
            self.dropped += 1
            raise requests.ReadTimeout("synthetic ACK lost AFTER real PostgREST COMMIT")
        return reply


class LocalWriter(SupabaseStorage):
    @property
    def headers(self):
        # Isolated PostgREST's explicit local role, no JWT and no service key.
        return {
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }


class CaptureSchema(LocalWriter):
    def __init__(self):
        super().__init__(SupabaseConfig(url=BASE, key="local-only"))
        self.captured: dict[str, list[dict]] = {}

    def _upsert(self, table, rows, on_conflict):
        if rows:
            self.captured[table] = rows

    def _persist_verified_symbol_children(self, run_id, children):
        self.captured["alpha_hunter_symbol_snapshots"] = children

    def _insert_immutable(self, table, rows, on_conflict):
        if rows:
            raise AssertionError("Synthetic paper stage must have no rows")

    def _reconcile_paper_stages(self, snapshot, run_id):
        pass


def disable_unrelated_paper_stage():
    # Only this local subprocess is modified. The canonical production
    # publish method is NOT mocked; the real database receives its HTTP POSTs.
    storage_module.build_initial_paper_lifecycle = lambda value: ([], [])
    storage_module.build_initial_paper_execution = lambda *a, **kw: ([], [], [])
    storage_module.build_initial_protective_orders = lambda *a, **kw: []
    SupabaseStorage._reconcile_paper_stages = lambda *a, **kw: None


def create_schema(dsn):
    capture = CaptureSchema()
    capture.save_snapshot(snapshot("schema-preview"))
    if set(capture.captured) != set(TABLES):
        raise AssertionError(
            f"Unexpected canonical stage set: {sorted(capture.captured)}"
        )
    assert len(capture.captured["alpha_hunter_signal_features"]) == 61

    with psycopg.connect(dsn, autocommit=True) as conn:
        current = conn.execute("SELECT current_database()").fetchone()[0]
        if current != "isolated_research":
            raise RuntimeError("Refusing non-disposable database")
        conn.execute("CREATE ROLE ah_p0_local_writer NOLOGIN")
        for table in TABLES:
            cols = []
            for field in capture.captured[table][0]:
                if field in TIMESTAMPS:
                    typ = "timestamptz"
                elif field in BOOLEAN:
                    typ = "boolean"
                elif field in TEXT:
                    typ = "text"
                elif field in NUMERIC:
                    typ = "integer"
                else:
                    typ = "jsonb"
                cols.append(sql.SQL("{} {}").format(
                    sql.Identifier(field), sql.SQL(typ),
                ))
            pk = sql.SQL("PRIMARY KEY ({})").format(
                sql.SQL(", ").join(sql.Identifier(k) for k in KEYS[table])
            )
            conn.execute(sql.SQL("CREATE TABLE public.{} ({})").format(
                sql.Identifier(table), sql.SQL(", ").join(cols + [pk])
            ))
        conn.execute("""ALTER TABLE public.alpha_hunter_symbol_snapshots
            ADD FOREIGN KEY (run_id) REFERENCES public.alpha_hunter_snapshots(run_id)""")
        conn.execute("""ALTER TABLE public.alpha_hunter_signal_features
            ADD FOREIGN KEY (signal_id) REFERENCES public.alpha_hunter_signals(signal_id)""")
        conn.execute("""CREATE TABLE public.p0_test_observations (
            run_id text NOT NULL, symbol text NOT NULL, strategy_id integer NOT NULL,
            PRIMARY KEY(run_id, symbol, strategy_id)
        )""")
        conn.execute("""CREATE FUNCTION public.p0_test_symbol_trigger() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.run_id='bad-child' AND NEW.symbol='TEST012USDT' THEN
            RAISE EXCEPTION 'synthetic nested child cancellation'
              USING ERRCODE='57014';
          END IF;
          INSERT INTO public.p0_test_observations
          SELECT NEW.run_id,NEW.symbol,g FROM generate_series(1,10) g
          ON CONFLICT(run_id,symbol,strategy_id) DO NOTHING;
          RETURN NEW;
        END $$""")
        conn.execute("""CREATE TRIGGER p0_child_capture AFTER INSERT OR UPDATE OF payload
        ON public.alpha_hunter_symbol_snapshots FOR EACH ROW
        EXECUTE FUNCTION public.p0_test_symbol_trigger()""")
        conn.execute("""CREATE FUNCTION public.p0_test_feature_trigger() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.run_id='bad-feature' THEN
            RAISE EXCEPTION 'synthetic feature-stage failure'
              USING ERRCODE='57014';
          END IF;
          RETURN NEW;
        END $$""")
        conn.execute("""CREATE TRIGGER p0_feature_fail BEFORE INSERT OR UPDATE
        ON public.alpha_hunter_signal_features FOR EACH ROW
        EXECUTE FUNCTION public.p0_test_feature_trigger()""")
        conn.execute("GRANT USAGE ON SCHEMA public TO ah_p0_local_writer")
        conn.execute("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO ah_p0_local_writer")
        conn.execute("NOTIFY pgrst, 'reload schema'")
    for attempt in range(100):
        try:
            statuses = [
                requests.get(BASE + "/" + table, params={"select": KEYS[table][0], "limit": "1"}, timeout=2).status_code
                for table in TABLES
            ]
            if statuses == [200] * len(TABLES):
                return
        except requests.RequestException:
            pass
        time.sleep(0.35)
    raise AssertionError("Local PostgREST schema did not become ready")


def writer(session=None) -> LocalWriter:
    return LocalWriter(
        SupabaseConfig(
            url=BASE, key="local-only", timeout_seconds=8,
            max_retries=2, retry_backoff_seconds=0.02,
        ),
        session=session or LocalSession(),
    )


def counts(conn, run_id):
    result = {}
    for table in TABLES:
        result[table] = conn.execute(
            sql.SQL("SELECT count(*) FROM public.{} WHERE run_id=%s").format(sql.Identifier(table)),
            (run_id,),
        ).fetchone()[0]
    result["observations"] = conn.execute(
        "SELECT count(*) FROM public.p0_test_observations WHERE run_id=%s",
        (run_id,),
    ).fetchone()[0]
    result["enabled_trading"] = conn.execute(
        "SELECT count(*) FROM public.alpha_hunter_symbol_snapshots "
        "WHERE run_id=%s AND trade_permission=true", (run_id,),
    ).fetchone()[0]
    return result


def assert_counts(conn, run_id, *, parent, child, signal, feature, readiness, obs):
    c = counts(conn, run_id)
    wanted = {
        "alpha_hunter_snapshots": parent,
        "alpha_hunter_symbol_snapshots": child,
        "alpha_hunter_signals": signal,
        "alpha_hunter_signal_features": feature,
        "alpha_hunter_readiness_observations_v01": readiness,
        "observations": obs,
        "enabled_trading": 0,
    }
    assert c == wanted, (run_id, c, wanted)
    return c


def test_success_and_idempotent_replay(conn, report):
    run = "success-real-http"
    full = snapshot(run)
    write = writer()
    started = time.perf_counter()
    assert write.save_snapshot(full) == run
    elapsed = (time.perf_counter() - started) * 1000
    c = assert_counts(conn, run, parent=1, child=61, signal=61,
                      feature=61, readiness=61, obs=610)
    # Provenance of every child must match the observed synthetic scan.
    actual = conn.execute(
        "SELECT symbol,collected_at_utc,state,trade_permission FROM "
        "public.alpha_hunter_symbol_snapshots WHERE run_id=%s ORDER BY symbol",
        (run,),
    ).fetchall()
    assert len(actual) == 61
    assert all(
        x[1] == datetime(2026, 11, 5, 3, 40, tzinfo=timezone.utc)
        and x[2] == "WATCH" and x[3] is False for x in actual
    )
    assert write.save_snapshot(full) == run
    assert_counts(conn, run, parent=1, child=61, signal=61,
                  feature=61, readiness=61, obs=610)
    report["success"] = {"counts": c, "first_publish_ms": round(elapsed, 3),
                         "duplicate_replay_safe": True}


def test_real_commit_lost_ack(conn, report):
    run = "lost-http-ack"
    session = LostAckSession()
    assert writer(session).save_snapshot(snapshot(run)) == run
    assert session.dropped == 3
    c = assert_counts(conn, run, parent=1, child=61, signal=61,
                      feature=61, readiness=61, obs=610)
    report["committed_lost_responses"] = {
        "real_http_commits_before_ack_drop": 3,
        "readback_proved_batch": True,
        "counts": c,
    }


def test_child_trigger_cancel_fails_closed(conn, report):
    run = "bad-child"
    try:
        writer().save_snapshot(snapshot(run, 17))
    except SupabaseStorageError as exc:
        assert "unverified" in str(exc), str(exc)
    else:
        raise AssertionError("Actual HTTP child SQLSTATE 57014 did not fail")
    # First 8-row batch survives; failing second statement rolls back;
    # no signal, feature, readiness or paper-authority stage proceeds.
    c = assert_counts(conn, run, parent=1, child=8, signal=0,
                      feature=0, readiness=0, obs=80)
    payload = conn.execute(
        "SELECT payload FROM public.alpha_hunter_snapshots WHERE run_id=%s", (run,),
    ).fetchone()[0]
    assert payload.get("_canonical_publication_state") != "VERIFIED"
    report["child_57014"] = {"counts": c, "fail_closed": True,
                             "atomic_whole_scan_publication": False}


def test_feature_failure_reveals_non_atomic_publication(conn, report):
    run = "bad-feature"
    try:
        writer().save_snapshot(snapshot(run, 17))
    except SupabaseStorageError as exc:
        assert "alpha_hunter_signal_features" in str(exc), str(exc)
    else:
        raise AssertionError("Actual HTTP feature failure did not fail")
    # Important: separate POST requests are not a single transaction.
    # Parent, children and signals exist despite feature failure. The
    # dashboard must not promote this partial run; an atomic RPC is required.
    c = assert_counts(conn, run, parent=1, child=17, signal=17,
                      feature=0, readiness=0, obs=170)
    payload = conn.execute(
        "SELECT payload FROM public.alpha_hunter_snapshots WHERE run_id=%s", (run,),
    ).fetchone()[0]
    assert payload.get("_canonical_publication_state") != "VERIFIED"
    report["feature_57014"] = {
        "counts": c,
        "partial_publication_observed": True,
        "production_release_no_go": True,
    }


def main():
    dsn = assert_disposable()
    disable_unrelated_paper_stage()
    create_schema(dsn)
    report = {
        "scope": "DISPOSABLE_TRUE_POSTGREST_AND_PG16_17",
        "real_production_trigger_equivalent": False,
        "supabase_gateway_or_RLS_proven": False,
        "paper_execution_exercised": False,
        "production_mutation": False,
        "real_order_authority": False,
    }
    with psycopg.connect(dsn, autocommit=True) as conn:
        report["pg_version"] = conn.execute("SHOW server_version").fetchone()[0]
        test_success_and_idempotent_replay(conn, report)
        test_real_commit_lost_ack(conn, report)
        test_child_trigger_cancel_fails_closed(conn, report)
        test_feature_failure_reveals_non_atomic_publication(conn, report)
    out = Path("p0_postgrest_acceptance_results")
    out.mkdir(exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    print("PASS: isolated HTTP semantics and fail-closed partial-publish detection.")
    print("RELEASE NO-GO: separate HTTP writes are not atomic, live trigger equivalence unproven.")


if __name__ == "__main__":
    main()
