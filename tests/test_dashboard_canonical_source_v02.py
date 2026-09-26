import app as dashboard


def test_dashboard_default_source_is_canonical_render_cron():
    assert dashboard.CANONICAL_RUN_SOURCE == "RENDER_CRON"


def test_latest_snapshot_filters_to_canonical_cron(monkeypatch):
    calls = []

    def fake_rows(table, params):
        calls.append((table, params))
        return [{
            "run_id": "run-cron",
            "collected_at_utc": "2026-09-26T15:04:00+00:00",
            "payload": {
                "validation_identity": {
                    "run_source": "RENDER_CRON",
                },
                "symbols": [],
            },
        }]

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    monkeypatch.setattr(dashboard, "CANONICAL_RUN_SOURCE", "RENDER_CRON")

    payload = dashboard.latest_snapshot()

    assert calls[0][0] == dashboard.SNAPSHOT_TABLE
    assert calls[0][1]["payload->validation_identity->>run_source"] == (
        "eq.RENDER_CRON"
    )
    assert payload["validation_identity"]["run_source"] == "RENDER_CRON"


def test_latest_snapshot_rejects_source_mismatch(monkeypatch):
    def fake_rows(table, params):
        return [{
            "run_id": "run-web",
            "payload": {
                "validation_identity": {
                    "run_source": "RENDER_WEB",
                },
            },
        }]

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    monkeypatch.setattr(dashboard, "CANONICAL_RUN_SOURCE", "RENDER_CRON")

    try:
        dashboard.latest_snapshot()
    except RuntimeError as exc:
        assert "source mismatch" in str(exc).lower()
    else:
        raise AssertionError("source mismatch must fail closed")


def test_latest_snapshot_rejects_legacy_payload_without_identity(monkeypatch):
    def fake_rows(table, params):
        return [{
            "run_id": "legacy",
            "payload": {"version": "0.7.1"},
        }]

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    monkeypatch.setattr(dashboard, "CANONICAL_RUN_SOURCE", "RENDER_CRON")

    try:
        dashboard.latest_snapshot()
    except RuntimeError as exc:
        assert "validation identity" in str(exc).lower()
    else:
        raise AssertionError("legacy payload must fail closed")


def test_compact_canonical_parent_hydrates_full_symbol_rows(monkeypatch):
    calls = []

    def fake_rows(table, params):
        calls.append((table, params))
        if table == dashboard.SNAPSHOT_TABLE:
            return [{
                "run_id": "run-compact",
                "collected_at_utc": "2026-09-26T15:20:00+00:00",
                "payload": {
                    "_storage_contract": "snapshot-parent-v0.2",
                    "validation_identity": {
                        "run_source": "RENDER_CRON",
                    },
                    "symbols": [{"symbol": "BTCUSDT"}],
                },
            }]
        assert table == "alpha_hunter_symbol_snapshots"
        return [
            {
                "symbol": "BTCUSDT",
                "payload": {
                    "symbol": "BTCUSDT",
                    "multi_strategy_engine": {"strategies": []},
                    "timeframes": {"1H": {}},
                },
            },
        ]

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    monkeypatch.setattr(dashboard, "CANONICAL_RUN_SOURCE", "RENDER_CRON")

    payload = dashboard.latest_snapshot()

    assert payload["run_id"] == "run-compact"
    assert payload["symbols"][0]["symbol"] == "BTCUSDT"
    assert "multi_strategy_engine" in payload["symbols"][0]
    assert calls[1][1]["run_id"] == "eq.run-compact"
