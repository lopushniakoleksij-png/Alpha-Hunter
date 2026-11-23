#!/usr/bin/env python3
"""Owner-gated port-corrected offline PostgreSQL 17 catalog census on THIRD recovered QA copy.

DEFAULT IS READ-ONLY PREFLIGHT. --approve-third-port-corrected-catalog-census
requires NEW, separate owner approval to start an isolated
server ONLY on the disposable THIRD recovered PGDATA. Verifies original stopped
container + 2 SHA-identical private backups, no network/ports, no preload/cron,
isolated socket and read-only SQL. Cleanly stops when done; never starts original.

Comparison against the 2026-11-08 historical PRODUCTION BASELINE is
necessary but NOT current production parity; owner must independently verify
current production baseline before release. All findings are counts/boolean
digests; never print SQL definitions, table contents, credentials or logs.

Changing disposable third-copy PGDATA is permitted ONLY with explicit owner
approval, but never modifies protected backups, first stage, production,
main branch, scanner, trading authority, migrations, or external services.
"""
from __future__ import annotations

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
RECOVERED = "ah-p0-third-crash-recovery-once"
PREVIOUS_CENSUS = "ah-p0-third-catalog-census-once"
PREVIOUS_DIAGS = (
    "ah-p0-third-psql-diagnostic-once",
    "ah-p0-third-psql-port-corrected-once",
)
CENSUS = "ah-p0-third-catalog-port-corrected-once"
IMAGE = "postgres:17"
PGDATA = "/var/lib/postgresql/data"
DB = "alpha_hunter_private_qa"
MAX_WAIT_S = 90
STRUCT_SQL = "ops/sql/readonly_stage2_structural_fingerprint_v01.sql"
PRIVATE_SQL = "ops/sql/readonly_p0_private_function_catalog_fingerprint_v01.sql"
BASE_COUNTS = ("128", "128", "3012", "360", "0", "131", "108", "36", "21")
BASE_HASHES = (
    "c802a3e3d96d620a20adc8c3af350472",
    "5a7e8cbe8b8450677f6be84a77caaa6e",
    "5c5b202307ef6bb57b4a9b08082c2a1e",
    "c9785c793fa51a732c2edc96ba22c7eb",
)
BASE_EXT = {
    "http|1.6|extensions",
    "pg_cron|1.6.4|pg_catalog",
    "pg_net|0.20.4|extensions",
    "pg_stat_statements|1.11|extensions",
    "pgcrypto|1.3|extensions",
    "plpgsql|1.0|pg_catalog",
    "supabase_vault|0.3.1|vault",
    "uuid-ossp|1.1|extensions",
}
BASE_FUNC = {
    "private|110|65|110|8fae5afad12f3040d30d0416cbfd9be1",
    "public|10|5|10|a75b1d2ed683766dbd5ffa3830f7f087",
}


class Blocked(Exception):
    pass


