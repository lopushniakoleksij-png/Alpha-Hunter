from __future__ import annotations

import json

from alpha_hunter.storage import SupabaseConfig
from alpha_hunter.test_engine import RealtimeTestEngine, format_report


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.posts = []
        self.gets = []

    def get(self, url, *, params, headers, timeout):
        relation = url.rsplit("/", 1)[-1]
        self.gets.append((relation, params))
        row = self.rows.get(relation)
        return FakeResponse(200, [] if row is None else [row])

    def post(self, url, *, params, headers, data, timeout):
        self.posts.append((url, params, json.loads(data)))
        return FakeResponse(201, [])


def settings():
    return SupabaseConfig(
        url="https://example.supabase.co",
        key="test-key",
        timeout_seconds=5,
    )


def healthy_rows(*, profitability_status="RUNNING_MINIMUM_DURATION_NOT_MET"):
    return {
        "alpha_hunter_realtime_profitability_monitor_v01": {
            "spec_id": "TEST-SPEC",
            "real_test_requested_at_utc": "2026-09-22T19:28:33+00:00",
            "real_counted_baseline_started_at_utc": "2026-09-22T20:00:00+00:00",
            "latest_live_run_id": "run-1",
            "latest_live_scan_at_utc": "2026-09-22T20:30:00+00:00",
            "latest_live_scan_age_seconds": 60,
            "latest_live_git_commit": "abc123",
            "latest_live_config_sha256": "cfg123",
            "previous_snapshot_source": "SUPABASE_CANONICAL",
            "catalyst_version": "0.2",
            "configured_strategy_count": 10,
            "real_scans_since_registration": 2,
            "real_strategy_observations_since_registration": 480,
            "real_shadow_candidates_since_registration": 3,
            "real_24h_forward_outcomes_since_registration": 0,
            "realtime_test_status": "RUNNING_FORWARD_REAL_TIME",
        },
        "alpha_hunter_profitability_validation_status_v01": {
            "spec_id": "TEST-SPEC",
            "test_activated": True,
            "identity_drift_gate_met": True,
            "profitability_test_status": profitability_status,
            "completed_paper_trades": 3,
            "test_days_elapsed": 0.5,
            "minimum_test_days": 30,
            "minimum_completed_paper_trades": 100,
            "avg_gross_r": 0.4,
            "gross_r_lower_95": -0.2,
            "avg_floor_adjusted_r": 0.1,
            "floor_adjusted_r_lower_95": -0.4,
            "floor_profit_factor": 1.1,
            "avg_modeled_net_r": None,
            "modeled_net_r_lower_95": None,
            "modeled_net_profit_factor": None,
            "cost_model_validated": False,
            "realistic_net_r_claim_permitted": False,
            "duration_gate_met": False,
            "sample_gate_met": False,
            "conservative_floor_edge_gate_met": False,
            "modeled_net_edge_gate_met": False,
        },
        "alpha_hunter_strategy_forward_status_v01": {
            "forward_outcomes": 0,
            "strategy_episodes": 30,
        },
        "alpha_hunter_strategy_opportunity_status_v01": {
            "opportunity_path_rows": 10,
        },
        "alpha_hunter_execution_cost_floor_status_v01": {
            "cost_scope": "ALL",
            "scientific_status": "DESCRIPTIVE_OBSERVED_COST_FLOOR_ONLY",
            "next_gate": "FORWARD_DECISION_TO_FILL_BENCHMARK_AND_SLIPPAGE_VALIDATION",
        },
    }


def test_engine_reports_operational_pass_but_profit_not_proven_without_cost_model():
    session = FakeSession(healthy_rows())
    engine = RealtimeTestEngine(settings(), session=session)

    report = engine.evaluate().row

    assert report["operational_status"] == "PASS"
    assert report["verdict"] == "TEST_RUNNING"
    assert report["real_time"] is True
    assert report["forward_only"] is True
    assert report["paper_only"] is True
    assert report["trade_permission"] is False
    assert report["order_path"] == "NONE"
    assert "VALIDATED_EXECUTION_COST_MODEL_MISSING" in report["blockers"]
    assert report["source_status"]["operational_blockers"] == []


def test_engine_blocks_operational_health_when_live_architecture_is_stale():
    rows = healthy_rows()
    live = rows["alpha_hunter_realtime_profitability_monitor_v01"]
    live["latest_live_scan_age_seconds"] = 8000
    live["latest_live_git_commit"] = None
    live["configured_strategy_count"] = 0
    live["previous_snapshot_source"] = "NONE"
    live["catalyst_version"] = None

    report = RealtimeTestEngine(
        settings(),
        session=FakeSession(rows),
    ).evaluate().row

    assert report["operational_status"] == "BLOCKED"
    assert "LIVE_SCAN_STALE" in report["blockers"]
    assert "LIVE_BUILD_IDENTITY_MISSING" in report["blockers"]
    assert "S1_S10_COVERAGE_NOT_10" in report["blockers"]
    assert "PREVIOUS_CANONICAL_CONTEXT_MISSING" in report["blockers"]
    assert "CATALYST_EVIDENCE_NOT_V02" in report["blockers"]


def test_engine_verdict_only_calls_paper_edge_when_sealed_status_does():
    rows = healthy_rows(
        profitability_status="POSITIVE_NET_EDGE_DEMONSTRATED_IN_SEALED_PAPER_TEST"
    )
    validation = rows["alpha_hunter_profitability_validation_status_v01"]
    validation["cost_model_validated"] = True
    validation["realistic_net_r_claim_permitted"] = True
    validation["duration_gate_met"] = True
    validation["sample_gate_met"] = True
    validation["modeled_net_edge_gate_met"] = True
    validation["completed_paper_trades"] = 120
    validation["test_days_elapsed"] = 31

    report = RealtimeTestEngine(
        settings(),
        session=FakeSession(rows),
    ).evaluate().row

    assert report["verdict"] == "PAPER_EDGE_DEMONSTRATED"
    assert report["live_money_claim_permitted"] is False
    assert report["production_promotion_permitted"] is False


def test_engine_persists_immutable_status_row():
    session = FakeSession(healthy_rows())
    engine = RealtimeTestEngine(settings(), session=session)
    report = engine.evaluate()

    engine.persist(report)

    assert len(session.posts) == 1
    url, params, payload = session.posts[0]
    assert url.endswith("/alpha_hunter_test_engine_runs_v01")
    assert params["on_conflict"] == "test_engine_run_id"
    assert payload["trade_permission"] is False
    assert payload["paper_only"] is True


def test_report_format_is_phone_friendly():
    report = RealtimeTestEngine(
        settings(),
        session=FakeSession(healthy_rows()),
    ).evaluate()

    text = format_report(report)

    assert "ALPHA HUNTER REAL-TIME TEST ENGINE" in text
    assert "operational_status=PASS" in text
    assert "paper_only=true trade_permission=false order_path=NONE" in text
