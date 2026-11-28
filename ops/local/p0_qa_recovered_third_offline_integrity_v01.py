#!/usr/bin/env python3
"""Alpha Hunter P0 A3: offline recovered-THIRD-copy PG17 page checksum check.

Owner runs ONLY in existing authorised private Codespace on isolated branch.
Requires original container stopped, two SHA-identical private TAR backups,
a previously recovered but now STOPPED third-copy container, and its sole
PGDATA bind mount. Invokes only pg_controldata and, if enabled, pg_checksums
--check in a networkless utility with read-only mount and root filesystem.
Never starts any PostgreSQL server, changes PGDATA/checksum setting, touches
original backups, queries production, deploys, merges, trades or spends.

LIMITATIONS: data checksums may be disabled; pg_checksums never certifies all
database relations, index semantics or full schema parity; no real benchmarks.
"""
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
RECOVERY = "ah-p0-third-crash-recovery-once"
IMAGE = "postgres:17"
INSIDE_PGDATA = "/var/lib/postgresql/data"


class Blocked(Exception):
    pass


def shell(args, timeout=40):
    try:
        proc = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        raise Blocked("local offline utility not available") from None
    return proc


def successful(args, timeout=30):
    p = shell(args, timeout=timeout)
    if p.returncode:
        raise Blocked("offline local prerequisite returned failure")
    return p.stdout


def checksum_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def require_dir(p):
    if p.is_symlink() or not p.is_dir() or stat.S_IMODE(p.stat().st_mode) != 0o700:
        raise Blocked("private directory missing or unsafe")


def require_file(p):
    if p.is_symlink() or not p.is_file() or stat.S_IMODE(p.stat().st_mode) != 0o600:
        raise Blocked("private file missing or unsafe")


