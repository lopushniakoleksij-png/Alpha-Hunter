"""Offline tests for guarded original stopped QA filesystem backup helper.

Never runs Docker, touches private files, starts a container or connects to DB.
"""
from io import BytesIO
from pathlib import Path
import runpy
import tarfile

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "ops/local/p0_qa_stopped_cluster_backup_v01.py"
scope = runpy.run_path(str(SCRIPT), run_name="p0_backup_test")
validate_tar = scope["validate_tar"]
Blocked = scope["Blocked"]


def write_tar(path, files, link=None):
    with tarfile.open(path, "w") as tar:
        for name, payload in files.items():
            raw = payload.encode()
            entry = tarfile.TarInfo(name)
            entry.mode = 0o600
            entry.size = len(raw)
            tar.addfile(entry, BytesIO(raw))
        if link:
            entry = tarfile.TarInfo("data/pg_tblspc/99999")
            entry.type = tarfile.SYMTYPE
            entry.linkname = "../../external"
            tar.addfile(entry)


def markers():
    return {
        "data/PG_VERSION": "17\n",
        "data/global/pg_control": "synthetic marker (not actual PG metadata)",
        "data/base/1/1": "synthetic test payload",
    }


def test_valid_synthetic_tar_is_fully_read_and_has_two_markers(tmp_path):
    tar = tmp_path / "test.tar"
    write_tar(tar, markers())
    files, links, payload_bytes = validate_tar(tar, "data")
    assert (files, links) == (3, 0)
    assert payload_bytes == sum(len(x) for x in markers().values())


def test_tar_links_are_counted_for_manual_tablespace_custody_review(tmp_path):
    tar = tmp_path / "links.tar"
    write_tar(tar, markers(), link=True)
    files, links, _ = validate_tar(tar, "data")
    assert (files, links) == (3, 1)


@pytest.mark.parametrize("bad", [
    {"data/PG_VERSION": "17", "data/base/1/1": "no global control"},
    {"data/global/pg_control": "fake", "data/base/1/1": "no PG version"},
    {"outside/PG_VERSION": "17", "data/global/pg_control": "fake"},
    {"data/../outside": "bad", **markers()},
])
def test_missing_markers_or_wrong_root_fail_closed(tmp_path, bad):
    tar = tmp_path / "bad.tar"
    write_tar(tar, bad)
    with pytest.raises(Blocked):
        validate_tar(tar, "data")


def test_preflight_refuses_outside_codespace_before_docker(tmp_path, monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="existing private Codespace"):
        scope["preflight"]()
