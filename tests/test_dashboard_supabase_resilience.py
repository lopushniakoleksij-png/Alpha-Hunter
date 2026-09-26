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
