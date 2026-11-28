"""Offline synthetic regression for guarded P0 third-copy psql diagnostic."""
from pathlib import Path
from types import SimpleNamespace
import runpy

import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_third_psql_failure_diagnostic_once_v01.py"),
    run_name="private_diag_unit_tests",
)
Blocked = S["Blocked"]


@pytest.mark.parametrize(("stderr", "expected"), [
    ("psql: error: connection to server on socket failed: No such file or directory",
     "SOCKET_OR_SERVER_CONNECTION"),
    ('psql: error: connection to server on socket "/tmp/.s.PGSQL.65432" failed: FATAL: database "postgres" does not exist',
     "DATABASE_NOT_FOUND"),
    ('psql: error: connection to server on socket "/tmp/.s.PGSQL.65432" failed: FATAL: role "postgres" does not exist',
     "ROLE_NOT_FOUND"),
    ('FATAL: database "postgres" does not exist', "DATABASE_NOT_FOUND"),
    ('FATAL: role "postgres" does not exist', "ROLE_NOT_FOUND"),
    ('FATAL: peer authentication failed for user "postgres"', "AUTHENTICATION"),
    ("FATAL: permission denied", "PERMISSION"),
    ("ERROR: cannot execute CREATE TABLE in a read-only transaction", "READ_ONLY_SQL_VIOLATION"),
    ("ERROR: relation unknown does not exist", "SQL_SYNTAX_OR_CATALOG"),
    ("psql: error: unexpected client failure", "CLIENT_CONFIGURATION_OR_OTHER"),
    ("unexpected diagnostics from private server", "CLIENT_UNKNOWN_NONZERO"),
])
def test_private_client_errors_are_classified_without_leaking(stderr, expected):
    assert S["classify_client_error"](stderr, 2) == expected


def test_zero_exit_always_no_error_category():
    assert S["classify_client_error"]('password=private token=secret', 0) == "NONE"


def test_sensitive_user_details_are_not_in_error_category():
    err = 'FATAL: database "very-private-qa" does not exist password=secret; SELECT * FROM private'
    value = S["classify_client_error"](err, 2)
    assert value == "DATABASE_NOT_FOUND"
    for forbidden in ("very-private-qa", "secret", "SELECT"):
        assert forbidden not in value


def test_launch_is_separate_single_named_networkless_nonprivileged_third_copy(tmp_path):
    pg = tmp_path / "pgdata"
    image_id = "sha256:" + "a" * 64
    args = S["start_args"](pg, image_id)
    assert args[:3] == ["docker", "run", "-d"]
    assert args[args.index("--network") + 1] == "none"
    assert "--read-only" in args
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert args[args.index("--user") + 1] != "0:0"
    assert args[args.index("--name") + 1] == S["DIAG"]
    assert args[args.index("--entrypoint") + 1] == "/bin/sh"
    binds = [args[i + 1] for i, arg in enumerate(args) if arg == "--mount"]
    assert len(binds) == 1
    assert binds[0] == "type=bind,source=" + str(pg) + ",target=" + S["PGDATA"]
    assert "local all postgres trust" in args[-1]
    assert "default_transaction_read_only=on" in args[-1]
    assert image_id in args
    for bad in ("--privileged", "--publish", "-p", "--volumes-from", "--env-file", "docker.sock"):
        assert bad not in args


def test_only_two_allowlisted_sql_probes(monkeypatch):
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="1\n", stderr="", returncode=0)
    monkeypatch.setitem(S["psql_probe"].__globals__, "run", fake_run)
    ok = S["psql_probe"]("SELECT 1;")
    assert ok.returncode == 0
    assert "default_transaction_read_only=on" in " ".join(calls[0])
    assert calls[0][calls[0].index("--user")+1] != "0:0"
    with pytest.raises(Blocked, match="unapproved"):
        S["psql_probe"]("DELETE FROM public.some_table;")


def test_no_arg_run_does_not_start_any_container(monkeypatch, capsys):
    calls = []
    monkeypatch.setitem(
        S["main"].__globals__, "preflight",
        lambda: (Path("/third-copy/pgdata"), ("original", "stopped", 2, "digest", "image")),
    )
    monkeypatch.setitem(
        S["main"].__globals__, "run",
        lambda *args, **kwargs: calls.append(args),
    )
    assert S["main"]([]) == 0
    assert not calls
    assert "QA_DIAGNOSTIC_DATABASE_STARTED=NO" in capsys.readouterr().out


@pytest.mark.parametrize("args", [
    ["--force"],
    ["--approve-third-catalog-census"],
    ["--approve-third-psql-diagnostic", "--again"],
])
def test_unapproved_flags_refused_early(args):
    assert S["main"](args) == 2


def test_unknown_codespace_refused_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        S["preflight"]()


def test_stop_failure_remains_blocked(monkeypatch):
    monkeypatch.setitem(
        S["stop_diagnostic"].__globals__,
        "run",
        lambda args, **kwargs: SimpleNamespace(
            stdout='[{"State":{"Status":"running","Running":true}}]',
            stderr="", returncode=0,
        ),
    )
    with pytest.raises(Blocked, match="not safely stopped"):
        S["stop_diagnostic"]()
