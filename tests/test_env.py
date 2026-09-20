import os
from pathlib import Path

from alpha_hunter.env import load_env_file


def test_load_env_file_accepts_plain_assignments(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ALPHA_HUNTER_TEST_PLAIN", raising=False)
    env = tmp_path / ".env"
    env.write_text("ALPHA_HUNTER_TEST_PLAIN=plain-value\n", encoding="utf-8")

    assert load_env_file(env) is True
    assert os.environ["ALPHA_HUNTER_TEST_PLAIN"] == "plain-value"


def test_load_env_file_accepts_export_prefixed_assignments(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ALPHA_HUNTER_TEST_EXPORT", raising=False)
    env = tmp_path / ".env"
    env.write_text("export ALPHA_HUNTER_TEST_EXPORT='export-value'\n", encoding="utf-8")

    assert load_env_file(env) is True
    assert os.environ["ALPHA_HUNTER_TEST_EXPORT"] == "export-value"


def test_load_env_file_preserves_existing_value_without_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_TEST_OVERRIDE", "existing")
    env = tmp_path / ".env"
    env.write_text("export ALPHA_HUNTER_TEST_OVERRIDE=new\n", encoding="utf-8")

    assert load_env_file(env, override=False) is True
    assert os.environ["ALPHA_HUNTER_TEST_OVERRIDE"] == "existing"


def test_load_env_file_replaces_existing_value_with_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_TEST_OVERRIDE", "existing")
    env = tmp_path / ".env"
    env.write_text("export ALPHA_HUNTER_TEST_OVERRIDE=new\n", encoding="utf-8")

    assert load_env_file(env, override=True) is True
    assert os.environ["ALPHA_HUNTER_TEST_OVERRIDE"] == "new"
