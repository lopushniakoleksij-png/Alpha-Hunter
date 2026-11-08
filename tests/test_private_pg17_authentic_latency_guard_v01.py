"""Fast mock-only guards for authentic private PostgreSQL latency runner.

These tests never touch a Codespace, a database, or real credentials.
They prove fail-closed fixture, SQL-quoting, and execution prerequisites only.
"""
import importlib.util
import json
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


def test_audit_sql_uses_only_synthetic_run_id():
    run = fixture()["p_parent"][0]["run_id"]
    audit = qa.scan_evidence_query(run)
    assert "alpha_hunter_payoff_geometry_health_observations_v01" in audit
    assert "alpha_hunter_calibrated_paper_orders_v01" in audit
    assert "alpha_hunter_strategy_24h_outcome_queue_v01" in audit
    with pytest.raises(qa.QABlocked, match="Non-synthetic run identifier"):
        qa.scan_evidence_query("production_123")


def test_offline_rpc_measurement_requires_exact_counts_and_all_nested_branches():
    f = qa.validate_fixture(fixture(), 30)
    result = {**{
        "parents": 1, "symbols": 30, "signals": 0, "features": 0, "readiness": 30
    }, **{name: 1 for name in (
        "observations", "quotes", "freezes", "payoff",
        "calibrated_orders", "queue"
    )}}
    def output(payload):
        return json.dumps([{"Execution Time": 345.67}]) + "\n" + json.dumps(payload)

    assert qa.parse_measured_trial(output(result), f) == pytest.approx(345.67)

    for name, value in (
        ("symbols", 29),
        ("payoff", 0),
        ("queue", 0),
        ("calibrated_orders", 0),
        ("parents", True),
    ):
        bad = dict(result, **{name: value})
        with pytest.raises(qa.QABlocked):
            qa.parse_measured_trial(output(bad), f)


def test_cleanliness_check_accepts_no_existing_core_or_nested_evidence(monkeypatch):
    calls = []
    def fake_psql(sql):
        calls.append(sql)
        return json.dumps({name: 0 for name in qa.AUDIT_FAMILIES})

    monkeypatch.setattr(qa, "psql", fake_psql)
    qa.require_clean_qa_run(fixture()["p_parent"][0]["run_id"])
    assert len(calls) == 1
    assert "alpha_hunter_symbol_snapshots" in calls[0]
    assert "alpha_hunter_payoff_geometry_health_observations_v01" in calls[0]


@pytest.mark.parametrize("overrides", [
    {"parents": 1},
    {"symbols": 30},
    {"observations": 1},
    {"payoff": 1},
    {"queue": 1},
    {"parents": False},  # bool is not a real SQL row count
])
def test_cleanliness_check_rejects_stale_or_inconsistent_evidence(monkeypatch, overrides):
    counters = {name: 0 for name in qa.AUDIT_FAMILIES}
    counters.update(overrides)
    monkeypatch.setattr(qa, "psql", lambda sql: json.dumps(counters))
    with pytest.raises(qa.QABlocked, match="preexisting or unrolled-back"):
        qa.require_clean_qa_run(fixture()["p_parent"][0]["run_id"])


def test_cleanliness_check_rejects_missing_or_malformed_receipt(monkeypatch):
    monkeypatch.setattr(qa, "psql", lambda sql: json.dumps({"parents": 0}))
    with pytest.raises(qa.QABlocked):
        qa.require_clean_qa_run(fixture()["p_parent"][0]["run_id"])


def test_latency_trial_checks_rollback_before_and_after_measurement(monkeypatch):
    f = qa.validate_fixture(fixture(), 30)
    clean = json.dumps({name: 0 for name in qa.AUDIT_FAMILIES})
    nested = {name: 1 for name in (
        "observations", "quotes", "freezes", "payoff",
        "calibrated_orders", "queue",
    )}
    counts = {
        "parents": 1, "symbols": 30, "signals": 0,
        "features": 0, "readiness": 30, **nested,
    }
    calls = []

    def fake_psql(sql):
        calls.append(sql)
        if "EXPLAIN (ANALYZE" in sql:
            return json.dumps([{"Execution Time": 321.5}]) + "\n" + json.dumps(counts)
        return clean

    monkeypatch.setattr(qa, "psql", fake_psql)
    monkeypatch.setattr(qa, "WARMUPS", 0)
    monkeypatch.setattr(qa, "REPEATS", 1)
    result = qa.benchmark_one(f)
    assert result["n"] == 1
    assert result["p95_ms"] == 321.5
    assert len(calls) == 3
    assert "EXPLAIN (ANALYZE" in calls[1]
    assert "ROLLBACK;" in calls[1]


def test_benchmark_wont_call_rpc_when_preexisting_run_found(monkeypatch):
    f = qa.validate_fixture(fixture(), 30)
    calls = []
    def fake_psql(sql):
        calls.append(sql)
        return json.dumps({**{name: 0 for name in qa.AUDIT_FAMILIES}, "parents": 1})

    monkeypatch.setattr(qa, "psql", fake_psql)
    with pytest.raises(qa.QABlocked, match="preexisting or unrolled-back"):
        qa.benchmark_one(f)
    assert len(calls) == 1
    assert "EXPLAIN" not in calls[0]
