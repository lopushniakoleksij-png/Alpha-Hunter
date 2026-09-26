from pathlib import Path

from alpha_hunter.scientific_identity import build_scientific_fingerprint


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    package = root / "alpha_hunter"
    package.mkdir(parents=True)
    (package / "strategy_engine.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (root / "strategy_forward_outcome_ledger_v01.sql").write_text(
        "select 1;\n",
        encoding="utf-8",
    )
    (root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (root / "hourly.py").write_text("INTERVAL = 20\n", encoding="utf-8")
    (root / ".python-version").write_text("3.12.14\n", encoding="utf-8")
    (root / "requirements.txt").write_text(
        "requests>=2.32,<3\n",
        encoding="utf-8",
    )
    (root / "web.py").write_text("UI = 'v1'\n", encoding="utf-8")
    return root


def test_fingerprint_ignores_dashboard_only_file_changes(tmp_path):
    root = make_root(tmp_path)
    config = {"minimum_reward_risk": 5}

    before = build_scientific_fingerprint(config, root=root)["sha256"]
    (root / "web.py").write_text("UI = 'v2'\n", encoding="utf-8")
    after = build_scientific_fingerprint(config, root=root)["sha256"]

    assert after == before


def test_fingerprint_changes_when_scientific_python_changes(tmp_path):
    root = make_root(tmp_path)
    config = {"minimum_reward_risk": 5}

    before = build_scientific_fingerprint(config, root=root)["sha256"]
    (root / "alpha_hunter" / "strategy_engine.py").write_text(
        "VALUE = 2\n",
        encoding="utf-8",
    )
    after = build_scientific_fingerprint(config, root=root)["sha256"]

    assert after != before


def test_fingerprint_changes_when_evidence_sql_changes(tmp_path):
    root = make_root(tmp_path)
    config = {"minimum_reward_risk": 5}

    before = build_scientific_fingerprint(config, root=root)["sha256"]
    (root / "strategy_forward_outcome_ledger_v01.sql").write_text(
        "select 2;\n",
        encoding="utf-8",
    )
    after = build_scientific_fingerprint(config, root=root)["sha256"]

    assert after != before


def test_fingerprint_changes_when_canonical_config_changes(tmp_path):
    root = make_root(tmp_path)

    before = build_scientific_fingerprint(
        {"minimum_reward_risk": 5},
        root=root,
    )["sha256"]
    after = build_scientific_fingerprint(
        {"minimum_reward_risk": 6},
        root=root,
    )["sha256"]

    assert after != before


def test_fingerprint_manifest_excludes_tests_and_ui(tmp_path):
    root = make_root(tmp_path)
    result = build_scientific_fingerprint(
        {"minimum_reward_risk": 5},
        root=root,
    )

    assert "web.py" not in result["files"]
    assert "alpha_hunter/strategy_engine.py" in result["files"]
    assert "hourly.py" in result["files"]
    assert ".python-version" in result["files"]
    assert "strategy_forward_outcome_ledger_v01.sql" in result["files"]
    assert "requirements.txt" in result["files"]


def test_fingerprint_changes_when_python_runtime_pin_changes(tmp_path):
    root = make_root(tmp_path)
    config = {"minimum_reward_risk": 5}

    before = build_scientific_fingerprint(config, root=root)["sha256"]
    (root / ".python-version").write_text("3.12.15\n", encoding="utf-8")
    after = build_scientific_fingerprint(config, root=root)["sha256"]

    assert after != before
