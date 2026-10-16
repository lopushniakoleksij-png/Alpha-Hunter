"""Regression for the 2026-10-16 16:03:50 UTC Gunicorn worker timeout.

Dashboard reads must return a controlled 503 before Gunicorn's default
30-second timeout when Supabase blocks. Cron and operator writes are untouched.
"""
import requests
import pytest

import app as dashboard


@pytest.mark.parametrize("path", ["/", "/api/latest"])
def test_slow_supabase_returns_controlled_503_before_worker_timeout(monkeypatch, path):
    clock = [1000.0]
    requests_seen = []

    def fake_get(*args, **kwargs):
        timeout = kwargs["timeout"]
        requests_seen.append(timeout)
        clock[0] += timeout
        raise requests.ReadTimeout("simulated slow Supabase")

    def fake_sleep(seconds):
        clock[0] += seconds

    monkeypatch.setattr(dashboard, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(dashboard, "SUPABASE_KEY", "nonproduction-test-key")
    monkeypatch.setattr(dashboard.requests, "get", fake_get)
    monkeypatch.setattr(dashboard.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(dashboard.time, "sleep", fake_sleep)

    response = dashboard.app.test_client().get(path)
    assert response.status_code == 503
    assert requests_seen
    assert clock[0] - 1000 <= dashboard.DASHBOARD_READ_BUDGET_SECONDS + 0.01
    assert dashboard.DASHBOARD_READ_BUDGET_SECONDS < 30
    assert dashboard._DASHBOARD_READ_DEADLINE.get() is None
    if path == "/":
        assert "LIVE DATA TEMPORARILY UNAVAILABLE" in response.get_data(as_text=True)
    else:
        assert response.get_json()["error"] == "live_data_unavailable"


def test_missing_paper_status_never_renders_trading_dashboard(monkeypatch):
    monkeypatch.setattr(dashboard, "latest_snapshot", lambda: {"symbols": []})
    monkeypatch.setattr(dashboard, "latest_test_engine_status", lambda: {})
    monkeypatch.setattr(dashboard, "latest_paper_lifecycle_status", lambda: {})

    result = dashboard.app.test_client().get("/")
    assert result.status_code == 503
    assert "Trading actions are intentionally hidden" in result.get_data(as_text=True)
    assert dashboard._DASHBOARD_READ_DEADLINE.get() is None
