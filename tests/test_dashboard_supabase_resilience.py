from pathlib import Path
import requests

import app as dashboard_app


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


def test_supabase_get_rows_retries_transient_then_succeeds(monkeypatch):
    calls = []
    responses = [
        FakeResponse(503, {"message": "recovering"}),
        FakeResponse(502, {"message": "retry"}),
        FakeResponse(200, [{"payload": {"symbols": []}}]),
    ]

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return responses.pop(0)

    sleeps = []
    monkeypatch.setattr(dashboard_app.requests, "get", fake_get)
    monkeypatch.setattr(dashboard_app.time, "sleep", sleeps.append)
    monkeypatch.setattr(dashboard_app, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(dashboard_app, "SUPABASE_KEY", "service-role-test")

    rows = dashboard_app.supabase_get_rows(
        "alpha_hunter_snapshots",
        {"select": "payload", "limit": "1"},
    )

    assert rows == [{"payload": {"symbols": []}}]
    assert len(calls) == 3
    assert sleeps == [0.75, 1.5]


def test_dashboard_fails_closed_with_recovery_page(monkeypatch):
    def unavailable():
        raise requests.ConnectionError("database unavailable")

    monkeypatch.setattr(dashboard_app, "latest_snapshot", unavailable)

    client = dashboard_app.app.test_client()
    response = client.get("/")

    assert response.status_code == 503
    body = response.get_data(as_text=True)
    assert "LIVE DATA TEMPORARILY UNAVAILABLE" in body
    assert "Trading actions are intentionally hidden" in body
    assert 'http-equiv="refresh" content="10"' in body
    assert "database unavailable" not in body


def test_api_latest_returns_generic_retryable_503(monkeypatch):
    def unavailable():
        raise requests.Timeout("timed out")

    monkeypatch.setattr(dashboard_app, "latest_snapshot", unavailable)

    client = dashboard_app.app.test_client()
    response = client.get("/api/latest")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["error"] == "live_data_unavailable"
    assert payload["retry_after_seconds"] == 10
    assert "build" in payload


def test_manual_web_scan_isolated_from_canonical_cron_source():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'scan_env["ALPHA_HUNTER_RUN_SOURCE"] = "RENDER_WEB"' in source
    assert 'scan_env["ALPHA_HUNTER_RUNTIME_ROLE"] = "RENDER_WEB"' in source
    assert "env=scan_env" in source


def test_slow_optional_successor_status_falls_back_without_retry(monkeypatch):
    """A heavy v09 view must not consume the whole 18s dashboard budget."""
    clock = [1000.0]
    calls = []

    def fake_get(url, **kwargs):
        table = url.rsplit("/", 1)[-1]
        calls.append((table, kwargs["timeout"]))
        if table == "alpha_hunter_paper_profitability_status_v09":
            clock[0] += kwargs["timeout"]
            raise requests.ReadTimeout("synthetic v09 statement timeout")
        if table == "alpha_hunter_test_engine_latest_v01":
            return FakeResponse(200, [{
                "spec_id": "R8", "operational_status": "BLOCKED",
                "profitability_status": "INVALIDATED_BY_R8_EXECUTION_INTEGRITY_DEFECT",
                "trade_permission": False, "production_promotion_permitted": False,
                "blockers": [],
            }])
        if table == "alpha_hunter_paper_repair_status_v01":
            return FakeResponse(200, [{
                "unresolved_entry_orders": 0, "open_positions_over_24h": 0,
            }])
        raise AssertionError(f"unexpected query: {table}")

    monkeypatch.setattr(dashboard_app.requests, "get", fake_get)
    monkeypatch.setattr(dashboard_app.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(dashboard_app, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(dashboard_app, "SUPABASE_KEY", "nonproduction-test-key")

    token = dashboard_app._DASHBOARD_READ_DEADLINE.set(clock[0] + 18.0)
    try:
        status = dashboard_app.latest_test_engine_status()
    finally:
        dashboard_app._DASHBOARD_READ_DEADLINE.reset(token)

    assert calls == [
        ("alpha_hunter_paper_profitability_status_v09", 2.5),
        ("alpha_hunter_test_engine_latest_v01", 12),
        ("alpha_hunter_paper_repair_status_v01", 12),
    ]
    assert clock[0] - 1000.0 == 2.5
    assert status["spec_id"] == "R8"
    assert status["profitability_status"] == "INVALIDATED_BY_R8_EXECUTION_INTEGRITY_DEFECT"
    assert status["trade_permission"] is False
    assert status["production_promotion_permitted"] is False
    assert status["operational_status"] == "REVIEW_REQUIRED"
    assert "SUCCESSOR_STATUS_UNAVAILABLE" in status["blockers"]


def test_fast_optional_successor_status_keeps_priority(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        table = url.rsplit("/", 1)[-1]
        calls.append((table, kwargs["timeout"]))
        if table == "alpha_hunter_paper_profitability_status_v09":
            return FakeResponse(200, [{
                "spec_id": "R9", "operational_status": "BLOCKED",
                "trade_permission": False, "blockers": [],
            }])
        if table == "alpha_hunter_paper_repair_status_v01":
            return FakeResponse(200, [{
                "unresolved_entry_orders": 0, "open_positions_over_24h": 0,
            }])
        raise AssertionError(f"unexpected fallback: {table}")

    monkeypatch.setattr(dashboard_app.requests, "get", fake_get)
    monkeypatch.setattr(dashboard_app, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(dashboard_app, "SUPABASE_KEY", "nonproduction-test-key")
    token = dashboard_app._DASHBOARD_READ_DEADLINE.set(
        dashboard_app.time.monotonic() + 18.0
    )
    try:
        status = dashboard_app.latest_test_engine_status()
    finally:
        dashboard_app._DASHBOARD_READ_DEADLINE.reset(token)
    assert status["spec_id"] == "R9"
    assert status["trade_permission"] is False
    assert [name for name, _ in calls] == [
        "alpha_hunter_paper_profitability_status_v09",
        "alpha_hunter_paper_repair_status_v01",
    ]
    assert calls[0][1] <= 2.5


def test_canonical_parent_before_children_is_publishing_not_outage(monkeypatch):
    from datetime import datetime, timezone
    import pytest

    parent = {
        "run_id": "publishing-run",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol_count": 2,
    }
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": "publishing-run",
        "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
    }
    monkeypatch.setattr(
        dashboard_app, "supabase_get_rows",
        lambda table, params: [
            {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}}
        ],
    )

    with pytest.raises(dashboard_app.CanonicalSnapshotPublishing):
        dashboard_app._hydrate_dashboard_snapshot(parent, payload)

    client = dashboard_app.app.test_client()
    monkeypatch.setattr(
        dashboard_app, "latest_snapshot",
        lambda: (_ for _ in ()).throw(
            dashboard_app.CanonicalSnapshotPublishing("publishing")
        ),
    )
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    monkeypatch.setenv("RENDER_SERVICE_ID", "web-only-test")
    page = client.get("/")
    assert page.status_code == 202
    assert "LATEST SCAN IS PUBLISHING" in page.get_data(as_text=True)
    assert "Bitget public market prices" in page.get_data(as_text=True)
    assert "Trading actions are intentionally hidden" in page.get_data(as_text=True)
    assert dashboard_app._DASHBOARD_READ_UNAVAILABLE_UNTIL == 0.0

    api = client.get("/api/latest")
    assert api.status_code == 503
    assert api.get_json()["error"] == "canonical_scan_publishing"
    assert dashboard_app._DASHBOARD_READ_UNAVAILABLE_UNTIL == 0.0


def test_persistently_missing_canonical_children_remains_hard_error(monkeypatch):
    from datetime import datetime, timedelta, timezone
    import pytest

    parent = {
        "run_id": "old-incomplete",
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=8)).isoformat(),
        "symbol_count": 2,
    }
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": "old-incomplete",
        "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
    }
    monkeypatch.setattr(dashboard_app, "supabase_get_rows", lambda *_: [])
    with pytest.raises(RuntimeError, match="Incomplete compact canonical snapshot"):
        dashboard_app._hydrate_dashboard_snapshot(parent, payload)


def test_published_complete_parent_uses_full_verified_children(monkeypatch):
    from datetime import datetime, timezone

    parent = {
        "run_id": "complete-run",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol_count": 2,
    }
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": "complete-run",
        "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
    }
    children = [
        {"symbol": "ETHUSDT", "payload": {"symbol": "ETHUSDT", "score": 2}},
        {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT", "score": 1}},
    ]
    monkeypatch.setattr(dashboard_app, "supabase_get_rows", lambda *_: children)
    hydrated = dashboard_app._hydrate_dashboard_snapshot(parent, payload)
    assert [r["symbol"] for r in hydrated["symbols"]] == ["BTCUSDT", "ETHUSDT"]
    assert hydrated["symbols"][0]["score"] == 1