def call(args, timeout=35, inp=None, fail=True):
    try:
        p = subprocess.run(
            args, input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        raise Blocked("local isolated operation unavailable") from None
    if p.returncode and fail:
        raise Blocked("local isolated operation returned failure")
    return p


def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def private_dir(p):
    if p.is_symlink() or not p.is_dir() or stat.S_IMODE(p.stat().st_mode) != 0o700:
        raise Blocked("unsafe private directory")


def private_file(p):
    if p.is_symlink() or not p.is_file() or stat.S_IMODE(p.stat().st_mode) != 0o600:
        raise Blocked("unsafe private file")


def preflight():
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("existing original Codespace required")
    if call(["git", "branch", "--show-current"]).stdout.strip() != BRANCH:
        raise Blocked("wrong isolated draft branch")
    private_dir(ROOT)
    orig = json.loads(call(["docker", "inspect", ORIGINAL]).stdout)[0]
    if (orig.get("Config", {}).get("Image") != ORIGINAL_IMAGE
            or orig.get("Path") != "docker-entrypoint.sh"
            or orig.get("HostConfig", {}).get("NetworkMode") != "none"
            or orig.get("State", {}).get("Status") != "exited"
            or orig.get("State", {}).get("Running")):
        raise Blocked("protected original QA container is not stopped or identity changed")
    backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backups) < 2:
        raise Blocked("two owner-only physical backups required")
    hashes = set()
    for d in backups:
        private_dir(d)
        tar, chk = d / "pgdata_original_stopped.tar", d / "pgdata_original_stopped.sha256"
        private_file(tar)
        private_file(chk)
        m = re.fullmatch(r"([0-9a-f]{64})  pgdata_original_stopped[.]tar",
                         chk.read_text(encoding="ascii").strip())
        if not m or digest(tar) != m.group(1):
            raise Blocked("protected original backup SHA mismatch")
        hashes.add(m.group(1))
    if len(hashes) != 1:
        raise Blocked("protected original backups diverged")

    runtimes = sorted(ROOT.glob("p0_recovery_runtime_*"))
    if len(runtimes) != 1:
        raise Blocked("expected one isolated third recovery copy")
    private_dir(runtimes[0])
    pg = runtimes[0] / "pgdata"
    private_dir(pg)
    if (pg / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("third PostgreSQL version invalid")
    if (pg / "postmaster.pid").exists():
        raise Blocked("third recovered PostgreSQL is not fully stopped")
    if any((pg / "pg_tblspc").iterdir()):
        raise Blocked("external tablespace reference in third copy")
    for name, literal in (
        ("postgresql.conf", "shared_preload_libraries = ''"),
        ("postgresql.conf", "listen_addresses = ''"),
        ("postgresql.conf", "max_worker_processes = 0"),
        ("postgresql.conf", "archive_mode = off"),
        ("postgresql.auto.conf", "# Third-copy only: inherited ALTER SYSTEM settings quarantined."),
    ):
        path = pg / name
        private_file(path)
        if literal not in path.read_text(encoding="ascii"):
            raise Blocked("hardened third configuration is not intact")
    old = json.loads(call(["docker", "inspect", RECOVERED]).stdout)[0]
    binds = [m for m in old.get("Mounts", []) if m.get("Type") == "bind"]
    if (old["State"].get("Running") or old["State"].get("Status") != "exited"
            or old["HostConfig"].get("NetworkMode") != "none"
            or len(binds) != 1 or binds[0].get("Source") != str(pg)):
        raise Blocked("prior isolated recovery container is not stopped/isolated")
    for oldname in (PREVIOUS_CENSUS,) + PREVIOUS_DIAGS:
        old = json.loads(call(["docker", "inspect", oldname]).stdout)[0]
        oldbinds = [m for m in old.get("Mounts", []) if m.get("Type") == "bind"]
        if (old.get("State", {}).get("Running")
                or old.get("State", {}).get("Status") != "exited"
                or old.get("HostConfig", {}).get("NetworkMode") != "none"
                or len(oldbinds) != 1 or oldbinds[0].get("Source") != str(pg)):
            raise Blocked("prior one-shot third-copy container not safely exited")
    if call(["docker", "container", "inspect", CENSUS], fail=False).returncode == 0:
        raise Blocked("new port-corrected catalog census already attempted; no retry")
    image = json.loads(call(["docker", "image", "inspect", IMAGE]).stdout)[0]
    ident = image.get("Id", "")
    if (image.get("Os") != "linux"
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", ident)):
        raise Blocked("cached PG17 binary image identity invalid")
    free = os.statvfs(pg)
    if free.f_bavail * free.f_frsize < 1024**3:
        raise Blocked("insufficient free private disk capacity")
    return pg, (orig["Id"], orig["State"].get("FinishedAt"), len(backups),
                next(iter(hashes)), ident)


def configured_port(pg):
    """Read the explicit isolated third-copy port; no fallback or raw value output."""
    port = None
    for name in ("postgresql.conf", "postgresql.auto.conf"):
        file = pg / name
        private_file(file)
        for line in file.read_text(encoding="ascii").splitlines():
            match = re.fullmatch(
                r"""\s*port\s*=\s*['"]?(\d{1,5})['"]?\s*(?:#.*)?""", line
            )
            if match:
                port = int(match.group(1))
    if port is None or not (1 <= port <= 65535) or port == 5432:
        raise Blocked("non-default isolated third-copy port not verified")
    return port


def load_allowed_sql(name):
    if name not in (STRUCT_SQL, PRIVATE_SQL):
        raise Blocked("unapproved catalog SQL file")
    sql = call(["git", "show", "FETCH_HEAD:" + name], timeout=12).stdout
    if len(sql) > 60000 or not sql.startswith("-- ALPHA HUNTER"):
        raise Blocked("unexpected SQL catalog source")
    text = "\n".join(line for line in sql.splitlines()
                     if not line.lstrip().startswith("--")).strip()
    if (not text.lower().startswith(("with ", "select "))
        or any(line.lstrip().startswith("\\") for line in text.splitlines())
        or re.search(r"\b(insert|update|delete|create|alter|drop|truncate|copy|do|call|grant|revoke)\b",
                     text, re.IGNORECASE)):
        raise Blocked("non-read-only catalog SQL source refused")
    return sql


def run_args(pg, image_id):
    uid, gid = os.geteuid(), os.getegid()
    # Peer authentication may not map owner UID to the DB's postgres role.
    # A temporary HBA policy on a container-private TMPFS permits ONLY local
    # socket login as postgres; NO host port, NO TCP listener, NO host socket.
    script = (
        "set -eu; "
        "printf '%s\\n' 'local all postgres trust' 'local all all reject' "
        "'host all all 0.0.0.0/0 reject' 'host all all ::/0 reject' "
        "> /tmp/p0_catalog_hba.conf; "
        "exec postgres -D " + PGDATA +
        " -c hba_file=/tmp/p0_catalog_hba.conf "
        " -c default_transaction_read_only=on"
    )
    return [
        "docker", "run", "-d", "--pull=never", "--name", CENSUS,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--memory", "512m", "--cpus", "1",
        "--stop-signal", "SIGINT",
        "--user", str(uid) + ":" + str(gid),
        "--env", "PGDATA=" + PGDATA,
        "--mount", "type=bind,source=" + str(pg) + ",target=" + PGDATA,
        "--tmpfs", "/var/run/postgresql:rw,nosuid,size=16m,uid=" +
            str(uid) + ",gid=" + str(gid) + ",mode=0700",
        "--tmpfs", "/tmp:rw,nosuid,size=32m,uid=" +
            str(uid) + ",gid=" + str(gid) + ",mode=0700",
        "--entrypoint", "/bin/sh", image_id, "-c", script,
    ]


def runtime_check(pg):
    x = json.loads(call(["docker", "inspect", CENSUS]).stdout)[0]
    hc = x["HostConfig"]
    mounts = x.get("Mounts", [])
    bind = [m for m in mounts if m.get("Type") == "bind"]
    if (hc.get("NetworkMode") != "none"
        or not hc.get("ReadonlyRootfs")
        or "ALL" not in [str(s).upper() for s in (hc.get("CapDrop") or [])]
        or hc.get("PortBindings")
        or len(bind) != 1
        or bind[0].get("Source") != str(pg)
        or bind[0].get("Destination") != PGDATA
        or any(m.get("Type") not in ("bind", "tmpfs") for m in mounts)
        or x.get("Config", {}).get("User") != str(os.geteuid()) + ":" + str(os.getegid())):
        raise Blocked("actual census container runtime isolation mismatch")
    return x


def psql_sql(db, sql, port):
    if db not in ("postgres", DB):
        raise Blocked("unexpected offline PostgreSQL database name")
    inp = "SET default_transaction_read_only=on;\nBEGIN READ ONLY;\n" + sql + "\nCOMMIT;\n"
    args = [
        "docker", "exec", "-i", "--user", str(os.geteuid()) + ":" + str(os.getegid()),
        "-e", "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=30000",
        CENSUS, "psql", "-X", "-q", "-A", "-t", "-F", "|",
        "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-h",
        "/var/run/postgresql", "-p", str(port), "-d", db,
    ]
    p = call(args, timeout=60, inp=inp, fail=False)
    if p.returncode:
        raise Blocked("isolated read-only catalog query failed; private diagnostics withheld")
    return [line.strip() for line in p.stdout.splitlines() if line.strip()]


def interpret_struct(lines):
    if not lines or len(lines[0].split("|")) != 13:
        raise Blocked("structural fingerprint returned an unexpected shape")
    fields = lines[0].split("|")
    if any(not re.fullmatch(r"\d+", x) for x in fields[:9]):
        raise Blocked("invalid structural census counts")
    counts_match = tuple(fields[:9]) == BASE_COUNTS
    hashes_match = tuple(fields[9:]) == BASE_HASHES
    ext = set(lines[1:])
    return {
        "table_count": fields[0], "trigger_count": fields[5],
        "indexes": fields[3],
        "counts_match": counts_match,
        "hashes_match": hashes_match,
        "extensions_match": ext == BASE_EXT,
        "extensions_observed": len(ext),
        "extension_mismatch_count": len(ext.symmetric_difference(BASE_EXT)),
    }


def interpret_private(lines):
    if not lines or len(lines[-1].split("|")) < 2:
        raise Blocked("private function census output missing")
    matched = BASE_FUNC.issubset(set(lines))
    trigger_zero = lines[-1].startswith("0|0|")
    return matched, trigger_zero


def log_ready():
    result = call(["docker", "logs", CENSUS], timeout=10, fail=False)
    raw = result.stdout + "\n" + result.stderr
    return ("database system is ready to accept connections" in raw,
            bool(re.search(r"\b(FATAL|PANIC)\b", raw)))


def stop_if_started():
    x = json.loads(call(["docker", "inspect", CENSUS]).stdout)[0]
    if x["State"].get("Running"):
        call(["docker", "stop", "--time", "45", CENSUS], timeout=55)


def verify_third_shutdown(pg, image_id):
    if (pg / "postmaster.pid").exists():
        raise Blocked("third catalog copy retained active postmaster PID")
    current = json.loads(call(["docker", "inspect", CENSUS]).stdout)[0]
    if current["State"].get("Running") or current["State"].get("Status") != "exited":
        raise Blocked("third catalog runtime not fully stopped")
    args = [
        "docker", "run", "--rm", "--pull=never", "--network", "none",
        "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", str(os.geteuid()) + ":" + str(os.getegid()),
        "--mount", "type=bind,source=" + str(pg) + ",target=/qa,readonly",
        "--entrypoint", "/bin/sh", image_id, "-c", "exec pg_controldata /qa",
    ]
    status = call(args, timeout=35).stdout
    if not re.search(r"(?m)^Database cluster state:\s*shut down\s*$", status):
        raise Blocked("isolated catalog runtime did not shut down cleanly")
    return True


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--approve-third-port-corrected-catalog-census"]):
        print("QA_USAGE=OPTIONAL_--approve-third-port-corrected-catalog-census")
        return 2
    print("QA_GATE=NEW_EXPLICIT_PORT_THIRD_COPY_CATALOG_CENSUS")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_ORIGINAL_SERVER_RESTART=NO")
    print("QA_REAL_ORDERS=DISABLED")
    started = False
    try:
        pg, before = preflight()
        port = configured_port(pg)
        print("QA_CATALOG_PORT_PREFLIGHT=PASS_NONDEFAULT")
        # Must ensure exact trusted read-only catalog query source exists
        # before any real third-copy server can launch.
        structural = load_allowed_sql(STRUCT_SQL)
        private = load_allowed_sql(PRIVATE_SQL)
        print("QA_SOURCE_CUSTODY=PASS")
        if not argv:
            print("QA_OWNER_APPROVAL=NOT_GIVEN")
            print("QA_THIRD_COPY_DATABASE_STARTED=NO")
            print("QA_NEXT_GATE=SEPARATE_OWNER_APPROVAL_PORT_CORRECTED_CATALOG_CENSUS")
            return 0

        print("QA_OWNER_APPROVAL=EXPLICIT_PORT_CORRECTED_THIRD_COPY_CATALOG_ONLY")
        started = True
        call(run_args(pg, before[4]), timeout=45)
        runtime_check(pg)
        ready = False
        for _ in range(45):
            ok, fatal = log_ready()
            if fatal:
                raise Blocked("isolated catalog server reported fatal error")
            state = runtime_check(pg)["State"]
            if ok:
                ready = True
                break
            if not state.get("Running"):
                break
            time.sleep(2)
        if not ready:
            raise Blocked("isolated third-copy catalog server did not become ready")

        db_exists = psql_sql("postgres",
            "SELECT count(*) FROM pg_database WHERE datname='" + DB + "';", port)
        if db_exists != ["1"]:
            print("QA_RESTORED_AUTHENTIC_QA_DATABASE=NOT_FOUND")
            raise Blocked("expected private QA database not present in recovered third copy")
        s = interpret_struct(psql_sql(DB, structural, port))
        funcs_match, private_trigs_zero = interpret_private(psql_sql(DB, private, port))
        stop_if_started()
        verify_third_shutdown(pg, before[4])
        started = False

        after_pg, after = preflight_after(pg)
        if after != before or after_pg != pg:
            raise Blocked("protected original or backups changed during census")
        print("QA_THIRD_COPY_READ_ONLY_CATALOG_CENSUS=COMPLETED")
        print("QA_RESTORED_AUTHENTIC_QA_DATABASE=FOUND")
        print("QA_PUBLIC_APPLICATION_TABLES=" + s["table_count"])
        print("QA_PUBLIC_APPLICATION_TRIGGERS=" + s["trigger_count"])
        print("QA_PUBLIC_APPLICATION_INDEXES=" + s["indexes"])
        print("QA_NOV8_BASELINE_COUNTS=" + ("MATCH" if s["counts_match"] else "MISMATCH"))
        print("QA_NOV8_BASELINE_DIGESTS=" + ("MATCH" if s["hashes_match"] else "MISMATCH"))
        print("QA_NOV8_EXTENSION_IDENTITIES=" + ("MATCH" if s["extensions_match"] else "MISMATCH"))
        print("QA_EXTENSION_MISMATCH_COUNT=" + str(s["extension_mismatch_count"]))
        print("QA_NOV8_FUNCTION_CUSTODY=" + ("MATCH" if funcs_match else "MISMATCH"))
        print("QA_PRIVATE_SCHEMA_TRIGGER_BASELINE=" +
              ("MATCH" if private_trigs_zero else "MISMATCH"))
        is_parity = all((s["counts_match"], s["hashes_match"], s["extensions_match"],
                         funcs_match, private_trigs_zero))
        print("QA_RECOVERED_THIRD_VS_NOV8_BASELINE=" + ("MATCH" if is_parity else "MISMATCH_REVIEW_REQUIRED"))
        print("QA_CURRENT_PRODUCTION_SCHEMA_PARITY=NOT_YET_VERIFIED")
        print("QA_THIRD_COPY_POST_STOP_CONTROL_STATE=SHUT_DOWN_VERIFIED")
        print("QA_30_50_61_BENCHMARKS=NOT_PERFORMED")
        print("QA_DBA_SECURITY_SIGNOFF=NOT_YET_GRANTED")
        print("QA_ORIGINAL_SERVER=STILL_STOPPED")
        print("QA_ORIGINAL_BACKUPS_SHA256_VERIFIED=" + str(before[2]))
        print("QA_RELEASE=NO_GO")
        return 0 if is_parity else 3
    except (Blocked, KeyError, ValueError, OSError, TypeError) as e:
        if started:
            try:
                stop_if_started()
            except Exception:
                print("QA_THIRD_COPY_STOP=MANUAL_REVIEW_REQUIRED")
        print("QA_CATALOG_CENSUS=BLOCKED_" + (
            str(e).upper().replace(" ", "_")[:100] if isinstance(e, Blocked)
            else "LOCAL_PRIVATE_INSPECTION_ERROR"
        ))
        print("QA_ORIGINAL_SERVER=DO_NOT_START")
        print("QA_RELEASE=NO_GO")
        return 2


def preflight_after(pg):
    # No re-start. Recheck only protected original and backups. Old recovered
    # container remains stopped; named census container now exists, so do not
    # call startup preflight again.
    orig = json.loads(call(["docker", "inspect", ORIGINAL]).stdout)[0]
    b = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    all_sha = {digest(d / "pgdata_original_stopped.tar") for d in b}
    img = json.loads(call(["docker", "image", "inspect", IMAGE]).stdout)[0]
    after = (orig["Id"], orig["State"].get("FinishedAt"),
             len(b), next(iter(all_sha)) if len(all_sha) == 1 else "MISMATCH",
             img["Id"])
    return pg, after


if __name__ == "__main__":
    sys.exit(main())
