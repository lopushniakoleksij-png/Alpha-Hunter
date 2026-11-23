"""Offline synthetic guard tests: no Docker, PostgreSQL, production or private files."""
from pathlib import Path
import runpy
import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_recovery_stage_runtime_readonly_v01.py"),
    run_name="p0_runtime_test"
)
Blocked = S["Blocked"]


def stage(tmp_path, pg_control=True, pg_version=b"17\n", with_wal=True):
    root = tmp_path / "p0_recovery_stage_fixture"
    pg = root / "pgdata"
    (pg / "global").mkdir(parents=True)
    for name in ("base", "pg_wal", "pg_xact", "pg_multixact", "pg_tblspc"):
        (pg / name).mkdir()
    (pg / "PG_VERSION").write_bytes(pg_version)
    if pg_control:
        (pg / "global" / "pg_control").write_bytes(b"x" * 8192)
    if with_wal:
        (pg / "pg_wal" / ("0" * 24)).write_bytes(b"w" * 16)
    return root, pg


def test_flags_are_presence_only_no_private_values(tmp_path):
    _, pg = stage(tmp_path)
    (pg / "postmaster.pid").write_text("12345\n/private/secret/config/path\n")
    (pg / "postgresql.conf").write_text("primary_conninfo = 'private-password'\n")
    wal, signals, configs, tablespaces = S["stage_classification"](pg)
    assert wal == 1
    assert signals["postmaster.pid"]
    assert configs["postgresql.conf"]
    assert not signals["recovery.signal"]
    assert tablespaces == 0


@pytest.mark.parametrize("change", ["no_control", "wrong_version", "no_wal", "no_xact"])
def test_invalid_stage_fails_closed(tmp_path, change):
    _, pg = stage(tmp_path)
    if change == "no_control":
        (pg / "global" / "pg_control").unlink()
    elif change == "wrong_version":
        (pg / "PG_VERSION").write_bytes(b"16\n")
    elif change == "no_wal":
        (pg / "pg_wal" / ("0" * 24)).unlink()
    else:
        (pg / "pg_xact").rmdir()
    with pytest.raises(Blocked):
        S["stage_classification"](pg)


def test_find_stage_is_sole_private_directory(tmp_path):
    root, pg = stage(tmp_path)
    root.chmod(0o700)
    pg.chmod(0o700)
    s = S["ROOT"]
    S["ROOT"] = tmp_path
    try:
        assert S["find_staged"]() == pg
        extra = tmp_path / "p0_recovery_stage_second"
        extra.mkdir(mode=0o700)
        with pytest.raises(Blocked, match="exactly one"):
            S["find_staged"]()
    finally:
        S["ROOT"] = s


def test_stage_symlink_refused(tmp_path):
    root, pg = stage(tmp_path)
    root.chmod(0o700)
    pg.chmod(0o700)
    (pg / "config_link").symlink_to("/private/not-for-qa")
    old = S["ROOT"]
    S["ROOT"] = tmp_path
    try:
        with pytest.raises(Blocked, match="linked"):
            S["find_staged"]()
    finally:
        S["ROOT"] = old


def test_not_in_codespace_blocks_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        S["environment_guard"]()
