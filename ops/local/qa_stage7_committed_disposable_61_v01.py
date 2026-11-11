#!/usr/bin/env python3
"""Stage 7 disposable committed persistence and retry probe.
ONLY in existing private Codespace + network-isolated QA PostgreSQL 17.
The reference is copied into an empty DB excluding pg_cron (single-DB extension)
and its scoped access-grant event trigger; only that disposable copy receives
durable synthetic writes. Never production. Cron callbacks OUTSIDE this probe.
One commit/retry does NOT establish p95/p99 or full end-to-end readiness.
"""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

N = "alpha-hunter-private-postgres17-qa"
BASE = "ah_authentic_schema_20261110"
BRANCH = "fix/supabase-write-timeout-qa"
P = Path.home() / ".alpha-hunter-private-dbqa/bench-fixtures/61.json"
K = ("p_parent", "p_children", "p_signals", "p_features", "p_readiness")
T = ("alpha_hunter_snapshots", "alpha_hunter_symbol_snapshots",
     "alpha_hunter_signals", "alpha_hunter_signal_features",
     "alpha_hunter_readiness_observations_v01")
EXPECTED = (1, 61, 7, 7, 61)
SIDE = ("private.alpha_hunter_snapshot_slim_v01",
        "public.alpha_hunter_account_ledger_materialization_events",
        "public.alpha_hunter_account_state_snapshots")

class Stop(Exception):
    pass

def run(args, payload=None, timeout=45):
    r = subprocess.run(args, input=payload, text=True, capture_output=True,
                       timeout=timeout)
    if r.returncode:
        error = next((s.strip() for s in r.stderr.splitlines()
                      if "ERROR:" in s or "FATAL:" in s), "")
        raise Stop("local QA command failed: " + error[:180])
    return r.stdout.strip()

def sql(db, q, role="postgres", timeout=45):
    assert role in ("postgres", "supabase_admin")
    return run(["docker", "exec", "-i", N, "psql", "-XqAt",
                "-v", "ON_ERROR_STOP=1", "-U", role, "-d", db],
               q, timeout)

def counts(db, rid):
    q = "SELECT " + " || ',' || ".join(
        f"(SELECT count(*)::text FROM public.{t} WHERE run_id='{rid}')"
        for t in T)
    return tuple(int(v) for v in sql(db, q).split(","))

def downstream(db, rid):
    out = {}
    for qualified in SIDE:
        schema, table = qualified.split(".")
        if sql(db, f"SELECT to_regclass('{qualified}') IS NOT NULL") != "t":
            raise Stop("missing expected QA side-effect table " + qualified)
        has_run_id = sql(db, f"SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='{schema}' AND table_name='{table}' AND column_name='run_id')") == "t"
        clause = f" WHERE run_id='{rid}'" if has_run_id else ""
        out[qualified] = int(sql(db, f"SELECT count(*) FROM {qualified}{clause}"))
    return out

def guard():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Stop("private Codespace required")
    if run(["git", "branch", "--show-current"]) != BRANCH:
        raise Stop("wrong branch")
    if run(["docker", "inspect", "-f",
            "{{.State.Running}}|{{.HostConfig.NetworkMode}}", N]) != "true|none":
        raise Stop("QA container must be running with network=none")
    ident = sql(BASE, "SELECT current_database()||'|'||current_user||'|'||current_setting('server_version_num')")
    if not re.fullmatch(re.escape(BASE) + r"\|postgres\|17\d{4}", ident):
        raise Stop("wrong source database identity")
    if not P.is_file() or P.is_symlink() or P.stat().st_mode & 0o777 != 0o600:
        raise Stop("private fixture absent or insecure")
    d = json.loads(P.read_text())
    if d.get("synthetic_only") is not True or any(not isinstance(d.get(k), list) for k in K):
        raise Stop("invalid synthetic-only fixture")
    if tuple(len(d[k]) for k in K) != EXPECTED:
        raise Stop("wrong fixture family counts")
    if any(not isinstance(row, dict) for k in K for row in d[k]):
        raise Stop("invalid fixture rows")
    rid = d["p_parent"][0].get("run_id")
    if not isinstance(rid, str) or not re.fullmatch(r"QA_ISOLATED_[a-f0-9]{16}", rid):
        raise Stop("unexpected run_id")
    if d["p_parent"][0].get("symbol_count") != 61:
        raise Stop("unexpected symbol count")
    if any(row.get("run_id") != rid or row.get("trade_permission") is True
           for k in K for row in d[k]):
        raise Stop("run identity/trading safety mismatch")
    if counts(BASE, rid) != (0, 0, 0, 0, 0):
        raise Stop("existing fixture ID in restored reference database")
    if int(sql("postgres", f"SELECT pg_database_size('{BASE}')")) > 400_000_000:
        raise Stop("QA reference exceeds disposable-copy size limit")
    if sql(BASE, "SELECT has_function_privilege('service_role','public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)','EXECUTE')") != "t":
        raise Stop("service_role cannot execute candidate RPC")
    return d, rid

