"""Read-only P0 production catalog custody check on an isolated DBA-supplied clone.

Never connects to production, never executes DML/DDL, never loads real keys.
Checks first-order production SHA256 catalog fingerprint only. Successful
execution is NOT independent DBA/security approval or full dependency closure.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

MANIFEST = Path("ops/reviews/p0_readonly_production_fingerprints_20261105.json")
CANDIDATES = Path("ops/reviews/p0_production_trigger_dependency_candidates_20261105.json")
CROSS_SCHEMA = Path("ops/reviews/p0_cross_schema_write_candidate_graph_20261105.json")
FORBIDDEN = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
             "RENDER_API_KEY", "BITGET_API_KEY", "BITGET_SECRET_KEY")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_isolated_dsn(dsn: str) -> dict:
    """Reject remote targets and libpq connection indirection before connecting."""
    try:
        params = conninfo_to_dict(dsn)
    except Exception as exc:
        raise RuntimeError("Invalid isolated connection configuration") from exc
    allowed = {"host", "port", "dbname", "user", "password", "connect_timeout"}
    if set(params) - allowed:
        raise RuntimeError("Unexpected connection parameter in isolated DSN")
    if params.get("host") != "127.0.0.1" or params.get("dbname") != "isolated_research":
        raise RuntimeError("Only explicit localhost isolated_research is allowed")
    if params.get("port", "5432") != "5432":
        raise RuntimeError("Unexpected isolated PostgreSQL port")
    return params


# Read-only catalog inventory recorded from production PostgreSQL 17.6
# on 2026-11-05. Exact counts are deliberately fail-closed on any drift.
# Counts are a coverage floor, NOT evidence of matching objects or runtime.
EXPECTED_INVENTORY = {
    "public": {"relations": 282, "tables": 128, "views": 154, "enabled_hooks": 131},
    "private": {"relations": 47, "tables": 34, "views": 13, "enabled_hooks": 0},
}


def inventory_failures(actual):
    """Reject incomplete restore or unreviewed drift across public/private."""
    issues = []
    if set(actual) != set(EXPECTED_INVENTORY):
        issues.append("full alpha_hunter schema inventory missing or unexpected schema")
    for namespace, wanted in EXPECTED_INVENTORY.items():
        present = actual.get(namespace, {})
        for field, value in wanted.items():
            if present.get(field) != value:
                issues.append(
                    "alpha_hunter inventory mismatch: "
                    + namespace + "." + field + " expected=" + str(value)
                    + " actual=" + str(present.get(field)))
    return issues


def isolated_connection():
    if os.environ.get("AH_P0_LOCAL_POSTGREST_ONLY") != "1":
        raise RuntimeError("Refusing non-isolated catalog inspection")
    if any(os.environ.get(key) for key in FORBIDDEN):
        raise RuntimeError("Real cloud or exchange credentials are forbidden")
    # Libpq can silently inherit PGHOST/PGSERVICE/PGOPTIONS and similar values.
    # Explicitly reject these rather than trusting textual DSN substrings.
    if any(os.environ.get(key) for key in os.environ if key.startswith("PG")
           and key not in {"AH_P0_PG_DSN"}):
        raise RuntimeError("Inherited libpq environment configuration is forbidden")
    params = validate_isolated_dsn(os.environ.get("AH_P0_PG_DSN", ""))
    connection = psycopg.connect(**params)
    connection.execute("SET TRANSACTION READ ONLY")
    if connection.execute("SELECT current_database()").fetchone()[0] != "isolated_research":
        raise RuntimeError("Unexpected database")
    version = int(connection.execute("SHOW server_version_num").fetchone()[0])
    if not 170000 <= version < 180000:
        raise RuntimeError("Exact catalog fingerprint requires PostgreSQL major version 17")
    return connection


def run():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    issues = []
    with isolated_connection() as conn:
        # A candidate-only restore is dangerous: it could match selected
        # trigger hashes while omitting many other Alpha Hunter objects.
        # Inventory covers ALL alpha_hunter_ relations in public and private.
        inventory_rows = conn.execute("""
            SELECT n.nspname,
                   COUNT(*)::integer AS total,
                   COUNT(*) FILTER (WHERE c.relkind IN ('r','p'))::integer AS tables,
                   COUNT(*) FILTER (WHERE c.relkind='v')::integer AS views,
                   (SELECT COUNT(*)::integer FROM pg_trigger t
                     JOIN pg_class c2 ON c2.oid=t.tgrelid
                     JOIN pg_namespace n2 ON n2.oid=c2.relnamespace
                     WHERE NOT t.tgisinternal AND t.tgenabled IN ('O','A')
                       AND n2.nspname=n.nspname
                       AND c2.relname LIKE 'alpha_hunter_%') AS enabled_hooks
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('public','private')
              AND c.relname LIKE 'alpha_hunter_%'
              AND c.relkind IN ('r','p','v','m')
            GROUP BY n.nspname
        """).fetchall()
        observed_inventory = {
            namespace: {"relations":total,"tables":tables,"views":views,
                        "enabled_hooks":hooks}
            for namespace,total,tables,views,hooks in inventory_rows
        }
        issues.extend(inventory_failures(observed_inventory))
        rows = conn.execute("""
            SELECT c.relname,
                   count(*)::integer AS ncols,
                   string_agg(
                     a.attname||':'||format_type(a.atttypid,a.atttypmod)
                     ||':'||a.attnotnull||':'||
                     coalesce(pg_get_expr(d.adbin,d.adrelid),''),
                     ';' ORDER BY a.attnum)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname='public' AND a.attnum > 0 AND NOT a.attisdropped
              AND c.relname = ANY(%s)
            GROUP BY c.relname
        """, ([x["table"] for x in expected["canonical_tables"]],)).fetchall()
        columns = {name: (n, sha256(signature)) for name, n, signature in rows}
        indexes = dict(conn.execute("""
            SELECT c.relname,
                   string_agg(pg_get_indexdef(i.indexrelid),';'
                              ORDER BY pg_get_indexdef(i.indexrelid))
            FROM pg_index i
            JOIN pg_class c ON c.oid=i.indrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname = ANY(%s)
            GROUP BY c.relname
        """, ([x["table"] for x in expected["canonical_tables"]],)).fetchall())
        idx_counts = dict(conn.execute("""
            SELECT c.relname,count(*)::integer
            FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname = ANY(%s)
            GROUP BY c.relname
        """, ([x["table"] for x in expected["canonical_tables"]],)).fetchall())
        perms = dict(conn.execute("""
            SELECT c.relname, (c.relrowsecurity,
                   (SELECT count(*)::integer FROM pg_policies pol
                    WHERE pol.schemaname='public' AND pol.tablename=c.relname))
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname = ANY(%s)
        """, ([x["table"] for x in expected["canonical_tables"]],)).fetchall())
        for t in expected["canonical_tables"]:
            name = t["table"]
            if columns.get(name) != (t["column_count"], t["columns_sha256"]):
                issues.append("column fingerprint drift: " + name)
            if sha256(indexes.get(name, "")) != t["indexes_sha256"] \
               or idx_counts.get(name) != t["index_count"]:
                issues.append("index fingerprint drift: " + name)
            if perms.get(name) != (t["rls_enabled"], t["policy_count"]):
                issues.append("RLS/policy drift: " + name)

        rows = conn.execute("""
            SELECT c.relname,t.tgname,nf.nspname||'.'||p.proname,
                   pg_get_triggerdef(t.oid,true),pg_get_functiondef(p.oid),
                   t.tgenabled
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_proc p ON p.oid=t.tgfoid
            JOIN pg_namespace nf ON nf.oid=p.pronamespace
            WHERE NOT t.tgisinternal AND n.nspname='public'
              AND c.relname = ANY(%s)
        """, (list(set(x["table"] for x in expected["first_order_triggers"])),)).fetchall()
        actual = {(table,trigger): (fn,sha256(definition),sha256(body),enabled)
                  for table,trigger,fn,definition,body,enabled in rows}
        expected_ids = {(t["table"], t["trigger"])
                        for t in expected["first_order_triggers"]}
        if set(actual) != expected_ids:
            issues.append("first-order trigger membership drift")
        for t in expected["first_order_triggers"]:
            key = (t["table"],t["trigger"])
            observed = actual.get(key)
            wanted = (t["function_name"],t["trigger_sha256"],
                      t["function_sha256"],"O")
            if observed != wanted:
                issues.append("trigger/function fingerprint drift: " + t["trigger"])
        # Additional metadata-only custody check for the broader candidate
        # trigger closure. This DOES NOT execute the trigger bodies.
        graph = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        names = [t["name"] for t in graph["relations"]]
        rows = conn.execute("""
            SELECT c.relname,c.relrowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname = ANY(%s)
        """, (names,)).fetchall()
        actual_relations = dict(rows)
        if len(actual_relations) != len(graph["relations"]):
            issues.append("candidate graph relation membership drift")
        for expected_rel in graph["relations"]:
            if actual_relations.get(expected_rel["name"]) != expected_rel["rls_enabled"]:
                issues.append("candidate graph RLS drift: " + expected_rel["name"])
        rows = conn.execute("""
            SELECT c.relname, t.tgname, nf.nspname||'.'||p.proname,
                   t.tgtype::integer, t.tgenabled, p.prosecdef,
                   pg_get_functiondef(p.oid)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_proc p ON p.oid=t.tgfoid
            JOIN pg_namespace nf ON nf.oid=p.pronamespace
            WHERE NOT t.tgisinternal AND n.nspname='public'
              AND t.tgenabled IN ('O','A') AND c.relname = ANY(%s)
        """, (names,)).fetchall()
        actual_hooks = {}
        for tbl,tg,fn,bits,enabled,definer,body in rows:
            events = ("I" if bits & 4 else "") + ("U" if bits & 16 else "")                      + ("D" if bits & 8 else "")
            actual_hooks[(tbl,tg)] = (fn, events, enabled, definer,
                                      hashlib.md5(body.encode("utf-8")).hexdigest())
        expected_hooks = {(x["table"],x["trigger"]): (
            x["function_name"],x["events"],x["enabled"],
            x["security_definer"],x["function_md5"])
            for x in graph["trigger_metadata"]}
        if set(actual_hooks) != set(expected_hooks):
            issues.append("candidate graph enabled trigger membership drift")
        for (tbl,tg), wanted in expected_hooks.items():
            if actual_hooks.get((tbl,tg)) != wanted:
                issues.append("candidate graph trigger signature drift: " + tbl + "." + tg)
        # CROSS-SCHEMA candidate audit: the earlier lexical-only graph excluded
        # private.* paper-order destinations. Compare both public and private
        # objects, but NEVER claim executed DML / network permissions parity.
        cross = json.loads(CROSS_SCHEMA.read_text(encoding="utf-8"))
        qualified_names = [x["qualified_name"] for x in cross["relations"]]
        actual_cross_relations = dict(conn.execute("""
            SELECT n.nspname||'.'||c.relname, c.relrowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('public','private')
              AND n.nspname||'.'||c.relname = ANY(%s)
        """, (qualified_names,)).fetchall())
        for expected_rel in cross["relations"]:
            n = expected_rel["qualified_name"]
            if actual_cross_relations.get(n) != expected_rel["rls"]:
                issues.append("cross-schema candidate RLS/object drift: " + n)
        if len(actual_cross_relations) != len(cross["relations"]):
            issues.append("cross-schema candidate relation count drift")
        records = conn.execute("""
            SELECT n.nspname||'.'||c.relname, t.tgname,
                   nf.nspname||'.'||p.proname, t.tgtype::integer,
                   p.prosecdef, pg_get_functiondef(p.oid)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_proc p ON p.oid=t.tgfoid
            JOIN pg_namespace nf ON nf.oid=p.pronamespace
            WHERE NOT t.tgisinternal AND t.tgenabled IN ('O','A')
              AND n.nspname IN ('public','private')
              AND n.nspname||'.'||c.relname = ANY(%s)
        """, (qualified_names,)).fetchall()
        actual_cross_hooks = {}
        for tbl,tg,fn,bits,definer,body in records:
            events = ("I" if bits & 4 else "") + ("U" if bits & 16 else "") \
                     + ("D" if bits & 8 else "")
            actual_cross_hooks[(tbl,tg)] = (
                fn,events,definer,
                hashlib.md5(body.encode("utf-8")).hexdigest())
        expected_cross_hooks = {
            (v["source_table"],v["trigger"]): (
                v["function_name"],v["events"],v["security_definer"],v["function_md5"])
            for v in cross["reachable_hooks"]
        }
        if set(actual_cross_hooks) != set(expected_cross_hooks):
            issues.append("cross-schema candidate trigger membership drift")
        for (tbl,tg),wanted in expected_cross_hooks.items():
            if actual_cross_hooks.get((tbl,tg)) != wanted:
                issues.append("cross-schema candidate trigger drift: " + tbl + "." + tg)
    status = "CATALOG_FINGERPRINT_MATCH_ONLY" if not issues else "CATALOG_MISMATCH_NO_GO"
    print(json.dumps({
        "status":status,
        "clone_pg17_only":True,
        "schema_first_order_fingerprints":len(expected["canonical_tables"]),
        "trigger_first_order_fingerprints":len(expected["first_order_triggers"]),
        "inventory_complete_count_only":not inventory_failures(observed_inventory),
        "inventory_scope_counts":observed_inventory,
        "inventory_objects_exact_identity_verified":False,
        "candidate_relation_count":len(graph["relations"]),
        "candidate_trigger_count":len(graph["trigger_metadata"]),
        "candidate_trigger_signatures_match":not issues,
        "candidate_edges_executable_verified":False,
        "cross_schema_candidate_relation_count":len(cross["relations"]),
        "cross_schema_candidate_private_relations":sum(
            x["qualified_name"].startswith("private.") for x in cross["relations"]),
        "cross_schema_candidate_trigger_count":len(cross["reachable_hooks"]),
        "cross_schema_executable_graph_verified":False,
        "issues":issues,
        "transitive_production_graph_verified":False,
        "real_workload_performance_verified":False,
        "real_production_authentication_verified":False,
        "independent_DBA_security_approval":False,
        "release_decision":"PRODUCTION NO-GO",
    },sort_keys=True))
    return 0 if not issues else 2


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:
        print(json.dumps({"status":"BLOCKED", "error_type":type(exc).__name__,
                          "release_decision":"PRODUCTION NO-GO"}))
        sys.exit(2)
