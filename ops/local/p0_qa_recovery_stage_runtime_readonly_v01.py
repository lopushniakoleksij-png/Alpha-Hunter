#!/usr/bin/env python3
"""P0 A3: owner-only read-only preflight of a STAGED PG17 recovery copy.

Does NOT modify any file, remove postmaster.pid, start PostgreSQL, use network,
connect to Supabase, run Docker containers, perform WAL replay or restore.
Prints booleans / counts only, NEVER data paths, config values or private SQL.
Original stopped QA container and two private TAR backups stay protected.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / ".alpha-hunter-private-dbqa"
ORIGINAL = "alpha-hunter-private-postgres17-qa"
BRANCH = "fix/supabase-write-timeout-qa"
IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"
REQUIRED_DIRS = ("base", "global", "pg_wal", "pg_xact", "pg_multixact")
SIGNALS = ("postmaster.pid", "postmaster.opts", "backup_label",
           "tablespace_map", "standby.signal", "recovery.signal")
CONFIGS = ("postgresql.conf", "postgresql.auto.conf", "pg_hba.conf",
           "pg_ident.conf")


class Blocked(Exception):
    pass


def run(args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=True, timeout=15
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise Blocked("original private environment inspection failed") from None


def environment_guard():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Blocked("existing private Codespace is required")
    if run(["git", "branch", "--show-current"]).strip() != BRANCH:
        raise Blocked("wrong branch")
    if ROOT.is_symlink() or not ROOT.is_dir() or ROOT.stat().st_mode & 0o777 != 0o700:
        raise Blocked("unsafe private recovery directory")

    c = json.loads(run(["docker", "inspect", ORIGINAL]))[0]
    if (c["Config"].get("Image") != IMAGE
            or c.get("Path") != "docker-entrypoint.sh"
            or c["HostConfig"].get("NetworkMode") != "none"
            or c["State"].get("Status") != "exited"
            or c["State"].get("Running")):
        raise Blocked("original QA state or identity changed")
    return c


def find_staged():
    roots = sorted(ROOT.glob("p0_recovery_stage_*"))
    if len(roots) != 1:
        raise Blocked("expected exactly one isolated recovery stage")
    base = roots[0]
    if base.is_symlink() or not base.is_dir() or base.stat().st_mode & 0o777 != 0o700:
        raise Blocked("unsafe isolated stage root")
    pgdata = base / "pgdata"
    if pgdata.is_symlink() or not pgdata.is_dir() or pgdata.stat().st_mode & 0o777 != 0o700:
        raise Blocked("unsafe staged PGDATA directory")
    # Fail closed if any symlink exists: external tablespaces may not have
    # been captured; avoid following any untrusted private path.
    total = 0
    for dirpath, dirs, files in os.walk(pgdata, followlinks=False):
        here = Path(dirpath)
        if here.is_symlink():
            raise Blocked("symlink directory in staged cluster")
        for name in dirs + files:
            total += 1
            if total > 200000:
                raise Blocked("unbounded staged cluster inventory")
            if (here / name).is_symlink():
                raise Blocked("linked staged PostgreSQL object")
    return pgdata


def stage_classification(pgdata):
    if (pgdata / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("wrong staged PG version")
    control = pgdata / "global" / "pg_control"
    if not control.is_file() or not (128 <= control.stat().st_size <= 65536):
        raise Blocked("staged pg_control missing or invalid size")
    missing = [d for d in REQUIRED_DIRS if not (pgdata / d).is_dir()]
    if missing:
        raise Blocked("required PostgreSQL subdirectory missing")
    wal_count = sum(1 for p in (pgdata / "pg_wal").iterdir()
                    if p.is_file() and re.fullmatch(r"[0-9A-F]{24}", p.name))
    if not wal_count:
        raise Blocked("staged WAL segments missing")
    signal_flags = {name: (pgdata / name).is_file() for name in SIGNALS}
    config_flags = {name: (pgdata / name).is_file() for name in CONFIGS}
    tablespace_entry_count = sum(1 for _ in (pgdata / "pg_tblspc").iterdir()) \
        if (pgdata / "pg_tblspc").is_dir() else None
    return wal_count, signal_flags, config_flags, tablespace_entry_count


def main():
    print("QA_RUNTIME_PREFLIGHT=READ_ONLY_STAGE_ONLY")
    print("QA_ORIGINAL_CONTAINER_RESTART=NOT_AUTHORISED")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_DATABASE_STARTED=NO")
    try:
        original = environment_guard()
        stage = find_staged()
        wal_count, signals, configs, tablespace_count = stage_classification(stage)
        # Check again after scanning, so a now-running original is not treated
        # as a valid preflight.
        environment_guard()
        print("QA_RECOVERY_STAGE_CLUSTER_FILES=PASS")
        print("QA_STAGED_WAL_SEGMENTS=" + str(wal_count))
        for name, present in signals.items():
            print("QA_STAGE_" + name.upper().replace(".", "_") +
                  "=" + ("PRESENT" if present else "ABSENT"))
        for name, present in configs.items():
            print("QA_STAGE_" + name.upper().replace(".", "_") +
                  "=" + ("PRESENT" if present else "ABSENT"))
        print("QA_STAGE_TABLESPACE_ENTRIES=" +
              (str(tablespace_count) if tablespace_count is not None else "MISSING_REVIEW"))
        cmd_args = original.get("Config", {}).get("Cmd") or []
        has_external_config_hint = any("config_file" in str(x) for x in cmd_args)
        print("QA_ORIGINAL_RUNTIME_CONFIG_OVERRIDE=" +
              ("PRESENT_REVIEW" if has_external_config_hint else "NOT_IN_CMD"))
        print("QA_STALE_POSTMASTER_PID=" +
              ("PRESENT_DO_NOT_DELETE" if signals["postmaster.pid"] else "ABSENT"))
        if not configs["postgresql.conf"]:
            print("QA_RUNTIME_CONFIG_CUSTODY=EXTERNAL_OR_ABSENT_REVIEW_REQUIRED")
        else:
            print("QA_RUNTIME_CONFIG_CUSTODY=LOCAL_CONFIG_PRESENT_REVIEW_REQUIRED")
        print("QA_STAGE_PROCESS_OWNERSHIP=NOT_YET_VALIDATED_FOR_SERVER")
        print("QA_CRASH_RECOVERY=NOT_PERFORMED")
        print("QA_NEXT_GATE=REVIEW_ISOLATION_CONFIG_PID_AND_OFFLINE_RECOVERY_PLAN")
        print("QA_ORIGINAL_CONTAINER=STILL_STOPPED")
        print("QA_RESTART_ALLOWED=NO")
        return 0
    except (Blocked, OSError, ValueError, TypeError, KeyError) as exc:
        print("QA_RUNTIME_PREFLIGHT_RESULT=BLOCKED_" + (
            str(exc).upper().replace(" ", "_")[:90]
            if isinstance(exc, Blocked) else "INSPECTION_FAILURE"
        ))
        print("QA_ORIGINAL_CONTAINER_RESTART=NO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
