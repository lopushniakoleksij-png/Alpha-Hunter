#!/usr/bin/env python3
"""One-shot offline non-server PG17 binary/network probe for Alpha Hunter P0.

Existing authorised private Codespace and draft branch only. Does NOT start
PostgreSQL, mount PGDATA, connect to production or modify protected backups.
Runs a short-lived shell, postgres --version and loopback-interface test in a
cached postgres:17 image with Docker --network none, --read-only, no mounts.
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
IMAGE = "postgres:17"


class Blocked(Exception):
    pass


def run(args, timeout=30):
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, timeout=timeout, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        raise Blocked("offline local utility failed or was refused") from None


def private_dir(d):
    if d.is_symlink() or not d.is_dir() or stat.S_IMODE(d.stat().st_mode) != 0o700:
        raise Blocked("private directory is missing/unsafe")


def private_file(f):
    if f.is_symlink() or not f.is_file() or stat.S_IMODE(f.stat().st_mode) != 0o600:
        raise Blocked("private file missing/unsafe")


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_custody():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Blocked("existing authorised Codespace only")
    if run(["git", "branch", "--show-current"]).strip() != BRANCH:
        raise Blocked("isolated repair branch required")
    private_dir(ROOT)
    original = json.loads(run(["docker", "inspect", ORIGINAL]))[0]
    if (original.get("Config", {}).get("Image") != ORIGINAL_IMAGE
        or original.get("Path") != "docker-entrypoint.sh"
        or original.get("HostConfig", {}).get("NetworkMode") != "none"
        or original.get("State", {}).get("Status") != "exited"
        or original.get("State", {}).get("Running")):
        raise Blocked("original PG17 state/identity changed")
    backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backups) < 2:
        raise Blocked("need two protected private backups")
    digests = set()
    for folder in backups:
        private_dir(folder)
        tar = folder / "pgdata_original_stopped.tar"
        check = folder / "pgdata_original_stopped.sha256"
        private_file(tar)
        private_file(check)
        match = re.fullmatch(r"([a-f0-9]{64})  pgdata_original_stopped[.]tar",
                             check.read_text(encoding="ascii").strip())
        if not match or sha(tar) != match.group(1):
            raise Blocked("original private backup checksum mismatch")
        digests.add(match.group(1))
    if len(digests) != 1:
        raise Blocked("original private backup copies have diverged")
    third = sorted(ROOT.glob("p0_recovery_runtime_*"))
    if len(third) != 1:
        raise Blocked("expected precisely one third recovery copy")
    private_dir(third[0])
    pgdata = third[0] / "pgdata"
    private_dir(pgdata)
    if (pgdata / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("third copy is not PostgreSQL 17")
    if (pgdata / "postmaster.pid").exists():
        raise Blocked("third-copy stale postmaster PID has not been quarantined")
    if any((pgdata / "pg_tblspc").iterdir()):
        raise Blocked("unexpected external tablespaces")
    config = pgdata / "postgresql.conf"
    private_file(config)
    text = config.read_text(encoding="ascii")
    for required in ("listen_addresses = ''", "shared_preload_libraries = ''",
                     "max_worker_processes = 0", "archive_mode = off",
                     "fsync = on"):
        if required not in text:
            raise Blocked("third copy missing required safe recovery setting")
    image = json.loads(run(["docker", "image", "inspect", IMAGE]))[0]
    if (image.get("Os") != "linux"
        or image.get("Architecture") not in ("amd64", "arm64")
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", image.get("Id", ""))):
        raise Blocked("cached utility PG17 image identity not recognised")
    return original["Id"], original["State"].get("FinishedAt"), len(backups), image["Id"]


def offline_command():
    payload = (
        "set -eu; "
        "postgres --version; "
        "set -- /sys/class/net/*; "
        'test "$#" -eq 1; '
        'test "$(basename "$1")" = "lo"; '
        "printf 'QA_LOOPBACK_ONLY=YES\n'"
    )
    return [
        "docker", "run", "--rm", "--pull=never", "--network", "none",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "32", "--memory", "128m",
        "--user", "65534:65534", "--entrypoint", "/bin/sh",
        IMAGE, "-c", payload,
    ]


def parse_probe(text):
    if not re.search(r"(?m)^postgres \(PostgreSQL\) 17(?:\.\d+)?(?:\s|$)", text):
        raise Blocked("cached PG binary not confirmed as PostgreSQL 17")
    if text.splitlines().count("QA_LOOPBACK_ONLY=YES") != 1:
        raise Blocked("offline utility did not confirm loopback-only network")
    return True


def main():
    print("QA_GATE=ONE_OFF_NO_DATABASE_BINARY_AND_DOCKER_NETWORK_PROBE")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_ORIGINAL_QA_RESTART=NO")
    print("QA_PRIVATE_PGDATA_MOUNTS=NONE")
    print("QA_POSTGRES_SERVER_STARTED=NO")
    try:
        before = verify_custody()
        result = run(offline_command(), timeout=45)
        parse_probe(result)
        if verify_custody() != before:
            raise Blocked("original container/backups/image changed during utility")
        print("QA_UTILITY_BINARY=POSTGRESQL_17_PASS")
        print("QA_UTILITY_NO_NETWORK=LOOPBACK_ONLY_PASS")
        print("QA_UTILITY_ROOTFS=READ_ONLY")
        print("QA_UTILITY_PRIVILEGES=DROPPED")
        print("QA_ORIGINAL_BACKUPS_SHA256_VERIFIED=" + str(before[2]))
        print("QA_ORIGINAL_QA=STILL_STOPPED")
        print("QA_THIRD_COPY_DATABASE_RUNTIME=NOT_STARTED")
        print("QA_THIRD_COPY_SERVER_NETWORK=NOT_YET_TESTED")
        print("QA_CRASH_RECOVERY=NOT_PERFORMED")
        print("QA_DATABASE_START_AUTHORISED=NO")
        print("QA_NEXT_GATE=APPROVE_CONTROLLED_THIRD_COPY_CRASH_RECOVERY_PLAN")
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError) as exc:
        why = str(exc).upper().replace(" ", "_")[:90] if isinstance(exc, Blocked) else "LOCAL_ERROR"
        print("QA_UTILITY_PROBE=BLOCKED_" + why)
        print("QA_DATABASE_START_AUTHORISED=NO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
