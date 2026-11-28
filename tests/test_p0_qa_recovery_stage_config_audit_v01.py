"""Offline synthetic tests for P0 private staged PostgreSQL configuration key audit."""
import runpy
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[1] /
          "ops/local/p0_qa_recovery_stage_config_audit_v01.py")
module = runpy.run_path(str(SCRIPT), run_name="audit_test")
audit = module["audit"]
parse_settings = module["parse_settings"]
Blocked = module["Blocked"]


def make_stage(tmp_path):
    pg = tmp_path / "pgdata"
    pg.mkdir(mode=0o700)
    (pg / "PG_VERSION").write_bytes(b"17\n")
    (pg / "global").mkdir()
    (pg / "global" / "pg_control").write_bytes(b"mock")
    (pg / "pg_tblspc").mkdir()
    (pg / "postmaster.pid").write_text("12345\n")
    return pg


def test_setting_values_and_credentials_are_never_returned():
    keys, unparsed = parse_settings(
        "# archive_command = 'ignored'\n"
        "primary_conninfo = 'password=never-print-me'\n"
        "shared_preload_libraries = 'pg_cron'\n"
        'include_dir = "secrets-folder"\n'
        "\n"
    )
    assert keys == {"primary_conninfo", "shared_preload_libraries", "include_dir"}
    assert unparsed == 0
    assert "never-print-me" not in repr(keys)


def test_audits_only_setting_names_and_recovery_markers(tmp_path):
    pg = make_stage(tmp_path)
    (pg / "postgresql.conf").write_text(
        "listen_addresses='*'\nshared_preload_libraries='pg_cron'\n"
        "archive_command='some private shell command'\n"
        "include_dir='conf.d'\n"
    )
    (pg / "postgresql.auto.conf").write_text("primary_conninfo='host=private'\n")
    (pg / "pg_hba.conf").write_text("host all all 0.0.0.0/0 trust\n")
    r = audit(pg, {"Config": {"Cmd": ["postgres"]}})
    assert r["config_count"] == 3
    assert r["pid_present"]
    assert r["includes"] == ["include_dir"]
    assert "primary_conninfo" in r["sensitive"]
    assert "archive_command" in r["sensitive"]
    assert "listen_addresses" in r["risk_keys"]
    assert "password" not in repr(r)
    assert "private" not in repr(r)


@pytest.mark.parametrize("change", ("pid_missing", "external_tablespace", "config_symlink", "oversize_config"))
def test_rejects_unsafe_recovery_stage(tmp_path, change):
    pg = make_stage(tmp_path)
    if change == "pid_missing":
        (pg / "postmaster.pid").unlink()
    elif change == "external_tablespace":
        (pg / "pg_tblspc" / "123").write_text("external")
    elif change == "config_symlink":
        (pg / "postgresql.conf").symlink_to("/etc/passwd")
    elif change == "oversize_config":
        (pg / "postgresql.conf").write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(Blocked):
        audit(pg, {"Config": {"Cmd": []}})


def test_unparsed_lines_marked_for_review():
    keys, n = parse_settings("listen_addresses=''\ninvalid config line\n")
    assert keys == {"listen_addresses"}
    assert n == 1


def test_rejects_non_codespace_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        module["guard"]()
