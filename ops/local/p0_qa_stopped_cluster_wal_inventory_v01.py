#!/usr/bin/env python3
"""P0 A3: check checkpoint/WAL custody in an owner-private stopped PG17 TAR.

Only runs in the existing Codespace on the draft repair branch.
No production connection, original-container start, Docker exec, pg_waldump,
pg_resetwal, SQL, or changes to the original PostgreSQL files.
This checks checkpoint WAL presence and segment sizes, NOT WAL replay.
"""
import hashlib
import io
import json
import os
import posixpath
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path.home() / ".alpha-hunter-private-dbqa"
CONTAINER = "alpha-hunter-private-postgres17-qa"
BRANCH = "fix/supabase-write-timeout-qa"
IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"
TAR = "pgdata_original_stopped.tar"
CHECKSUM = "pgdata_original_stopped.sha256"
WAL_RE = re.compile(r"[0-9A-F]{24}")


class Blocked(Exception):
    pass


def run(args, timeout=35):
    try:
        return subprocess.run(
            args, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=timeout
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise Blocked("offline local inspection command failed") from None


def guard_environment():
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("existing authorised Codespace required")
    if run(["git", "branch", "--show-current"]).strip() != BRANCH:
        raise Blocked("isolated repair branch required")
    if ROOT.is_symlink() or not ROOT.is_dir() or ROOT.stat().st_mode & 0o777 != 0o700:
        raise Blocked("private backup root missing/unsafe")
    c = json.loads(run(["docker", "inspect", CONTAINER]))[0]
    if (c["Config"]["Image"] != IMAGE
            or c["Path"] != "docker-entrypoint.sh"
            or c["HostConfig"]["NetworkMode"] != "none"
            or c["State"]["Status"] != "exited"
            or c["State"]["Running"]):
        raise Blocked("original PostgreSQL container identity or stopped state changed")
    run(["docker", "image", "inspect", "postgres:17"], timeout=12)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verified_backups():
    copies = []
    for folder in sorted(ROOT.glob("p0_original_stopped_cluster_*")):
        if folder.is_symlink() or not folder.is_dir() or folder.stat().st_mode & 0o777 != 0o700:
            raise Blocked("unexpected private backup folder topology")
        archive, chk = folder / TAR, folder / CHECKSUM
        if not archive.is_file() or not chk.is_file() or archive.is_symlink() or chk.is_symlink():
            raise Blocked("private backup archive or checksum file missing")
        if archive.stat().st_mode & 0o777 != 0o600 or chk.stat().st_mode & 0o777 != 0o600:
            raise Blocked("unsafe private archive/checksum permissions")
        match = re.fullmatch(
            r"([0-9a-f]{64})  pgdata_original_stopped[.]tar",
            chk.read_text(encoding="ascii").strip(),
        )
        if not match or sha256(archive) != match.group(1):
            raise Blocked("private backup checksum verification failed")
        copies.append((archive, match.group(1)))
    if len(copies) < 2 or len({h for _, h in copies}) != 1:
        raise Blocked("at least two identical protected private backup copies required")
    return copies


def inspect_tar(path):
    """Only return minimal marker bytes and WAL name-size metadata."""
    version = control = None
    wal = {}
    root = None
    links = 0
    with tarfile.open(path, mode="r|") as stream:
        for member in stream:
            p = PurePosixPath(member.name)
            if p.is_absolute() or ".." in p.parts:
                raise Blocked("unsafe archive path")
            clean = posixpath.normpath(member.name.lstrip("./"))
            pieces = PurePosixPath(clean).parts
            if not pieces or pieces[0] in (".", ".."):
                raise Blocked("invalid archive root")
            if root is None:
                root = pieces[0]
            if pieces[0] != root:
                raise Blocked("multiple archive roots")
            if member.issym() or member.islnk():
                links += 1
            if clean == root + "/PG_VERSION" and member.isfile() and member.size <= 64:
                f = stream.extractfile(member)
                version = f.read() if f else None
            elif clean == root + "/global/pg_control" and member.isfile() and 0 < member.size <= 65536:
                f = stream.extractfile(member)
                control = f.read() if f else None
            elif clean.startswith(root + "/pg_wal/") and member.isfile():
                filename = clean.rsplit("/", 1)[-1]
                if WAL_RE.fullmatch(filename):
                    if filename in wal:
                        raise Blocked("duplicate WAL segment in private TAR")
                    wal[filename] = member.size
    if version is None or version.strip() != b"17" or not control:
        raise Blocked("saved PostgreSQL 17 marker pair missing")
    if links:
        raise Blocked("linked tablespace/storage content requires separate manual custody check")
    return version, control, wal


def extract_control_info(output):
    def require(key, pattern):
        m = re.search(pattern, output, re.MULTILINE)
        if not m:
            raise Blocked("pg_controldata missing required " + key)
        return m.group(1).strip()

    redo = require("redo_file", r"^Latest checkpoint's REDO WAL file:\s*([0-9A-F]{24})\s*$")
    segment_size = int(require("wal_segment_size", r"^Bytes per WAL segment:\s*(\d+)\s*$"))
    state = require("cluster_state", r"^Database cluster state:\s*(.*?)\s*$")
    if not (1024**2 <= segment_size <= 1024**3):
        raise Blocked("implausible PostgreSQL WAL segment size")
    return redo, segment_size, state


def offline_pg_controldata(version, control):
    with tempfile.TemporaryDirectory(prefix=".p0-wal-control-", dir=ROOT) as temp:
        d = Path(temp)
        (d / "global").mkdir(mode=0o700)
        for name, value in (("PG_VERSION", version), ("global/pg_control", control)):
            p = d / name
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(value)
        # Does not start a PG server. Only invokes the read-only control utility.
        output = run([
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--mount", f"type=bind,source={d},target=/qa,readonly",
            "postgres:17", "pg_controldata", "/qa",
        ])
    return extract_control_info(output)


def classify_wal(redo, segment_size, wal):
    if not wal:
        return "MISSING_WAL_FILES", 0
    unexpected = sum(1 for size in wal.values() if size != segment_size)
    if redo not in wal:
        return "CHECKPOINT_REDO_SEGMENT_MISSING", unexpected
    if unexpected:
        return "WAL_SEGMENT_SIZE_MISMATCH", unexpected
    return "CHECKPOINT_REDO_SEGMENT_PRESENT", 0


def main():
    print("QA_WAL_MODE=READ_ONLY_PRIVATE_BACKUP")
    print("QA_ORIGINAL_CONTAINER_RESTART=NOT_AUTHORISED")
    print("QA_PRODUCTION_CONNECTION=NONE")
    try:
        guard_environment()
        copies = verified_backups()
        version, control, wal = inspect_tar(copies[-1][0])
        redo, segment_size, state = offline_pg_controldata(version, control)
        guard_environment()
        status, size_anomalies = classify_wal(redo, segment_size, wal)
        print("QA_IDENTICAL_PRIVATE_BACKUPS=" + str(len(copies)))
        print("QA_CONTROL_CLUSTER_STATE=" + state.upper().replace(" ", "_"))
        print("QA_WAL_SEGMENT_COUNT=" + str(len(wal)))
        print("QA_WAL_SIZE_MISMATCHES=" + str(size_anomalies))
        print("QA_CHECKPOINT_REDO_WAL=" + ("PRESENT" if redo in wal else "MISSING"))
        print("QA_WAL_CUSTODY_STATUS=" + status)
        print("QA_WAL_RECORD_DECODING=NOT_ATTEMPTED")
        print("QA_CRASH_RECOVERY_TEST=NOT_PERFORMED")
        print("QA_PHYSICAL_CONSISTENCY=NOT_YET_VERIFIED")
        print("QA_RESTART_ALLOWED=NO")
        return 0 if status == "CHECKPOINT_REDO_SEGMENT_PRESENT" else 2
    except (Blocked, OSError, ValueError, TypeError, KeyError, tarfile.TarError) as exc:
        detail = str(exc).upper().replace(" ", "_")[:100] if isinstance(exc, Blocked) else "INTERNAL_CHECK_FAILED"
        print("QA_WAL_CUSTODY_STATUS=BLOCKED_" + detail)
        print("QA_RESTART_ALLOWED=NO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