def rpc(db, args):
    q = ("BEGIN;\nSET LOCAL ROLE service_role;\n"
         "SET LOCAL statement_timeout='12000ms';\n"
         "SET LOCAL lock_timeout='8000ms';\n"
         "SELECT public.alpha_hunter_commit_core_scan_v01(" + args + ");\n"
         "COMMIT;")
    start = time.perf_counter()
    output = sql(db, q, timeout=45)
    elapsed = (time.perf_counter()-start)*1000
    json_rows = [x for x in output.splitlines() if x.startswith("{")]
    if len(json_rows) != 1:
        raise Stop("RPC response missing or ambiguous")
    obj = json.loads(json_rows[0])
    if obj.get("committed") is not True or tuple(obj.get(k) for k in
            ("parent_count", "symbol_count", "signal_count",
             "feature_count", "readiness_count")) != EXPECTED:
        raise Stop("RPC evidence count mismatch")
    return obj, elapsed

def drop_disposable(db):
    if not re.fullmatch(r"ah_stage7_ephemeral_qa_[0-9a-f]{12}", db):
        raise Stop("disposable cleanup name mismatch")
    sql("postgres", "DROP DATABASE IF EXISTS " + db + " WITH (FORCE);",
        role="supabase_admin", timeout=70)
    if sql("postgres", f"SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='{db}')") != "f":
        raise Stop("disposable cleanup unverified")


def excluded_pg_cron_toc(row):
    """Select only known pg_cron-owned TOC items; leave app objects intact."""
    m = re.match(r"^[0-9]+;\s+[0-9]+\s+[0-9]+\s+(.+)$", row)
    if not m:
        return False
    desc = m.group(1)
    if desc.startswith(("EXTENSION - pg_cron", "COMMENT - EXTENSION pg_cron")):
        return True
    # The restored Supabase access-grant DDL event trigger invokes a function
    # that expects cron.job, absent here because pg_cron is single-DB.
    # Skip only this cron-scoped event trigger, never application row triggers.
    if re.match(r"^EVENT TRIGGER - issue_pg_cron_access(?:\s|$)", desc):
        return True
    return bool(re.match(
        r"^(?:ACL - SCHEMA cron(?:\s|$)"
        r"|ACL cron (?:FUNCTION|TABLE|SEQUENCE|TYPE)\s"
        r"|TABLE DATA cron\s"
        r"|SEQUENCE SET cron\s"
        r"|DEFAULT ACL cron\s)", desc))


def restore_failure_evidence(stderr, rows):
    """Return safe TOC id/class only, never stderr or private SQL text."""
    ids = re.findall(r"from TOC entry ([0-9]+);", stderr)
    if not ids:
        ids = re.findall(r"processing item ([0-9]+)\s", stderr)
    if not ids:
        return "UNKNOWN", "UNKNOWN"
    toc_id = ids[-1]
    toc_line = next(
        (line for line in rows if line.startswith(toc_id + ";")), "")
    if not toc_line:
        return toc_id, "UNKNOWN"
    # Whitelist broad object classes; never print object names or SQL.
    parts = re.match(r"^[0-9]+;\s+[0-9]+\s+[0-9]+\s+(.+)$", toc_line)
    desc = parts.group(1) if parts else ""
    for kind in ("DEFAULT ACL", "TABLE DATA", "SEQUENCE SET",
                 "EVENT TRIGGER", "FK CONSTRAINT", "MATERIALIZED VIEW",
                 "ROW SECURITY", "PUBLICATION TABLE", "COMMENT",
                 "ACL", "TRIGGER", "FUNCTION", "TABLE", "VIEW",
                 "INDEX", "EXTENSION", "SCHEMA", "SEQUENCE", "TYPE",
                 "CONSTRAINT", "POLICY", "RULE", "DOMAIN", "CAST"):
        if desc.startswith(kind + " ") or desc == kind:
            return toc_id, kind.replace(" ", "_")
    return toc_id, "OTHER"

