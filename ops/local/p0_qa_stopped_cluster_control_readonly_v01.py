#!/usr/bin/env python3
"""P0 A2/A3: verify saved original stopped PG17 control file OFFLINE.

Owner must run in the existing authorised Codespace on draft repair branch.
Never starts the original server, runs SQL, contacts Supabase, or extracts
private files into the git repository. Uses the already cached postgres:17
image to read copied PG_VERSION and pg_control via pg_controldata, offline.
A readable control file is NOT proof of complete physical recovery.
"""
from __future__ import annotations

import hashlib
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
SHA_NAME = "pgdata_original_stopped.sha256"
TAR_NAME = "pgdata_original_stopped.tar"
MAX_MARKER = 65536


class Blocked(Exception):
    pass


def cmd(args, timeout=40, *, suppress=True):
    try:
        return subprocess.run(
            args, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if suppress else subprocess.PIPE,
            text=True, check=True, timeout=timeout,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise Blocked("owner-only local command unavailable or failed") from None


def ensure_environment():
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("existing Codespace only")
    if cmd(["git", "branch", "--show-current"]).strip() != BRANCH:
        raise Blocked("isolated repair branch required")
    if not ROOT.is_dir() or ROOT.is_symlink() or ROOT.stat().st_mode & 0o777 != 0o700:
        raise Blocked("private archive root missing or has unsafe permissions")

    # Inspect exact original container but never start, exec in it or restart it.
    import json
    obj = json.loads(cmd(["docker", "inspect", CONTAINER]))[0]
    if (obj["Config"]["Image"] != IMAGE or
            obj["Path"] != "docker-entrypoint.sh" or
            obj["HostConfig"]["NetworkMode"] != "none" or
            obj["State"]["Status"] != "exited" or
            obj["State"]["Running"]):
        raise Blocked("original container identity/isolation/stopped state mismatch")
    cmd(["docker", "image", "inspect", "postgres:17"], timeout=15)


def digest_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_inventory():
    candidates = sorted(
        (d for d in ROOT.glob("p0_original_stopped_cluster_*") if d.is_dir() and not d.is_symlink()),
        key=lambda d: d.name, reverse=True,
    )
    verified = []
    for folder in candidates:
        if folder.stat().st_mode & 0o777 != 0o700:
            raise Blocked("unsafe backup folder mode")
        archive = folder / TAR_NAME
        checksum = folder / SHA_NAME
        if not archive.is_file() or not checksum.is_file() or archive.is_symlink() or checksum.is_symlink():
            continue
        if archive.stat().st_mode & 0o777 != 0o600 or checksum.stat().st_mode & 0o777 != 0o600:
            raise Blocked("unsafe private archive file mode")
        recorded = checksum.read_text(encoding="ascii").strip()
        match = re.fullmatch(r"([0-9a-f]{64})  pgdata_original_stopped[.]tar", recorded)
        if not match or digest_file(archive) != match.group(1):
            raise Blocked("stopped-container archive SHA-256 mismatch")
        verified.append((archive, match.group(1)))
    if not verified:
        raise Blocked("no verified stopped-container TAR archive found")
    return verified


def read_markers(archive_path):
    found = {}
    base = None
    wal_files = 0
    links = 0
    with tarfile.open(archive_path, "r|") as inp:
        for member in inp:
            raw = PurePosixPath(member.name)
            if raw.is_absolute() or ".." in raw.parts:
                raise Blocked("invalid TAR path component")
            name = posixpath.normpath(member.name)
            parts = PurePosixPath(name).parts
            if not parts or parts[0] in (".", ".."):
                raise Blocked("unexpected TAR path")
            if base is None:
                base = parts[0]
            if parts[0] != base:
                raise Blocked("TAR has multiple roots")
            if member.issym() or member.islnk():
                links += 1
            if "/pg_wal/" in "/" + name and member.isfile():
                wal_files += 1
            if name in (base + "/PG_VERSION", base + "/global/pg_control"):
                if not member.isfile() or member.size < 1 or member.size > MAX_MARKER:
                    raise Blocked("missing or oversized PostgreSQL marker")
                if name in found:
                    raise Blocked("duplicate PG marker in TAR")
                handle = inp.extractfile(member)
                if handle is None:
                    raise Blocked("unreadable marker")
                found[name] = handle.read()
    if base is None or len(found) != 2:
        raise Blocked("PG_VERSION and pg_control markers not both present")
    version = found[base + "/PG_VERSION"]
    if version.strip() != b"17":
        raise Blocked("PostgreSQL archive is not major version 17")
    return version, found[base + "/global/pg_control"], wal_files, links


def offline_control(version, control):
    with tempfile.TemporaryDirectory(prefix=".p0-offline-control-", dir=ROOT) as temp:
        directory = Path(temp)
        (directory / "global").mkdir(mode=0o700)
        for relative, payload in (
            ("PG_VERSION", version),
            ("global/pg_control", control),
        ):
            p = directory / relative
            with open(p, "xb") as out:
                os.chmod(p, 0o600)
                out.write(payload)
        # This launches a ONE-OFF offline control-reader utility; it does NOT
        # start the original PostgreSQL container or any database server.
        try:
            completed = subprocess.run([
                "docker", "run", "--rm", "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--user", f"{os.getuid()}:{os.getgid()}",
                "--mount", f"type=bind,source={directory},target=/qa,readonly",
                "postgres:17", "pg_controldata", "/qa",
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               text=True, check=True, timeout=40)
        except (OSError, subprocess.SubprocessError):
            raise Blocked("offline control reader could not verify control file") from None
        output = completed.stdout
        if re.search(r"CRC|checksum|WARNING|invalid", completed.stderr, re.IGNORECASE) or (
            re.search(r"CRC|checksum|WARNING|invalid", output, re.IGNORECASE)
            and re.search(r"WARNING|mismatch|invalid", output, re.IGNORECASE)
        ):
            raise Blocked("offline PG control reader reported a warning")

    state_match = re.search(r"(?m)^Database cluster state:\s*(\S.*)\s*$", output)
    crc_match = re.search(r"(?m)^pg_control version number:\s*(\d+)\s*$", output)
    catalog_match = re.search(r"(?m)^Catalog version number:\s*(\d+)\s*$", output)
    if not (state_match and crc_match and catalog_match):
        raise Blocked("offline pg_controldata output incomplete")
    return state_match.group(1).strip(), crc_match.group(1), catalog_match.group(1)


def main():
    print("QA_MODE=OFFLINE_STOPPED_CLUSTER_CONTROL_INSPECTION")
    print("QA_PRODUCTION_DB=NOT_TOUCHED")
    print("QA_RESTART_ALLOWED=NO")
    try:
        ensure_environment()
        copies = archive_inventory()
        if len({digest for _, digest in copies}) != 1:
            raise Blocked("private backup copies differ; preserve for review")
        version, control, wal, links = read_markers(copies[0][0])
        state, ctl_version, catalog = offline_control(version, control)
        ensure_environment()  # Recheck original server remains stopped.
        print("QA_VERIFIED_PRIVATE_BACKUP_COPIES=" + str(len(copies)))
        print("QA_ALL_BACKUPS_BYTE_IDENTICAL=" + (
            "YES" if len({digest for _, digest in copies}) == 1 else "NO_REVIEW_REQUIRED"
        ))
        print("QA_BACKUP_WAL_FILE_COUNT=" + str(wal))
        print("QA_BACKUP_LINK_COUNT=" + str(links))
        print("QA_PG_CONTROL_READABLE=PASS")
        print("QA_PG_MAJOR_VERSION=17")
        print("QA_CONTROL_FORMAT_VERSION=" + ctl_version)
        print("QA_CONTROL_CATALOG_VERSION=" + catalog)
        print("QA_CLUSTER_STATE=" + state.upper().replace(" ", "_"))
        print("QA_CLUSTER_CONSISTENCY=NOT_YET_VERIFIED")
        print("QA_FULL_PHYSICAL_RECOVERY=NOT_YET_VERIFIED")
        print("QA_DATABASE_RESTART=NOT_AUTHORISED")
        print("QA_NEXT_GATE=REVIEW_OFFLINE_CONTROL_AND_ARCHIVE_CUSTODY")
        return 0
    except (Blocked, OSError, ValueError, KeyError, tarfile.TarError) as exc:
        print("QA_CONTROL_CHECK=BLOCKED_" + (
            str(exc).upper().replace(" ", "_")[:100] if isinstance(exc, Blocked)
            else "PRIVATE_INSPECTION_ERROR"
        ))
        print("QA_ORIGINAL_CONTAINER=DO_NOT_RESTART")
        return 2


if __name__ == "__main__":
    sys.exit(main())
