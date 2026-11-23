#!/usr/bin/env python3
"""Owner-run P0 A2 recovery: back up a stopped original private PG17 cluster.

Runs ONLY inside the existing authorised private GitHub Codespace on the
isolated draft branch. Copies original stopped-container PGDATA to a new
owner-only private TAR outside the Git worktree and checks readable TAR
headers + payloads, required PostgreSQL markers, and SHA-256.

NEVER runs docker start/run/restart/commit/exec, SQL, Supabase, migrations,
backfill, production-scanner operations, or writes to original PGDATA.
This is a stopped-filesystem copy, NOT proof of PostgreSQL consistency,
archive restoratability, complete tablespace custody, or DBA approval.
"""
import hashlib
import io
import json
import os
import posixpath
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

NAME = "alpha-hunter-private-postgres17-qa"
BRANCH = "fix/supabase-write-timeout-qa"
IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"
ROOT = Path.home() / ".alpha-hunter-private-dbqa"
CANDIDATES = (
    "/var/lib/postgresql/data",
    "/var/lib/postgresql/data/pgdata",
    "/var/lib/postgresql/17/main",
)


class Blocked(Exception):
    pass


def capture(args, timeout=30):
    try:
        return subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=timeout,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        raise Blocked("private local read-only inspection was not available") from None


def inspect():
    obj = json.loads(capture(["docker", "inspect", "--size", NAME]))[0]
    if obj.get("Config", {}).get("Image") != IMAGE:
        raise Blocked("original container image identity mismatch")
    if obj.get("Path") != "docker-entrypoint.sh":
        raise Blocked("original PostgreSQL entrypoint identity mismatch")
    if obj.get("HostConfig", {}).get("NetworkMode") != "none":
        raise Blocked("offline QA network isolation mismatch")
    if obj.get("HostConfig", {}).get("RestartPolicy", {}).get("Name") not in ("no", ""):
        raise Blocked("original QA has unexpected auto-restart policy")
    if obj.get("State", {}).get("Running") or obj.get("State", {}).get("Status") != "exited":
        raise Blocked("original QA must remain stopped")
    return obj


def marker(source):
    raw = capture(["docker", "cp", NAME + ":" + source, "-"], timeout=30)
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
            return any(m.isfile() and m.size > 0 for m in archive)
    except (tarfile.TarError, OSError):
        return False


def preflight():
    if os.getenv("CODESPACES") != "true" or os.getenv("GITHUB_ACTIONS") == "true":
        raise Blocked("operation allowed only in existing private Codespace")
    if capture(["git", "branch", "--show-current"]).decode().strip() != BRANCH:
        raise Blocked("wrong branch; isolated draft branch required")
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise Blocked("existing owner-only private archive root missing/unsafe")
    if ROOT.stat().st_mode & 0o777 != 0o700:
        raise Blocked("private archive directory permissions must be 700")

    obj = inspect()
    mounts = obj.get("Mounts", [])
    if len(mounts) != 1 or mounts[0].get("Type") != "bind":
        raise Blocked("original bind mount topology changed")
    pgdata = next(
        (x.split("=", 1)[1] for x in (obj["Config"].get("Env") or [])
         if x.startswith("PGDATA=")),
        "/var/lib/postgresql/data",
    )
    candidates = list(dict.fromkeys(
        posixpath.normpath(p) for p in (pgdata,) + CANDIDATES
    ))
    found = []
    for p in candidates:
        if (not p.startswith("/var/lib/postgresql/")
                or ".." in PurePosixPath(p).parts):
            continue
        if marker(posixpath.join(p, "PG_VERSION")) and marker(
            posixpath.join(p, "global", "pg_control")
        ):
            found.append(p)
    if len(found) != 1:
        raise Blocked("PGDATA cluster marker pair is not unique or absent")
    source = found[0]
    for mount in mounts:
        dest = posixpath.normpath(mount.get("Destination", ""))
        if source == dest or source.startswith(dest + "/"):
            raise Blocked("PGDATA is under a bind mount; separate backup plan required")

    reserve = max(2 * 1024**3, 4 * int(obj.get("SizeRw") or 0))
    if shutil.disk_usage(ROOT).free < reserve:
        raise Blocked("not enough private free disk space for guarded copy")
    return obj, source


