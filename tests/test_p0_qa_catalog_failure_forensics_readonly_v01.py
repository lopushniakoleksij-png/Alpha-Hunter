"""Synthetic-only tests for P0 catalog failure postmortem; never starts database."""
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_catalog_failure_forensics_readonly_v01.py"),
    run_name="p0_catalog_forensics_test"
)


@pytest.mark.parametrize(("log", "expected"), [
    ("FATAL: database \"postgres\" does not exist", "SERVER_DATABASE_MISSING"),
    ("FATAL: role \"postgres\" does not exist", "SERVER_ROLE_MISSING"),
    ("FATAL: no pg_hba.conf entry for local connection", "SERVER_AUTHENTICATION_REJECTED"),
    ("FATAL: peer authentication failed for user X", "SERVER_AUTHENTICATION_REJECTED"),
    ("FATAL: permission denied", "SERVER_PERMISSION_OR_FILE_PROBLEM"),
    ("PANIC: recovery failed", "SERVER_PANIC"),
    ("FATAL: unexpected server issue", "SERVER_FATAL_OTHER_REVIEW"),
    ("database system is ready to accept connections", "SERVER_NO_CLASSIFYING_ERROR_OBSERVED"),
    ("", "SERVER_NO_CLASSIFYING_ERROR_OBSERVED"),
])
def test_server_logs_reduced_to_nonsecret_category(log, expected):
    assert S["log_classification"](log) == expected


def test_server_logs_cannot_leak_credentials_or_raw_sql():
    log = "FATAL: role 'secret-user' does not exist, password=xyz; SELECT user_secret"
    result = S["log_classification"](log)
    assert result == "SERVER_ROLE_MISSING"
    assert "secret-user" not in result
    assert "xyz" not in result
    assert "SELECT" not in result


def test_unbounded_server_log_not_exposed():
    assert S["log_classification"]("x" * (S["MAX_LOG_BYTES"] + 1)) == (
        "SERVER_LOG_TOO_LARGE_UNCLASSIFIED"
    )


def test_does_not_start_or_stop_server_on_previous_query_failure(monkeypatch, capsys):
    pg = Path("/isolated/third/pgdata")
    original = {"Id": "stopped-original", "State": {"Status": "exited"}}
    census = {"State": {"Status": "exited", "Running": False}}
    monkeypatch.setitem(S["main"].__globals__, "custody",
                        lambda: (original, 2, pg, census))
    monkeypatch.setitem(S["main"].__globals__, "command",
                        lambda args, **kwargs: SimpleNamespace(stdout="", stderr=""))
    assert S["main"]() == 0
    result = capsys.readouterr().out
    assert "QA_PRIOR_CLIENT_PSQL_STDERR=NOT_RETAINED" in result
    assert "QA_PSQL_QUERY_FAILURE_ROOT_CAUSE=NOT_YET_VERIFIED" in result
    assert "QA_POSTGRES_SERVER_STARTED=NO" in result
    assert "QA_AUTO_RETRY=NOT_AUTHORISED" in result


def test_running_catalog_container_fails_closed_without_stop(monkeypatch):
    census = {"State": {"Status": "running", "Running": True}}
    monkeypatch.setitem(S["main"].__globals__, "custody",
                        lambda: ({}, 2, Path("/nowhere"), census))
    assert S["main"]() == 2


def test_original_codespace_required_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(S["Blocked"], match="Codespace"):
        S["custody"]()
