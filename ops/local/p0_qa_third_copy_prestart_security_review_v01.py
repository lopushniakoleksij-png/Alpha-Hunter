#!/usr/bin/env python3
"""P0 A3: static security/identity review of THIRD hardened private PG17 tree.

Only runs in the existing owner-authorised Codespace on the unmerged repair
branch. Read-only: never launches a container or PostgreSQL server, changes
files, removes a PID, contacts production, runs SQL, or prints secret config.
A PASS here is NOT approval to start the server, proof of crash recovery,
or independent DBA/security review.
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
RUNTIME_IMAGE = "postgres:17"
CONF = ("postgresql.conf", "postgresql.auto.conf", "pg_hba.conf", "pg_ident.conf")
INHERITED = ("postmaster.pid",) + CONF
REQUIRED_DIRS = ("base", "global", "pg_wal", "pg_xact", "pg_multixact", "pg_tblspc")

SAFE_CONFIG = {
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


def run(args, timeout=25):
    try:
        return subprocess.run(
            args, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=timeout
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise Blocked("local read-only environment inspection unavailable") from None


def digest(path):
    out = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            out.update(chunk)
    return out.hexdigest()


def require_dir(path):
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise Blocked("owner-only private directory required")


def require_file(path):
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise Blocked("owner-only private regular file required")


def environment():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Blocked("existing owner-authorised Codespace required")
    if run(["git", "branch", "--show-current"]).strip() != BRANCH:
        raise Blocked("wrong repair branch")
    if os.geteuid() == 0:
        raise Blocked("root identity not permitted for owner-only review")
    require_dir(ROOT)
    original = json.loads(run(["docker", "inspect", ORIGINAL]))[0]
    if (original.get("Config", {}).get("Image") != ORIGINAL_IMAGE
        or original.get("Path") != "docker-entrypoint.sh"
        or original.get("HostConfig", {}).get("NetworkMode") != "none"
        or original.get("HostConfig", {}).get("RestartPolicy", {}).get("Name") not in ("no", "")
        or original.get("State", {}).get("Running")
        or original.get("State", {}).get("Status") != "exited"):
        raise Blocked("protected original container identity/stopped-state mismatch")
    return original["Id"], original["State"].get("FinishedAt")


def custody():
    backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backups) < 2:
        raise Blocked("two protected PostgreSQL TAR copies required")
    digests = set()
    for folder in backups:
        require_dir(folder)
        archive, sha = folder / "pgdata_original_stopped.tar", folder / "pgdata_original_stopped.sha256"
        require_file(archive)
        require_file(sha)
        m = re.fullmatch(
            r"([0-9a-f]{64})  pgdata_original_stopped[.]tar",
            sha.read_text(encoding="ascii").strip(),
        )
        if not m or digest(archive) != m.group(1):
            raise Blocked("protected backup SHA-256 verification failed")
        digests.add(m.group(1))
    if len(digests) != 1:
        raise Blocked("protected backup copies differ")
    return len(backups)


def staged_trees():
    stages = sorted(ROOT.glob("p0_recovery_stage_*"))
    thirds = sorted(ROOT.glob("p0_recovery_runtime_*"))
    if len(stages) != 1 or len(thirds) != 1:
        raise Blocked("exactly one first stage and one third copy required")
    source, third = stages[0], thirds[0]
    for d in (source, third, source / "pgdata", third / "pgdata"):
        require_dir(d)
    original_pg, third_pg = source / "pgdata", third / "pgdata"
    if original_pg.resolve() == third_pg.resolve():
        raise Blocked("third copy unexpectedly aliases first stage")
    vault = third / ".p0_prestart_saved"
    require_dir(vault)
    return original_pg, third_pg, vault


def inspect_tree(source, third, vault):
    if (third / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("hardened third copy is not PostgreSQL 17")
    for d in REQUIRED_DIRS:
        require_dir(third / d)
    if any((third / "pg_tblspc").iterdir()):
        raise Blocked("hardened third copy has external tablespace references")
    if (third / "postmaster.pid").exists():
        raise Blocked("hardened third-copy stale PID still active")
    for flag in ("standby.signal", "recovery.signal", "backup_label", "tablespace_map"):
        if (third / flag).exists():
            raise Blocked("unexpected replication/recovery/backup marker present")

    # Ensure quarantined originals still match first stage; NEVER read out
    # or print original config values, names of host paths or PID payload.
    for name in INHERITED:
        older = source / name
        saved = vault / (name + ".third_original")
        require_file(older)
        require_file(saved)
        if digest(older) != digest(saved):
            raise Blocked("quarantined original does not match source staging")
    if len(list(vault.iterdir())) != len(INHERITED):
        raise Blocked("unexpected additional private vault entries")

    for name, safe in SAFE_CONFIG.items():
        f = third / name
        require_file(f)
        if f.read_bytes() != safe.encode("ascii"):
            raise Blocked("hardened configuration differs from strict offline policy")

    for name in ("PG_VERSION", "global/pg_control"):
        original, current = source / name, third / name
        require_file(original)
        require_file(current)
        if digest(original) != digest(current):
            raise Blocked("third-copy protected PostgreSQL marker changed")

    wal = 0
    file_count = 0
    for base, dirs, files in os.walk(third, followlinks=False):
        here = Path(base)
        require_dir(here)
        for name in dirs:
            require_dir(here / name)
        for name in files:
            item = here / name
            require_file(item)
            file_count += 1
            if file_count > 100000:
                raise Blocked("unexpectedly large PG17 recovery tree")
            if here == third / "pg_wal" and re.fullmatch(r"[0-9A-F]{24}", name):
                wal += 1
    if wal < 1:
        raise Blocked("no checkpoint WAL segments present in hardened copy")
    return file_count, wal


def runtime_image():
    payload = json.loads(run(["docker", "image", "inspect", RUNTIME_IMAGE]))
    if len(payload) != 1:
        raise Blocked("expected one locally cached PostgreSQL 17 image")
    im = payload[0]
    if im.get("Os") != "linux" or im.get("Architecture") not in ("amd64", "arm64"):
        raise Blocked("unsupported cached runtime image platform")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", im.get("Id", "")):
        raise Blocked("cached runtime image ID invalid")
    # A Docker tag or image ID does not prove its PG binary's version or trust.
    return im.get("Architecture"), bool(im.get("RepoDigests"))


def main():
    print("QA_GATE=THIRD_COPY_STATIC_RUNTIME_SECURITY_REVIEW")
    print("QA_ORIGINAL_POSTGRES_RESTART=NO")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_SERVER_STARTED=NO")
    try:
        before = environment()
        count = custody()
        source, third, vault = staged_trees()
        files, wal = inspect_tree(source, third, vault)
        arch, has_repo_digest = runtime_image()
        if environment() != before or custody() != count:
            raise Blocked("protected source/backup custody changed")
        print("QA_THIRD_COPY_STATIC_POLICY=PASS")
        print("QA_THIRD_COPY_REGULAR_FILES=" + str(files))
        print("QA_THIRD_COPY_WAL_SEGMENTS=" + str(wal))
        print("QA_THIRD_COPY_NO_STALE_PID=PASS")
        print("QA_THIRD_COPY_QUARANTINED_CONFIGS=5_MATCH_STAGE")
        print("QA_THIRD_COPY_NO_PRELOAD_NO_TCP_CONFIG=PASS")
        print("QA_THIRD_COPY_EXTERNAL_TABLESPACES=0")
        print("QA_RUNTIME_IMAGE_CACHED=YES")
        print("QA_RUNTIME_IMAGE_PLATFORM=linux/" + arch)
        print("QA_RUNTIME_IMAGE_REPO_DIGEST_PRESENT=" + ("YES" if has_repo_digest else "NO_REVIEW"))
        print("QA_RUNTIME_PG_BINARY_VERSION=NOT_EXECUTED")
        print("QA_DOCKER_NETWORK_ISOLATION=NOT_RUNTIME_TESTED")
        print("QA_CRASH_RECOVERY=NOT_PERFORMED")
        print("QA_OWNER_SERVER_START_AUTHORISED=NO")
        print("QA_ORIGINAL_CONTAINER=STILL_STOPPED")
        print("QA_PRIVATE_BACKUPS_SHA256_VERIFIED=" + str(count))
        print("QA_NEXT_GATE=OFFLINE_RUNTIME_IMAGE_BINARY_AND_SECURITY_APPROVAL")
        return 0
    except (Blocked, KeyError, ValueError, OSError, TypeError) as e:
        print("QA_THIRD_COPY_STATIC_POLICY=BLOCKED_" + (
            str(e).upper().replace(" ", "_")[:100]
            if isinstance(e, Blocked) else "PRIVATE_RUNTIME_REVIEW_ERROR"
        ))
        print("QA_OWNER_SERVER_START_AUTHORISED=NO")
        print("QA_ORIGINAL_CONTAINER_RESTART=NO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
