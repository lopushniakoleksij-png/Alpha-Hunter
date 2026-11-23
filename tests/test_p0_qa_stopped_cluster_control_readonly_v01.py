"""Offline-only synthetic tests for owner-operated stopped-cluster control checker.

No Docker container, database, private archive, network or production access.
"""
from io import BytesIO
from pathlib import Path
import runpy
import tarfile

import pytest

SCRIPT = (Path(__file__).resolve().parents[1] /
          "ops/local/p0_qa_stopped_cluster_control_readonly_v01.py")
scope = runpy.run_path(str(SCRIPT), run_name="offline_control_test")
read_markers = scope["read_markers"]
Blocked = scope["Blocked"]


def make_archive(path, contents, symlink=False):
    with tarfile.open(path, mode="w") as out:
        for name, value in contents.items():
            payload = value if isinstance(value, bytes) else value.encode()
            item = tarfile.TarInfo(name)
            item.size = len(payload)
            out.addfile(item, BytesIO(payload))
        if symlink:
            item = tarfile.TarInfo("data/pg_tblspc/123")
            item.type = tarfile.SYMTYPE
            item.linkname = "/private/external-tablespace"
            out.addfile(item)


def correct():
    return {
        "data/PG_VERSION": b"17\n",
        "data/global/pg_control": b"SYNTHETIC_METADATA" * 100,
        "data/pg_wal/000000010000000000000001": b"SYNTHETIC_WAL",
    }


def test_synthetic_control_markers_and_wal_count(tmp_path):
    archive = tmp_path / "cluster.tar"
    make_archive(archive, correct())
    version, control, wal, links = read_markers(archive)
    assert version == b"17\n"
    assert control.startswith(b"SYNTHETIC_METADATA")
    assert (wal, links) == (1, 0)


def test_external_tablespace_links_explicitly_reported(tmp_path):
    archive = tmp_path / "cluster.tar"
    make_archive(archive, correct(), symlink=True)
    assert read_markers(archive)[-1] == 1


@pytest.mark.parametrize("contents", [
    {"data/PG_VERSION": b"17\n"},
    {"data/global/pg_control": b"mock"},
    {"data/PG_VERSION": b"16\n", "data/global/pg_control": b"mock"},
    {"data/PG_VERSION": b"17\n", "wrong/global/pg_control": b"mock"},
    {"data/../outside": b"x", **correct()},
    {"data/PG_VERSION": b"17\n", "data/global/pg_control": b""},
])
def test_malformed_or_missing_control_fails_closed(tmp_path, contents):
    archive = tmp_path / "cluster.tar"
    make_archive(archive, contents)
    with pytest.raises(Blocked):
        read_markers(archive)


def test_environment_refuses_non_codespace(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        scope["ensure_environment"]()
