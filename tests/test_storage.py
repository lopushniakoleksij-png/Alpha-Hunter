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
            "symbol_count": 2,
            "payload": {
                "version": "0.7.1",
                "product_type": "usdt-futures",
                "_storage_contract": "snapshot-parent-v0.2",
                "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
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


def _stored_compact_parent(run_id, symbol_names, *, identity=None):
    return {
        "run_id": run_id,
        "collected_at_utc": "2026-11-06T18:00:00+00:00",
        "symbol_count": len(symbol_names),
        "payload": {
            "_storage_contract": "snapshot-parent-v0.2",
            "symbols": [{"symbol": name} for name in symbol_names],
            "validation_identity": identity or {"test_contract": "synthetic-contract"},
            "multi_strategy_summary": {},
            "microstructure_summary": {},
            "catalyst_summary": {},
        },
    }


def _stored_child(symbol):
    return {"symbol": symbol, "payload": {"symbol": symbol, "last_price": 1.25}}


def test_filtered_predecessor_skips_parent_without_children():
    """A timed-out child write must not become the next scan's prior run."""
    session = SequencedSession([
        StatusResponse(200, payload=[
            _stored_compact_parent("newer-partial", ["ALPHAUSDT", "BETAUSDT"]),
            _stored_compact_parent("older-complete", ["GAMMAUSDT", "DELTAUSDT"]),
        ]),
        StatusResponse(200, payload=[]),  # Newer parent outlived failed write.
        StatusResponse(200, payload=[
            _stored_child("DELTAUSDT"), _stored_child("GAMMAUSDT"),
        ]),
    ])
    storage = SupabaseStorage(SupabaseConfig(
        url="https://example.supabase.co", key="synthetic",
        retry_backoff_seconds=0,
    ), session=session)

    prior = storage.load_latest_snapshot(
        expected_identity={"test_contract": "synthetic-contract"},
        require_strategy_context=True,
    )
    assert prior is not None
    assert prior["run_id"] == "older-complete"
    assert {row["symbol"] for row in prior["symbols"]} == {
        "GAMMAUSDT", "DELTAUSDT",
    }
    assert len(session.calls) == 3
    assert session.calls[0][1]["params"]["limit"] == "25"
    assert session.calls[1][1]["params"]["run_id"] == "eq.newer-partial"
    assert session.calls[2][1]["params"]["run_id"] == "eq.older-complete"


@pytest.mark.parametrize("children", [
    [],
    [_stored_child("ALPHAUSDT")],
    [_stored_child("ALPHAUSDT"), _stored_child("ALPHAUSDT")],
    [_stored_child("ALPHAUSDT"), _stored_child("WRONGUSDT")],
    [_stored_child("ALPHAUSDT"), {"symbol": "BETAUSDT", "payload": None}],
])
def test_compact_parent_child_integrity_rejects_incomplete_shapes(children):
    from alpha_hunter.storage import IncompleteSnapshotError
    session = SequencedSession([
        StatusResponse(200, payload=[
            _stored_compact_parent("partial", ["ALPHAUSDT", "BETAUSDT"]),
        ]),
        StatusResponse(200, payload=children),
    ])
    storage = SupabaseStorage(SupabaseConfig(
        url="https://example.supabase.co", key="synthetic",
        retry_backoff_seconds=0,
    ), session=session)
    # Unfiltered single-latest consumers must fail visibly, not substitute an
    # old scan and accidentally present stale findings as current.
    with pytest.raises(IncompleteSnapshotError):
        storage.load_latest_snapshot()


def test_no_identity_matched_complete_predecessor_is_none():
    session = SequencedSession([
        StatusResponse(200, payload=[
            _stored_compact_parent("partial", ["ALPHAUSDT"]),
        ]),
        StatusResponse(200, payload=[]),
    ])
    storage = SupabaseStorage(SupabaseConfig(
        url="https://example.supabase.co", key="synthetic",
        retry_backoff_seconds=0,
    ), session=session)
    assert storage.load_latest_snapshot(
        expected_identity={"test_contract": "synthetic-contract"},
        require_strategy_context=True,
    ) is None


def _complete_stage_rows(*symbols):
    signal_rows = [
        {"symbol": symbol, "signal_id": f"synthetic-id-{i}"}
        for i, symbol in enumerate(symbols)
    ]
    feature_rows = [dict(row) for row in signal_rows]
    readiness_rows = [{"symbol": symbol} for symbol in symbols]
    return signal_rows, feature_rows, readiness_rows


def test_predecessor_requires_all_five_stages_with_exact_identifiers():
    first = _stored_compact_parent("complete", ["ALPHAUSDT", "BETAUSDT"])
    sig, feat, ready = _complete_stage_rows("ALPHAUSDT", "BETAUSDT")
    session = SequencedSession([
        StatusResponse(200, payload=[first]),
        StatusResponse(200, payload=[_stored_child("ALPHAUSDT"),
                                      _stored_child("BETAUSDT")]),
        StatusResponse(200, payload=sig),
        StatusResponse(200, payload=feat),
        StatusResponse(200, payload=ready),
    ])
    storage = SupabaseStorage(SupabaseConfig(
        url="https://example.supabase.co", key="synthetic",
        retry_backoff_seconds=0,
    ), session=session)
    prior = storage.load_latest_snapshot(
        expected_identity={"test_contract": "synthetic-contract"},
        require_strategy_context=True,
        require_complete_publication=True,
    )
    assert prior is not None
    assert prior["run_id"] == "complete"
    assert len(session.calls) == 5
    assert session.calls[2][0].endswith("/alpha_hunter_signals")
    assert session.calls[3][0].endswith("/alpha_hunter_signal_features")
    assert session.calls[4][0].endswith(
        "/alpha_hunter_readiness_observations_v01"
    )
    assert session.calls[2][1]["params"] == {
        "select": "symbol,signal_id", "run_id": "eq.complete", "limit": "2001",
    }


def test_predecessor_skips_complete_symbols_with_missing_later_stages():
    # A separate-HTTP write can leave complete symbols but zero signals.
    new = _stored_compact_parent("partial-new", ["ALPHAUSDT", "BETAUSDT"])
    old = _stored_compact_parent("complete-old", ["GAMMAUSDT", "DELTAUSDT"])
    sig, feat, ready = _complete_stage_rows("GAMMAUSDT", "DELTAUSDT")
    session = SequencedSession([
        StatusResponse(200, payload=[new, old]),
        StatusResponse(200, payload=[_stored_child("ALPHAUSDT"),
                                      _stored_child("BETAUSDT")]),
        StatusResponse(200, payload=[]),
        StatusResponse(200, payload=[]),
        StatusResponse(200, payload=[]),
        StatusResponse(200, payload=[_stored_child("GAMMAUSDT"),
                                      _stored_child("DELTAUSDT")]),
        StatusResponse(200, payload=sig),
        StatusResponse(200, payload=feat),
        StatusResponse(200, payload=ready),
    ])
    storage = SupabaseStorage(SupabaseConfig(
        url="https://example.supabase.co", key="synthetic",
        retry_backoff_seconds=0,
    ), session=session)
    prior = storage.load_latest_snapshot(
        expected_identity={"test_contract": "synthetic-contract"},
        require_strategy_context=True,
        require_complete_publication=True,
    )
    assert prior is not None
    assert prior["run_id"] == "complete-old"
    assert len(session.calls) == 9


@pytest.mark.parametrize("bad_group", ["signal", "feature", "readiness"])
def test_predecessor_rejects_equal_counts_with_mismatched_identity(bad_group):
    parent = _stored_compact_parent("identity-fail", ["ALPHAUSDT", "BETAUSDT"])
    sig, feat, ready = _complete_stage_rows("ALPHAUSDT", "BETAUSDT")
    if bad_group == "signal":
        sig[1]["signal_id"] = sig[0]["signal_id"]
    elif bad_group == "feature":
        feat[1]["signal_id"] = "synthetic-wrong-id"
    else:
        ready[1]["symbol"] = "WRONGUSDT"
    session = SequencedSession([
        StatusResponse(200, payload=[parent]),
        StatusResponse(200, payload=[_stored_child("ALPHAUSDT"),
                                      _stored_child("BETAUSDT")]),
        StatusResponse(200, payload=sig),
        StatusResponse(200, payload=feat),
        StatusResponse(200, payload=ready),
    ])
    storage = SupabaseStorage(SupabaseConfig(
        url="https://example.supabase.co", key="synthetic",
        retry_backoff_seconds=0,
    ), session=session)
    assert storage.load_latest_snapshot(
        expected_identity={"test_contract": "synthetic-contract"},
        require_strategy_context=True,
        require_complete_publication=True,
    ) is None


def test_predecessor_read_errors_abort_instead_of_skipping():
    session = SequencedSession([
        StatusResponse(200, payload=[
            _stored_compact_parent("read-fail", ["ALPHAUSDT"])
        ]),
        StatusResponse(200, payload=[_stored_child("ALPHAUSDT")]),
        StatusResponse(503, text="synthetic read service unavailable"),
    ])
    storage = SupabaseStorage(SupabaseConfig(
        url="https://example.supabase.co", key="synthetic",
        max_retries=0, retry_backoff_seconds=0,
    ), session=session)
    with pytest.raises(SupabaseStorageError, match="evidence read failed"):
        storage.load_latest_snapshot(
            expected_identity={"test_contract": "synthetic-contract"},
            require_strategy_context=True,
            require_complete_publication=True,
        )


def test_previous_snapshot_guard_keeps_legacy_full_payload():
    # Older storage contracts already contain the complete symbol objects in
    # the parent. The guard must not reject those solely because there are no
    # compact child reads.
    legacy = {
        "run_id": "legacy",
        "collected_at_utc": "2026-07-20T18:00:00+00:00",
        "payload": {"symbols": [{"symbol": "BTCUSDT"}]},
    }
    session = SequencedSession([StatusResponse(200, payload=[legacy])])
    storage = SupabaseStorage(SupabaseConfig(
        url="https://example.supabase.co", key="synthetic",
        retry_backoff_seconds=0,
    ), session=session)
    assert storage.load_latest_snapshot()["symbols"] == [{"symbol": "BTCUSDT"}]
    assert len(session.calls) == 1


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


def test_render_burst_prioritizes_scanner_before_auxiliary_jobs():
    source = Path("hourly.py").read_text(encoding="utf-8")
    burst = source.split("def run_render_cron_burst(", 1)[1]
    assert "run_auxiliary_jobs=False" in burst
    assert "run_auxiliary_jobs_with_deadline" in burst
    assert "DEFAULT_AUXILIARY_JOB_TIMEOUT_SECONDS = 300" in source
    assert "DEFAULT_BURST_EXIT_BUFFER_SECONDS = 90" in source


def test_auxiliary_deadline_cannot_grant_order_authority():
    source = Path("hourly.py").read_text(encoding="utf-8").lower()
    for forbidden in [
        "place_order(",
        "cancel_order(",
        "modify_order(",
        "set_leverage(",
    ]:
        assert forbidden not in source


class FakeBitgetTickerClient:
    def __init__(self):
        self.calls = []

    def tickers(self, product_type):
        self.calls.append(product_type)
        return [
            {
                "symbol": "ALICEUSDT",
                "bidPr": "0.2016",
                "askPr": "0.2017",
                "bidSz": "900",
                "askSz": "700",
                "fundingRate": "0.0001",
            },
            {
                "symbol": "SUIUSDT",
                "bidPr": "0.749",
                "askPr": "0.751",
                "bidSz": "1000",
                "askSz": "1000",
                "fundingRate": "0.0002",
            },
        ]


def test_open_order_quote_capture_fetches_only_missing_deep_scan_symbols():
    client = FakeBitgetTickerClient()
    storage = SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="secret"),
        session=FakeSession(),
        bitget_client=client,
    )
    value = sample_snapshot()
    value["symbols"][0]["bid_price"] = 0.749
    value["symbols"][0]["ask_price"] = 0.751

    quotes = storage._capture_missing_reconciliation_quotes(
        value,
        [{"symbol": "ALICEUSDT"}, {"symbol": "SUIUSDT"}],
    )

    assert client.calls == ["usdt-futures"]
    assert set(quotes) == {"ALICEUSDT"}
    assert quotes["ALICEUSDT"]["bid_price"] == "0.2016"
    assert quotes["ALICEUSDT"]["ask_price"] == "0.2017"
    assert quotes["ALICEUSDT"]["_reconciliation_quote_source"] == (
        "BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"
    )


def test_open_order_quote_capture_skips_bitget_when_snapshot_quote_exists():
    client = FakeBitgetTickerClient()
    storage = SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="secret"),
        session=FakeSession(),
        bitget_client=client,
    )
    value = sample_snapshot()
    value["symbols"][0]["bid_price"] = 0.749
    value["symbols"][0]["ask_price"] = 0.751

    quotes = storage._capture_missing_reconciliation_quotes(
        value,
        [{"symbol": "SUIUSDT"}],
    )

    assert quotes == {}
    assert client.calls == []
