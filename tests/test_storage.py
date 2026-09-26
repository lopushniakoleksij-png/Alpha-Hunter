from pathlib import Path
from datetime import datetime, timezone

import pytest
import requests

from alpha_hunter.storage import (
    SupabaseConfig,
    SupabaseStorage,
    SupabaseStorageError,
    build_run_id,
)
from hourly import (
    next_scan_at,
    remaining_burst_boundaries,
    render_cron_burst_enabled,
    should_run_initial_burst_scan,
    seconds_until_next_hour,
    seconds_until_next_interval,
)


class FakeResponse:
    status_code = 201
    text = ""


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


class SequencedSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    post = get


class StatusResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def sample_snapshot():
    return {
        "version": "0.3.0",
        "collected_at_utc": "2026-07-26T18:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "SUIUSDT",
            "state": "WATCH_LONG",
            "trade_permission": False,
            "last_price": 0.75,
            "execution_setup": {"direction": None, "rr": None},
        }],
    }


def test_run_id_is_deterministic():
    first = sample_snapshot()
    second = sample_snapshot()
    assert build_run_id(first) == build_run_id(second)


def test_supabase_writes_parent_and_children():
    session = FakeSession()
    storage = SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="secret"), session=session
    )
    run_id = storage.save_snapshot(sample_snapshot())
    assert len(run_id) == 32
    assert len(session.calls) == 5
    assert session.calls[0][1]["params"] == {"on_conflict": "run_id"}
    assert session.calls[1][1]["params"] == {"on_conflict": "run_id,symbol"}
    assert session.calls[2][1]["params"] == {"on_conflict": "signal_id"}
    assert session.calls[3][1]["params"] == {"on_conflict": "signal_id"}
    assert session.calls[4][1]["params"] == {"on_conflict": "run_id,symbol"}
    assert session.calls[2][0].endswith("/rest/v1/alpha_hunter_signals")
    assert session.calls[3][0].endswith("/rest/v1/alpha_hunter_signal_features")
    assert session.calls[4][0].endswith(
        "/rest/v1/alpha_hunter_readiness_observations_v01"
    )


def test_supabase_read_retries_transient_status_then_succeeds():
    session = SequencedSession([
        StatusResponse(503, text="temporary upstream reset"),
        StatusResponse(200, payload=[]),
    ])
    storage = SupabaseStorage(
        SupabaseConfig(
            url="https://example.supabase.co",
            key="secret",
            max_retries=2,
            retry_backoff_seconds=0,
        ),
        session=session,
    )

    assert storage.load_latest_snapshot() is None
    assert len(session.calls) == 2


def test_supabase_read_retries_timeout_then_succeeds():
    session = SequencedSession([
        requests.ReadTimeout("temporary timeout"),
        StatusResponse(200, payload=[]),
    ])
    storage = SupabaseStorage(
        SupabaseConfig(
            url="https://example.supabase.co",
            key="secret",
            max_retries=2,
            retry_backoff_seconds=0,
        ),
        session=session,
    )

    assert storage.load_latest_snapshot() is None
    assert len(session.calls) == 2


def test_supabase_upsert_retries_transient_status_without_duplicate_identity():
    session = SequencedSession([
        StatusResponse(503, text="temporary upstream reset"),
        StatusResponse(201),
        StatusResponse(201),
        StatusResponse(201),
        StatusResponse(201),
        StatusResponse(201),
    ])
    storage = SupabaseStorage(
        SupabaseConfig(
            url="https://example.supabase.co",
            key="secret",
            max_retries=2,
            retry_backoff_seconds=0,
        ),
        session=session,
    )

    run_id = storage.save_snapshot(sample_snapshot())

    assert len(run_id) == 32
    assert len(session.calls) == 6
    assert session.calls[0][1]["params"] == {"on_conflict": "run_id"}
    assert session.calls[1][1]["params"] == {"on_conflict": "run_id"}


def test_supabase_request_exhaustion_remains_fail_closed():
    session = SequencedSession([
        requests.ReadTimeout("timeout one"),
        requests.ReadTimeout("timeout two"),
        requests.ReadTimeout("timeout three"),
    ])
    storage = SupabaseStorage(
        SupabaseConfig(
            url="https://example.supabase.co",
            key="secret",
            max_retries=2,
            retry_backoff_seconds=0,
        ),
        session=session,
    )

    with pytest.raises(SupabaseStorageError, match="failed after 3 attempts"):
        storage.load_latest_snapshot()

    assert len(session.calls) == 3


def test_seconds_until_next_hour():
    now = datetime(2026, 7, 26, 18, 45, 30, tzinfo=timezone.utc)
    assert seconds_until_next_hour(now) == 870


