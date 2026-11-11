#!/usr/bin/env python3
"""Identify Stage 7 failed VIEW TOC 474 using private offline QA only.

Reads the existing PostgreSQL 17 QA reference database. Emits only counts
and safe classifications; never prints names, view SQL, credentials or data.
No restore, no production connection, no source database modification.
"""
import os
import re
import secrets
import subprocess
import sys

N = "alpha-hunter-private-postgres17-qa"
BASE = "ah_authentic_schema_20261110"
BRANCH = "fix/supabase-write-timeout-qa"
FAIL_ID = "474"


class Blocked(Exception):
    pass


def run(args, data=None, timeout=180):
    p = subprocess.run(
        args, input=data, capture_output=True, text=True, timeout=timeout
    )
    if p.returncode != 0:
        raise Blocked("offline QA command failed (private stderr withheld)")
    return p.stdout.strip()


def sql(query):
    return run(
        ["docker", "exec", "-i", N, "psql", "-XqAt",
         "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", BASE],
        data=query, timeout=45,
    )


def parse_view_toc(line):
    """Only unquoted simple identifiers are accepted; never return raw TOC."""
    m = re.fullmatch(
        r"474;\s+\d+\s+\d+\s+VIEW\s+"
        r"([a-z_][a-z_0-9]*)\s+([a-z_][a-z_0-9]*)\s+\S+",
        line.strip(),
    )
    if not m:
        raise Blocked("TOC 474 not a simple safely classifiable VIEW")
    return m.group(1), m.group(2)


def guard():
    if os.environ.get("CODESPACES") != "true":
        raise Blocked("private Codespaces only")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("never execute against CI database")
    if run(["git", "branch", "--show-current"], timeout=15) != BRANCH:
        raise Blocked("incorrect repair branch")
    ident = run(
        ["docker", "inspect", "-f",
         "{{.State.Running}}|{{.HostConfig.NetworkMode}}", N],
        timeout=15,
    )
    if ident != "true|none":
        raise Blocked("network-isolated running QA container required")
    dbid = sql("SELECT current_database()||'|'||current_user||'|'||"
               "current_setting('server_version_num');")
    if not re.fullmatch(re.escape(BASE) + r"\|postgres\|17\d{4}", dbid):
        raise Blocked("unexpected QA database identity")
    if sql("SELECT to_regclass('cron.job') IS NOT NULL;") != "t":
        raise Blocked("cron.job missing from QA reference database")


def inspect(archive):
    toc = run(["docker", "exec", N, "pg_restore", "--list", archive])
    lines = [
        line for line in toc.splitlines()
        if line.startswith(FAIL_ID + ";")
    ]
    if len(lines) != 1:
        raise Blocked("TOC entry 474 missing or duplicated")
    schema, name = parse_view_toc(lines[0])
    # Identifiers were restricted to [a-z_0-9] by parse_view_toc.
    relation = schema + "." + name
    exists = sql(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
        "ON n.oid=c.relnamespace "
        f"WHERE n.nspname='{schema}' AND c.relname='{name}' "
        "AND c.relkind='v';"
    )
    if exists != "1":
        raise Blocked("TOC view identity does not match QA reference catalog")

    cron_dependencies = sql(
        "SELECT count(*) FROM pg_depend d "
        "JOIN pg_rewrite rw ON rw.oid=d.objid "
        "WHERE d.classid='pg_rewrite'::regclass "
        "AND d.refclassid='pg_class'::regclass "
        f"AND rw.ev_class=to_regclass('{relation}') "
        "AND d.refobjid=to_regclass('cron.job');"
    )
    if not cron_dependencies.isdecimal():
        raise Blocked("cron dependency count malformed")
    other_view_dependents = sql(
        "SELECT count(*) FROM pg_depend d "
        "JOIN pg_rewrite rw ON rw.oid=d.objid "
        "WHERE d.classid='pg_rewrite'::regclass "
        "AND d.refclassid='pg_class'::regclass "
        f"AND d.refobjid=to_regclass('{relation}') "
        f"AND rw.ev_class<>to_regclass('{relation}');"
    )
    core_table_refs = sql(
        "SELECT count(*) FROM pg_depend d "
        "JOIN pg_rewrite rw ON rw.oid=d.objid "
        "JOIN pg_class ref ON ref.oid=d.refobjid "
        "JOIN pg_namespace ns ON ns.oid=ref.relnamespace "
        "WHERE d.classid='pg_rewrite'::regclass "
        "AND d.refclassid='pg_class'::regclass "
        f"AND rw.ev_class=to_regclass('{relation}') "
        "AND ns.nspname IN ('public','private') "
        "AND ref.relname LIKE 'alpha\\_hunter\\_%' ESCAPE '\\';"
    )
    for value in (other_view_dependents, core_table_refs):
        if not value.isdecimal():
            raise Blocked("dependent-object count malformed")
    category = (
        "PUBLIC" if schema == "public" else
        "PRIVATE" if schema == "private" else
        "EXTENSIONS" if schema == "extensions" else "OTHER"
    )
    print("STAGE7_FAILED_VIEW_INSPECT=PASS")
    print("TOC_ID=474")
    print("SOURCE_VIEW_PRESENT=YES")
    print("VIEW_SCHEMA_CLASS=" + category)
    print("VIEW_NAME_ALPHA_HUNTER_PREFIX=" +
          ("YES" if name.startswith("alpha_hunter_") else "NO"))
    print("DIRECT_CRON_JOB_DEPENDENCY_COUNT=" + cron_dependencies)
    print("OTHER_VIEW_DEPENDENTS_COUNT=" + other_view_dependents)
    print("DIRECT_ALPHA_HUNTER_TABLE_DEPENDENCY_COUNT=" + core_table_refs)
    print("VIEW_CANNOT_BE_EXCLUDED_WITHOUT_REVIEW=YES")
    print("NO_PRODUCTION_CONNECTION=PASS")
    print("NO_DATABASE_MUTATION=PASS")
    print("LIMITATION=CATALOG_DEPENDENCIES_ONLY;DYNAMIC_SQL_NOT_PROVEN")


def main():
    archive = "/tmp/ah_stage7_inspect_" + secrets.token_hex(12) + ".dump"
    try:
        guard()
        run(
            ["docker", "exec", N, "bash", "-c",
             "umask 077; exec pg_dump -U supabase_admin -d "
             + BASE + " -Fc -f " + archive],
            timeout=180,
        )
        inspect(archive)
        return 0
    except (Blocked, OSError, subprocess.TimeoutExpired) as exc:
        print("STAGE7_FAILED_VIEW_INSPECT=BLOCKED")
        print("REASON=" +
              (str(exc) if isinstance(exc, Blocked) else "private QA unavailable"))
        print("NO_PRODUCTION_FALLBACK")
        return 2
    finally:
        try:
            run(["docker", "exec", N, "rm", "-f", archive], timeout=15)
        except (Blocked, OSError, subprocess.TimeoutExpired):
            print("TEMP_ARCHIVE_CLEANUP=NOT_VERIFIED")


if __name__ == "__main__":
    sys.exit(main())
