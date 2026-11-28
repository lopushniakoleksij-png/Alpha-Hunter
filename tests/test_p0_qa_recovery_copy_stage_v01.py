"""Synthetic, offline tests: never Docker/start a PostgreSQL server."""
import io
import runpy
import tarfile
from pathlib import Path
import pytest

SCOPE = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        'ops/local/p0_qa_recovery_copy_stage_v01.py'),
    run_name='stage_test'
)
stage_archive = SCOPE['stage_archive']
Blocked = SCOPE['Blocked']
relative_member = SCOPE['relative_member']


def mk_tar(path, entries, link=False):
    with tarfile.open(path, 'w') as t:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            if data is None:
                info.type = tarfile.DIRTYPE
                t.addfile(info)
            else:
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        if link:
            info = tarfile.TarInfo('data/pg_tblspc/123')
            info.type = tarfile.SYMTYPE
            info.linkname = '/external/secret'
            t.addfile(info)


def contents():
    return {
        'data': None,
        'data/global': None,
        'data/pg_wal': None,
        'data/PG_VERSION': b'17\n',
        'data/global/pg_control': b'not-real-control',
        'data/pg_wal/000000010000000000000001': b'not-real-wal',
    }


def test_regular_cluster_staged_offline_and_wal_counted(tmp_path):
    t = tmp_path / 'backup.tar'
    mk_tar(t, contents())
    p = tmp_path / 'stage'
    p.mkdir()
    r = stage_archive(t, p)
    assert r['files'] == 3
    assert r['wal_files'] == 1
    assert r['signals'] == {
        'standby.signal': False,
        'recovery.signal': False,
        'postmaster.pid': False,
        'backup_label': False,
    }
    assert (p / 'global/pg_control').read_bytes() == b'not-real-control'
    assert (p / 'PG_VERSION').stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('bad', [
    {'data': None, 'data/PG_VERSION': b'17\n'},
    {'data': None, 'data/PG_VERSION': b'16\n', 'data/global/pg_control': b'x'},
    {'data': None, 'data/PG_VERSION': b'17\n', 'data/global/pg_control': b'x'},
    {'data': None, 'data/../outside': b'x', **contents()},
    {'data': None, '/outside/exfil': b'x', **contents()},
    {'data': None, 'elsewhere/surprise': b'x', **contents()},
])
def test_bad_archives_refused(tmp_path, bad):
    t = tmp_path / 'bad.tar'
    mk_tar(t, bad)
    p = tmp_path / 'stage'
    p.mkdir()
    with pytest.raises(Blocked):
        stage_archive(t, p)


def test_symlink_refused_not_extracted(tmp_path):
    t = tmp_path / 'bad.tar'
    mk_tar(t, contents(), link=True)
    p = tmp_path / 'stage'
    p.mkdir()
    with pytest.raises(Blocked, match='link'):
        stage_archive(t, p)
    assert not (p / 'pg_tblspc/123').exists()


def test_duplicate_member_refused(tmp_path):
    t = tmp_path / 'double.tar'
    with tarfile.open(t, 'w') as tar:
        for _ in range(2):
            raw = b'17\n'
            entry = tarfile.TarInfo('data/PG_VERSION')
            entry.size = len(raw)
            tar.addfile(entry, io.BytesIO(raw))
    p = tmp_path / 'stage'
    p.mkdir()
    with pytest.raises(Blocked, match='duplicate'):
        stage_archive(t, p)


def test_path_protection_before_staging():
    for raw in ('../escape', '/root/escape', 'data/../../x', 'data\\escape'):
        with pytest.raises(Blocked):
            relative_member(raw, None)


def test_non_codespace_refuses_before_docker(monkeypatch):
    monkeypatch.delenv('CODESPACES', raising=False)
    assert SCOPE['main']() == 2