def custody():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Blocked("owner's existing private Codespace required")
    if successful(["git", "branch", "--show-current"]).strip() != BRANCH:
        raise Blocked("isolated repair branch required")
    require_dir(ROOT)
    original = json.loads(successful(["docker", "inspect", ORIGINAL]))[0]
    if (original.get("Config", {}).get("Image") != ORIGINAL_IMAGE
            or original.get("Path") != "docker-entrypoint.sh"
            or original.get("HostConfig", {}).get("NetworkMode") != "none"
            or original.get("State", {}).get("Status") != "exited"
            or original.get("State", {}).get("Running")):
        raise Blocked("original protected PG17 container state/identity changed")

    backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backups) < 2:
        raise Blocked("expected two owner-private physical backups")
    hashes = set()
    for d in backups:
        require_dir(d)
        archive, recorded = d / "pgdata_original_stopped.tar", d / "pgdata_original_stopped.sha256"
        require_file(archive)
        require_file(recorded)
        m = re.fullmatch(
            r"([a-f0-9]{64})  pgdata_original_stopped[.]tar",
            recorded.read_text(encoding="ascii").strip(),
        )
        if not m or checksum_file(archive) != m.group(1):
            raise Blocked("private original backup checksum failure")
        hashes.add(m.group(1))
    if len(hashes) != 1:
        raise Blocked("original backup copies diverged")

    dirs = sorted(ROOT.glob("p0_recovery_runtime_*"))
    if len(dirs) != 1:
        raise Blocked("expected exactly one recovered third copy")
    require_dir(dirs[0])
    pg = dirs[0] / "pgdata"
    require_dir(pg)
    if (pg / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("third-copy PG17 marker invalid")
    if (pg / "postmaster.pid").exists():
        raise Blocked("third-copy PID exists: database may be running")
    if any((pg / "pg_tblspc").iterdir()):
        raise Blocked("external tablespaces require separate review")
    control_file = pg / "global" / "pg_control"
    require_file(control_file)

    image = json.loads(successful(["docker", "image", "inspect", IMAGE]))[0]
    ident = image.get("Id", "")
    if (image.get("Os") != "linux" or
            not re.fullmatch(r"sha256:[a-f0-9]{64}", ident)):
        raise Blocked("cached PG17 image identity invalid")
    completed = json.loads(successful(["docker", "inspect", RECOVERY]))[0]
    hc = completed["HostConfig"]
    binds = [m for m in completed.get("Mounts", []) if m.get("Type") == "bind"]
    if (completed.get("State", {}).get("Running")
            or completed.get("State", {}).get("Status") != "exited"
            or completed.get("Config", {}).get("Image") not in (IMAGE, ident)
            or hc.get("NetworkMode") != "none"
            or not hc.get("ReadonlyRootfs")
            or hc.get("PortBindings")
            or len(binds) != 1
            or binds[0].get("Source") != str(pg)
            or binds[0].get("Destination") != INSIDE_PGDATA):
        raise Blocked("third-copy recovered container shutdown/isolation mismatch")
    return (
        (original["Id"], original["State"].get("FinishedAt")),
        len(backups),
        next(iter(hashes)),
        str(pg),
        ident,
        completed["Id"],
    )


def utility(image_id, pgdata, program):
    assert program in ("pg_controldata", "pg_checksums")
    args = [
        "docker", "run", "--rm", "--pull=never", "--network", "none",
        "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "32", "--memory", "256m",
        "--user", str(os.geteuid()) + ":" + str(os.getegid()),
        "--mount", "type=bind,source=" + pgdata + ",target=/qa,readonly",
        "--entrypoint", "/bin/sh", image_id, "-c",
        ("exec pg_controldata /qa" if program == "pg_controldata"
         else "exec pg_checksums --check -D /qa"),
    ]
    return shell(args, timeout=180 if program == "pg_checksums" else 30)


def interpret_control(stdout):
    st = re.search(r"(?m)^Database cluster state:\s*(.+?)\s*$", stdout)
    ck = re.search(r"(?m)^Data page checksum version:\s*(\d+)\s*$", stdout)
    if not st or not ck:
        raise Blocked("offline PG control state or checksum metadata missing")
    state = st.group(1).strip().lower()
    if state != "shut down":
        raise Blocked("recovered third copy was not cleanly shut down")
    version = int(ck.group(1))
    if version not in (0, 1):
        raise Blocked("unexpected data page checksum version")
    return version


def interpret_checksums(p):
    if p.returncode:
        raise Blocked("offline pg_checksums check failed; private diagnostics withheld")
    # PG17 reports 'Bad checksums: 0' on successful verification.
    # A zero exit code is the authoritative result; no raw output printed.
    return True


def main():
    print("QA_GATE=RECOVERED_THIRD_COPY_OFFLINE_PHYSICAL_CHECK")
    print("QA_ORIGINAL_DATABASE_RESTART=NO")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_POSTGRES_SERVER_STARTED=NO")
    try:
        before = custody()
        control = utility(before[4], before[3], "pg_controldata")
        if control.returncode:
            raise Blocked("offline control inspection failed")
        checksums_version = interpret_control(control.stdout)
        if checksums_version == 1:
            verify = utility(before[4], before[3], "pg_checksums")
            interpret_checksums(verify)
            print("QA_DATA_CHECKSUMS=ENABLED")
            print("QA_OFFLINE_PAGE_CHECKSUM_CHECK=PASS")
        else:
            print("QA_DATA_CHECKSUMS=DISABLED")
            print("QA_OFFLINE_PAGE_CHECKSUM_CHECK=NOT_AVAILABLE")
        if custody() != before:
            raise Blocked("original container/backup/recovered copy identity changed")
        print("QA_THIRD_COPY_CONTROL_STATE=SHUT_DOWN")
        print("QA_THIRD_COPY_SERVER_RESTART=NO")
        print("QA_ORIGINAL_CONTAINER=STILL_STOPPED")
        print("QA_ORIGINAL_BACKUPS_SHA256_VERIFIED=" + str(before[1]))
        print("QA_HEAP_INDEX_LOGICAL_INTEGRITY=NOT_CERTIFIED")
        print("QA_SCHEMA_PARITY=NOT_YET_VERIFIED")
        print("QA_BENCHMARK_30_50_61=NOT_EXECUTED")
        print("QA_NEXT_GATE=READ_ONLY_AUTHENTIC_SCHEMA_AND_TABLE_CUSTODY_COMPARISON")
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError) as e:
        msg = str(e).upper().replace(" ", "_")[:90] if isinstance(e, Blocked) else "INSPECTION_ERROR"
        print("QA_OFFLINE_INTEGRITY=BLOCKED_" + msg)
        print("QA_ORIGINAL_DATABASE_RESTART=NO")
        print("QA_PRODUCTION_RELEASE=NO_GO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
