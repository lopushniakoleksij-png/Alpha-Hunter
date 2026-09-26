from pathlib import Path

from alpha_hunter.collector import build_validation_identity
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage


SQL = Path("sealed_profitability_source_isolation_v02.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def config():
    return {
        "snapshot_directory": "snapshots",
        "minimum_reward_risk": 5.0,
        "multi_strategy_engine": {
            "enabled": True,
            "minimum_shadow_reward_risk": 5.0,
        },
    }


def test_validation_identity_includes_explicit_run_source(monkeypatch):
    monkeypatch.setenv(
        "ALPHA_HUNTER_RUN_SOURCE",
        "GITHUB_REALTIME_HOURLY",
    )
    identity = build_validation_identity(config())
    assert identity["run_source"] == "GITHUB_REALTIME_HOURLY"
    assert identity["scientific_fingerprint_version"] == "scientific-fingerprint-v0.1"
    assert len(identity["scientific_fingerprint_sha256"]) == 64
    assert identity["scientific_fingerprint_file_count"] > 0
    assert identity["runtime_versions"]["python"]
    assert identity["test_contract"] == "sealed-profitability-v0.1"


def test_sql_binds_activation_and_monitor_to_required_run_source():
    required = [
        "required_run_source",
        "run_source_isolation",
        "run_source_isolated",
        "previous_run_source_ok",
        "forward_only_source_isolated",
    ]
    for marker in required:
        assert marker in LOWER

    assert (
        "p.payload->'validation_identity'->>'run_source'"
        in SQL
    )


def test_paper_economics_requires_first_and_candidate_decisions_from_source():
    required = [
        "fo.observation_id=ep.first_observation_id",
        "co.strategy_instance_id=o.episode_id",
        "co.status='SHADOW_CANDIDATE'",
        "cp.payload->'validation_identity'->>'run_source'",
        "fp.payload->'validation_identity'->>'run_source'",
    ]
    for marker in required:
        assert marker in SQL


def test_source_isolation_never_changes_trading_authority():
    required = [
        "true as paper_only",
        "false as live_money_claim_permitted",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER

    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, rows):
        self.rows = rows

    def json(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.rows)


def modern_payload(source, config_sha):
    return {
        "validation_identity": {
            "run_source": source,
            "config_sha256": config_sha,
            "test_contract": "sealed-profitability-v0.1",
        },
        "multi_strategy_summary": {},
        "microstructure_summary": {},
        "catalyst_summary": {"version": "0.2"},
        "symbols": [],
    }


def test_storage_skips_newer_foreign_source_and_returns_same_source_snapshot():
    expected = {
        "run_source": "GITHUB_REALTIME_HOURLY",
        "config_sha256": "cfg",
        "test_contract": "sealed-profitability-v0.1",
    }
    rows = [
        {
            "run_id": "foreign-new",
            "collected_at_utc": "2026-09-23T05:55:00+00:00",
            "payload": modern_payload("RENDER", "cfg"),
        },
        {
            "run_id": "legacy",
            "collected_at_utc": "2026-09-23T05:50:00+00:00",
            "payload": {"symbols": []},
        },
        {
            "run_id": "same-source",
            "collected_at_utc": "2026-09-23T05:02:00+00:00",
            "payload": modern_payload("GITHUB_REALTIME_HOURLY", "cfg"),
        },
    ]
    session = FakeSession(rows)
    storage = SupabaseStorage(
        SupabaseConfig(
            url="https://example.supabase.co",
            key="test",
        ),
        session=session,
    )

    snapshot = storage.load_latest_snapshot(
        expected_identity=expected,
        require_strategy_context=True,
    )

    assert snapshot is not None
    assert snapshot["run_id"] == "same-source"
    assert session.calls[0][1]["params"]["limit"] == "25"


def test_source_isolated_realtime_monitor_uses_only_latest_spec():
    monitor = LOWER.split(
        "create or replace view public.alpha_hunter_realtime_profitability_monitor_v01",
        1,
    )[1]
    spec_cte = monitor.split("with spec as (", 1)[1].split("),\nlatest_scan as (", 1)[0]
    assert "order by s.preregistered_at_utc desc" in spec_cte
    assert "limit 1" in spec_cte
