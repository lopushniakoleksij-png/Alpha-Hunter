#!/usr/bin/env python3
"""P0: one bounded, sanitised psql diagnosis after failed catalog census.

Default invocation is READ-ONLY PLAN: never starts a PostgreSQL server.
Only --approve-third-psql-diagnostic authorises a single diagnostic startup
of the already recovered and hardened THIRD disposable PostgreSQL 17 copy.
No original DB restart, no production connection, no network/ports, no cron,
no SQL mutation, no private log/client error messages printed, no auto retry.
The prior failed catalog container is retained, stopped, for forensics.
"""
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.home() / ".alpha-hunter-private-dbqa"
BRANCH = "fix/supabase-write-timeout-qa"
ORIGINAL = "alpha-hunter-private-postgres17-qa"
ORIGINAL_IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"
OLD_CENSUS = "ah-p0-third-catalog-census-once"
RECOVERED = "ah-p0-third-crash-recovery-once"
DIAG = "ah-p0-third-psql-diagnostic-once"
IMAGE = "postgres:17"
PGDATA = "/var/lib/postgresql/data"


class Blocked(Exception):
    pass


def run(args, *, timeout=35, allow_failure=False):
    try:
        r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise Blocked("isolated local command unavailable") from None
    if r.returncode and not allow_failure:
        raise Blocked("isolated local command failed")
    return r


def private_dir(d):
    if d.is_symlink() or not d.is_dir() or stat.S_IMODE(d.stat().st_mode) != 0o700:
        raise Blocked("owner-private directory missing/unsafe")


def private_file(f):
    if f.is_symlink() or not f.is_file() or stat.S_IMODE(f.stat().st_mode) != 0o600:
        raise Blocked("owner-private file missing/unsafe")


def hash_file(f):
    h = hashlib.sha256()
    with f.open("rb") as source:
        for buf in iter(lambda: source.read(1024*1024), b""):
            h.update(buf)
    return h.hexdigest()


