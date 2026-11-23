"""Synthetic-only QA: verify private backup checkpoint/WAL metadata inspector.

No Docker use, no private archive access, no DB connection or server startup.
"""
from io import BytesIO
from pathlib import Path
import runpy
import tarfile

import pytest

script = Path(__file__).resolve().parents[1] / "ops/local/p0_qa_stopped_cluster_wal_inventory_v01.py"
scope = runpy.run_path(str(script), run_name="private_wal_inventory_test")
inspect_tar = scope["inspect_tar"]
extract_control_info = scope["extract_control_info"]
classify_wal = scope["classify_wal"]
Blocked = scope["Blocked"]

REDO = "000000010000000000000001"
OTHER = "000000010000000000000002"
SEGMENT = 16 * 1024 * 1024
CONTROL = (
    "pg_control version number: 1700\n"
    "Database cluster state: in production\n"
    "Latest checkpoint's REDO WAL file: " + REDO + "\n"
    "Bytes per WAL segment: 16777216\n"
)


def fake_tar(path, files, *, add_link=False):
    with tarfile.open(path, mode="w") as tar:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            tar.addfile(item, BytesIO(data))
        if add_link:
            item = tarfile.TarInfo("data/pg_tblspc/1234")
            item.type = tarfile.SYMTYPE
            item.linkname = "/external"
            tar.addfile(item)


def base_files():
    return {
        "data/PG_VERSION": b"17\n",
        "data/global/pg_control": b"SYNTHETIC_CONTROL",
        "data/pg_wal/" + REDO: b"A" * 64,
        "data/pg_wal/" + OTHER: b"B" * 32,
    }


def test_control_metadata_parses_checkpoint_and_segment_size():
    assert extract_control_info(CONTROL) == (REDO, SEGMENT, "in production")


@pytest.mark.parametrize("bad", [
    CONTROL.replace("in production", "").replace("Database cluster state: \n", ""),
    CONTROL.replace(REDO, "something-secret"),
    CONTROL.replace("16777216", "0"),
])
def test_control_metadata_missing_or_bad_fails_closed(bad):
    with pytest.raises(Blocked):
        extract_control_info(bad)


def test_tar_inventory_only_reads_wal_metadata_and_markers(tmp_path):
    f = tmp_path / "sample.tar"
    fake_tar(f, base_files())
    version, control, segments = inspect_tar(f)
    assert version == b"17\n"
    assert control == b"SYNTHETIC_CONTROL"
    assert segments == {REDO: 64, OTHER: 32}


@pytest.mark.parametrize("bad", [
    {"data/PG_VERSION": b"17\n"},
    {"data/global/pg_control": b"mock"},
    {"data/PG_VERSION": b"16\n", "data/global/pg_control": b"mock"},
    {"outside/PG_VERSION": b"17\n", "data/global/pg_control": b"mock"},
    {"data/../outside": b"x", **base_files()},
])
def test_missing_or_unsafe_archive_refused(tmp_path, bad):
    f = tmp_path / "sample.tar"
    fake_tar(f, bad)
    with pytest.raises(Blocked):
        inspect_tar(f)


def test_external_tablespace_symlink_fails_closed(tmp_path):
    f = tmp_path / "sample.tar"
    fake_tar(f, base_files(), add_link=True)
    with pytest.raises(Blocked, match="linked tablespace"):
        inspect_tar(f)


def test_checkpoint_redo_wal_present_and_sized():
    assert classify_wal(REDO, SEGMENT, {REDO: SEGMENT, OTHER: SEGMENT}) == (
        "CHECKPOINT_REDO_SEGMENT_PRESENT", 0,
    )


def test_missing_checkpoint_redo_segment_never_passes():
    assert classify_wal(REDO, SEGMENT, {OTHER: SEGMENT}) == (
        "CHECKPOINT_REDO_SEGMENT_MISSING", 0,
    )


def test_malformed_segment_sizes_never_pass():
    assert classify_wal(REDO, SEGMENT, {REDO: SEGMENT-1}) == (
        "WAL_SEGMENT_SIZE_MISMATCH", 1,
    )


def test_no_wal_never_passes():
    assert classify_wal(REDO, SEGMENT, {}) == ("MISSING_WAL_FILES", 0)


def test_disallows_non_codespace_before_any_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="existing authorised Codespace"):
        scope["guard_environment"]()