def test_twenty_minute_scanner_alignment():
    now = datetime(2026, 7, 26, 18, 2, 0, tzinfo=timezone.utc)
    assert next_scan_at(now, 20) == datetime(
        2026, 7, 26, 18, 20, 0, tzinfo=timezone.utc
    )
    assert seconds_until_next_interval(now, 20) == 1080


def test_exact_boundary_advances_instead_of_double_running():
    now = datetime(2026, 7, 26, 18, 20, 0, tzinfo=timezone.utc)
    assert next_scan_at(now, 20) == datetime(
        2026, 7, 26, 18, 40, 0, tzinfo=timezone.utc
    )
    assert seconds_until_next_interval(now, 20) == 1200


def test_invalid_interval_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        next_scan_at(
            datetime(2026, 7, 26, 18, 2, 0, tzinfo=timezone.utc),
            17,
        )


def test_render_cron_auto_enables_burst_but_web_service_does_not():
    assert render_cron_burst_enabled({
        "RENDER_SERVICE_NAME": "alpha-hunter-hourly",
    }) is True
    assert render_cron_burst_enabled({
        "RENDER_SERVICE_NAME": "alpha-hunter-j5i3",
        "PORT": "10000",
    }) is False


def test_render_burst_override_is_explicit():
    assert render_cron_burst_enabled({
        "ALPHA_HUNTER_RENDER_BURST_MODE": "1",
    }) is True
    assert render_cron_burst_enabled({
        "RENDER_SERVICE_NAME": "alpha-hunter-hourly",
        "ALPHA_HUNTER_RENDER_BURST_MODE": "0",
    }) is False


def test_late_render_cron_start_waits_for_next_boundary():
    safe = datetime(2026, 7, 26, 18, 4, 0, tzinfo=timezone.utc)
    late = datetime(2026, 7, 26, 18, 6, 0, tzinfo=timezone.utc)
    near_boundary = datetime(2026, 7, 26, 18, 19, 0, tzinfo=timezone.utc)

    assert should_run_initial_burst_scan(safe, 20) is True
    assert should_run_initial_burst_scan(late, 20) is False
    assert should_run_initial_burst_scan(near_boundary, 20) is False


def test_render_burst_source_skips_missed_boundaries_instead_of_backfill():
    source = Path("hourly.py").read_text(encoding="utf-8")
    assert "if current >= scheduled_at:" in source
    assert "no late backfill" in source
    assert "skipped late immediate scan" in source


def test_remaining_render_burst_boundaries_are_aligned():
    now = datetime(2026, 7, 26, 18, 4, 0, tzinfo=timezone.utc)
    assert remaining_burst_boundaries(now, 20) == [
        datetime(2026, 7, 26, 18, 20, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 26, 18, 40, 0, tzinfo=timezone.utc),
    ]

    late = datetime(2026, 7, 26, 18, 25, 0, tzinfo=timezone.utc)
    assert remaining_burst_boundaries(late, 20) == [
        datetime(2026, 7, 26, 18, 40, 0, tzinfo=timezone.utc),
    ]


def test_render_cron_launcher_stamps_canonical_source_lane():
    source = Path("hourly.py").read_text(encoding="utf-8")
    assert 'run_source_override="RENDER_CRON"' in source
    assert 'run_env["ALPHA_HUNTER_RUN_SOURCE"] = run_source_override' in source
    assert 'run_env["ALPHA_HUNTER_RUNTIME_ROLE"] = run_source_override' in source


def test_hourly_lock_prevents_overlap(tmp_path):
    from hourly import acquire_lock, release_lock
    lock = tmp_path / ".lock"
    assert acquire_lock(lock) is True
    assert acquire_lock(lock) is False
    release_lock(lock)
    assert acquire_lock(lock) is True
    release_lock(lock)


def test_env_file_loader(tmp_path, monkeypatch):
    from alpha_hunter.env import load_env_file
    env_file = tmp_path / ".env"
    env_file.write_text('SUPABASE_URL="https://demo.supabase.co"\n# comment\nSUPABASE_SERVICE_ROLE_KEY=test-key\n')
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert load_env_file(env_file) is True
    import os
    assert os.environ["SUPABASE_URL"] == "https://demo.supabase.co"
    assert os.environ["SUPABASE_SERVICE_ROLE_KEY"] == "test-key"


