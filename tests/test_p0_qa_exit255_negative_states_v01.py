"""Fail-closed state and identity regressions for the private exit-255 diagnostic.

All Docker responses are mocked; no private container is accessed.
"""
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "ops/local/p0_qa_exit255_readonly_diag_v01.py"


def _load():
    spec = importlib.util.spec_from_file_location("p0_exit255_negative", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_identity_mismatch_blocks_before_state_or_logs(monkeypatch, capsys):
    module = _load()
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    calls = []

    def fake_command(args, **kwargs):
        calls.append(args)
        if args[:2] == ["git", "branch"]:
            return module.BRANCH + "\n"
        if args[:2] == ["docker", "inspect"]:
            return "unexpected-private-container"
        raise AssertionError("must not inspect state, logs or events after identity mismatch")

    monkeypatch.setattr(module, "command", fake_command)
    assert module.main() == 2
    out = capsys.readouterr().out
    assert "QA_A1_RESULT=BLOCKED_NEEDS_PRIVATE_REVIEW" in out
    assert "unexpected-private-container" not in out
    assert len(calls) == 2


def test_unexpected_container_state_blocks_without_log_access(monkeypatch, capsys):
    module = _load()
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    calls = []

    def fake_command(args, **kwargs):
        calls.append(args)
        if args[:2] == ["git", "branch"]:
            return module.BRANCH
        if args[:2] == ["docker", "inspect"] and ".Config.Image" in args[3]:
            return module.IDENT
        if args[:2] == ["docker", "inspect"] and ".State" in args[3]:
            return '{"Running":false,"ExitCode":255,"OOMKilled":false,"Error":"private secret","Status":"paused"}'
        raise AssertionError("unexpected private data access")

    monkeypatch.setattr(module, "command", fake_command)
    assert module.main() == 2
    out = capsys.readouterr().out
    assert "QA_A1_RESULT=BLOCKED_NEEDS_PRIVATE_REVIEW" in out
    assert "private secret" not in out
    assert not any(args[:2] == ["docker", "logs"] for args in calls)
    assert not any(args[:2] == ["docker", "events"] for args in calls)
