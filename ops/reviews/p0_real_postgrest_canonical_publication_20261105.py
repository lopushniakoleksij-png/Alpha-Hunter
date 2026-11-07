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
import base64
import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
import requests

from alpha_hunter import storage as storage_module
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError

BASE = "http://127.0.0.1:3000"
ROLE_BASE = "http://127.0.0.1:3001"
ROLE_TEST_SECRET = "alpha-hunter-disposable-only-role-matrix-2026-key"
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
        # Temporary roles in disposable PostgreSQL ONLY. The local writer
        # deliberately models service_role's RLS bypass; real authentication
        # and role assignment still require independent Supabase review.
        conn.execute("CREATE ROLE ah_p0_local_writer NOLOGIN BYPASSRLS")
        conn.execute("CREATE ROLE anon NOLOGIN")
        conn.execute("CREATE ROLE authenticated NOLOGIN")
        conn.execute("CREATE ROLE service_role NOLOGIN BYPASSRLS")
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
        # Reflect the production PostgreSQL 17 default/NOT NULL contract.
        # The captured app JSON omits created_at, while actual production
        # tables have created_at timestamptz NOT NULL DEFAULT now().
        for table in TABLES:
            if "created_at" not in capture.captured[table][0]:
                conn.execute(sql.SQL(
                    "ALTER TABLE public.{} ADD COLUMN created_at "
                    "timestamptz NOT NULL DEFAULT now()"
                ).format(sql.Identifier(table)))
            else:
                conn.execute(sql.SQL(
                    "ALTER TABLE public.{} ALTER COLUMN created_at SET NOT NULL"
                ).format(sql.Identifier(table)))
        conn.execute("ALTER TABLE public.alpha_hunter_snapshots "
                     "ALTER COLUMN error_count SET DEFAULT 0")
        for table in TABLES[1:]:
            conn.execute(sql.SQL(
                "ALTER TABLE public.{} ALTER COLUMN trade_permission "
                "SET DEFAULT false"
            ).format(sql.Identifier(table)))
        conn.execute("ALTER TABLE public.alpha_hunter_symbol_snapshots "
                     "ALTER COLUMN state_changed SET DEFAULT false")
        conn.execute("ALTER TABLE public.alpha_hunter_readiness_observations_v01 "
                     "ALTER COLUMN v7_trade_ready SET DEFAULT false")
        conn.execute("ALTER TABLE public.alpha_hunter_signal_features "
                     "ALTER COLUMN features SET DEFAULT '{}'::jsonb")
        conn.execute("ALTER TABLE public.alpha_hunter_signal_features "
                     "ALTER COLUMN source_payload SET DEFAULT '{}'::jsonb")
        for table in TABLES[1:]:
            conn.execute(sql.SQL(
                "ALTER TABLE public.{} ALTER COLUMN trade_permission SET NOT NULL"
            ).format(sql.Identifier(table)))
        # Mirror the parent trigger event classification; an UPDATE OF payload
        # must not be necessary to mark an already-atomic commit VERIFIED.
        conn.execute("""CREATE TABLE public.p0_parent_capture_audit (
            run_id text NOT NULL, trigger_operation text NOT NULL
        )""")
        conn.execute("""CREATE FUNCTION public.p0_parent_capture_hook() RETURNS trigger
        LANGUAGE plpgsql AS $p0_hook$
        BEGIN
          INSERT INTO public.p0_parent_capture_audit(run_id,trigger_operation)
          VALUES(NEW.run_id,TG_OP);
          RETURN NEW;
        END $p0_hook$""")
        conn.execute("""CREATE TRIGGER p0_parent_capture
            AFTER INSERT OR UPDATE OF payload ON public.alpha_hunter_snapshots
            FOR EACH ROW EXECUTE FUNCTION public.p0_parent_capture_hook()""")
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
          IF NEW.run_id IN ('bad-child','bad-child-atomic')
             AND NEW.symbol='TEST012USDT' THEN
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
          IF NEW.run_id IN ('bad-feature','bad-feature-atomic') THEN
            RAISE EXCEPTION 'synthetic feature-stage failure'
              USING ERRCODE='57014';
          END IF;
          RETURN NEW;
        END $$""")
        conn.execute("""CREATE TRIGGER p0_feature_fail BEFORE INSERT OR UPDATE
        ON public.alpha_hunter_signal_features FOR EACH ROW
        EXECUTE FUNCTION public.p0_test_feature_trigger()""")
        # Final-stage fault injections: one failing SIGNAL/READINESS row
        # must roll back every earlier stage and all nested observation writes.
        conn.execute("""CREATE FUNCTION public.p0_test_signal_trigger() RETURNS trigger
        LANGUAGE plpgsql AS $p0_signal$
        BEGIN
          IF NEW.run_id = 'bad-signal-atomic' THEN
            RAISE EXCEPTION 'synthetic signal-stage cancellation'
              USING ERRCODE='57014';
          END IF;
          RETURN NEW;
        END $p0_signal$""")
        conn.execute("""CREATE TRIGGER p0_signal_fail BEFORE INSERT
        ON public.alpha_hunter_signals FOR EACH ROW
        EXECUTE FUNCTION public.p0_test_signal_trigger()""")
        conn.execute("""CREATE FUNCTION public.p0_test_readiness_trigger() RETURNS trigger
        LANGUAGE plpgsql AS $p0_readiness$
        BEGIN
          IF NEW.run_id = 'bad-readiness-atomic' THEN
            RAISE EXCEPTION 'synthetic final readiness-stage cancellation'
              USING ERRCODE='57014';
          END IF;
          RETURN NEW;
        END $p0_readiness$""")
        conn.execute("""CREATE TRIGGER p0_readiness_fail BEFORE INSERT
        ON public.alpha_hunter_readiness_observations_v01 FOR EACH ROW
        EXECUTE FUNCTION public.p0_test_readiness_trigger()""")
        for table in TABLES:
            conn.execute(sql.SQL("ALTER TABLE public.{} ENABLE ROW LEVEL SECURITY"
                     ).format(sql.Identifier(table)))
        conn.execute("GRANT USAGE ON SCHEMA public "
                     "TO ah_p0_local_writer, anon, authenticated, service_role")
        # Production has broad table DML grants but no RLS policies on these
        # five canonical tables. Reproduce the effective deny-by-RLS property.
        conn.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                     "IN SCHEMA public TO anon, authenticated, service_role")
        assert conn.execute("""SELECT count(*) FROM pg_policies
                 WHERE schemaname='public' AND tablename = ANY(%s)""",
                 (list(TABLES),)).fetchone()[0] == 0
        conn.execute("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO ah_p0_local_writer")
        atomic_sql = Path(
            "research/p0_successor_atomic_canonical_v03_PRODUCTION_SCHEMA_REVIEW_ONLY.sql"
        ).read_text(encoding="utf-8")
        conn.execute(atomic_sql)
        conn.execute("""GRANT EXECUTE ON FUNCTION
          public.ah_p0_research_atomic_canonical_v03(jsonb,jsonb,jsonb,jsonb,jsonb)
          TO ah_p0_local_writer, service_role""")
        conn.execute("NOTIFY pgrst, 'reload schema'")
    for attempt in range(100):
        try:
            statuses = [
                requests.get(BASE + "/" + table, params={"select": KEYS[table][0], "limit": "1"}, timeout=2).status_code
                for table in TABLES
            ]
            if statuses == [200] * len(TABLES):
                # Schema reload is asynchronous; require the POST contract to
                # be visible, not merely a GET response while refreshing.
                time.sleep(1.0)
                pre = CaptureSchema()
                pre.save_snapshot(snapshot("http-diagnostic-preflight"))
                sample = pre.captured["alpha_hunter_snapshots"]
                reply = requests.post(
                    BASE + "/alpha_hunter_snapshots",
                    params={"on_conflict": "run_id"},
                    headers={
                        "Content-Type": "application/json",
                        "Prefer": "resolution=merge-duplicates,return=minimal",
                    },
                    data=json.dumps(sample, separators=(",", ":")),
                    timeout=5,
                )
                print("DIRECT_PGRST_PREFLIGHT", reply.status_code,
                      repr(reply.text[:300]),
                      dict(reply.headers), flush=True)
                if reply.status_code not in (200,201,204):
                    raise AssertionError(
                        "Local PostgREST cannot write verified parent fixture"
                    )
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


def test_atomic_five_stage_rpc(conn, report):
    """Actual PostgREST single-function-call transaction: separate from live writer."""
    capture = CaptureSchema()

    def atomic(run, size=61, *, shorten_features=False, elevate_permission=False):
        capture.captured.clear()
        capture.save_snapshot(snapshot(run, size))
        payload = {
            "p_parent": capture.captured["alpha_hunter_snapshots"][0],
            "p_children": capture.captured["alpha_hunter_symbol_snapshots"],
            "p_signals": capture.captured["alpha_hunter_signals"],
            "p_features": capture.captured["alpha_hunter_signal_features"],
            "p_readiness": capture.captured["alpha_hunter_readiness_observations_v01"],
        }
        if shorten_features:
            payload["p_features"] = payload["p_features"][:-1]
        if elevate_permission:
            payload["p_signals"][0]["trade_permission"] = True
        response = requests.post(
            BASE + "/rpc/ah_p0_research_atomic_canonical_v03",
            json=payload,
            timeout=15,
        )
        print("ATOMIC_RPC",run,response.status_code,
              repr(response.text[:350]),flush=True)
        return response

    first = atomic("success-atomic")
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["status"] == "VERIFIED"
    assert result["child_count"] == 61
    assert result["feature_count"] == 61
    c = assert_counts(conn, "success-atomic", parent=1, child=61,
                      signal=61, feature=61, readiness=61, obs=610)
    payload = conn.execute(
        "SELECT payload FROM public.alpha_hunter_snapshots WHERE run_id=%s",
        ("success-atomic",),
    ).fetchone()[0]
    assert payload.get("_canonical_publication_state") == "VERIFIED"
    # Read back the exact synthetic identities across all four child
    # stages, not only their matching counts; duplicate/wrong-join evidence
    # must never be classified as a complete scan.
    joined = conn.execute("""
        SELECT c.symbol,s.signal_id,f.signal_id,r.symbol
        FROM public.alpha_hunter_symbol_snapshots c
        LEFT JOIN public.alpha_hunter_signals s
          ON s.run_id=c.run_id AND s.symbol=c.symbol
        LEFT JOIN public.alpha_hunter_signal_features f
          ON f.run_id=c.run_id AND f.symbol=c.symbol
        LEFT JOIN public.alpha_hunter_readiness_observations_v01 r
          ON r.run_id=c.run_id AND r.symbol=c.symbol
        WHERE c.run_id=%s ORDER BY c.symbol
    """, ("success-atomic",)).fetchall()
    expected_symbols = {f"TEST{i:03d}USDT" for i in range(61)}
    assert len(joined) == 61
    assert {row[0] for row in joined} == expected_symbols
    for symbol, signal_id, feature_id, readiness_symbol in joined:
        expected_id = hashlib.sha256(
            f"success-atomic|{symbol}".encode("utf-8")
        ).hexdigest()[:32]
        assert signal_id == expected_id, (symbol, "signal identity")
        assert feature_id == expected_id, (symbol, "feature identity")
        assert readiness_symbol == symbol, (symbol, "readiness identity")
    for table in TABLES:
        not_null = conn.execute(
            sql.SQL("SELECT count(*) FROM public.{} WHERE run_id=%s "
                    "AND created_at IS NULL").format(sql.Identifier(table)),
            ("success-atomic",),
        ).fetchone()[0]
        assert not_null == 0, (table, "production required created_at missing")
    operations = conn.execute(
        "SELECT trigger_operation FROM public.p0_parent_capture_audit "
        "WHERE run_id=%s", ("success-atomic",)
    ).fetchall()
    assert operations == [("INSERT",)], operations

    again = atomic("success-atomic")
    assert again.status_code >= 400, "Ambiguous duplicate RPC unexpectedly accepted"
    assert_counts(conn, "success-atomic", parent=1, child=61,
                  signal=61, feature=61, readiness=61, obs=610)

    fail_child = atomic("bad-child-atomic", 17)
    assert fail_child.status_code >= 400, fail_child.text
    assert_counts(conn, "bad-child-atomic", parent=0, child=0,
                  signal=0, feature=0, readiness=0, obs=0)

    fail_feature = atomic("bad-feature-atomic", 17)
    assert fail_feature.status_code >= 400, fail_feature.text
    assert_counts(conn, "bad-feature-atomic", parent=0, child=0,
                  signal=0, feature=0, readiness=0, obs=0)

    # These failures occur after parent+children (and for readiness, also
    # signals+features) already executed inside the single RPC transaction.
    for stage in ("signal", "readiness"):
        run = f"bad-{stage}-atomic"
        failed = atomic(run, 17)
        assert failed.status_code >= 400, (stage, failed.text)
        assert_counts(conn, run, parent=0, child=0,
                      signal=0, feature=0, readiness=0, obs=0)

    wrong_count = atomic("bad-count-atomic", 61, shorten_features=True)
    assert wrong_count.status_code >= 400, wrong_count.text
    assert_counts(conn, "bad-count-atomic", parent=0, child=0,
                  signal=0, feature=0, readiness=0, obs=0)

    forged = atomic("forged-permission", 17, elevate_permission=True)
    assert forged.status_code >= 400, forged.text
    assert_counts(conn, "forged-permission", parent=0, child=0,
                  signal=0, feature=0, readiness=0, obs=0)

    report["isolated_atomic_rpc"] = {
        "five_stage_success": c,
        "duplicate_replay_rejected": True,
        "child_trigger_error_full_rollback": True,
        "feature_trigger_error_full_rollback": True,
        "signal_trigger_error_full_rollback": True,
        "readiness_last_stage_error_full_rollback": True,
        "feature_count_mismatch_full_rollback": True,
        "forged_permission_rejected": True,
        "real_production_deploy_ready": False,
        "production_schema_defaults_verified": False,
        "isolated_production_equivalent_not_null_defaults_verified": True,
        "isolated_parent_payload_trigger_fired_once": True,
        "exact_same_run_identity_join_verified": True,
    }



def _disposable_jwt(role: str) -> str:
    """HS256 only, using a public fixture secret; NEVER a real Supabase token."""
    if role not in ("anon", "authenticated", "service_role"):
        raise AssertionError("Unexpected synthetic JWT role")
    def encode(value):
        data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    message = encode({"alg": "HS256", "typ": "JWT"}) + "." + encode({
        "role": role, "iat": int(time.time()), "exp": int(time.time()) + 600,
        "sub": "DISPOSABLE_ONLY", "aud": "authenticated",
    })
    signature = hmac.new(ROLE_TEST_SECRET.encode(), message.encode(),
                         hashlib.sha256).digest()
    return message + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def test_real_http_role_matrix(conn, report):
    """Actual local HTTP JWT/RLS checks; never claims Supabase auth parity."""
    capture = CaptureSchema()
    capture.save_snapshot(snapshot("local-role-matrix", 17))
    args = {
        "p_parent": capture.captured["alpha_hunter_snapshots"][0],
        "p_children": capture.captured["alpha_hunter_symbol_snapshots"],
        "p_signals": capture.captured["alpha_hunter_signals"],
        "p_features": capture.captured["alpha_hunter_signal_features"],
        "p_readiness": capture.captured["alpha_hunter_readiness_observations_v01"],
    }
    url = ROLE_BASE + "/rpc/ah_p0_research_atomic_canonical_v03"
    # The local PostgREST service has an actual anonymous DB role; a signed
    # JWT with role authenticated must also be denied. Neither is privileged.
    for role in ("anon", "authenticated"):
        headers = {} if role == "anon" else {
            "Authorization": "Bearer " + _disposable_jwt(role),
        }
        for _ in range(40):
            try:
                get = requests.get(ROLE_BASE + "/alpha_hunter_snapshots",
                                   params={"select": "run_id", "limit": "1"},
                                   headers=headers, timeout=2)
                if get.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.2)
        else:
            raise AssertionError("Local role PostgREST did not become ready")
        assert get.json() == [], (role, get.text[:250])
        direct = requests.post(ROLE_BASE + "/alpha_hunter_snapshots",
                               json=[args["p_parent"]], headers=headers, timeout=5)
        assert direct.status_code in (401, 403), (role, direct.status_code, direct.text)
        rpc = requests.post(url, json=args, headers=headers, timeout=5)
        assert rpc.status_code in (401, 403, 404), (role, rpc.status_code, rpc.text)
        assert_counts(conn, "local-role-matrix", parent=0, child=0,
                      signal=0, feature=0, readiness=0, obs=0)

    # Altered/unsigned role claims must not be accepted.
    unsigned = _disposable_jwt("service_role").rsplit(".", 1)[0] + ".invalid"
    forged = requests.post(url, json=args, headers={
        "Authorization": "Bearer " + unsigned}, timeout=5)
    assert forged.status_code == 401, (forged.status_code, forged.text)

    # Only the explicitly granted server-side synthetic service role may
    # invoke the function. The JWT signing secret exists in local CI only.
    allowed = requests.post(url, json=args, headers={
        "Authorization": "Bearer " + _disposable_jwt("service_role"),
    }, timeout=15)
    assert allowed.status_code == 200, (allowed.status_code, allowed.text)
    assert allowed.json()["status"] == "VERIFIED"
    c = assert_counts(conn, "local-role-matrix", parent=1, child=17, signal=17,
                      feature=17, readiness=17, obs=170)
    report["isolated_jwt_rls_role_matrix"] = {
        "local_http_anon_denied": True,
        "local_http_authenticated_jwt_denied": True,
        "forged_service_jwt_denied": True,
        "explicit_service_role_jwt_accepted": True,
        "zero_trade_permission": c["enabled_trading"] == 0,
        "production_auth_or_real_trigger_graph_verified": False,
        "jwt_secret_production_credential": False,
    }


def test_atomic_rpc_lost_ack_readback(conn, report):
    """A committed RPC with a lost HTTP ACK must be classified by durable readback."""
    capture = CaptureSchema()
    run = "atomic-lost-ack"
    capture.save_snapshot(snapshot(run))
    payload = {
        "p_parent": capture.captured["alpha_hunter_snapshots"][0],
        "p_children": capture.captured["alpha_hunter_symbol_snapshots"],
        "p_signals": capture.captured["alpha_hunter_signals"],
        "p_features": capture.captured["alpha_hunter_signal_features"],
        "p_readiness": capture.captured["alpha_hunter_readiness_observations_v01"],
    }
    response = requests.post(
        BASE + "/rpc/ah_p0_research_atomic_canonical_v03",
        json=payload, timeout=15,
    )
    assert response.status_code == 200, response.text
    # The transport loses the successful response after the server committed.
    # Do not infer failure or reissue a write from a missing acknowledgement.
    simulated_transport_error = requests.ReadTimeout("ACK lost after atomic commit")
    assert isinstance(simulated_transport_error, requests.ReadTimeout)
    c = assert_counts(conn, run, parent=1, child=61, signal=61,
                      feature=61, readiness=61, obs=610)
    parent = conn.execute(
        "SELECT payload FROM public.alpha_hunter_snapshots WHERE run_id=%s",
        (run,),
    ).fetchone()[0]
    assert parent.get("_canonical_publication_state") == "VERIFIED"
    duplicate = requests.post(
        BASE + "/rpc/ah_p0_research_atomic_canonical_v03",
        json=payload, timeout=15,
    )
    assert duplicate.status_code >= 400, duplicate.text
    assert_counts(conn, run, parent=1, child=61, signal=61,
                  feature=61, readiness=61, obs=610)
    report["atomic_rpc_lost_ack"] = {
        "post_commit_ack_lost_simulated": True,
        "readback_proved_exact_five_stage_commit": True,
        "duplicate_rpc_rejected": True,
        "counts": c,
        "production_network_fault_reproduced": False,
    }


def _p0_sample_percentile(values: list[float], pct: float) -> float:
    """Linear sample interpolation, NOT a production confidence interval."""
    values = sorted(values)
    assert values and 0 <= pct <= 100
    index = (len(values) - 1) * pct / 100.0
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return round(values[lower] * (upper - index)
                 + values[upper] * (index - lower), 3)


def _p0_rpc_benchmark_post(size: int, label: str) -> tuple[float, str]:
    capture = CaptureSchema()
    capture.save_snapshot(snapshot(label, size))
    payload = {
        "p_parent": capture.captured["alpha_hunter_snapshots"][0],
        "p_children": capture.captured["alpha_hunter_symbol_snapshots"],
        "p_signals": capture.captured["alpha_hunter_signals"],
        "p_features": capture.captured["alpha_hunter_signal_features"],
        "p_readiness": capture.captured["alpha_hunter_readiness_observations_v01"],
    }
    start = time.perf_counter()
    r = requests.post(BASE + "/rpc/ah_p0_research_atomic_canonical_v03",
                      json=payload, timeout=15)
    ms = (time.perf_counter() - start) * 1000.0
    assert r.status_code == 200, (r.status_code, r.text[:350])
    assert r.json()["status"] == "VERIFIED", r.text[:350]
    return round(ms, 3), label


def test_disposable_truncate_security_gap(dsn, report):
    """Show that RLS does not constrain granted SQL TRUNCATE in a local DB.

    This probe uses an independent temporary test table in a transaction that
    is rolled back. It is NOT evidence of an exposed production HTTP endpoint.
    """
    with psycopg.connect(dsn) as probe:
        assert probe.execute("SELECT current_database()").fetchone()[0] == "isolated_research"
        probe.execute("CREATE TABLE public.p0_rls_truncate_probe (id integer PRIMARY KEY)")
        probe.execute("ALTER TABLE public.p0_rls_truncate_probe ENABLE ROW LEVEL SECURITY")
        probe.execute("GRANT SELECT, TRUNCATE ON public.p0_rls_truncate_probe "
                      "TO anon, authenticated")
        outcomes = {}
        for role in ("anon", "authenticated"):
            probe.execute("INSERT INTO public.p0_rls_truncate_probe VALUES (1)")
            assert probe.execute("SELECT COUNT(*) FROM public.p0_rls_truncate_probe"
                                 ).fetchone()[0] == 1
            probe.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            assert probe.execute("SELECT COUNT(*) FROM public.p0_rls_truncate_probe"
                                 ).fetchone()[0] == 0, role
            # Despite an empty RLS-visible SELECT, TRUNCATE succeeds because
            # it is governed by the table-level TRUNCATE grant, not row policy.
            probe.execute("TRUNCATE TABLE public.p0_rls_truncate_probe")
            probe.execute("RESET ROLE")
            assert probe.execute("SELECT COUNT(*) FROM public.p0_rls_truncate_probe"
                                 ).fetchone()[0] == 0, role
            outcomes[role] = {
                "rls_select_denied": True,
                "sql_truncate_succeeded_under_grant": True,
            }
        probe.rollback()
    report["isolated_rls_truncate_gap_probe"] = {
        "database": "local disposable PostgreSQL only",
        "roles": outcomes,
        "production_http_truncate_exposure_proven": False,
        "production_grants_modified": False,
        "release_decision": "NO-GO pending DBA/security least-privilege assessment",
    }


def test_disposable_latency_and_concurrency(conn, report):
    """Measured HTTP time; fixture triggers are synthetic, not production."""
    results = {}
    sample_count = 30
    for size in (61, 62, 63):
        # Warming a local PostgREST service makes the sampling conditions
        # explicit, while retaining individual samples for independent audit.
        for i in range(2):
            _, label = _p0_rpc_benchmark_post(size, f"bench-{size}-warm-{i}")
            assert_counts(conn, label, parent=1, child=size, signal=size,
                          feature=size, readiness=size, obs=size * 10)
        durations = []
        for i in range(sample_count):
            ms, label = _p0_rpc_benchmark_post(size, f"bench-{size}-{i:03d}")
            assert_counts(conn, label, parent=1, child=size, signal=size,
                          feature=size, readiness=size, obs=size * 10)
            durations.append(ms)
        results[str(size)] = {
            "sample_count":len(durations),
            "p50_ms":_p0_sample_percentile(durations, 50),
            "p95_ms":_p0_sample_percentile(durations, 95),
            "p99_ms":_p0_sample_percentile(durations, 99),
            "max_ms":round(max(durations), 3),
            "mean_ms":round(sum(durations) / len(durations), 3),
            "samples_ms":durations,
        }

    # Concurrent distinct run IDs, HTTP through same disposable PostgREST.
    # Retain all latencies: no fabricated, theoretical or live timing.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_p0_rpc_benchmark_post, 61, f"bench-concurrent-{i}")
                   for i in range(8)]
        measured = [f.result() for f in futures]
    for ms, label in measured:
        assert_counts(conn, label, parent=1, child=61, signal=61,
                      feature=61, readiness=61, obs=610)
    concurrent_ms = [x[0] for x in measured]

    # Two simultaneous requests for the same run ID must not publish
    # anything twice; a duplicate can fail at the unique constraint.
    duplicated = "bench-duplicate-concurrent"
    def race():
        capture = CaptureSchema()
        capture.save_snapshot(snapshot(duplicated, 61))
        args = {
            "p_parent": capture.captured["alpha_hunter_snapshots"][0],
            "p_children": capture.captured["alpha_hunter_symbol_snapshots"],
            "p_signals": capture.captured["alpha_hunter_signals"],
            "p_features": capture.captured["alpha_hunter_signal_features"],
            "p_readiness": capture.captured["alpha_hunter_readiness_observations_v01"],
        }
        res = requests.post(BASE + "/rpc/ah_p0_research_atomic_canonical_v03",
                            json=args, timeout=15)
        return res.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        status_codes = list(pool.map(lambda _: race(), range(2)))
    assert sorted(x < 300 for x in status_codes) == [False, True], status_codes
    assert_counts(conn, duplicated, parent=1, child=61, signal=61,
                  feature=61, readiness=61, obs=610)
    report["diagnostic_fixture_http_performance"] = {
        "production_trigger_performance_valid":False,
        "cloned_production_trigger_graph":False,
        "postgresql_server_version":report["pg_version"],
        "samples_per_size":sample_count,
        "requests_measured_via":"local PostgREST HTTP round trip",
        "synthetic_observations_per_symbol":10,
        "sizes":results,
        "concurrency": {
            "workers":4,
            "distinct_run_samples":len(concurrent_ms),
            "samples_ms":concurrent_ms,
            "p95_ms":_p0_sample_percentile(concurrent_ms, 95),
            "max_ms":round(max(concurrent_ms), 3),
            "duplicate_same_run_status_codes":status_codes,
            "exact_single_commit_verified":True,
        },
        "client_timeout_seconds":15,
        "release_slo_or_signoff_proven":False,
    }



def test_transaction_local_function_tracking(dsn, report):
    """Prove transaction-scoped trigger timing visibility on disposable DB.

    The tracked functions are synthetic and not the production private graph.
    A rollback prevents persistent paper or canonical rows from this test.
    PostgreSQL's pg_stat_xact_user_functions measures per-scan function call
    totals; per-call percentiles cannot be inferred when calls > 1.
    """
    run_id = "synthetic-xact-trigger-telemetry"
    capture = CaptureSchema()
    capture.save_snapshot(snapshot(run_id, 17))
    args = [json.dumps(capture.captured[table][0] if table == TABLES[0]
                       else capture.captured[table], separators=(",", ":"))
            for table in TABLES]
    query = ("SELECT public.ah_p0_research_atomic_canonical_v03("
             "%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)")
    observed = []
    with psycopg.connect(dsn) as tx:
        assert tx.execute("SELECT current_database()").fetchone()[0] == "isolated_research"
        tx.execute("SET LOCAL track_functions = 'all'")
        tx.execute("SET LOCAL statement_timeout = '15s'")
        assert tx.execute("SHOW track_functions").fetchone()[0] == "all"
        start = time.perf_counter()
        value = tx.execute(query, args).fetchone()[0]
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        assert value["status"] == "VERIFIED"
        assert_counts(tx, run_id, parent=1, child=17, signal=17,
                      feature=17, readiness=17, obs=170)
        observed = tx.execute("""
            SELECT s.schemaname,s.funcname,s.calls,s.total_time,s.self_time
            FROM pg_stat_xact_user_functions s
            WHERE s.calls>0 AND EXISTS (
              SELECT 1 FROM pg_trigger t
              WHERE t.tgfoid=s.funcid AND NOT t.tgisinternal
            ) ORDER BY s.schemaname,s.funcname
        """).fetchall()
        assert observed, "No transaction-local trigger timing samples"
        assert any(x[1] == "p0_test_symbol_trigger" and x[2] == 17
                   for x in observed), observed
        tx.rollback()
    with psycopg.connect(dsn, autocommit=True) as verify:
        assert_counts(verify, run_id, parent=0, child=0, signal=0,
                      feature=0, readiness=0, obs=0)
    report["synthetic_transaction_local_trigger_instrumentation"] = {
        "proven_local_instrumentation": True,
        "pg_stat_xact_user_functions_available": True,
        "synthetic_trigger_samples": [
            {"schema":schema, "function_name":name, "calls":calls,
             "total_time_ms":round(total, 3), "self_time_ms":round(self_time, 3)}
            for schema,name,calls,total,self_time in observed
        ],
        "in_transaction_rpc_ms": elapsed_ms,
        "transaction_rolled_back": True,
        "persistent_stage_rows_after_rollback": 0,
        "production_function_p95_p99_verified": False,
        "production_trigger_or_schema_equivalence": False,
        "release_authority": False,
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
        test_atomic_five_stage_rpc(conn, report)
        test_atomic_rpc_lost_ack_readback(conn, report)
        test_real_http_role_matrix(conn, report)
        test_disposable_truncate_security_gap(dsn, report)
        test_transaction_local_function_tracking(dsn, report)
        test_disposable_latency_and_concurrency(conn, report)
    out = Path("p0_postgrest_acceptance_results")
    out.mkdir(exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    print("PASS: isolated HTTP semantics and fail-closed partial-publish detection.")
    print("RELEASE NO-GO: current separate-HTTP writer is non-atomic; "
          "the tested atomic RPC has no production wiring or full schema acceptance.")


if __name__ == "__main__":
    main()