def test_canonical_signal_and_feature_rows_share_same_signal_id():
    import json

    session = FakeSession()
    storage = SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="secret"),
        session=session,
    )
    run_id = storage.save_snapshot(sample_snapshot())

    signal_rows = json.loads(session.calls[2][1]["data"])
    feature_rows = json.loads(session.calls[3][1]["data"])

    assert signal_rows[0]["run_id"] == run_id
    assert feature_rows[0]["run_id"] == run_id
    assert signal_rows[0]["signal_id"] == feature_rows[0]["signal_id"]
    assert signal_rows[0]["symbol"] == "SUIUSDT"
    assert feature_rows[0]["symbol"] == "SUIUSDT"
    assert signal_rows[0]["trade_permission"] is False


def test_compact_parent_snapshot_hydrates_from_symbol_rows():
    parent = StatusResponse(
        200,
        payload=[{
            "run_id": "run-1",
            "collected_at_utc": "2026-09-25T12:00:00+00:00",
            "payload": {
                "version": "0.7.1",
                "product_type": "usdt-futures",
                "_storage_contract": "snapshot-parent-v0.2",
            },
        }],
    )
    children = StatusResponse(
        200,
        payload=[
            {
                "symbol": "BTCUSDT",
                "payload": {"symbol": "BTCUSDT", "last_price": 100.0},
            },
            {
                "symbol": "ETHUSDT",
                "payload": {"symbol": "ETHUSDT", "last_price": 50.0},
            },
        ],
    )
    session = SequencedSession([parent, children])
    storage = SupabaseStorage(
        SupabaseConfig(
            url="https://example.supabase.co",
            key="secret",
            retry_backoff_seconds=0,
        ),
        session=session,
    )

    snapshot = storage.load_latest_snapshot()

    assert snapshot is not None
    assert snapshot["run_id"] == "run-1"
    assert [row["symbol"] for row in snapshot["symbols"]] == [
        "BTCUSDT",
        "ETHUSDT",
    ]
    assert session.calls[1][1]["params"]["run_id"] == "eq.run-1"


def test_signal_feature_and_parent_payloads_are_compact():
    import json

    snapshot = sample_snapshot()
    symbol = snapshot["symbols"][0]
    symbol.update({
        "collected_at_utc": snapshot["collected_at_utc"],
        "change_24h_pct": 2.5,
        "market_phase": "IGNITION",
        "opportunity_timing": "EARLY",
        "execution_setup": {
            "direction": "LONG",
            "rr": 6.0,
            "entry": 0.75,
            "stop": 0.70,
            "target": 1.05,
        },
        "behaviour": {"score": 81.0, "spread_pct": 0.03},
        "timeframes": {
            "1H": {
                "indicators": {"rsi": 55},
                "latest_candle": {"close": 0.75},
            },
        },
        "multi_strategy_engine": {
            "strategies": [
                {"strategy_id": "S1", "evidence": {"large": "x" * 5000}},
            ],
        },
        "microstructure": {"depth": {"large": "y" * 5000}},
        "catalyst": {"notices": [{"large": "z" * 5000}]},
    })

    session = FakeSession()
    storage = SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="secret"),
        session=session,
    )
    storage.save_snapshot(snapshot)

    signal_rows = json.loads(session.calls[2][1]["data"])
    feature_rows = json.loads(session.calls[3][1]["data"])
    signal_payload = signal_rows[0]["payload"]
    feature_source = feature_rows[0]["source_payload"]

    for compact in (signal_payload, feature_source):
        assert compact["_storage_contract"] == "signal-source-v0.2"
        assert compact["symbol"] == "SUIUSDT"
        assert compact["change_24h_pct"] == 2.5
        assert compact["market_phase"] == "IGNITION"
        assert compact["opportunity_timing"] == "EARLY"
        assert compact["execution_setup"]["rr"] == 6.0
        assert compact["behaviour"]["score"] == 81.0
        assert "timeframes" not in compact
        assert "multi_strategy_engine" not in compact
        assert "microstructure" not in compact
        assert "catalyst" not in compact

    child_rows = json.loads(session.calls[1][1]["data"])
    assert "timeframes" in child_rows[0]["payload"]
    assert "multi_strategy_engine" in child_rows[0]["payload"]

    parent_rows = json.loads(session.calls[0][1]["data"])
    parent_payload = parent_rows[0]["payload"]
    assert parent_payload["_storage_contract"] == "snapshot-parent-v0.2"
    assert parent_payload["symbols"][0]["symbol"] == "SUIUSDT"
    assert parent_payload["symbols"][0]["market_phase"] == "IGNITION"
    assert "timeframes" not in parent_payload["symbols"][0]
    assert "multi_strategy_engine" not in parent_payload["symbols"][0]

    readiness_rows = json.loads(session.calls[4][1]["data"])
    assert readiness_rows[0]["symbol"] == "SUIUSDT"
    assert readiness_rows[0]["reward_risk"] == 6.0
    assert readiness_rows[0]["trade_permission"] is False
