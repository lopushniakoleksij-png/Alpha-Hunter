"""Synthetic-only tests for offline recovered PG17 third-copy integrity check.

No real Docker, PostgreSQL, network, production or private physical archive.
"""
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_recovered_third_offline_integrity_v01.py"),
    run_name="p0_recovered_integrity_tests",
)
Blocked = S["Blocked"]


@pytest.mark.parametrize(("value", "expected"), [
    ("Database cluster state: shut down\nData page checksum version: 0\n", 0),
    ("Database cluster state: shut down\nData page checksum version: 1\n", 1),
])
def test_control_reports_shutdown_and_known_checksum_version(value, expected):
    assert S["interpret_control"](value) == expected


@pytest.mark.parametrize("value", [
    "Database cluster state: in production\nData page checksum version: 1\n",
    "Database cluster state: shut down\nData page checksum version: 2\n",
    "Database cluster state: shut down\n",
    "Data page checksum version: 1\n",
    "",
])
def test_control_unknown_or_unclean_state_refused(value):
    with pytest.raises(Blocked):
        S["interpret_control"](value)


def test_failed_checksum_verification_does_not_succeed():
    with pytest.raises(Blocked, match="pg_checksums"):
        S["interpret_checksums"](SimpleNamespace(returncode=1))


def test_successful_checksum_check_uses_exit_code():
    assert S["interpret_checksums"](SimpleNamespace(returncode=0))


@pytest.mark.parametrize(("program", "expected_cmd"), [
    ("pg_controldata", "exec pg_controldata /qa"),
    ("pg_checksums", "exec pg_checksums --check -D /qa"),
])
def test_utility_uses_no_server_read_only_bind_and_networkless_mode(
    monkeypatch, program, expected_cmd,
):
    calls = []
    def fake_shell(argv, timeout=40):
        calls.append((argv, timeout))
        return SimpleNamespace(returncode=0, stdout="")
    monkeypatch.setitem(S["utility"].__globals__, "shell", fake_shell)
    ident = "sha256:" + "a" * 64
    pg = "/isolated/third/pgdata"
    S["utility"](ident, pg, program)
    assert len(calls) == 1
    argv, _ = calls[0]
    assert argv[:3] == ["docker", "run", "--rm"]
    assert argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--entrypoint") + 1] == "/bin/sh"
    assert argv[-1] == expected_cmd
    assert argv[-3] == ident
    mounts = [argv[i+1] for i, x in enumerate(argv) if x == "--mount"]
    assert mounts == ["type=bind,source=" + pg + ",target=/qa,readonly"]
    for forbidden in ("--publish", "-p", "--privileged", "--volume", "--env-file"):
        assert forbidden not in argv


def test_no_checksums_does_not_falsely_claim_page_integrity(monkeypatch, capsys):
    monkeypatch.setitem(
        S["main"].__globals__,
        "custody",
        lambda: ("stopped", 2, "samehash", "/isolated/third/pgdata", "sha256:image", "container")
    )
    calls = []
    def fake_utility(image_id, pgdata, program):
        calls.append(program)
        assert program == "pg_controldata"
        return SimpleNamespace(
            returncode=0,
            stdout="Database cluster state: shut down\nData page checksum version: 0\n"
        )
    monkeypatch.setitem(S["main"].__globals__, "utility", fake_utility)
    assert S["main"]() == 0
    output = capsys.readouterr().out
    assert "QA_OFFLINE_PAGE_CHECKSUM_CHECK=NOT_AVAILABLE" in output
    assert "QA_SCHEMA_PARITY=NOT_YET_VERIFIED" in output
    assert calls == ["pg_controldata"]


def test_outside_codespace_fails_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        S["custody"]()
