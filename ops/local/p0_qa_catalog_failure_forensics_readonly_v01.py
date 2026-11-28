#!/usr/bin/env python3
"""P0 owner-only READ-ONLY post-failure census inspection (no server startup).

For the original authorised Codespace and isolated draft branch only.
Verifies the protected original container and two matching private backups.
Checks the previously created third-copy catalog container's stopped state,
bind/network policy, third-copy PID, and server logs (category-only).

NO database starts, Docker exec, Docker run, SQL, productions connections,
container stop/restart/delete, original/stage/backup write, config modification,
raw PostgreSQL logs or private values printed.

Prior psql client stderr was discarded. If no evidence exists in SERVER logs,
report UNKNOWN, not an invented root cause or schema mismatch.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / ".alpha-hunter-private-dbqa"
BRANCH = "fix/supabase-write-timeout-qa"
ORIGINAL = "alpha-hunter-private-postgres17-qa"
ORIGINAL_IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"
CENSUS = "ah-p0-third-catalog-census-once"
INSIDE_PGDATA = "/var/lib/postgresql/data"
MAX_LOG_BYTES = 2_000_000


class Blocked(Exception):
    pass


def command(args, *, timeout=25, ok=True):
    try:
        p = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise Blocked("local owner-only inspection command unavailable") from None
    if ok and p.returncode != 0:
        raise Blocked("local owner-only inspection command failed")
    return p


def private_dir(p):
    if p.is_symlink() or not p.is_dir() or stat.S_IMODE(p.stat().st_mode) != 0o700:
        raise Blocked("owner-only directory missing or unsafe")


def private_file(p):
    if p.is_symlink() or not p.is_file() or stat.S_IMODE(p.stat().st_mode) != 0o600:
        raise Blocked("owner-only file missing or unsafe")


def sha256(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def custody():
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("existing authorised Codespace required")
    if command(["git", "branch", "--show-current"]).stdout.strip() != BRANCH:
        raise Blocked("isolated repair branch required")
    private_dir(ROOT)
    orig = json.loads(command(["docker", "inspect", ORIGINAL]).stdout)[0]
    if (orig.get("Config", {}).get("Image") != ORIGINAL_IMAGE
            or orig.get("Path") != "docker-entrypoint.sh"
            or orig.get("HostConfig", {}).get("NetworkMode") != "none"
            or orig.get("State", {}).get("Status") != "exited"
            or orig.get("State", {}).get("Running")):
        raise Blocked("original private PostgreSQL identity/offline status changed")
    backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backups) < 2:
        raise Blocked("two original private backups required")
    hashes = set()
    for folder in backups:
        private_dir(folder)
        archive, sha = folder / "pgdata_original_stopped.tar", folder / "pgdata_original_stopped.sha256"
        private_file(archive)
        private_file(sha)
        m = re.fullmatch(
            r"([0-9a-f]{64})  pgdata_original_stopped[.]tar",
            sha.read_text(encoding="ascii").strip(),
        )
        if not m or sha256(archive) != m.group(1):
            raise Blocked("protected physical backup checksum mismatch")
        hashes.add(m.group(1))
    if len(hashes) != 1:
        raise Blocked("original physical backups not identical")
    third = sorted(ROOT.glob("p0_recovery_runtime_*"))
    if len(third) != 1:
        raise Blocked("third recovery directory identity ambiguous")
    private_dir(third[0])
    pg = third[0] / "pgdata"
    private_dir(pg)
    if (pg / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("third-copy PostgreSQL version mismatch")
    census = json.loads(command(["docker", "inspect", CENSUS]).stdout)[0]
    mounts = [m for m in census.get("Mounts", []) if m.get("Type") == "bind"]
    hc = census.get("HostConfig", {})
    if (hc.get("NetworkMode") != "none"
            or not hc.get("ReadonlyRootfs")
            or hc.get("PortBindings")
            or len(mounts) != 1
            or mounts[0].get("Source") != str(pg)
            or mounts[0].get("Destination") != INSIDE_PGDATA):
        raise Blocked("past catalog container was not fully isolated")
    return orig, len(backups), pg, census


def log_classification(raw):
    """No raw log bytes or private SQL content are returned."""
    if len(raw.encode("utf-8", errors="ignore")) > MAX_LOG_BYTES:
        return "SERVER_LOG_TOO_LARGE_UNCLASSIFIED"
    if re.search(r"database [\"']?[^\"'\s]+[\"']? does not exist", raw, re.I):
        return "SERVER_DATABASE_MISSING"
    if re.search(r"role [\"']?[^\"'\s]+[\"']? does not exist", raw, re.I):
        return "SERVER_ROLE_MISSING"
    if re.search(r"no pg_hba.conf entry|password authentication failed|peer authentication failed",
                 raw, re.I):
        return "SERVER_AUTHENTICATION_REJECTED"
    if re.search(r"permission denied|could not open file", raw, re.I):
        return "SERVER_PERMISSION_OR_FILE_PROBLEM"
    if re.search(r"\bPANIC\b", raw):
        return "SERVER_PANIC"
    if re.search(r"\bFATAL\b", raw):
        return "SERVER_FATAL_OTHER_REVIEW"
    return "SERVER_NO_CLASSIFYING_ERROR_OBSERVED"


def main():
    print("QA_GATE=PRIOR_FAILED_CATALOG_READ_ONLY_FORENSICS")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_POSTGRES_SERVER_STARTED=NO")
    print("QA_DOCKER_RUN_OR_EXEC=NONE")
    print("QA_RECOVERY_RESTART_AUTHORISED=NO")
    try:
        orig, copies, pg, census = custody()
        state = census.get("State", {})
        if state.get("Running") or state.get("Status") != "exited":
            print("QA_CENSUS_CONTAINER_STATE=NOT_STOPPED_MANUAL_REVIEW_REQUIRED")
            print("QA_NEXT_GATE=STOPPED_CONTAINER_SAFETY_REVIEW")
            return 2
        if (pg / "postmaster.pid").exists():
            print("QA_THIRD_COPY_POSTMASTER_PID=PRESENT_DO_NOT_REMOVE")
            print("QA_NEXT_GATE=PRIVATELY_INSPECT_RUNNING_PROCESS_STATE")
            return 2
        logs = command(["docker", "logs", CENSUS], timeout=12, ok=False)
        category = log_classification(logs.stdout + "\n" + logs.stderr)
        # Never expose raw logs, role identifiers, DB names or SQL text.
        print("QA_CENSUS_CONTAINER_STATE=EXITED")
        print("QA_THIRD_COPY_POSTMASTER_PID=ABSENT")
        print("QA_PRIOR_SERVER_LOG_CLASS=" + category)
        print("QA_PRIOR_CLIENT_PSQL_STDERR=NOT_RETAINED")
        print("QA_PSQL_QUERY_FAILURE_ROOT_CAUSE=NOT_YET_VERIFIED")
        print("QA_CATALOG_SQL_RETURN_CODE=PREVIOUS_NONZERO")
        print("QA_CURRENT_PRODUCTION_PARITY=NOT_YET_VERIFIED")
        print("QA_ORIGINAL_SERVER=STILL_STOPPED")
        print("QA_ORIGINAL_BACKUPS_SHA256_VERIFIED=" + str(copies))
        print("QA_AUTO_RETRY=NOT_AUTHORISED")
        print("QA_NEXT_GATE=OWNER_APPROVED_NEW_SINGLE_SHOT_SANITISED_PSQL_DIAGNOSTIC")
        return 0
    except (Blocked, OSError, TypeError, ValueError, KeyError) as e:
        code = str(e).upper().replace(" ", "_")[:95] if isinstance(e, Blocked) else "PRIVATE_ERROR"
        print("QA_FORENSICS=BLOCKED_" + code)
        print("QA_AUTO_RETRY=NOT_AUTHORISED")
        return 2


if __name__ == "__main__":
    sys.exit(main())
