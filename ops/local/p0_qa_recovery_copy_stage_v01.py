#!/usr/bin/env python3
"""Stage an isolated, owner-private copy of a stopped PostgreSQL 17 cluster.

ONLY inside the pre-existing authorised Codespace on the isolated draft branch.
Reads two SHA-identical protected TARs and extracts one into a distinct new
private directory. Never touches original container, copies or production.
Does not start PostgreSQL, run crash recovery, restore schema or issue trades.
"""
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path.home() / '.alpha-hunter-private-dbqa'
BRANCH = 'fix/supabase-write-timeout-qa'
CONTAINER = 'alpha-hunter-private-postgres17-qa'
IMAGE = 'public.ecr.aws/supabase/postgres:17.6.1.156'
TAR_NAME = 'pgdata_original_stopped.tar'
SHA_NAME = 'pgdata_original_stopped.sha256'
MAX_FILES = 100000
MAX_BYTES = 2 * 1024**3


class Blocked(Exception):
    pass


def checked(args):
    try:
        return subprocess.run(args, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, check=True,
                              text=True, timeout=30).stdout
    except (subprocess.SubprocessError, OSError):
        raise Blocked('local read-only environment inspection failed') from None


def original_offline():
    c = json.loads(checked(['docker', 'inspect', CONTAINER]))[0]
    if (c['Config'].get('Image') != IMAGE
        or c.get('Path') != 'docker-entrypoint.sh'
        or c['HostConfig'].get('NetworkMode') != 'none'
        or c['HostConfig'].get('RestartPolicy', {}).get('Name') not in ('no', '')
        or c['State'].get('Running')
        or c['State'].get('Status') != 'exited'):
        raise Blocked('original container identity/isolation/stopped state mismatch')
    return c['Id'], c['State'].get('FinishedAt')


def sha256(path):
    d = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            d.update(block)
    return d.hexdigest()


def archive_inventory():
    matches = []
    for folder in sorted(ROOT.glob('p0_original_stopped_cluster_*')):
        if not folder.is_dir() or folder.is_symlink() or folder.stat().st_mode & 0o777 != 0o700:
            raise Blocked('private backup folder has unsafe layout/permissions')
        p, checksum = folder / TAR_NAME, folder / SHA_NAME
        if (not p.is_file() or not checksum.is_file() or p.is_symlink()
            or checksum.is_symlink()
            or p.stat().st_mode & 0o777 != 0o600
            or checksum.stat().st_mode & 0o777 != 0o600):
            raise Blocked('private archive/checksum missing or unsafe')
        m = re.fullmatch(r'([0-9a-f]{64})  pgdata_original_stopped[.]tar',
                         checksum.read_text(encoding='ascii').strip())
        if not m or sha256(p) != m.group(1):
            raise Blocked('private backup checksum mismatch')
        matches.append((p, m.group(1)))
    if len(matches) < 2 or len({h for _, h in matches}) != 1:
        raise Blocked('need at least two byte-identical owner-private backup TARs')
    return matches


def relative_member(raw, root):
    p = PurePosixPath(raw)
    if p.is_absolute() or '..' in p.parts or '\\' in raw or len(raw) > 1024:
        raise Blocked('unsafe archive member path')
    parts = tuple(part for part in p.parts if part not in ('.', ''))
    if not parts:
        raise Blocked('empty archive member')
    if root is None:
        root = parts[0]
    if parts[0] != root:
        raise Blocked('archive has multiple roots')
    return root, parts[1:]


