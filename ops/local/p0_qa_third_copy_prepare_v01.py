#!/usr/bin/env python3
"""P0 A3 — copy an offline PG17 cluster stage to a THIRD private disposable tree.

Owner-run ONLY in the original authorised Codespace; draft branch only.
Never starts a database, runs Docker containers, removes stale postmaster.pid,
edits PostgreSQL configuration, connects to production or changes protected
backups or the original stopped container.

The third copy is NOT safe to start until a separate no-network/no-cron
configuration review, owner authorisation and runtime isolation gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / ".alpha-hunter-private-dbqa"
BRANCH = "fix/supabase-write-timeout-qa"
ORIGINAL = "alpha-hunter-private-postgres17-qa"
ORIGINAL_IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"
CHECKSUM = "pgdata_original_stopped.sha256"
TAR_NAME = "pgdata_original_stopped.tar"
REQUIRED = ("PG_VERSION", "global/pg_control", "postmaster.pid")
REQUIRED_DIRS = ("base", "global", "pg_wal", "pg_xact", "pg_multixact")
MAX_FILES = 200000
MAX_BYTES = 2 * 1024**3


class Blocked(Exception):
    pass


def local(args):
    try:
        return subprocess.run(
            args, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise Blocked("local identity verification unavailable") from None


def source_identity():
    info = json.loads(local(["docker", "inspect", ORIGINAL]))[0]
    if (info.get("Config", {}).get("Image") != ORIGINAL_IMAGE
        or info.get("Path") != "docker-entrypoint.sh"
        or info.get("HostConfig", {}).get("NetworkMode") != "none"
        or info.get("HostConfig", {}).get("RestartPolicy", {}).get("Name")
            not in ("no", "")
        or info.get("State", {}).get("Status") != "exited"
        or info.get("State", {}).get("Running")):
        raise Blocked("original container is not known stopped offline QA")
    return info["Id"], info["State"].get("FinishedAt")


def sha256_file(p):
    h = hashlib.sha256()
    with p.open("rb") as file:
        for b in iter(lambda: file.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def backup_guard():
    backups = sorted(ROOT.glob("p0_original_stopped_cluster_*"))
    if len(backups) < 2:
        raise Blocked("two protected physical TAR backups required")
    checksums = set()
    for folder in backups:
        if not folder.is_dir() or folder.is_symlink() or stat.S_IMODE(folder.stat().st_mode) != 0o700:
            raise Blocked("unsafe physical backup directory")
        tar, sha = folder / TAR_NAME, folder / CHECKSUM
        for item in (tar, sha):
            if not item.is_file() or item.is_symlink() or stat.S_IMODE(item.stat().st_mode) != 0o600:
                raise Blocked("unsafe private physical backup file")
        match = re.fullmatch(
            r"([0-9a-f]{64})  pgdata_original_stopped[.]tar",
            sha.read_text(encoding="ascii").strip(),
        )
        if not match or sha256_file(tar) != match.group(1):
            raise Blocked("physical backup checksum mismatch")
        checksums.add(match.group(1))
    if len(checksums) != 1:
        raise Blocked("original physical backups differ")
    return len(backups)


def private_root():
    if (os.getenv("CODESPACES") != "true"
        or os.getenv("GITHUB_ACTIONS") == "true"
        or local(["git", "branch", "--show-current"]).strip() != BRANCH):
        raise Blocked("original Codespace and draft repair branch only")
    if (ROOT.is_symlink() or not ROOT.is_dir()
        or stat.S_IMODE(ROOT.stat().st_mode) != 0o700):
        raise Blocked("owner-private directory is missing or unsafe")


def single_stage():
    stage_roots = sorted(ROOT.glob("p0_recovery_stage_*"))
    if len(stage_roots) != 1:
        raise Blocked("expected exactly one verified extracted recovery stage")
    top = stage_roots[0]
    pg = top / "pgdata"
    for d in (top, pg):
        if (d.is_symlink() or not d.is_dir()
            or stat.S_IMODE(d.stat().st_mode) != 0o700):
            raise Blocked("unsafe extracted recovery stage")
    if (pg / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("wrong staged PostgreSQL version")
    for key in REQUIRED:
        p = pg / key
        if not p.is_file() or p.is_symlink() or not p.stat().st_size:
            raise Blocked("missing recovery staging marker")
    for d in REQUIRED_DIRS:
        if not (pg / d).is_dir() or (pg / d).is_symlink():
            raise Blocked("incomplete staged PostgreSQL directory")
    if list(ROOT.glob("p0_recovery_runtime_*")):
        raise Blocked("third runtime copy already exists; do not create duplicate")
    return pg


def file_inventory(pg):
    """Read-only tree manifest; rejects symlinks and devices before copying."""
    manifest = {}
    dirs_seen = []
    bytes_seen = 0
    for folder, dirs, files in os.walk(pg, followlinks=False):
        base = Path(folder)
        if base.is_symlink():
            raise Blocked("symlink in offline recovery stage")
        dirs.sort()
        files.sort()
        if stat.S_IMODE(base.stat().st_mode) != 0o700:
            raise Blocked("untrusted staged directory permissions")
        dirs_seen.append(base.relative_to(pg))
        for name in dirs:
            p = base / name
            if p.is_symlink() or not p.is_dir():
                raise Blocked("stage contains unexpected directory object")
        for name in files:
            p = base / name
            if p.is_symlink() or not p.is_file():
                raise Blocked("stage contains symlink or unusual file type")
            if stat.S_IMODE(p.stat().st_mode) != 0o600:
                raise Blocked("unsafe staged file permission")
            bytes_seen += p.stat().st_size
            if bytes_seen > MAX_BYTES or len(manifest) >= MAX_FILES:
                raise Blocked("source stage larger than permitted")
            manifest[p.relative_to(pg)] = (p.stat().st_size, sha256_file(p))
    if not manifest or "postmaster.pid" not in {str(x) for x in manifest}:
        raise Blocked("original inherited PID marker missing from stage")
    return manifest, dirs_seen, bytes_seen


def copy_verified(pg, target, inventory, directories):
    """Create a new tree; verify each file against original stage SHA-256."""
    target.mkdir(mode=0o700)
    for d in directories:
        if d.parts:
            (target / d).mkdir(mode=0o700, parents=True, exist_ok=False)
    for rel, (size, digest) in inventory.items():
        src, dst = pg / rel, target / rel
        # Exclusive creation, no symlink following. Source was preflighted.
        fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as out, src.open("rb") as source:
            shutil.copyfileobj(source, out, 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        if dst.stat().st_size != size or sha256_file(dst) != digest:
            raise Blocked("independent runtime copy differs from staged recovery tree")
    # Also catch source modification during the copy.
    again, _, _ = file_inventory(pg)
    if again != inventory:
        raise Blocked("original staged tree changed during third-copy preparation")
    return len(inventory)


def main():
    print("QA_MODE=THIRD_OWNER_PRIVATE_RECOVERY_COPY")
    print("QA_PRODUCTION_ACCESS=NONE")
    print("QA_ORIGINAL_QA_RESTART=NO")
    print("QA_POSTGRES_SERVER_STARTED=NO")
    print("QA_INHERITED_POSTMASTER_PID=NOT_REMOVED")
    try:
        private_root()
        stopped_before = source_identity()
        n_backups = backup_guard()
        pg = single_stage()
        manifest, directories, source_bytes = file_inventory(pg)
        if shutil.disk_usage(ROOT).free < max(2 * 1024**3, source_bytes * 4):
            raise Blocked("insufficient private headroom for separate runtime copy")
        name = "p0_recovery_runtime_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") \
            + "_" + uuid.uuid4().hex[:8]
        folder = ROOT / name
        folder.mkdir(mode=0o700)
        result = copy_verified(pg, folder / "pgdata", manifest, directories)
        if source_identity() != stopped_before:
            raise Blocked("original stopped container changed during copy")
        if n_backups != backup_guard():
            raise Blocked("original protected backups changed during copy")
        print("QA_THIRD_RECOVERY_COPY=PASS")
        print("QA_THIRD_COPY_FILES=" + str(result))
        print("QA_THIRD_COPY_BYTES=" + str(source_bytes))
        print("QA_STAGED_SOURCE_HASHES_MATCH=YES")
        print("QA_PHYSICAL_BACKUP_COPIES_SHA256_VERIFIED=" + str(n_backups))
        print("QA_ORIGINAL_QA=STILL_STOPPED")
        print("QA_COPY_CONFIG_SANITISED=NO")
        print("QA_BACKGROUND_CRON_DISABLED=NOT_YET")
        print("QA_CRASH_RECOVERY_PERFORMED=NO")
        print("QA_THIRD_COPY_START_AUTHORISED=NO")
        print("QA_NEXT_GATE=THIRD_COPY_SAFE_CONFIG_AND_PID_PRESTART_REVIEW")
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError) as err:
        print("QA_THIRD_RECOVERY_COPY=BLOCKED_" + (
            str(err).upper().replace(" ", "_")[:90] if isinstance(err, Blocked)
            else "PRIVATE_INSPECTION_FAILURE"
        ))
        print("QA_PARTIAL_THIRD_COPY_IF_ANY=KEEP_PRIVATE_FOR_REVIEW")
        print("QA_ORIGINAL_QA_RESTART=NO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
