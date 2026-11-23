"""Synthetic-only checks for private third PG17 recovery-copy safety.

No actual Codespace, Docker, PostgreSQL, production data or filesystem paths.
"""
import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ops/local/p0_qa_third_copy_prepare_v01.py"
ns = runpy.run_path(str(SCRIPT), run_name="p0_third_copy_offline_tests")
Blocked = ns["Blocked"]
file_inventory = ns["file_inventory"]
copy_verified = ns["copy_verified"]


def pg_tree(base):
    p = base / "pgdata"
    p.mkdir(mode=0o700, parents=True)
    for name in ("base", "global", "pg_wal", "pg_xact", "pg_multixact", "pg_tblspc"):
        (p / name).mkdir(mode=0o700)
    for name, raw in {
        "PG_VERSION": b"17\n",
        "global/pg_control": b"fake-control",
        "postmaster.pid": b"1000\n",
        "postgresql.conf": b"cron.launch_active_jobs=on\n",
        "pg_wal/000000010000000000000001": b"FAKE_WAL",
    }.items():
        f = p / name
        f.write_bytes(raw)
        f.chmod(0o600)
    return p


def test_third_copy_preserves_all_bytes_with_independent_checksums(tmp_path):
    pg = pg_tree(tmp_path / "source")
    inventory, directories, total = file_inventory(pg)
    third = tmp_path / "third" / "pgdata"
    third.parent.mkdir(mode=0o700)
    result = copy_verified(pg, third, inventory, directories)
    assert result == len(inventory)
    assert (third / "PG_VERSION").read_bytes() == b"17\n"
    assert (third / "postmaster.pid").exists()  # no PID deletion
    assert (third / "postgresql.conf").read_bytes().startswith(b"cron.")
    assert (pg / "postmaster.pid").exists()      # source remains untouched
    assert total == sum(size for size, _ in inventory.values())
    assert (third / "postgresql.conf").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("name", ["postmaster.pid", "PG_VERSION", "global/pg_control"])
def test_incomplete_staging_copy_refused_when_pid_or_cluster_markers_missing(tmp_path, name):
    pg = pg_tree(tmp_path / "source")
    (pg / name).unlink()
    if name == "postmaster.pid":
        with pytest.raises(Blocked):
            file_inventory(pg)
    else:
        original_root = ns["single_stage"].__globals__["ROOT"]
        root = tmp_path / "root"
        root.mkdir(mode=0o700)
        stage = root / "p0_recovery_stage_A"
        stage.mkdir(mode=0o700)
        target = stage / "pgdata"
        target.mkdir(mode=0o700)
        for dirname in ("base", "global", "pg_wal", "pg_xact", "pg_multixact"):
            (target / dirname).mkdir(mode=0o700)
        for filename in ("PG_VERSION", "global/pg_control", "postmaster.pid"):
            if filename != name:
                f = target / filename
                f.write_bytes(b"17" if filename == "PG_VERSION" else b"marker")
                f.chmod(0o600)
        ns["single_stage"].__globals__["ROOT"] = root
        try:
            with pytest.raises(Blocked):
                ns["single_stage"]()
        finally:
            ns["single_stage"].__globals__["ROOT"] = original_root


def test_source_symlink_rejected_before_any_copy(tmp_path):
    pg = pg_tree(tmp_path / "source")
    (pg / "pg_wal" / "outside_link").symlink_to("/etc/passwd")
    with pytest.raises(Blocked, match="symlink"):
        file_inventory(pg)


def test_source_permission_drift_rejected(tmp_path):
    pg = pg_tree(tmp_path / "source")
    (pg / "postgresql.conf").chmod(0o644)
    with pytest.raises(Blocked, match="permission"):
        file_inventory(pg)


def test_source_changes_during_copy_refused(tmp_path, monkeypatch):
    pg = pg_tree(tmp_path / "source")
    inventory, directories, _ = file_inventory(pg)
    orig = ns["copy_verified"].__globals__["file_inventory"]
    def changed(q):
        result = orig(q)
        return ({**result[0], Path("PG_VERSION"): (99, "tampered")}, result[1], result[2])
    monkeypatch.setitem(ns["copy_verified"].__globals__, "file_inventory", changed)
    third = tmp_path / "third" / "pgdata"
    third.parent.mkdir(mode=0o700)
    with pytest.raises(Blocked, match="changed"):
        copy_verified(pg, third, inventory, directories)


def test_not_running_in_codespace_is_refused_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        ns["private_root"]()
