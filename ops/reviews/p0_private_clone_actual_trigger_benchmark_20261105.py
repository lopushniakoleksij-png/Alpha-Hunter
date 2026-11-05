"""Independent DBA-only exact-clone trigger benchmark. Never targets production.

Requires a separately reconstructed and fingerprint-matched PRIVATE PostgreSQL
17 clone on loopback, egress disabled, sanitized datasets outside the repo.
Runs the v03 candidate RPC in a transaction, reads actual transaction-local
trigger statistics, and ROLLS BACK every sample. No human sign-off implied.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import time
from collections import defaultdict
from pathlib import Path

import psycopg
from psycopg import sql

from p0_verify_isolated_production_catalog_clone_20261105 import (
    isolated_connection,
    run as fingerprint_run,
    validate_isolated_dsn,
)

SIZES = (61, 62, 63)
GROUPS = ("p_parent", "p_children", "p_signals", "p_features", "p_readiness")
STAGES = (
    "alpha_hunter_snapshots",
    "alpha_hunter_symbol_snapshots",
    "alpha_hunter_signals",
    "alpha_hunter_signal_features",
    "alpha_hunter_readiness_observations_v01",
)
PAPER = ("alpha_hunter_paper_orders_v01", "alpha_hunter_calibrated_paper_orders_v01")
RPC_SIGNATURE = "public.ah_p0_research_atomic_canonical_v03(jsonb,jsonb,jsonb,jsonb,jsonb)"
CLONE_MARKER = "P0_PRIVATE_DISPOSABLE_CLONE_EGRESS_DISABLED"


def require(condition, message):
    """Runtime safety guard unaffected by python -O optimisation."""
    if not condition:
        raise RuntimeError(message)


def percentile(values, percentage):
    if not values or not 0 <= percentage <= 100:
        raise ValueError("Invalid percentile inputs")
    a = sorted(float(x) for x in values)
    pos = (len(a) - 1) * percentage / 100
    lo = int(pos)
    hi = min(lo + 1, len(a) - 1)
    return round(a[lo] * (hi - pos) + a[hi] * (pos - lo), 3)


def private_dir(value, *, require_permissions=False):
    if not value:
        raise RuntimeError("DBA private path missing")
    path = Path(value).expanduser()
    if not path.is_dir() or path.is_symlink():
        raise RuntimeError("DBA private directory absent or a symlink")
    path = path.resolve(strict=True)
    if path == Path.cwd().resolve() or Path.cwd().resolve() in path.parents:
        raise RuntimeError("Private evidence must never be inside the public repository")
    if require_permissions and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError("DBA private directory permissions too broad")
    return path


def validate_fixture(data, size):
    if not isinstance(data, dict) or set(data) != set(GROUPS):
        raise RuntimeError("Private fixture has invalid five-stage shape")
    parent = data["p_parent"]
    if not isinstance(parent, dict) or not isinstance(parent.get("payload"), dict):
        raise RuntimeError("Invalid canonical parent")
    run_id = parent.get("run_id")
    if (not isinstance(run_id, str) or len(run_id) < 8
            or parent["payload"].get("run_id") != run_id
            or parent.get("symbol_count") != size):
        raise RuntimeError("Invalid fixture run identity or count")
    if parent["payload"].get("_canonical_publication_state") is not None:
        raise RuntimeError("Fixture must not be pre-marked verified")
    seen = []
    for group in GROUPS[1:]:
        batch = data[group]
        if not isinstance(batch, list) or len(batch) != size:
            raise RuntimeError("Invalid fixture group cardinality")
        symbols = []
        for item in batch:
            if (not isinstance(item, dict) or item.get("run_id") != run_id
                    or item.get("trade_permission") is not False
                    or not isinstance(item.get("symbol"), str)):
                raise RuntimeError("Invalid fixture symbol or paper-only flag")
            symbols.append(item["symbol"])
        if len(set(symbols)) != size:
            raise RuntimeError("Duplicate fixture symbols")
        seen.append(set(symbols))
    if any(x != seen[0] for x in seen[1:]):
        raise RuntimeError("Fixture stage symbol sets differ")
    signal_ids = [
        [entry.get("signal_id") for entry in data[group]]
        for group in ("p_signals", "p_features")
    ]
    if any(not isinstance(value, str) or not value.strip()
           for group in signal_ids for value in group):
        raise RuntimeError("Missing or empty fixture signal_id")
    if (len(set(signal_ids[0])) != size
            or len(set(signal_ids[1])) != size
            or set(signal_ids[0]) != set(signal_ids[1])):
        raise RuntimeError("Fixture signal IDs duplicated or stages differ")
    return run_id


def load_private_fixtures(folder):
    all_data = {}
    for size in SIZES:
        path = folder / f"sanitized_{size}.json"
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Missing or symlinked private fixture")
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise RuntimeError("Private fixture must have mode 0600")
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_fixture(data, size)
        all_data[size] = data
    if len({v["p_parent"]["run_id"] for v in all_data.values()}) != 3:
        raise RuntimeError("Independent fixture run IDs must be unique")
    return all_data


def gate():
    if (os.getenv("AH_P0_PRIVATE_CLONE_APPROVED") != "1"
            or os.getenv("AH_P0_EGRESS_BLOCKED") != "1"
            or os.getenv("AH_P0_LOCAL_POSTGREST_ONLY") != "1"):
        raise RuntimeError("DBA approval and egress-isolation attestations required")
    if any(os.getenv(x) for x in (
        "DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
        "BITGET_API_KEY", "BITGET_SECRET_KEY", "RENDER_API_KEY",
    )):
        raise RuntimeError("Live service credentials are forbidden")
    params = validate_isolated_dsn(os.getenv("AH_P0_PG_DSN", ""))
    # Existing verifier checks inherited libpq PG* overrides and PG17 identity.
    fixtures = private_dir(os.getenv("AH_P0_PRIVATE_FIXTURES_DIR"), require_permissions=True)
    evidence = private_dir(os.getenv("AH_P0_PRIVATE_EVIDENCE_DIR"), require_permissions=True)
    if fixtures == evidence:
        raise RuntimeError("Fixtures and output must use distinct private directories")
    return params,fixtures,evidence


def field_names(conn, schema, table):
    return {r[0] for r in conn.execute("""
        SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND c.relname=%s
          AND a.attnum>0 AND NOT a.attisdropped
    """,(schema,table)).fetchall()}


def traced_rows(conn, schema, table, run_id, signal_ids):
    fields = field_names(conn,schema,table)
    q = sql.SQL("SELECT count(*) FROM {}.{} WHERE {}").format(
        sql.Identifier(schema), sql.Identifier(table),
        sql.SQL("run_id=%s" if "run_id" in fields else "signal_id = ANY(%s)"))
    if "run_id" in fields:
        params = (run_id,)
    elif "signal_id" in fields:
        params = (signal_ids,)
    else:
        raise RuntimeError("Cannot trace table to fixture without run_id/signal_id: "
                           + schema + "." + table)
    return conn.execute(q,params).fetchone()[0]


def check_clone_preflight(conn, fixtures):
    require(conn.execute("SHOW session_replication_role").fetchone()[0] == "origin",
            "Clone trigger replication mode disabled")
    require(conn.execute("SELECT current_database()").fetchone()[0] == "isolated_research",
            "Clone database identity changed")
    major = int(conn.execute("SHOW server_version_num").fetchone()[0])
    if not 170000 <= major < 180000:
        raise RuntimeError("DBA benchmark requires PostgreSQL major version 17")
    # The clone-only sentinel must be created by the DBA *after* restore.
    # Never import this marker into production or any external database.
    if conn.execute("SELECT to_regclass('ah_p0_isolated.clone_attestation')"
                    ).fetchone()[0] is None:
        raise RuntimeError("Disposable clone-only schema sentinel absent")
    ready = conn.execute(
        "SELECT EXISTS(SELECT 1 FROM ah_p0_isolated.clone_attestation "
        "WHERE marker=%s)",(CLONE_MARKER,)).fetchone()[0]
    if ready is not True:
        raise RuntimeError("Disposable clone is not explicitly attested")
    require(conn.execute("SELECT to_regprocedure(%s)",(RPC_SIGNATURE,)).fetchone()[0] is not None,
            "Required candidate RPC not installed in isolated clone")
    # Refuse a tiny empty fixture as evidence for a production-volume workload.
    samples = dict(conn.execute("""
        SELECT c.relname,c.reltuples::bigint
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname IN (
            'alpha_hunter_symbol_snapshots','alpha_hunter_strategy_observations_v01')
    """).fetchall())
    if samples.get("alpha_hunter_symbol_snapshots",0) < 150000 or samples.get(
            "alpha_hunter_strategy_observations_v01",0) < 1000000:
        raise RuntimeError("Representative clone statistics/volume are absent")
    for size,data in fixtures.items():
        run_id = data["p_parent"]["run_id"]
        ids = [v["signal_id"] for v in data["p_signals"]]
        for table in STAGES:
            if traced_rows(conn,"public",table,run_id,ids) != 0:
                raise RuntimeError("Private fixture run already exists; refuse mutation")
        for table in PAPER:
            if traced_rows(conn,"private",table,run_id,ids) != 0:
                raise RuntimeError("Private paper-order fixture already exists")
    return samples


def one_run(params, data, size):
    run_id = data["p_parent"]["run_id"]
    ids = [x["signal_id"] for x in data["p_signals"]]
    observed = {}
    with psycopg.connect(**params) as conn:
        conn.execute("SET LOCAL statement_timeout = '15s'")
        conn.execute("SET LOCAL track_functions = 'all'")
        require(conn.execute("SHOW session_replication_role").fetchone()[0] == "origin",
                "Trigger execution disabled or altered in DBA sample")
        require(conn.execute("SHOW track_functions").fetchone()[0] == "all",
                "Trigger function measurement disabled")
        for table in PAPER:
            require(traced_rows(conn,"private",table,run_id,ids) == 0,
                    "Preexisting paper-order rows; refusing DBA sample: " + table)
        args = [json.dumps(data[x],separators=(",", ":")) for x in GROUPS]
        ts = time.perf_counter()
        result = conn.execute(
            "SELECT public.ah_p0_research_atomic_canonical_v03("
            "%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)",args
        ).fetchone()[0]
        ms = round((time.perf_counter()-ts)*1000,3)
        require(isinstance(result,dict) and result.get("status") == "VERIFIED",
                "Atomic candidate RPC failed or returned invalid status")
        require(result.get("run_id") == run_id
                and result.get("child_count") == size
                and result.get("feature_count") == size,
                "Atomic candidate RPC identity/count response mismatch")
        # Capture trigger timings immediately after the RPC and BEFORE
        # follow-up stage readback queries, avoiding readback contamination.
        stats = conn.execute("""
            SELECT s.schemaname,s.funcname,s.calls,s.total_time,s.self_time
            FROM pg_stat_xact_user_functions s
            WHERE s.calls>0 AND EXISTS (
              SELECT 1 FROM pg_trigger t
              WHERE NOT t.tgisinternal AND t.tgfoid=s.funcid
            )
        """).fetchall()
        if not stats or not any(x[0]=="private" for x in stats):
            raise RuntimeError("No instrumented private trigger function calls")
        for table in STAGES:
            require(traced_rows(conn,"public",table,run_id,ids) == (
                1 if table == STAGES[0] else size
            ), "Unexpected canonical stage count: " + table)
        private_counts = {
            table:traced_rows(conn,"private",table,run_id,ids) for table in PAPER
        }
        for table in STAGES[1:]:
            enabled = conn.execute(
                sql.SQL("SELECT count(*) FROM public.{} "
                        "WHERE run_id=%s AND trade_permission=true").format(
                    sql.Identifier(table)), (run_id,)
            ).fetchone()[0]
            require(enabled == 0, "Trade permission unexpectedly enabled: " + table)
        observed = {
            "sql_roundtrip_ms":ms,
            "private_paper_rows":private_counts,
            "trigger_functions":{
                schema+"."+name:{
                    "calls":int(calls),"total_ms":round(float(total),3),
                    "self_ms":round(float(self_t),3)}
                for schema,name,calls,total,self_t in stats
            },
        }
        conn.rollback()
    # Independent transaction: verify nothing has persisted.
    with psycopg.connect(**params, autocommit=True) as check:
        for table in STAGES:
            require(traced_rows(check,"public",table,run_id,ids) == 0,
                    "Rollback left canonical rows: " + table)
        for table in PAPER:
            require(traced_rows(check,"private",table,run_id,ids) == 0,
                    "Rollback left paper-order rows: " + table)
    return observed


def measure(params, fixtures, evidence, stats):
    report = {
        "result":"DIAGNOSTIC_ONLY_PRODUCTION_NO_GO",
        "mode":"DBA_PRIVATE_PG17_EXACT_CATALOG_FINGERPRINT_REQUIRED",
        "selected_catalog_fingerprint_match_only":True,
        "entire_public_private_schema_equivalence_verified":False,
        "authenticated_gateway_security_review_approved":False,
        "network_egress_isolated_attested_not_technically_proven":True,
        "full_runtime_dynamic_trigger_graph_verified":False,
        "physical_executed_trade_authority":False,
        "side_effects_outside_transaction_excluded":False,
        "clone_row_estimates":stats,
        "sample_count_each_size":30,
        "p99_estimate_low_sample_confidence":True,
        "schema_catalog_drift_check_is_partial":True,
        "sizes":{},
    }
    for size in SIZES:
        # warm-ups are discarded and individually rolled back.
        for _ in range(2):
            one_run(params,fixtures[size],size)
        values = [one_run(params,fixtures[size],size) for _ in range(30)]
        latency = [v["sql_roundtrip_ms"] for v in values]
        function_names = set().union(*(v["trigger_functions"] for v in values))
        by_function = {}
        for name in sorted(function_names):
            if any(name not in v["trigger_functions"] for v in values):
                raise RuntimeError("Trigger call coverage drift across identical inputs: "+name)
            per_scan_ms = [v["trigger_functions"][name]["self_ms"] for v in values]
            calls = [v["trigger_functions"][name]["calls"] for v in values]
            by_function[name] = {
                "calls_min":min(calls),"calls_max":max(calls),
                "per_scan_self_ms_p50":percentile(per_scan_ms,50),
                "per_scan_self_ms_p95":percentile(per_scan_ms,95),
                "per_scan_self_ms_p99":percentile(per_scan_ms,99),
                "per_invocation_percentiles_proven":False,
            }
        report["sizes"][str(size)] = {
            "rpc_sql_roundtrip_ms_p50":percentile(latency,50),
            "rpc_sql_roundtrip_ms_p95":percentile(latency,95),
            "rpc_sql_roundtrip_ms_p99":percentile(latency,99),
            "max_ms":round(max(latency),3),
            "paper_order_rows_min_max":{
                t:[min(v["private_paper_rows"][t] for v in values),
                   max(v["private_paper_rows"][t] for v in values)] for t in PAPER
            },
            "nested_trigger_stats_by_function":by_function,
            "database_transactions_rolled_back":32,
            "post_rollback_persistent_rows":0,
        }
    # Sanitized metric-only artifact; no private SQL, original run IDs or records.
    output = evidence/"p0_exact_clone_private_metrics.json"
    if output.is_symlink():
        raise RuntimeError("Refusing symlink evidence output")
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    output.chmod(0o600)
    return report


def main():
    params,folder,out = gate()
    fixtures = load_private_fixtures(folder)
    # Existing verifier is deliberately strict and checks fingerprints from
    # BOTH public and private; false-positive acceptance is a critical failure.
    if fingerprint_run() != 0:
        raise RuntimeError("Exact PG17 catalog fingerprint mismatch. NO-GO")
    with isolated_connection() as readonly:
        sizes = check_clone_preflight(readonly,fixtures)
        readonly.rollback()
    report = measure(params,fixtures,out,sizes)
    print(json.dumps({
        "status":report["result"],
        "pg17_clone_metrics_saved_privately":True,
        "real_production_runtime_or_independent_signoff_proven":False,
        "release_decision":"PRODUCTION NO-GO",
    },sort_keys=True))


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status":"BLOCKED","exception_type":type(exc).__name__,
                          "release_decision":"PRODUCTION NO-GO"},sort_keys=True))
        sys.exit(2)
