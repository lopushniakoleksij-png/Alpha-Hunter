"""Fast mock-only guards for authentic private PostgreSQL latency runner.

These tests never touch a Codespace, a database, or real credentials.
They prove fail-closed fixture, SQL-quoting, and execution prerequisites only.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "alpha_hunter_offline_latency",
    ROOT / "ops/local/qa_authentic_pg17_rpc_latency_v01.py",
)
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


def fixture(size=30):
    run = "QA_ISOLATED_20261108_CASE"
    children = [{"run_id": run, "symbol": f"TEST{i}USDT", "trade_permission": False}
                for i in range(size)]
    return {
        "synthetic_only": True,
        "p_parent": [{"run_id": run, "symbol_count": size, "error_count": 0}],
        "p_children": children,
        "p_signals": [],
        "p_features": [],
        "p_readiness": children,
    }


def test_correctly_scoped_synthetic_fixture_is_accepted():
    result = qa.validate_fixture(fixture(), 30)
    assert set(result) == set(qa.FAMILIES)
    assert result["p_parent"][0]["symbol_count"] == 30


@pytest.mark.parametrize("mutator", [
    lambda f: f.update(synthetic_only=False),
    lambda f: f["p_parent"][0].update(run_id="real-production-run"),
    lambda f: f["p_parent"][0].update(symbol_count=31),
    lambda f: f["p_children"][0].update(trade_permission=True),
    lambda f: f["p_readiness"][0].update(run_id="another-scan"),
    lambda f: f.pop("p_features"),
])
def test_invalid_or_sensitive_fixture_is_refused(mutator):
    sample = fixture()
    mutator(sample)
    with pytest.raises(qa.QABlocked):
        qa.validate_fixture(sample, 30)


def test_sql_json_literals_escape_quotes_and_only_use_local_rpc():
    sample = fixture()
    sample["p_children"][0]["payload"] = "QA payload with ' ; DROP TABLE public.anything; --"
    sql = qa.statement_for_fixture(qa.validate_fixture(sample, 30))
    assert sql.startswith("EXPLAIN (ANALYZE, BUFFERS, WAL, FORMAT JSON)")
    assert sql.count("public.alpha_hunter_commit_core_scan_v01(") == 1
    assert "with '' ; DROP TABLE" in sql
    assert sql.count("::jsonb") == 5


def test_percentile_interpolation_does_not_exclude_tail():
    assert qa.percentile([10, 20, 30, 40, 50], .5) == 30
    assert qa.percentile([10, 20, 30, 40, 50], .95) == 48
    assert qa.percentile([10, 20, 30, 40, 50], .99) == pytest.approx(49.6)


def test_script_refuses_to_run_outside_codespace(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(qa.QABlocked, match="Existing Codespace only"):
        qa.ensure_offline_clone()


def test_github_actions_never_runs_private_benchmark(monkeypatch):
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(qa.QABlocked, match="never run in GitHub Actions"):
        qa.ensure_offline_clone()
