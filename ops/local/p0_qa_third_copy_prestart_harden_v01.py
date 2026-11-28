#!/usr/bin/env python3
"""P0 A3 — harden only the THIRD private PostgreSQL 17 crash-recovery copy.

OWNER RUN in the EXISTING authorised Codespace on draft branch only.
Never runs PostgreSQL/Docker containers, removes any protected original
file, changes original stopped container / first stage / backup archives,
connects to production, or initiates crash recovery.

This stage quarantines the inherited PID and the FOUR original config files
in a private subdirectory INSIDE the disposable third-copy directory, then
writes restrictive server config. Not approval for PostgreSQL startup.
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
CONF_FILES = ("postgresql.conf", "postgresql.auto.conf", "pg_hba.conf", "pg_ident.conf")
INHERITED = ("postmaster.pid",) + CONF_FILES
DIRS = ("base", "global", "pg_wal", "pg_xact", "pg_multixact", "pg_tblspc")
MAX_CONFIG_SIZE = 2 * 1024**2

# Offline recovery policy, not an arbitrary inherited/production config.
# No preloaded extensions, external network listener, scheduler background
# worker, archive command, replication sender or autovacuum workers.
SAFE_POSTGRES = """# Alpha Hunter P0 disposable third-copy only; not production.
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
"""
SAFE_AUTO = "# Third-copy only: inherited ALTER SYSTEM settings quarantined.\n"
SAFE_HBA = ("# Third-copy only: local OS peer identity, all TCP rejected.\n"
            "local all all peer\n"
            "host all all 0.0.0.0/0 reject\n"
            "host all all ::/0 reject\n")
SAFE_IDENT = "# Third-copy only: no inherited identity mapping.\n"
SAFE_FILES = dict(zip(CONF_FILES, (SAFE_POSTGRES, SAFE_AUTO, SAFE_HBA, SAFE_IDENT)))


class Blocked(Exception):
    pass


def shell(args):
    try:
        return subprocess.run(
            args, check=True, capture_output=True, text=True, timeout=20
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise Blocked("local Codespace identity check failed") from None


def safe_dir(path):
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise Blocked("private directory permissions or type invalid")


def safe_regular(path):
    if (path.is_symlink() or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o600):
        raise Blocked("private file permissions or type invalid")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def original_state():
    c = json.loads(shell(["docker", "inspect", ORIGINAL]))[0]
    if (c["Config"].get("Image") != ORIGINAL_IMAGE
            or c.get("Path") != "docker-entrypoint.sh"
            or c["HostConfig"].get("NetworkMode") != "none"
            or c["HostConfig"].get("RestartPolicy", {}).get("Name") not in ("no", "")
            or c["State"].get("Status") != "exited"
            or c["State"].get("Running")):
        raise Blocked("original private PostgreSQL container no longer stopped/isolated")
    return c["Id"], c["State"].get("FinishedAt")


def private_preflight():
    if (os.environ.get("CODESPACES") != "true"
            or os.environ.get("GITHUB_ACTIONS") == "true"
            or shell(["git", "branch", "--show-current"]).strip() != BRANCH):
        raise Blocked("existing authorised Codespace and isolated repair branch required")
    safe_dir(ROOT)


def backup_protection():
    backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backups) < 2:
        raise Blocked("two original private backups required")
    hashes = set()
    for d in backups:
        safe_dir(d)
        archive = d / "pgdata_original_stopped.tar"
        checksum = d / "pgdata_original_stopped.sha256"
        safe_regular(archive)
        safe_regular(checksum)
        m = re.fullmatch(
            r"([0-9a-f]{64})  pgdata_original_stopped[.]tar",
            checksum.read_text(encoding="ascii").strip(),
        )
        if not m or digest(archive) != m.group(1):
            raise Blocked("original backup integrity check failed")
        hashes.add(m.group(1))
    if len(hashes) != 1:
        raise Blocked("private backup copies are not identical")
    return len(backups)


def paths_preflight():
    staged = sorted(ROOT.glob("p0_recovery_stage_*"))
    runtimes = sorted(ROOT.glob("p0_recovery_runtime_*"))
    if len(staged) != 1 or len(runtimes) != 1:
        raise Blocked("exactly one stage and one third copy required")
    srcroot, dstroot = staged[0], runtimes[0]
    for p in (srcroot, dstroot, srcroot / "pgdata", dstroot / "pgdata"):
        safe_dir(p)
    source, target = srcroot / "pgdata", dstroot / "pgdata"
    if source.resolve() == target.resolve():
        raise Blocked("third copy unexpectedly aliases the stage")
    if (dstroot / ".p0_prestart_saved").exists():
        raise Blocked("third-copy prestart changes already applied")
    for d in DIRS:
        for p in (source / d, target / d):
            safe_dir(p)
    if list((target / "pg_tblspc").iterdir()):
        raise Blocked("external tablespaces present: stop for custody review")
    if (target / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("third copy is not PostgreSQL 17")
    for relative in ("PG_VERSION", "global/pg_control") + INHERITED:
        a, b = source / relative, target / relative
        safe_regular(a)
        safe_regular(b)
        if a.stat().st_size != b.stat().st_size or digest(a) != digest(b):
            raise Blocked("inherited third-copy input differs from stage")
    for name in CONF_FILES:
        if (target / name).stat().st_size > MAX_CONFIG_SIZE:
            raise Blocked("oversized third-copy inherited config")
    if any((target / name).is_symlink() for name in INHERITED):
        raise Blocked("untrusted third-copy symlink")
    return srcroot, dstroot, target


def write_exclusive(path, body):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())


def harden_third_copy(target, dstroot):
    """Never touches protected backup or original stage. Fail-closed on rerun."""
    vault = dstroot / ".p0_prestart_saved"
    vault.mkdir(mode=0o700)
    # Quarantine inherited files in the THIRD copy. Preserve exact bytes.
    for name in INHERITED:
        src = target / name
        saved = vault / (name + ".third_original")
        original_bytes = src.read_bytes()
        write_exclusive(saved, original_bytes)
        if digest(src) != digest(saved):
            raise Blocked("quarantined config/PID failed integrity check")
    # All original configuration/PID bytes now exist privately in THIRD
    # vault. Only THIRD files below are replaced/removed.
    for name in INHERITED:
        (target / name).unlink()
    for name, content in SAFE_FILES.items():
        write_exclusive(target / name, content.encode("ascii"))
    if (target / "postmaster.pid").exists():
        raise Blocked("third-copy inherited PID not quarantined")
    for name, content in SAFE_FILES.items():
        if (target / name).read_bytes() != content.encode("ascii"):
            raise Blocked("restricted third-copy config verification failed")
    if not (target / "global" / "pg_control").is_file():
        raise Blocked("third-copy PostgreSQL control file disappeared")
    return len(INHERITED)


def main():
    print("QA_GATE=THIRD_COPY_NO_NETWORK_NO_CRON_PRESTART_HARDENING")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_POSTGRES_SERVER_STARTED=NO")
    print("QA_ORIGINAL_CONTAINER_RESTART=NO")
    try:
        private_preflight()
        original_before = original_state()
        backup_count = backup_protection()
        _, dstroot, target = paths_preflight()
        saved = harden_third_copy(target, dstroot)
        if original_state() != original_before or backup_protection() != backup_count:
            raise Blocked("protected source custody changed")
        print("QA_THIRD_COPY_RESTRICTIVE_CONFIG=PASS")
        print("QA_THIRD_COPY_INHERITED_FILES_QUARANTINED=" + str(saved))
        print("QA_THIRD_COPY_STALE_PID=QUARANTINED_ON_THIRD_ONLY")
        print("QA_THIRD_COPY_SHARED_PRELOAD_LIBRARIES=EMPTY")
        print("QA_THIRD_COPY_CRON_WORKER=NO_SHARED_PRELOAD")
        print("QA_THIRD_COPY_ARCHIVE_MODE=OFF")
        print("QA_THIRD_COPY_TCP_LISTEN=DISABLED_IN_CONFIG")
        print("QA_DOCKER_NETWORK_NONE=NOT_YET_TESTED_AT_RUNTIME")
        print("QA_ORIGINAL_PHYSICAL_BACKUPS_SHA256_VERIFIED=" + str(backup_count))
        print("QA_ORIGINAL_CONTAINER=STILL_STOPPED")
        print("QA_CRASH_RECOVERY=NOT_PERFORMED")
        print("QA_DATABASE_RUNTIME_START_AUTHORISED=NO")
        print("QA_NEXT_GATE=ISOLATED_THIRD_COPY_RUNTIME_IMAGE_AND_SECURITY_REVIEW")
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError) as e:
        print("QA_THIRD_COPY_RESTRICTIVE_CONFIG=BLOCKED_" + (
            str(e).upper().replace(" ", "_")[:90]
            if isinstance(e, Blocked) else "PRIVATE_CONFIGURATION_FAILURE"
        ))
        print("QA_PARTIAL_THIRD_COPY=DO_NOT_START_OR_DELETE_REVIEW_PRIVATELY")
        print("QA_ORIGINAL_CONTAINER_RESTART=NO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
