"""Offline safety checks for private QA exit-255 diagnostic. No Docker calls."""
import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/local/p0_qa_exit255_readonly_diag_v01.py"


def _load():
    spec = importlib.util.spec_from_file_location("ah_p0_exit_diag", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostic_restricts_docker_to_readonly_inspect_logs_events():
    content = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(SOURCE))
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.List) and len(node.elts) >= 2:
            first, second = node.elts[:2]
            if isinstance(first, ast.Constant) and first.value == "docker":
                assert isinstance(second, ast.Constant)
                calls.append(second.value)
    assert set(calls) == {"inspect", "logs", "events"}
    for prohibited in (
        '"docker", "start"', '"docker", "stop"', '"docker", "restart"',
        '"docker", "exec"', '"docker", "rm"', '"docker", "run"',
        "pg_terminate_backend", "ALTER SYSTEM", "DROP DATABASE"
    ):
        assert prohibited not in content
    assert "QA_RESTART_AUTHORIZATION=NOT_GRANTED" in content
    assert "QA_RESTART_ALLOWED=NO" in content
    assert "PRODUCTION_RELEASE=NO_GO" in content
    assert "GITHUB_ACTIONS" in content


def test_diagnostic_classifies_logs_without_disclosing_sql():
    module = _load()
    classified = module.classify_logs(
        "FATAL: password supplied in secret SQL\n"
        "database system is shut down\n"
        "permission denied for sensitive schema\n"
        "PANIC: unrecoverable\n"
        "no space left\n"
    )
    assert classified["FATAL"] == 1
    assert classified["PANIC"] == 1
    assert classified["PERMISSION_DENIED"] == 1
    assert classified["NORMAL_SHUTDOWN"] == 1
    assert classified["DISK_FULL"] == 1
    assert "secret" not in str(classified)


def test_diagnostic_event_parser_only_counts_known_actions():
    module = _load()
    result = module.classify_events(
        '{"Action":"die","Actor":{"Attributes":{"secret":"do not print"}}}\n'
        '{"Action":"stop"}\n'
        '{"Action":"die"}\n'
        '{"Action":"some_untrusted_extra_key"}\n'
        'invalid json\n'
    )
    assert result["die"] == 2
    assert result["stop"] == 1
    assert sum(result.values()) == 3
    assert "secret" not in str(result)


def test_private_environment_gate_is_fail_closed(monkeypatch, capsys):
    module = _load()
    monkeypatch.delenv("CODESPACES", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert module.main() == 2
    assert "QA_A1_RESULT=BLOCKED_ENV" in capsys.readouterr().out
