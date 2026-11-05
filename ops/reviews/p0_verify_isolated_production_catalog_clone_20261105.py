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

MANIFEST = Path("ops/reviews/p0_readonly_production_fingerprints_20261105.json")
FORBIDDEN = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
             "RENDER_API_KEY", "BITGET_API_KEY", "BITGET_SECRET_KEY")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def isolated_connection():
    if os.environ.get("AH_P0_LOCAL_POSTGREST_ONLY") != "1":
        raise RuntimeError("Refusing non-isolated catalog inspection")
    if any(os.environ.get(key) for key in FORBIDDEN):
        raise RuntimeError("Real cloud or exchange credentials are forbidden")
    dsn = os.environ.get("AH_P0_PG_DSN", "")
    if "host=127.0.0.1" not in dsn or "dbname=isolated_research" not in dsn:
        raise RuntimeError("Only approved localhost isolated_research is allowed")
    connection = psycopg.connect(dsn)
    if connection.execute("SELECT current_database()").fetchone()[0] != "isolated_research":
        raise RuntimeError("Unexpected database")
    if int(connection.execute("SHOW server_version_num").fetchone()[0]) < 170000:
        raise RuntimeError("This exact production fingerprint was taken on PostgreSQL 17")
    connection.execute("SET TRANSACTION READ ONLY")
    return connection


def run():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    issues = []
    with isolated_connection() as conn:
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
    status = "FIRST_ORDER_MATCH_ONLY" if not issues else "FIRST_ORDER_MISMATCH_NO_GO"
    print(json.dumps({
        "status":status,
        "clone_pg17_only":True,
        "schema_first_order_fingerprints":len(expected["canonical_tables"]),
        "trigger_first_order_fingerprints":len(expected["first_order_triggers"]),
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