def stage_archive(tar_path, destination):
    """Extract regular files/dirs manually, no links/devices or TAR metadata trust."""
    root = None
    seen = set()
    files = 0
    total = 0
    directories = 0
    with tarfile.open(tar_path, 'r|') as archive:
        for entry in archive:
            root, path_parts = relative_member(entry.name, root)
            if not path_parts:
                if not entry.isdir():
                    raise Blocked('invalid archive root type')
                continue
            rel = '/'.join(path_parts)
            if rel in seen:
                raise Blocked('duplicate archive member')
            seen.add(rel)
            out = destination.joinpath(*path_parts)
            if entry.isdir():
                out.mkdir(parents=True, exist_ok=True, mode=0o700)
                out.chmod(0o700)
                directories += 1
                continue
            if not entry.isfile():
                raise Blocked('archive contains link/device/non-file object')
            files += 1
            total += entry.size
            if files > MAX_FILES or total > MAX_BYTES or entry.size < 0:
                raise Blocked('archive exceeds isolated recovery staging limits')
            out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'wb') as target:
                item = archive.extractfile(entry)
                if item is None:
                    raise Blocked('unreadable archive payload')
                remaining = entry.size
                while remaining:
                    block = item.read(min(1024 * 1024, remaining))
                    if not block:
                        raise Blocked('truncated archive payload')
                    target.write(block)
                    remaining -= len(block)
            out.chmod(0o600)
    if files == 0 or directories == 0:
        raise Blocked('empty PostgreSQL recovery staging copy')
    if (destination / 'PG_VERSION').read_bytes().strip() != b'17':
        raise Blocked('recovery staging copy is not PostgreSQL 17')
    if not (destination / 'global' / 'pg_control').is_file():
        raise Blocked('recovery staging copy missing control file')
    wal_files = [p for p in (destination / 'pg_wal').glob('*')
                 if p.is_file() and re.fullmatch('[0-9A-F]{24}', p.name)]
    if not wal_files:
        raise Blocked('recovery staging copy contains no WAL segments')
    signals = ['standby.signal', 'recovery.signal', 'postmaster.pid', 'backup_label']
    return {'files': files, 'directories': directories, 'bytes': total,
            'wal_files': len(wal_files),
            'signals': {name: (destination / name).exists() for name in signals}}


def main():
    print('QA_MODE=OWNER_ONLY_ISOLATED_RECOVERY_COPY_STAGING')
    print('QA_PRODUCTION_CONNECTION=NONE')
    print('QA_ORIGINAL_CONTAINER_RESTART=NO')
    print('QA_CRASH_RECOVERY_ATTEMPT=NOT_STARTED')
    try:
        if os.environ.get('CODESPACES') != 'true' or os.environ.get('GITHUB_ACTIONS') == 'true':
            raise Blocked('requires existing authorised Codespace')
        if checked(['git', 'branch', '--show-current']).strip() != BRANCH:
            raise Blocked('wrong repair branch')
        if ROOT.is_symlink() or not ROOT.is_dir() or ROOT.stat().st_mode & 0o777 != 0o700:
            raise Blocked('private archive root invalid/unsafe')
        old_state = original_offline()
        copies = archive_inventory()
        archive_size = copies[0][0].stat().st_size
        if shutil.disk_usage(ROOT).free < max(2 * 1024**3, 4 * archive_size):
            raise Blocked('insufficient disk headroom for isolated recovery stage')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        stage_root = ROOT / ('p0_recovery_stage_' + stamp + '_' + uuid.uuid4().hex[:8])
        stage_root.mkdir(mode=0o700)
        dest = stage_root / 'pgdata'
        dest.mkdir(mode=0o700)
        result = stage_archive(copies[0][0], dest)
        if sha256(copies[0][0]) != copies[0][1]:
            raise Blocked('original archive digest changed during staging')
        if original_offline() != old_state:
            raise Blocked('original PostgreSQL container changed during staging')
        print('QA_RECOVERY_STAGE=PASS')
        print('QA_STAGED_REGULAR_FILES=' + str(result['files']))
        print('QA_STAGED_WAL_SEGMENTS=' + str(result['wal_files']))
        print('QA_STAGE_BYTES=' + str(result['bytes']))
        for key, value in result['signals'].items():
            print('QA_STAGED_' + key.replace('.', '_').upper() + '=' + ('YES' if value else 'NO'))
        print('QA_PRIVATE_ORIGINAL_BACKUPS=UNCHANGED_SHA256_VERIFIED')
        print('QA_ORIGINAL_CONTAINER=STILL_STOPPED')
        print('QA_DATABASE_STARTED=NO')
        print('QA_STAGE_CONTENT_VALIDATION=TAR_EXTRACTED_MARKERS_PRESENT')
        print('QA_PHYSICAL_RECOVERY_CERTIFICATION=NOT_YET_VERIFIED')
        print('QA_NEXT_GATE=OFFLINE_COPY_RUNTIME_CONFIG_AND_CONTROLLED_CRASH_RECOVERY_REVIEW')
        return 0
    except (Blocked, OSError, ValueError, KeyError, tarfile.TarError) as e:
        print('QA_RECOVERY_STAGE=BLOCKED_' + (
            str(e).upper().replace(' ', '_')[:90] if isinstance(e, Blocked) else 'PRIVATE_ERROR'))
        print('QA_STAGE_PARTIAL_IF_ANY=KEEP_PRIVATE_FOR_REVIEW')
        print('QA_ORIGINAL_CONTAINER_RESTART=NO')
        return 2


if __name__ == '__main__':
    sys.exit(main())
