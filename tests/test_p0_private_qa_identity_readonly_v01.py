"""P0 private-QA identity separation, with no Docker or database execution."""
import ast
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/local/p0_private_qa_identity_readonly_v01.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ah_private_qa_identity", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reference_and_authentic_restored_target_are_never_equated():
    mod = load_module()
    assert mod.REFERENCE_DB == "ah_authentic_schema_20261110"
    assert mod.RESTORED_DB == "alpha_hunter_private_qa"
    assert mod.REFERENCE_DB != mod.RESTORED_DB
    assert mod.CONTAINER == "alpha-hunter-private-postgres17-qa"
    assert mod.IMAGE == "public.ecr.aws/supabase/postgres:17.6.1.156"


@pytest.mark.parametrize(
    ("rows", "want"),
    [
        ("", (False, False)),
        ("ah_authentic_schema_20261110", (True, False)),
        ("alpha_hunter_private_qa", (False, True)),
        ("ah_authentic_schema_20261110\nalpha_hunter_private_qa", (True, True)),
    ],
)
def test_db_inventory_valid_names_only(rows, want):
    assert load_module().classify_inventory(rows) == want


def test_unexpected_db_inventory_refuses_without_disclosure():
    mod = load_module()
    with pytest.raises(mod.Blocked, match="unexpected local PostgreSQL identity"):
        mod.classify_inventory("production\nah_authentic_schema_20261110")


def test_readonly_code_never_starts_or_rewrites_container():
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(SOURCE))
    docker_verbs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.List) and len(node.elts) >= 2:
            first, second = node.elts[:2]
            if isinstance(first, ast.Constant) and first.value == "docker":
                assert isinstance(second, ast.Constant)
                docker_verbs.add(second.value)
    assert docker_verbs == {"inspect", "exec"}
    for prohibited in ("ALTER SYSTEM", "DROP DATABASE", "CREATE DATABASE",
                       "pg_terminate_backend", '"docker", "start"',
                       '"docker", "restart"', '"docker", "rm"'):
        assert prohibited not in text
    assert "default_transaction_read_only=on" in text
    assert "NetworkMode" in text
    assert "QA_SCHEMA_PARITY=NOT_VERIFIED" in text
    assert "QA_RESTART_AUTHORIZATION=NOT_GRANTED" in text


def test_requires_private_codespace_and_does_not_run_ci(monkeypatch, capsys):
    mod = load_module()
    monkeypatch.delenv("CODESPACES", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(mod, "command", lambda *_a, **_kw: pytest.fail("should not execute"))
    assert mod.main() == 2
    assert "QA_IDENTITY_RESULT=BLOCKED_ENV" in capsys.readouterr().out


def test_stopped_container_is_blocked_before_sql(monkeypatch, capsys):
    mod = load_module()
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    calls = []

    def fake_command(args, **_kwargs):
        calls.append(args)
        if args[0] == "git":
            return mod.BRANCH
        if args[0] == "docker" and args[1] == "inspect":
            return mod.IMAGE + "|docker-entrypoint.sh|no|false|none"
        raise AssertionError("stopped QA must not reach SQL")

    monkeypatch.setattr(mod, "command", fake_command)
    assert mod.main() == 2
    assert len(calls) == 2
    output = capsys.readouterr().out
    assert "QA_IDENTITY_RESULT=BLOCKED_PRIVATE_REVIEW" in output
    assert "QA_SCHEMA_PARITY=NOT_VERIFIED" in output


def test_restored_target_missing_fails_closed(monkeypatch, capsys):
    mod = load_module()
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(
        mod, "command",
        lambda args, **_kwargs: (
            mod.BRANCH if args[0] == "git"
            else mod.IMAGE + "|docker-entrypoint.sh|no|true|none"
        ),
    )
    calls = []
    def fake_sql(db, query):
        calls.append(db)
        if db == "postgres":
            return mod.REFERENCE_DB
        if db == mod.REFERENCE_DB:
            return mod.REFERENCE_DB + "|postgres|170006"
        raise AssertionError("missing full-parity target must not be accessed")
    monkeypatch.setattr(mod, "sql", fake_sql)
    assert mod.main() == 2
    assert calls == ["postgres", mod.REFERENCE_DB]
    assert "QA_IDENTITY_RESULT=BLOCKED_RESTORED_TARGET_MISSING" in capsys.readouterr().out
