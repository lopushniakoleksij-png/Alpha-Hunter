import json
from pathlib import Path

import alpha_hunter.collector as collector
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage
from alpha_hunter.strategy_engine import apply_multi_strategy_engine


class FakeCloudStorage:
    snapshot = None

    def __init__(self, settings):
        self.settings = settings

    def load_latest_snapshot(self, **kwargs):
        return self.snapshot


def write_local_snapshot(tmp_path: Path, snapshot: dict):
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "latest.json").write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )


def config():
    return {
        "snapshot_directory": "snapshots",
        "minimum_reward_risk": 5.0,
        "candidate_quality": {
            "minimum_execution_reward_risk": 5.0,
            "minimum_data_integrity": 88,
        },
        "multi_strategy_engine": {
            "enabled": True,
            "minimum_shadow_reward_risk": 5.0,
            "minimum_signal_score": 6.5,
            "maximum_spread_pct": 0.15,
        },
    }


def cloud_settings():
    return SupabaseConfig(
        url="https://example.supabase.co",
        key="test",
    )


def test_cloud_snapshot_is_used_when_local_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_RUN_SOURCE", "GITHUB_REALTIME_HOURLY")
    FakeCloudStorage.snapshot = modern_snapshot(
        "cloud-1",
        "2026-09-22T19:00:00+00:00",
    )
    monkeypatch.setattr(collector, "SupabaseStorage", FakeCloudStorage)

    previous, source = collector.load_previous_snapshot(
        tmp_path / "config.json",
        config(),
        cloud_settings=cloud_settings(),
    )

    assert source == "SUPABASE_CANONICAL"
    assert previous["run_id"] == "cloud-1"


def test_newer_cloud_snapshot_wins_over_stale_local(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_RUN_SOURCE", "GITHUB_REALTIME_HOURLY")
    write_local_snapshot(
        tmp_path,
        modern_snapshot(
            "local-old",
            "2026-09-22T18:00:00+00:00",
        ),
    )
    FakeCloudStorage.snapshot = modern_snapshot(
        "cloud-new",
        "2026-09-22T19:00:00+00:00",
    )
    monkeypatch.setattr(collector, "SupabaseStorage", FakeCloudStorage)

    previous, source = collector.load_previous_snapshot(
        tmp_path / "config.json",
        config(),
        cloud_settings=cloud_settings(),
    )

    assert source == "SUPABASE_CANONICAL"
    assert previous["run_id"] == "cloud-new"


def test_newer_local_snapshot_wins_over_cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_RUN_SOURCE", "GITHUB_REALTIME_HOURLY")
    write_local_snapshot(
        tmp_path,
        modern_snapshot(
            "local-new",
            "2026-09-22T20:00:00+00:00",
        ),
    )
    FakeCloudStorage.snapshot = modern_snapshot(
        "cloud-old",
        "2026-09-22T19:00:00+00:00",
    )
    monkeypatch.setattr(collector, "SupabaseStorage", FakeCloudStorage)

    previous, source = collector.load_previous_snapshot(
        tmp_path / "config.json",
        config(),
        cloud_settings=cloud_settings(),
    )

    assert source == "LOCAL_LATEST"
    assert previous["run_id"] == "local-new"


def low_rr_relative_strength_record():
    return {
        "symbol": "TESTUSDT",
        "last_price": 105.0,
        "support": 100.0,
        "resistance": 106.0,
        "data_integrity_score": 100,
        "funding_history": {"extreme": False},
        "behaviour": {
            "spread_pct": 0.02,
            "relative_strength_vs_btc_pct": 3.0,
            "relative_strength_acceleration": 1.0,
        },
        "timeframes": {
            "15m": {"trend": "BULLISH", "indicators": {}},
            "1H": {
                "trend": "BULLISH",
                "support": 100.0,
                "resistance": 106.0,
                "indicators": {},
            },
            "4H": {
                "trend": "BULLISH",
                "support": 98.0,
                "resistance": 106.0,
                "indicators": {},
            },
        },
        "trade_permission": False,
        "v7_trade_ready": False,
    }


def test_watch_never_exposes_execute_now_action_when_rr_gate_fails():
    record = low_rr_relative_strength_record()
    payload = apply_multi_strategy_engine(
        record,
        None,
        config(),
    )
    s4 = next(
        row for row in payload["strategies"]
        if row["strategy_id"] == "S4"
    )

    assert s4["status"] == "WATCH"
    assert s4["proposed_action"] == "EXECUTE_NOW"
    assert s4["action"] == "WAIT_FOR_TRIGGER"
    assert s4["checks"]["rr_minimum_met"] is False
    assert s4["trade_permission"] is False


class FakeReadResponse:
    status_code = 200
    text = ""

    def json(self):
        return [{
            "run_id": "cloud-read",
            "collected_at_utc": "2026-09-22T19:00:00+00:00",
            "payload": {
                "symbols": [{"symbol": "BTCUSDT"}],
            },
        }]


class FakeReadSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeReadResponse()


def test_supabase_storage_reads_latest_canonical_parent_snapshot():
    session = FakeReadSession()
    storage = SupabaseStorage(
        cloud_settings(),
        session=session,
    )

    snapshot = storage.load_latest_snapshot()

    assert snapshot["run_id"] == "cloud-read"
    assert snapshot["collected_at_utc"] == "2026-09-22T19:00:00+00:00"
    assert snapshot["symbols"][0]["symbol"] == "BTCUSDT"
    assert session.calls[0][1]["params"]["order"] == "collected_at_utc.desc"
    assert session.calls[0][1]["params"]["limit"] == "1"


def modern_snapshot(run_id, collected_at, source="GITHUB_REALTIME_HOURLY"):
    return {
        "run_id": run_id,
        "collected_at_utc": collected_at,
        "validation_identity": {
            "run_source": source,
            "git_commit": "abc",
            "git_branch": "main",
            "config_sha256": collector.build_validation_identity(config())["config_sha256"],
            "test_contract": "sealed-profitability-v0.1",
        },
        "multi_strategy_summary": {},
        "microstructure_summary": {},
        "catalyst_summary": {"version": "0.2"},
        "symbols": [],
    }


def test_load_previous_snapshot_rejects_legacy_cloud_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_RUN_SOURCE", "GITHUB_REALTIME_HOURLY")
    FakeCloudStorage.snapshot = {
        "run_id": "legacy",
        "collected_at_utc": "2026-09-23T05:55:00+00:00",
        "symbols": [],
    }
    monkeypatch.setattr(collector, "SupabaseStorage", FakeCloudStorage)

    previous, source = collector.load_previous_snapshot(
        tmp_path / "config.json",
        config(),
        cloud_settings=cloud_settings(),
    )

    assert previous is None
    assert source == "NONE"


def test_load_previous_snapshot_rejects_different_run_source(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_RUN_SOURCE", "GITHUB_REALTIME_HOURLY")
    FakeCloudStorage.snapshot = modern_snapshot(
        "render-run",
        "2026-09-23T05:55:00+00:00",
        source="RENDER",
    )
    monkeypatch.setattr(collector, "SupabaseStorage", FakeCloudStorage)

    previous, source = collector.load_previous_snapshot(
        tmp_path / "config.json",
        config(),
        cloud_settings=cloud_settings(),
    )

    assert previous is None
    assert source == "NONE"


def test_validation_identity_contains_explicit_run_source(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_RUN_SOURCE", "GITHUB_REALTIME_HOURLY")
    identity = collector.build_validation_identity(config())
    assert identity["run_source"] == "GITHUB_REALTIME_HOURLY"