def main():
    db = None
    status = 0
    try:
        d, rid = guard()
        db = "ah_stage7_ephemeral_qa_" + secrets.token_hex(6)
        if sql("postgres", f"SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='{db}')") != "f":
            raise Stop("disposable DB name collision")
        # TEMPLATE BASE cannot be used with active source connections.
        # pg_cron is bound to cron.database_name (the reference DB): trying
        # to CREATE EXTENSION pg_cron in the disposable DB is forbidden.
        # Use a local, private custom archive with a filtered restore TOC,
        # excluding only verified cron-owned entries and the cron-specific
        # access-grant DDL event trigger (not application row triggers).
        # No network, production access, cluster settings changes, or job
        # activation. Cron behavior is intentionally OUTSIDE this test.
        if sql(BASE, "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_cron')") != "t":
            raise Stop("reference pg_cron extension inventory differs")
        cron_event_identity = (
            "SELECT count(*) FROM pg_event_trigger e "
            "JOIN pg_proc p ON p.oid=e.evtfoid "
            "JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE e.evtname='issue_pg_cron_access' "
            "AND e.evtevent='ddl_command_end' "
            "AND n.nspname='extensions' "
            "AND p.proname='grant_pg_cron_access'"
        )
        if sql(BASE, cron_event_identity) != "1":
            raise Stop("reference cron access event trigger identity differs")
        sql("postgres",
            "CREATE DATABASE " + db + " TEMPLATE template0 OWNER supabase_admin;",
            role="supabase_admin", timeout=90)
        # Store all private schema bytes only in container-local, randomized
        # temporary files. Avoid shell pipelines and shell interpolation.
        token = secrets.token_hex(12)
        archive = "/tmp/ah_stage7_copy_" + token + ".dump"
        tocfile = "/tmp/ah_stage7_copy_" + token + ".list"
        try:
            run(
                ["docker", "exec", N, "bash", "-c",
                 "umask 077; exec pg_dump -U supabase_admin -d "
                 + BASE + " -Fc -f " + archive],
                timeout=180
            )
            raw_toc = run(["docker", "exec", N, "pg_restore",
                           "--list", archive], timeout=45)
            rows = raw_toc.splitlines(keepends=True)
            # pg_cron belongs to one cluster-configured database. Its
            # extension-owned cron schema cannot be restored in this
            # disposable DB. Exclude only known pg_cron TOC entries:
            # extension/comment, cron-schema ACLs, cron function/table
            # grants, cron runtime table data and sequence/default ACLs,
            # plus the one verified cron-scoped access-grant event trigger.
            # Keep the access-grant function definition; suppress its
            # invocation by omitting only its event-trigger registration.
            # No production SQL or scheduler changes.
            excluded_rows = [row for row in rows if excluded_pg_cron_toc(row)]
            extension_count = sum(
                "EXTENSION - pg_cron" in row
                for row in excluded_rows
                if re.match(r"^[0-9]+;", row)
            )
            if extension_count != 1:
                raise Stop("unexpected pg_cron extension TOC inventory")
            cron_trigger_count = sum(
                bool(re.search(r"EVENT TRIGGER - issue_pg_cron_access(?:\s|$)", row))
                for row in excluded_rows
            )
            if cron_trigger_count != 1:
                raise Stop("unexpected cron access event trigger TOC inventory")
            if not any("TABLE DATA cron job " in row for row in excluded_rows):
                raise Stop("unexpected pg_cron runtime table inventory")
            # Refuse to silently omit any unexpected cron objects: add an
            # explicitly reviewed class here, never blanket-skip a schema.
            for row in rows:
                if (re.match(r"^[0-9]+;", row)
                        and re.search(r"\bcron\b", row)
                        and not excluded_pg_cron_toc(row)
                        and not re.search(r"\b(?:FUNCTION|COMMENT) extensions grant_pg_cron_access\(", row)):
                    raise Stop("unclassified pg_cron archive dependency")
            filtered_toc = "".join(
                row for row in rows if not excluded_pg_cron_toc(row))
            run(["docker", "exec", "-i", N, "bash", "-c",
                 "umask 077; cat > " + tocfile], payload=filtered_toc)
            # Never print pg_restore stderr: it may contain private
            # definitions/SQL. Capture a numeric failing TOC entry only.
            restore = subprocess.run(
                ["docker", "exec", N, "pg_restore",
                 "-U", "supabase_admin", "-d", db,
                 "--use-list", tocfile, "--single-transaction",
                 "--exit-on-error", "--verbose", archive],
                text=True, capture_output=True, timeout=180,
            )
            if restore.returncode:
                toc_id, toc_class = restore_failure_evidence(
                    restore.stderr, rows)
                print("RESTORE_FAILURE_TOC_ID=" + toc_id)
                print("RESTORE_FAILURE_TOC_CLASS=" + toc_class)
                print("RESTORE_FAILURE_CRON_JOB_REFERENCE=" +
                      ("YES" if 'relation "cron.job" does not exist'
                       in restore.stderr else "NOT_CONFIRMED"))
                raise Stop(
                    "isolated pg_restore failed; failing TOC metadata above; "
                    "private SQL withheld")
        finally:
            # The reference clone remains untouched even if restore fails.
            run(["docker", "exec", N, "rm", "-f", archive, tocfile])
        if sql(db, "SELECT current_database()") != db:
            raise Stop("disposable clone identity mismatch")
        if sql(db, "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_cron')") != "f":
            raise Stop("disposable copy unexpectedly contains pg_cron")
        # The prior Stage 6 reconciliation is required in the scratch copy.
        verify = (
            "SELECT count(*) FROM pg_trigger t "
            "JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_proc p ON p.oid=t.tgfoid "
            "JOIN pg_namespace pn ON pn.oid=p.pronamespace "
            "WHERE n.nspname='public' AND pn.nspname='private' "
            "AND c.relname IN ('alpha_hunter_snapshots',"
            "'alpha_hunter_symbol_snapshots','alpha_hunter_signals',"
            "'alpha_hunter_signal_features',"
            "'alpha_hunter_readiness_observations_v01') "
            "AND NOT t.tgisinternal "
            "AND p.proowner='postgres'::regrole::oid "
            "AND p.prosecdef"
        )
        if sql(db, verify) != "5":
            raise Stop("disposable copy failed five-callback owner/security baseline")
        if counts(db, rid) != (0, 0, 0, 0, 0):
            raise Stop("existing fixture ID in disposable clone")
        side_before = downstream(db, rid)
        args = ",".join(
            "'" + json.dumps(d[k], separators=(",", ":"), ensure_ascii=True).replace("'", "''") + "'::jsonb"
            for k in K)
        result1, first_ms = rpc(db, args)
        if result1.get("run_id") != rid or counts(db, rid) != EXPECTED:
            raise Stop("post-COMMIT core evidence incomplete")
        side_after = downstream(db, rid)
        if side_after[SIDE[0]] != side_before[SIDE[0]] + 1:
            raise Stop("private snapshot trigger side effect missing")
        if any(side_after[t] < side_before[t] for t in SIDE):
            raise Stop("side-effect evidence count decreased")
        result2, retry_ms = rpc(db, args)
        if result2.get("run_id") != rid or counts(db, rid) != EXPECTED:
            raise Stop("post-RETRY core evidence changed")
        if downstream(db, rid) != side_after:
            raise Stop("retry replayed downstream side effects")
        print("STAGE7_DISPOSABLE_COMMIT=PASS")
        print("COMMITTED_CORE_COUNTS=1,61,7,7,61")
        print("RETRY_NO_DUPLICATES=PASS")
        print("PRIVATE_SNAPSHOT_SIDE_EFFECT=PASS")
        print("CRON_DDL_EVENT_TRIGGER_EXCLUDED_IN_DISPOSABLE=PASS")
        for t in SIDE:
            print("SIDE_EFFECT_COUNT_" + t.upper().replace(".", "_") + "=" + str(side_after[t]))
        print(f"FIRST_TRANSACTION_CLIENT_WALL_MS={first_ms:.3f}")
        print(f"RETRY_TRANSACTION_CLIENT_WALL_MS={retry_ms:.3f}")
        print("LIMITATION=NO_PG_CRON_OR_CRON_DDL_EVENT_TRIGGER_IN_DISPOSABLE;ONE_COMMIT_RETRY;NO_P95_P99_OR_CONCURRENT_LOAD")
        print("PRODUCTION_CONNECTIONS=NONE")
    except (Stop, OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        status = 2
        print("STAGE7_DISPOSABLE_COMMIT=BLOCKED")
        print("REASON=" + (str(e) if isinstance(e, Stop) else "private QA input unavailable"))
        print("NO_PRODUCTION_FALLBACK")
    finally:
        if db is not None:
            try:
                drop_disposable(db)
                print("DISPOSABLE_DB_REMOVED=PASS")
            except (Stop, OSError, subprocess.TimeoutExpired):
                status = 3
                print("DISPOSABLE_DB_REMOVED=NOT_VERIFIED")
                print("CLEANUP_ATTENTION_REQUIRED=" + db)
    return status

if __name__ == "__main__":
    sys.exit(main())
