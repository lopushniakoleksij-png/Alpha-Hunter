"""Synthetic offline tests for static third-copy runtime security review.

Never reaches Docker daemon, original private archives, or PostgreSQL.
"""
import json
import runpy
from pathlib import Path

import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_third_copy_prestart_security_review_v01.py"),
    run_name="third_security_test",
)
Blocked = S["Blocked"]
inspect_tree = S["inspect_tree"]
require_dir = S["require_dir"]
require_file = S["require_file"]


def private_dir(path):
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)


def private_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o600)


def fixture(tmp_path):
    source = tmp_path / "p0_recovery_stage_TEST" / "pgdata"
    third_root = tmp_path / "p0_recovery_runtime_TEST"
    third = third_root / "pgdata"
    vault = third_root / ".p0_prestart_saved"
    for folder in (source, third, vault):
        private_dir(folder)
    for d in S["REQUIRED_DIRS"]:
        private_dir(third / d)
    for name in S["INHERITED"]:
        original = (b"1234\nPRIVATE_DATA\n" if name == "postmaster.pid"
                    else b"PRIVATE CONFIGURATION WITH CREDENTIALS")
        private_file(source / name, original)
        private_file(vault / (name + ".third_original"), original)
    for name, safe in S["SAFE_CONFIG"].items():
        private_file(third / name, safe.encode("ascii"))
    for name, value in (
        ("PG_VERSION", b"17\n"),
        ("global/pg_control", b"NOT_A_REAL_PG_CONTROL" * 100),
    ):
        private_file(source / name, value)
        private_file(third / name, value)
    private_file(third / "pg_wal" / ("0" * 24), b"not real WAL")
    return source, third, vault


def test_static_policy_accepts_exactly_hardened_offline_copy(tmp_path):
    source, third, vault = fixture(tmp_path)
    count, wal = inspect_tree(source, third, vault)
    assert wal == 1
    assert count >= 6
    assert not (third / "postmaster.pid").exists()
    assert (source / "postmaster.pid").exists()


@pytest.mark.parametrize("problem", [
    "unsafe_conf", "inherited_pid", "different_saved", "tablespace_link",
    "recovery_signal", "wrong_version", "missing_wal", "vault_extra",
])
def test_invalid_policy_refuses_without_mutation(tmp_path, problem):
    source, third, vault = fixture(tmp_path)
    if problem == "unsafe_conf":
        private_file(third / "postgresql.conf", b"shared_preload_libraries='pg_cron'\n")
    elif problem == "inherited_pid":
        private_file(third / "postmaster.pid", b"12345")
    elif problem == "different_saved":
        private_file(vault / "postgresql.auto.conf.third_original", b"DIFFERENT")
    elif problem == "tablespace_link":
        (third / "pg_tblspc" / "123").symlink_to("/private/danger")
    elif problem == "recovery_signal":
        private_file(third / "recovery.signal", b"")
    elif problem == "wrong_version":
        private_file(third / "PG_VERSION", b"16\n")
    elif problem == "missing_wal":
        (third / "pg_wal" / ("0" * 24)).unlink()
    else:
        private_file(vault / "extra", b"bad")
    with pytest.raises(Blocked):
        inspect_tree(source, third, vault)
    assert (source / "postmaster.pid").is_file()


def test_runtime_image_checks_platform_digest_only(monkeypatch):
    def fake_run(args, timeout=25):
        assert args == ["docker", "image", "inspect", "postgres:17"]
        return json.dumps([{
            "Os": "linux", "Architecture": "amd64",
            "Id": "sha256:" + "a" * 64,
            "RepoDigests": ["postgres@sha256:" + "b" * 64]
        }])
    monkeypatch.setitem(S["runtime_image"].__globals__, "run", fake_run)
    assert S["runtime_image"]() == ("amd64", True)


def test_runtime_image_fails_closed_for_unverified_metadata(monkeypatch):
    monkeypatch.setitem(
        S["runtime_image"].__globals__, "run",
        lambda args, timeout=25: json.dumps([{
            "Os": "windows", "Architecture": "amd64", "Id": "bad",
        }]),
    )
    with pytest.raises(Blocked):
        S["runtime_image"]()


def test_non_codespace_refused_before_container_or_backup(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        S["environment"]()
