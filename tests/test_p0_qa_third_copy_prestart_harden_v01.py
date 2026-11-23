"""Offline synthetic tests for third-copy-only PG17 recovery hardening.

No Docker calls, server start, real Codespace backup or production access.
"""
from pathlib import Path
import runpy

import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_third_copy_prestart_harden_v01.py"),
    run_name="p0_third_harden_test"
)
Blocked = S["Blocked"]


def make_pair(tmp_path):
    stage = tmp_path / "p0_recovery_stage_TEST"
    third = tmp_path / "p0_recovery_runtime_TEST"
    for root in (stage, third):
        d = root / "pgdata"
        d.mkdir(parents=True, mode=0o700)
        for dirname in S["DIRS"]:
            (d / dirname).mkdir(mode=0o700)
        for name, value in {
            "PG_VERSION": b"17\n",
            "global/pg_control": b"x" * 8192,
            "postmaster.pid": b"9876\n/owner-private/secret\n",
            "postgresql.conf": b"shared_preload_libraries='pg_cron'\n",
            "postgresql.auto.conf": b"cron.launch_active_jobs='on'\n",
            "pg_hba.conf": b"host all all 0.0.0.0/0 trust\n",
            "pg_ident.conf": b"# private config\n",
        }.items():
            f = d / name
            f.write_bytes(value)
            f.chmod(0o600)
    return stage, third


def test_only_third_copy_is_hardened_and_original_stage_unmodified(tmp_path):
    stage, third = make_pair(tmp_path)
    source = stage / "pgdata"
    dest = third / "pgdata"
    source_hashes = {name: S["digest"](source / name) for name in S["INHERITED"]}
    assert S["harden_third_copy"](dest, third) == 5
    for name in S["INHERITED"]:
        assert (source / name).is_file()
        assert S["digest"](source / name) == source_hashes[name]
        private_saved = third / ".p0_prestart_saved" / (name + ".third_original")
        assert private_saved.is_file()
        assert S["digest"](private_saved) == source_hashes[name]
        assert private_saved.stat().st_mode & 0o777 == 0o600
    assert not (dest / "postmaster.pid").exists()
    assert "pg_cron" not in (dest / "postgresql.conf").read_text()
    assert "shared_preload_libraries = ''" in (dest / "postgresql.conf").read_text()
    assert "listen_addresses = ''" in (dest / "postgresql.conf").read_text()
    assert (dest / "postgresql.auto.conf").read_text().startswith("# Third-copy only")
    assert "0.0.0.0/0 reject" in (dest / "pg_hba.conf").read_text()
    assert (third / ".p0_prestart_saved").stat().st_mode & 0o777 == 0o700


def test_bad_third_copy_config_never_modified_by_preflight(tmp_path):
    stage, third = make_pair(tmp_path)
    before = (third / "pgdata" / "postgresql.auto.conf").read_bytes()
    old = S["paths_preflight"].__globals__["ROOT"]
    S["paths_preflight"].__globals__["ROOT"] = tmp_path
    try:
        (third / "pgdata" / "pg_ident.conf").write_text("changed on third")
        with pytest.raises(Blocked, match="differs"):
            S["paths_preflight"]()
        assert (third / "pgdata" / "postgresql.auto.conf").read_bytes() == before
        assert not (third / ".p0_prestart_saved").exists()
    finally:
        S["paths_preflight"].__globals__["ROOT"] = old


@pytest.mark.parametrize("bad", ("tablespace", "stage_symlink", "existing_vault", "no_pid"))
def test_unsafe_third_prestart_blocks_before_mutation(tmp_path, bad):
    stage, third = make_pair(tmp_path)
    if bad == "tablespace":
        (third / "pgdata/pg_tblspc/1").write_text("external")
    elif bad == "stage_symlink":
        (stage / "pgdata/pg_wal").rmdir()
        (stage / "pgdata/pg_wal").symlink_to("/private/other")
    elif bad == "existing_vault":
        (third / ".p0_prestart_saved").mkdir()
    else:
        (third / "pgdata/postmaster.pid").unlink()
    old = S["paths_preflight"].__globals__["ROOT"]
    S["paths_preflight"].__globals__["ROOT"] = tmp_path
    try:
        with pytest.raises(Blocked):
            S["paths_preflight"]()
        assert (third / "pgdata" / "postgresql.conf").is_file()
    finally:
        S["paths_preflight"].__globals__["ROOT"] = old


def test_command_refuses_outside_codespace_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        S["private_preflight"]()