def validate_tar(path, expected_base):
    marker_files = set()
    count = 0
    links = 0
    regular_bytes = 0
    with tarfile.open(path, mode="r|") as archive:
        for item in archive:
            raw = item.name
            pure = PurePosixPath(raw)
            if pure.is_absolute() or ".." in pure.parts:
                raise Blocked("unsafe TAR member path")
            norm = posixpath.normpath(raw.lstrip("./"))
            if norm != expected_base and not norm.startswith(expected_base + "/"):
                raise Blocked("TAR unexpectedly includes objects outside PGDATA")
            if item.issym() or item.islnk():
                links += 1
            if item.isfile():
                count += 1
                regular_bytes += item.size
                if norm in (
                    expected_base + "/PG_VERSION",
                    expected_base + "/global/pg_control",
                ) and item.size > 0:
                    marker_files.add(norm)
                fd = archive.extractfile(item)
                if fd is None:
                    raise Blocked("TAR member unreadable")
                remaining = item.size
                while remaining:
                    chunk = fd.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise Blocked("truncated TAR payload")
                    remaining -= len(chunk)
    if count == 0 or len(marker_files) != 2:
        raise Blocked("PostgreSQL marker files missing from backup")
    return count, links, regular_bytes


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as file:
        while True:
            buf = file.read(1024 * 1024)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def main():
    print("QA_BACKUP_MODE=STOPPED_CONTAINER_PRIVATE_FILESYSTEM_COPY")
    print("QA_PRODUCTION_CONNECTION=NONE")
    print("QA_RESTART_AUTHORIZATION=NOT_GRANTED")
    print("QA_BACKUP_VERIFIED=NO")
    destination = None
    try:
        before, source = preflight()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        folder = ROOT / ("p0_original_stopped_cluster_" + stamp)
        folder.mkdir(mode=0o700)
        destination = folder / "pgdata_original_stopped.tar"
        # Exclusive create. The PRIVATE archive never enters the git working tree.
        fd = os.open(str(destination), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as file:
            try:
                subprocess.run(
                    ["docker", "cp", NAME + ":" + source, "-"],
                    stdout=file, stderr=subprocess.DEVNULL, check=True,
                    timeout=240,
                )
            except (subprocess.SubprocessError, OSError):
                raise Blocked("stopped container data copy failed") from None
            file.flush()
            os.fsync(file.fileno())

        after = inspect()
        if before["Id"] != after["Id"] or before["State"]["FinishedAt"] != after["State"]["FinishedAt"]:
            raise Blocked("original container identity or stopped state changed during copy")

        members, links, payload_bytes = validate_tar(
            destination, posixpath.basename(source)
        )
        digest = sha256(destination)
        checksum = folder / "pgdata_original_stopped.sha256"
        with open(checksum, "x", encoding="utf-8") as out:
            os.chmod(checksum, 0o600)
            out.write(digest + "  pgdata_original_stopped.tar\n")
            out.flush()
            os.fsync(out.fileno())
        if destination.stat().st_size < 1024 or payload_bytes < 1024:
            raise Blocked("original stopped cluster copy is implausibly small")
        print("QA_ORIGINAL_CONTAINER=STILL_STOPPED")
        print("QA_BACKUP_ARCHIVE_BYTES=" + str(destination.stat().st_size))
        print("QA_BACKUP_REGULAR_FILES=" + str(members))
        print("QA_BACKUP_LINK_MEMBERS=" + str(links))
        print("QA_BACKUP_POSTGRES_MARKERS=2_OF_2")
        print("QA_BACKUP_SHA256=" + digest)
        print("QA_BACKUP_PRIVATE_PERMISSIONS=700_DIRECTORY_600_FILES")
        print("QA_BACKUP_TAR_VALIDATION=PASS")
        if links:
            print("QA_POSSIBLE_EXTERNAL_TABLESPACES=REVIEW_REQUIRED")
            print("QA_BACKUP_CUSTODY=PARTIAL_PENDING_LINK_REVIEW")
        else:
            print("QA_BACKUP_CUSTODY=PRIVATE_TAR_COPY_VERIFIED")
        print("QA_RESTORE_TEST=NOT_PERFORMED")
        print("QA_POSTGRES_CONSISTENCY=NOT_VERIFIED")
        print("QA_RESTART_ALLOWED=NO")
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        # Intentionally retain a possibly incomplete copy for private forensic review.
        print("QA_BACKUP_RESULT=BLOCKED_" + (
            str(error).upper().replace(" ", "_")[:100]
            if isinstance(error, Blocked) else "PRIVATE_INSPECTION_FAILED"
        ))
        print("QA_ORIGINAL_CONTAINER=DO_NOT_RESTART")
        print("QA_PARTIAL_ARCHIVE_IF_ANY=RETAIN_PRIVATE_FOR_REVIEW")
        print("QA_RESTART_ALLOWED=NO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
