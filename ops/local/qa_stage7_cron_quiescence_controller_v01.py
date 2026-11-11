#!/usr/bin/env python3
"""QA-only reversible cron launcher redirection for physical-template probe.

Scope: already existing network-isolated Codespaces PostgreSQL 17 QA container.
Zero scheduled jobs required. No production connections, scanner changes,
credential output, session termination, or schema-altering SQL.
Runs the verified child probe while cron.database_name temporarily = postgres.
Restores the original postmaster setting and restarts QA even if probe blocks.
This is limited QA evidence, NOT production certification.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import time

N = "alpha-hunter-private-postgres17-qa"
BASE = "ah_authentic_schema_20261110"
BRANCH = "fix/supabase-write-timeout-qa"
IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"


class Blocked(Exception):
    pass


def run(args, payload=None, timeout=50):
    p = subprocess.run(args, input=payload, text=True, capture_output=True,
                       timeout=timeout, check=False)
    if p.returncode:
        # Avoid exposing any private SQL, filesystem paths, secrets, or logs.
        raise Blocked("isolated QA command failed; private stderr withheld")
    return p.stdout.strip()


def sql(db, query, role="postgres"):
    if role not in ("postgres", "supabase_admin"):
        raise Blocked("unapproved local QA database role")
    return run(["docker", "exec", "-i", N, "psql", "-XqAt",
                "-v", "ON_ERROR_STOP=1", "-U", role, "-d", db],
               payload=query, timeout=35)


def inspect_container():
    raw = run([
        "docker", "inspect", "-f",
        "{{.Config.Image}}|{{.Path}}|{{.HostConfig.RestartPolicy.Name}}|"
        "{{.State.Running}}|{{.HostConfig.NetworkMode}}", N,
    ])
    if raw != IMAGE + "|docker-entrypoint.sh|no|true|none":
        raise Blocked("unexpected QA container image, process or isolation")


def await_qa_ready():
    for _ in range(40):
        try:
            inspect_container()
            if sql("postgres", "SELECT current_database()") == "postgres":
                return
        except (Blocked, OSError, subprocess.TimeoutExpired):
            pass
        time.sleep(1)
    raise Blocked("isolated QA container not ready after restart")


def restart_qa():
    # docker restart preserves the same isolated container and named volumes.
    run(["docker", "restart", "-t", "30", N], timeout=90)
    await_qa_ready()


def original_override():
    # Whether cron.database_name was already set in postgresql.auto.conf.
    # Restoring the same override state avoids leaving a new persistent setting.
    return sql("postgres", (
        "SELECT coalesce((SELECT setting FROM pg_file_settings "
        "WHERE name='cron.database_name' "
        "AND sourcefile=current_setting('data_directory')"
        "||'/postgresql.auto.conf' ORDER BY seqno DESC LIMIT 1),"
        "'__UNSET__');"
    ), role="supabase_admin")


def source_sessions():
    return sql("postgres", (
        "SELECT count(*)::text || '|' || "
        "coalesce(string_agg(backend_type, ',' ORDER BY backend_type), '') "
        "FROM pg_stat_activity "
        "WHERE datname='" + BASE + "';"
    ))


def guard(child):
    if os.environ.get("CODESPACES") != "true":
        raise Blocked("private Codespace required")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("not permitted in GitHub Actions")
    if run(["git", "branch", "--show-current"]) != BRANCH:
        raise Blocked("wrong repair branch")
    print("QA_GUARD_GIT_BRANCH=PASS")
    inspect_container()
    print("QA_GUARD_CONTAINER=PASS")
    if not child.is_file() or child.is_symlink():
        raise Blocked("verified child probe file missing")
    if child.stat().st_mode & 0o077:
        raise Blocked("child probe file must be private mode 0600")
    print("QA_GUARD_FIXTURE_FILE=PASS")
    pgid = sql("postgres", (
        "SELECT current_setting('server_version_num') || '|' || "
        "current_setting('cron.database_name');"
    ))
    if not re.fullmatch(r"17\d{4}\|" + re.escape(BASE), pgid):
        raise Blocked("unexpected QA server or cron target")
    print("QA_GUARD_PG_IDENTITY=PASS")
    if sql(BASE, "SELECT count(*) FROM cron.job") != "0":
        raise Blocked("QA reference has scheduled cron jobs")
    print("QA_GUARD_ZERO_JOBS=PASS")
    if sql("postgres", (
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE backend_type='client backend' AND pid<>pg_backend_pid()"
    )) != "0":
        raise Blocked("other client sessions exist; no QA restart")
    print("QA_GUARD_ZERO_OTHER_CLIENTS=PASS")
    if source_sessions() != "1|pg_cron launcher":
        raise Blocked("unexpected reference sessions; no QA restart")
    print("QA_GUARD_SOURCE_SESSIONS=PASS")
    # PostgreSQL/Supabase may use a non-superuser postgres role. Check the
    # two distinct privileges *before* reading pg_file_settings, altering
    # system settings or restarting the isolated QA container.
    privilege = sql("postgres", (
        "SELECT has_parameter_privilege(current_user,"
        "'cron.database_name','ALTER SYSTEM')::text || '|' || "
        "has_table_privilege(current_user,"
        "'pg_catalog.pg_file_settings','SELECT')::text;"
    ), role="supabase_admin")
    if privilege != "true|true":
        print("QA_GUARD_CONFIG_PRIVILEGES=BLOCKED")
        print("QA_CONFIG_ROUTE=REQUIRES_AUTHORIZED_ADMIN")
        raise Blocked("QA role lacks privileged config access; no restart")
    print("QA_GUARD_CONFIG_PRIVILEGES=PASS")
    # Configuration operations always use the existing authorised isolated-QA
    # supabase_admin role, never the non-superuser postgres compatibility role.
    old = original_override()
    if old not in (BASE, "__UNSET__"):
        raise Blocked("unexpected original auto-conf override; no restart")
    print("QA_GUARD_AUTO_CONF_OVERRIDE=PASS")
    return old


def evidence(lines):
    accepted = (
        "STAGE7_PHYSICAL_CLONE_COMMIT=", "COMMITTED_CORE_COUNTS=",
        "RETRY_NO_DUPLICATES=", "PRIVATE_SNAPSHOT_SIDE_EFFECT=",
        "CRON_DEPENDENT_VIEW_PRESERVED_BY_TEMPLATE=",
        "CRON_REDIRECTED_DURING_DISPOSABLE_TEST=",
        "SIDE_EFFECT_COUNT_", "FIRST_TRANSACTION_CLIENT_WALL_MS=",
        "RETRY_TRANSACTION_CLIENT_WALL_MS=", "LIMITATION=",
        "DISPOSABLE_DB_REMOVED=", "PRODUCTION_CONNECTIONS=",
        "REFERENCE_DATABASE_WRITES=", "NO_PRODUCTION_FALLBACK",
        "DURABLE_", "SAME_RUN_", "QA_MANUAL_DISPOSABLE_CLEANUP_REQUIRED=",
    )
    for line in lines.splitlines():
        if line.startswith(accepted) and re.fullmatch(r"[A-Z0-9_.=,;+-]{1,160}", line):
            print(line)


def main():
    changed = False
    old = None
    probe_status = False
    restored = False
    diagnose_only = (
        len(sys.argv) == 3 and sys.argv[2] == "--diagnose"
    )
    durable30 = (
        len(sys.argv) == 3 and sys.argv[2] == "--durable30"
    )
    if not (len(sys.argv) == 2 or diagnose_only or durable30):
        print("QA_CRON_CONTROLLER=BLOCKED")
        print("REASON=exact child script path required")
        return 2
    child = Path(sys.argv[1])
    try:
        old = guard(child)
        print("QA_ONLY_GUARDS=PASS")
        if diagnose_only:
            print("QA_GUARD_DIAGNOSTIC=PASS")
            print("QA_DATABASE_MUTATIONS=NONE")
            return 0
        changed = True  # restore even if ALTER SYSTEM partially succeeds
        sql("postgres", "ALTER SYSTEM SET cron.database_name = 'postgres';",
            role="supabase_admin")
        restart_qa()
        if sql("postgres", "SELECT current_setting('cron.database_name')") != "postgres":
            raise Blocked("temporary cron redirect not active")
        if sql("postgres", (
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname='" + BASE + "'"
        )) != "0":
            raise Blocked("reference still has sessions after temporary redirect")
        print("QA_CRON_LAUNCHER_REDIRECTED=PASS")
        child_result = subprocess.run(
            [sys.executable, str(child)], text=True,
            capture_output=True, timeout=1200 if durable30 else 300,
            check=False,
        )
        evidence(child_result.stdout)
        probe_status = (
            child_result.returncode == 0
            and "STAGE7_PHYSICAL_CLONE_COMMIT=PASS" in child_result.stdout
            and "DISPOSABLE_DB_REMOVED=PASS" in child_result.stdout
            and "COMMITTED_CORE_COUNTS=1,61,7,7,61" in child_result.stdout
            and "RETRY_NO_DUPLICATES=PASS" in child_result.stdout
            and (not durable30 or
                 ("DURABLE_TRIAL_STATUS=PASS" in child_result.stdout and
                  "DURABLE_TRIALS_COMPLETED=30" in child_result.stdout and
                  "DURABLE_ALL_DISPOSABLE_DATABASES_REMOVED=PASS" in child_result.stdout))
        )
        if not probe_status:
            print("QA_PROBE_STATUS=BLOCKED")
        else:
            print("QA_PROBE_STATUS=PASS")
    except (Blocked, OSError, subprocess.TimeoutExpired) as exc:
        print("QA_CRON_CONTROLLER=BLOCKED")
        print("REASON=" +
              (str(exc) if isinstance(exc, Blocked)
               else "isolated QA command unavailable; private details withheld"))
    finally:
        if changed:
            try:
                # If a QA restart unexpectedly stopped container, start only
                # the same exact named instance; never create a new one.
                status = run([
                    "docker", "inspect", "-f", "{{.State.Running}}", N
                ])
                if status == "false":
                    run(["docker", "start", N], timeout=90)
                    await_qa_ready()
                elif status != "true":
                    raise Blocked("QA restart state unknown")
                if old == "__UNSET__":
                    sql("postgres", "ALTER SYSTEM RESET cron.database_name;",
                        role="supabase_admin")
                else:
                    sql("postgres", "ALTER SYSTEM SET cron.database_name = '" + BASE + "';",
                        role="supabase_admin")
                restart_qa()
                if sql("postgres", "SELECT current_setting('cron.database_name')") != BASE:
                    raise Blocked("original QA cron target not restored")
                if original_override() != old:
                    raise Blocked("original QA auto-conf override not restored")
                if sql(BASE, "SELECT count(*) FROM cron.job") != "0":
                    raise Blocked("QA reference cron-job count changed")
                restored = True
                print("QA_ORIGINAL_CRON_CONFIG_RESTORED=PASS")
            except (Blocked, OSError, subprocess.TimeoutExpired):
                print("QA_ORIGINAL_CRON_CONFIG_RESTORED=NOT_VERIFIED")
                print("QA_MANUAL_CONFIG_RECOVERY_REQUIRED=YES")
    if restored and probe_status:
        print("QA_CRON_CONTROLLER=PASS")
        print("PRODUCTION_RELEASE=NO_GO")
        return 0
    print("QA_CRON_CONTROLLER=BLOCKED")
    print("PRODUCTION_RELEASE=NO_GO")
    return 2


if __name__ == "__main__":
    sys.exit(main())
