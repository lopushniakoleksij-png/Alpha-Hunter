#!/usr/bin/env python3
"""P0 A3 — one controlled crash recovery on THIRD disposable private PG17 copy.

OWNER must explicitly pass --approve-third-copy-recovery in their original,
authorised Codespace. Default invocation is a READ-ONLY plan. No production,
scanner, trade, deployment, migration, new spend or original PG17 restart.

Execution, when explicitly approved, starts one isolated postgres:17 SERVER
against ONLY the independently hardened THIRD COPY, with --network none,
no published ports, nonroot UID, no Docker socket, no inherited environment,
no preloads/cron, and a read-only container root filesystem. Data writes
occur solely inside the third copy. The server is gracefully stopped, and
pg_controldata is read offline for an initial physical-recovery result.

This is NOT permission for production release or a full physical/SQL/schema
certification. Never copy private file contents or logs into a public repo.
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
IMAGE = "postgres:17"
CONTAINER = "ah-p0-third-crash-recovery-once"
INSIDE_PGDATA = "/var/lib/postgresql/data"
MAX_WAIT_S = 120
EXPECTED = {
    "postgresql.conf": """# Alpha Hunter P0 disposable third-copy only; not production.
listen_addresses = ''
port = 65432
unix_socket_directories = '/var/run/postgresql'
shared_preload_libraries = ''
max_worker_processes = 0
autovacuum = off
archive_mode = off
archive_command = ''
max_wal_senders = 0
hot_standby = off
ssl = off
logging_collector = off
fsync = on
full_page_writes = on
max_connections = 10
""",
    "postgresql.auto.conf": "# Third-copy only: inherited ALTER SYSTEM settings quarantined.\n",
    "pg_hba.conf": ("# Third-copy only: local OS peer identity, all TCP rejected.\n"
                    "local all all peer\n"
                    "host all all 0.0.0.0/0 reject\n"
                    "host all all ::/0 reject\n"),
    "pg_ident.conf": "# Third-copy only: no inherited identity mapping.\n",
}


class Blocked(Exception):
    pass


def cmd(args, timeout=35, allow_failure=False):
    try:
        r = subprocess.run(args, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise Blocked("isolated local operation failed") from None
    if r.returncode and not allow_failure:
        raise Blocked("isolated local operation returned failure")
    return r


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_dir(path):
    if (path.is_symlink() or not path.is_dir()
            or stat.S_IMODE(path.stat().st_mode) != 0o700):
        raise Blocked("unsafe owner-private directory")


def safe_file(path):
    if (path.is_symlink() or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o600):
        raise Blocked("unsafe owner-private regular file")


def preflight():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Blocked("owner's original Codespace required")
    if cmd(["git", "branch", "--show-current"]).stdout.strip() != BRANCH:
        raise Blocked("protected isolated repair branch required")
    if os.geteuid() == 0:
        raise Blocked("root execution refused")
    safe_dir(ROOT)
    original = json.loads(cmd(["docker", "inspect", ORIGINAL]).stdout)[0]
    if (original.get("Config", {}).get("Image") != ORIGINAL_IMAGE
        or original.get("Path") != "docker-entrypoint.sh"
        or original.get("HostConfig", {}).get("NetworkMode") != "none"
        or original.get("State", {}).get("Status") != "exited"
        or original.get("State", {}).get("Running")):
        raise Blocked("original private PostgreSQL server identity/state changed")
    backup_dirs = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backup_dirs) < 2:
        raise Blocked("two unchanged original physical backups required")
    hashes = set()
    for folder in backup_dirs:
        safe_dir(folder)
        tar = folder / "pgdata_original_stopped.tar"
        chk = folder / "pgdata_original_stopped.sha256"
        safe_file(tar)
        safe_file(chk)
        match = re.fullmatch(
            r"([0-9a-f]{64})  pgdata_original_stopped[.]tar",
            chk.read_text(encoding="ascii").strip(),
        )
        if not match or digest(tar) != match.group(1):
            raise Blocked("original physical backup checksum mismatch")
        hashes.add(match.group(1))
    if len(hashes) != 1:
        raise Blocked("original backups diverged")
    stages = sorted(ROOT.glob("p0_recovery_stage_*"))
    thirds = sorted(ROOT.glob("p0_recovery_runtime_*"))
    if len(stages) != 1 or len(thirds) != 1:
        raise Blocked("exactly one protected stage and one disposable third copy required")
    stage, third_root = stages[0], thirds[0]
    for folder in (stage, third_root, stage / "pgdata", third_root / "pgdata",
                   third_root / ".p0_prestart_saved"):
        safe_dir(folder)
    pg = third_root / "pgdata"
    if pg.resolve() == (stage / "pgdata").resolve():
        raise Blocked("third copy aliases original protected stage")
    if pg.stat().st_uid != os.geteuid():
        raise Blocked("third-copy PGDATA not owned by Codespace UID")
    if (pg / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("wrong PostgreSQL version in third copy")
    if (pg / "postmaster.pid").exists():
        raise Blocked("third-copy stale postmaster PID remains")
    if list((pg / "pg_tblspc").iterdir()):
        raise Blocked("external tablespaces not permitted")
    for name, value in EXPECTED.items():
        target = pg / name
        safe_file(target)
        if target.read_bytes() != value.encode("ascii"):
            raise Blocked("third-copy hardened configuration differs from approved baseline")
    for name in ("standby.signal", "recovery.signal", "backup_label", "tablespace_map"):
        if (pg / name).exists():
            raise Blocked("unexpected third-copy recovery or backup signal")
    for name in ("postmaster.pid",) + tuple(EXPECTED):
        old = stage / "pgdata" / name
        saved = third_root / ".p0_prestart_saved" / (name + ".third_original")
        safe_file(old)
        safe_file(saved)
        if digest(old) != digest(saved):
            raise Blocked("quarantined inherited original differs from stage")
    segment_names = [
        p for p in (pg / "pg_wal").iterdir()
        if p.is_file() and re.fullmatch(r"[0-9A-F]{24}", p.name)
    ]
    if len(segment_names) < 1:
        raise Blocked("third-copy WAL absent")
    # Prohibit reusing an existing recovery container or generating a second
    # recovery attempt on the same third copy without manual evidence review.
    existing = cmd(["docker", "container", "inspect", CONTAINER], allow_failure=True)
    if existing.returncode == 0:
        raise Blocked("recovery container already exists; automatic retry forbidden")
    image = json.loads(cmd(["docker", "image", "inspect", IMAGE]).stdout)[0]
    if not (image.get("Os") == "linux"
            and image.get("Architecture") in ("amd64", "arm64")
            and re.fullmatch(r"sha256:[a-f0-9]{64}", image.get("Id", ""))):
        raise Blocked("cached postgres:17 image identity invalid")
    if os.statvfs(pg).f_bavail * os.statvfs(pg).f_frsize < 2*1024**3:
        raise Blocked("insufficient free disk headroom for crash recovery")
    source_signature = (original["Id"], original["State"].get("FinishedAt"),
                        len(backup_dirs), next(iter(hashes)), image["Id"])
    return pg, source_signature


def launch_args(pg):
    user = str(os.geteuid()) + ":" + str(os.getegid())
    uid, gid = os.geteuid(), os.getegid()
    # Only the third COPY is bind mounted RW; no original stage, no backups.
    # Shell is an explicit fixed entrypoint, not the image's initialization.
    return [
        "docker", "run", "-d", "--name", CONTAINER, "--pull=never",
        "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "512m", "--cpus", "1",
        "--stop-signal", "SIGINT",
        "--user", user, "--env", "PGDATA=" + INSIDE_PGDATA,
        "--mount", "type=bind,source=" + str(pg) + ",target=" + INSIDE_PGDATA,
        "--tmpfs", "/var/run/postgresql:rw,nosuid,size=16m,uid=" +
            str(uid) + ",gid=" + str(gid) + ",mode=0700",
        "--tmpfs", "/tmp:rw,nosuid,size=64m,uid=" +
            str(uid) + ",gid=" + str(gid) + ",mode=0700",
        "--entrypoint", "/bin/sh", IMAGE,
        "-c", "exec postgres -D " + INSIDE_PGDATA,
    ]


def runtime_policy(pg):
    obj = json.loads(cmd(["docker", "container", "inspect", CONTAINER]).stdout)[0]
    hc = obj["HostConfig"]
    mounts = obj["Mounts"]
    if (hc.get("NetworkMode") != "none"
        or not hc.get("ReadonlyRootfs")
        or "ALL" not in hc.get("CapDrop", [])
        or "no-new-privileges" not in hc.get("SecurityOpt", [])
        or hc.get("PortBindings")
        or len(mounts) != 1
        or mounts[0].get("Type") != "bind"
        or mounts[0].get("Source") != str(pg)
        or mounts[0].get("Destination") != INSIDE_PGDATA
        or not mounts[0].get("RW")
        or obj["Config"].get("User") != str(os.geteuid()) + ":" + str(os.getegid())):
        raise Blocked("third-copy actual runtime isolation policy mismatch")
    return obj


def log_flags():
    raw = cmd(["docker", "logs", CONTAINER], timeout=10, allow_failure=True).stdout
    # Never print raw PostgreSQL logs, which may include private settings.
    return {
        "ready": "database system is ready to accept connections" in raw,
        "redo": "redo starts at" in raw or "automatic recovery in progress" in raw,
        "redo_done": "redo done" in raw or "database system was interrupted" not in raw,
        "fatal": bool(re.search(r"\b(FATAL|PANIC)\b", raw)),
    }


def stop_if_running():
    obj = json.loads(cmd(["docker", "container", "inspect", CONTAINER]).stdout)[0]
    if obj["State"].get("Running"):
        # Never docker kill the original server: this exact identifier is
        # used only for the third-copy disposable recovery container.
        cmd(["docker", "stop", "--time", "45", CONTAINER], timeout=55)


def offline_control(pg):
    args = [
        "docker", "run", "--rm", "--pull=never", "--network", "none",
        "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", str(os.geteuid()) + ":" + str(os.getegid()),
        "--mount", "type=bind,source=" + str(pg) + ",target=/qa,readonly",
        "--entrypoint", "/bin/sh", IMAGE, "-c", "exec pg_controldata /qa",
    ]
    raw = cmd(args, timeout=30).stdout
    m = re.search(r"(?m)^Database cluster state:\s*(.+)$", raw)
    if not m:
        raise Blocked("offline PostgreSQL control state unreadable")
    return m.group(1).strip().lower()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--approve-third-copy-recovery"]):
        print("QA_USAGE=OPTIONAL_--approve-third-copy-recovery")
        return 2
    print("QA_SCOPE=THIRD_COPY_ONLY")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_ORIGINAL_SERVER_RESTART=NO")
    print("QA_BACKUPS_ORIGINAL_STAGE_MUTATION=NO")
    started = False
    try:
        pg, signature = preflight()
        print("QA_PREFLIGHT=PASS")
        print("QA_THIRD_COPY_ONLY_MOUNT=REVIEWED")
        print("QA_NETWORK_PLAN=DOCKER_NONE_NO_PORTS")
        if not argv:
            print("QA_APPROVAL=NOT_GIVEN")
            print("QA_DATABASE_SERVER_STARTED=NO")
            print("QA_NEXT_GATE=EXPLICIT_OWNER_APPROVAL_FLAG_FOR_THIRD_COPY_ONLY")
            return 0

        print("QA_APPROVAL=EXPLICIT_CLI_FLAG_THIRD_COPY_ONLY")
        cmd(launch_args(pg), timeout=45)
        started = True
        runtime_policy(pg)
        ready = False
        observed_redo = False
        fatal = False
        for _ in range(MAX_WAIT_S // 2):
            obs = log_flags()
            ready |= obs["ready"]
            observed_redo |= obs["redo"]
            fatal |= obs["fatal"]
            state = runtime_policy(pg)["State"]
            if ready or fatal or not state.get("Running"):
                break
            time.sleep(2)
        # Always stop the third-copy database before verifying physical state.
        stop_if_running()
        if not ready or fatal:
            raise Blocked("isolated server did not become ready without fatal errors")
        control = offline_control(pg)
        if control != "shut down":
            raise Blocked("isolated recovery copy did not complete clean shutdown")
        # Verify original source custody after writes occurred only on third.
        original = json.loads(cmd(["docker", "inspect", ORIGINAL]).stdout)[0]
        if (original["Id"], original["State"].get("FinishedAt")) != signature[:2]:
            raise Blocked("protected original container state changed")
        backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
        if len(backups) != signature[2]:
            raise Blocked("protected backup set changed")
        for folder in backups:
            if digest(folder / "pgdata_original_stopped.tar") != signature[3]:
                raise Blocked("protected physical backup changed")
        print("QA_CRASH_RECOVERY_RESULT=PASS_INITIAL_PHYSICAL_START_AND_SHUTDOWN")
        print("QA_POSTGRES_READY_OBSERVED=YES")
        print("QA_REDO_ACTIVITY_LOG_OBSERVED=" + ("YES" if observed_redo else "NO_REVIEW"))
        print("QA_POST_STOP_CLUSTER_STATE=SHUT_DOWN")
        print("QA_ORIGINAL_SERVER=STILL_STOPPED")
        print("QA_ORIGINAL_BACKUPS_SHA256_VERIFIED=" + str(signature[2]))
        print("QA_PHYSICAL_TABLE_INTEGRITY=NOT_CERTIFIED")
        print("QA_SCHEMA_PARITY=NOT_YET_VERIFIED")
        print("QA_30_50_61_BENCHMARKS=NOT_EXECUTED")
        print("QA_PRODUCTION_RELEASE=NO_GO")
        return 0
    except (Blocked, KeyError, ValueError, OSError, TypeError) as e:
        if started:
            try:
                stop_if_running()
            except Exception:
                print("QA_THIRD_COPY_STOP_STATUS=MANUAL_REVIEW_REQUIRED")
        print("QA_CRASH_RECOVERY_RESULT=BLOCKED_" + (
            str(e).upper().replace(" ", "_")[:90]
            if isinstance(e, Blocked) else "LOCAL_RUNTIME_ERROR"
        ))
        print("QA_PROTECTED_ORIGINAL=DO_NOT_START")
        print("QA_THIRD_COPY=RETAIN_FOR_PRIVATE_FORENSIC_REVIEW")
        print("QA_PRODUCTION_RELEASE=NO_GO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