def preflight():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Blocked("owner's original authorised Codespace required")
    if run(["git", "branch", "--show-current"]).stdout.strip() != BRANCH:
        raise Blocked("isolated draft branch required")
    private_dir(ROOT)
    orig = json.loads(run(["docker", "inspect", ORIGINAL]).stdout)[0]
    if (orig.get("Config", {}).get("Image") != ORIGINAL_IMAGE
        or orig.get("Path") != "docker-entrypoint.sh"
        or orig.get("HostConfig", {}).get("NetworkMode") != "none"
        or orig.get("State", {}).get("Status") != "exited"
        or orig.get("State", {}).get("Running")):
        raise Blocked("original PostgreSQL is not confirmed stopped and isolated")

    backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backups) < 2:
        raise Blocked("two private physical backup archives required")
    digests = set()
    for folder in backups:
        private_dir(folder)
        tar, sha = folder / "pgdata_original_stopped.tar", folder / "pgdata_original_stopped.sha256"
        private_file(tar)
        private_file(sha)
        m = re.fullmatch(
            r"([0-9a-f]{64})  pgdata_original_stopped[.]tar",
            sha.read_text(encoding="ascii").strip(),
        )
        if not m or hash_file(tar) != m.group(1):
            raise Blocked("private original backup SHA mismatch")
        digests.add(m.group(1))
    if len(digests) != 1:
        raise Blocked("original backup copies diverged")

    trees = sorted(ROOT.glob("p0_recovery_runtime_*"))
    if len(trees) != 1:
        raise Blocked("exactly one recovered third-copy tree required")
    private_dir(trees[0])
    pg = trees[0] / "pgdata"
    private_dir(pg)
    if pg.stat().st_uid != os.geteuid():
        raise Blocked("third PGDATA ownership mismatch")
    if (pg / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("third PG version mismatch")
    if (pg / "postmaster.pid").exists() or any((pg / "pg_tblspc").iterdir()):
        raise Blocked("unsafe third-copy PID or external tablespace")
    safe_settings = (
        ("postgresql.conf", "shared_preload_libraries = ''"),
        ("postgresql.conf", "listen_addresses = ''"),
        ("postgresql.conf", "archive_mode = off"),
        ("postgresql.conf", "max_worker_processes = 0"),
        ("postgresql.auto.conf", "# Third-copy only: inherited ALTER SYSTEM settings quarantined."),
    )
    for name, setting in safe_settings:
        f = pg / name
        private_file(f)
        if setting not in f.read_text(encoding="ascii"):
            raise Blocked("third copy hardening config mismatch")

    for oldname in (OLD_CENSUS, RECOVERED):
        old = json.loads(run(["docker", "inspect", oldname]).stdout)[0]
        binds = [m for m in old.get("Mounts", []) if m.get("Type") == "bind"]
        if (old.get("State", {}).get("Status") != "exited"
            or old.get("State", {}).get("Running")
            or old.get("HostConfig", {}).get("NetworkMode") != "none"
            or len(binds) != 1 or binds[0].get("Source") != str(pg)):
            raise Blocked("prior third-copy container is not stopped/isolated")
    if run(["docker", "inspect", DIAG], allow_failure=True).returncode == 0:
        raise Blocked("diagnostic already attempted; automatic retry forbidden")
    image = json.loads(run(["docker", "image", "inspect", IMAGE]).stdout)[0]
    ident = image.get("Id", "")
    if (image.get("Os") != "linux" or not re.fullmatch(r"sha256:[0-9a-f]{64}", ident)):
        raise Blocked("cached PostgreSQL 17 runtime image identity invalid")
    if os.statvfs(pg).f_bavail * os.statvfs(pg).f_frsize < 1024**3:
        raise Blocked("insufficient free disk for safe third-copy startup")
    return pg, (orig["Id"], orig["State"].get("FinishedAt"),
                len(backups), next(iter(digests)), ident)


def start_args(pg, image_id):
    uid, gid = os.geteuid(), os.getegid()
    script = (
        "set -eu; "
        "printf '%s\\n' 'local all postgres trust' 'local all all reject' "
        "'host all all 0.0.0.0/0 reject' 'host all all ::/0 reject' "
        "> /tmp/p0_diag_hba.conf; "
        "exec postgres -D " + PGDATA +
        " -c hba_file=/tmp/p0_diag_hba.conf "
        " -c default_transaction_read_only=on"
    )
    return [
        "docker", "run", "-d", "--pull=never", "--name", DIAG,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--memory", "512m", "--cpus", "1", "--stop-signal", "SIGINT",
        "--user", str(uid) + ":" + str(gid),
        "--env", "PGDATA=" + PGDATA,
        "--mount", "type=bind,source=" + str(pg) + ",target=" + PGDATA,
        "--tmpfs", "/var/run/postgresql:rw,nosuid,size=16m,uid=" +
            str(uid) + ",gid=" + str(gid) + ",mode=0700",
        "--tmpfs", "/tmp:rw,nosuid,size=32m,uid=" +
            str(uid) + ",gid=" + str(gid) + ",mode=0700",
        "--entrypoint", "/bin/sh", image_id, "-c", script,
    ]


def inspect_runtime(pg):
    x = json.loads(run(["docker", "inspect", DIAG]).stdout)[0]
    h = x.get("HostConfig", {})
    binds = [m for m in x.get("Mounts", []) if m.get("Type") == "bind"]
    if (h.get("NetworkMode") != "none" or not h.get("ReadonlyRootfs")
        or "ALL" not in [str(s).upper() for s in h.get("CapDrop") or []]
        or h.get("PortBindings")
        or len(binds) != 1 or binds[0].get("Source") != str(pg)
        or binds[0].get("Destination") != PGDATA
        or not binds[0].get("RW")
        or x.get("Config", {}).get("User") != str(os.geteuid()) + ":" + str(os.getegid())):
        raise Blocked("diagnostic container isolation policy mismatch")
    return x


def classify_client_error(stderr, rc):
    """Only enum categories; NEVER return raw stderr, database or user names."""
    if rc == 0:
        return "NONE"
    text = stderr.lower()
    # Specific PostgreSQL FATAL/ERROR must win over psql's generic
    # "connection to server on socket ... failed" wrapper.
    rules = (
        (r"database [^\n]*does not exist", "DATABASE_NOT_FOUND"),
        (r"role [^\n]*does not exist", "ROLE_NOT_FOUND"),
        (r"no pg_hba.conf entry|authentication failed|password authentication", "AUTHENTICATION"),
        (r"permission denied", "PERMISSION"),
        (r"read.only transaction|cannot execute .*in a read.only", "READ_ONLY_SQL_VIOLATION"),
        (r"syntax error|relation [^\n]*does not exist|function [^\n]*does not exist|column [^\n]*does not exist", "SQL_SYNTAX_OR_CATALOG"),
        (r"could not connect to server|connection refused|no such file or directory|socket[^\n]*failed", "SOCKET_OR_SERVER_CONNECTION"),
        (r"unrecognized option|invalid option|psql: error", "CLIENT_CONFIGURATION_OR_OTHER"),
    )
    for pattern, category in rules:
        if re.search(pattern, text):
            return category
    return "CLIENT_UNKNOWN_NONZERO"


def psql_probe(query):
    if query not in ("SELECT 1;", (
        "SELECT count(*) FILTER (WHERE datname='alpha_hunter_private_qa'), "
        "count(*) FILTER (WHERE datname='alpha_hunter_qa') FROM pg_database;"
    )):
        raise Blocked("unapproved read-only metadata probe")
    args = [
        "docker", "exec", "-i",
        "--user", str(os.geteuid()) + ":" + str(os.getegid()),
        "-e", "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=15000",
        DIAG, "psql", "-X", "-q", "-A", "-t", "-F", "|",
        "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-h",
        "/var/run/postgresql", "-d", "postgres", "-c", query,
    ]
    return run(args, timeout=28, allow_failure=True)


def stop_diagnostic():
    x = json.loads(run(["docker", "inspect", DIAG]).stdout)[0]
    if x["State"].get("Running"):
        run(["docker", "stop", "--time", "45", DIAG], timeout=55)
    x = json.loads(run(["docker", "inspect", DIAG]).stdout)[0]
    if x["State"].get("Running") or x["State"].get("Status") != "exited":
        raise Blocked("diagnostic container not safely stopped")


def verify_after(before):
    orig = json.loads(run(["docker", "inspect", ORIGINAL]).stdout)[0]
    if (orig["Id"], orig["State"].get("FinishedAt")) != before[:2] or orig["State"].get("Running"):
        raise Blocked("original protected database state changed")
    dirs = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(dirs) != before[2]:
        raise Blocked("protected backup count changed")
    for d in dirs:
        if hash_file(d / "pgdata_original_stopped.tar") != before[3]:
            raise Blocked("protected physical backup content changed")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--approve-third-psql-diagnostic"]):
        print("QA_USAGE=OPTIONAL_--approve-third-psql-diagnostic")
        return 2
    print("QA_GATE=THIRD_COPY_PSQL_FAILURE_CLASSIFICATION")
    print("QA_PRODUCTION_DB_CONNECTION=NONE")
    print("QA_ORIGINAL_CONTAINER_START=NO")
    print("QA_PREVIOUS_CENSUS_RETRY=NO")
    start_attempted = False
    try:
        pg, before = preflight()
        print("QA_DIAGNOSTIC_PREFLIGHT=PASS")
        if not argv:
            print("QA_OWNER_APPROVAL=NOT_GIVEN")
            print("QA_DIAGNOSTIC_DATABASE_STARTED=NO")
            print("QA_NEXT_GATE=EXPLICIT_THIRD_COPY_PSQL_DIAGNOSTIC_APPROVAL")
            return 0
        print("QA_OWNER_APPROVAL=EXPLICIT_THIRD_COPY_ONLY")
        start_attempted = True
        run(start_args(pg, before[4]), timeout=45)
        inspect_runtime(pg)
        ready = False
        for _ in range(45):
            logs = run(["docker", "logs", DIAG], timeout=10, allow_failure=True)
            log = logs.stdout + "\n" + logs.stderr
            if "database system is ready to accept connections" in log:
                ready = True
                break
            if re.search(r"\b(FATAL|PANIC)\b", log):
                raise Blocked("diagnostic server startup error; logs remain private")
            if not inspect_runtime(pg)["State"].get("Running"):
                break
            time.sleep(2)
        if not ready:
            raise Blocked("diagnostic third-copy server not ready")
        basic = psql_probe("SELECT 1;")
        label = classify_client_error(basic.stderr, basic.returncode)
        print("QA_PSQL_CONNECT_PROBE=" + ("PASS" if basic.returncode == 0 and basic.stdout.strip() == "1" else "FAIL"))
        print("QA_PSQL_CLIENT_ERROR_CLASS=" + label)
        if basic.returncode == 0 and basic.stdout.strip() == "1":
            census = psql_probe(
                "SELECT count(*) FILTER (WHERE datname='alpha_hunter_private_qa'), "
                "count(*) FILTER (WHERE datname='alpha_hunter_qa') FROM pg_database;"
            )
            print("QA_DATABASE_NAME_CENSUS=" + ("PASS" if census.returncode == 0 else "FAIL"))
            if census.returncode:
                print("QA_DATABASE_NAME_ERROR_CLASS=" +
                      classify_client_error(census.stderr, census.returncode))
            elif re.fullmatch(r"[01]\|[01]", census.stdout.strip()):
                observed, legacy = census.stdout.strip().split("|")
                print("QA_EXPECTED_QA_DB_PRESENT=" + ("YES" if observed == "1" else "NO"))
                print("QA_ALTERNATE_QA_DB_PRESENT=" + ("YES" if legacy == "1" else "NO"))
            else:
                print("QA_DATABASE_NAME_CENSUS=UNEXPECTED_RESPONSE_REVIEW")
        stop_diagnostic()
        start_attempted = False
        verify_after(before)
        print("QA_DIAGNOSTIC_CONTAINER=EXITED")
        print("QA_ORIGINAL_DATABASE=STILL_STOPPED")
        print("QA_ORIGINAL_BACKUPS_SHA256_VERIFIED=" + str(before[2]))
        print("QA_SCHEMA_PARITY=NOT_YET_VERIFIED")
        print("QA_BENCHMARK_30_50_61=NOT_PERFORMED")
        print("QA_RELEASE=NO_GO")
        print("QA_NEXT_GATE=CORRECT_SINGLE_ROOT_CAUSE_BEFORE_CATALOG_RETRY")
        return 0
    except (Blocked, OSError, KeyError, ValueError, TypeError) as error:
        if start_attempted:
            try:
                stop_diagnostic()
            except Exception:
                print("QA_DIAGNOSTIC_STOP=MANUAL_REVIEW_REQUIRED")
        why = (str(error).upper().replace(" ", "_")[:90]
               if isinstance(error, Blocked) else "PRIVATE_RUNTIME_ERROR")
        print("QA_DIAGNOSTIC=BLOCKED_" + why)
        print("QA_AUTO_RETRY=NO")
        print("QA_RELEASE=NO_GO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
