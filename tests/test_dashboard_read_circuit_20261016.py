"""Bounded public recovery during a Supabase outage; no trading authority changes."""
import requests
import app as dashboard


def test_repeated_browser_refreshes_fail_fast_without_repeating_db_load(monkeypatch):
    current = [100.0]
    call_count = [0]
    monkeypatch.setenv("RENDER_SERVICE_ID", "isolated-render-test")
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    monkeypatch.setattr(dashboard.time, "monotonic", lambda: current[0])

    def fail():
        call_count[0] += 1
        raise requests.ReadTimeout("synthetic database outage")

    monkeypatch.setattr(dashboard, "latest_snapshot", fail)
    client = dashboard.app.test_client()

    original = client.get("/")
    assert original.status_code == 503
    assert call_count == [1]
    assert dashboard._DASHBOARD_READ_DEADLINE.get() is None
    assert dashboard.dashboard_read_circuit_open()

    for _ in range(4):
        assert client.get("/").status_code == 503
        api = client.get("/api/latest")
        assert api.status_code == 503
        assert api.get_json()["error"] == "live_data_unavailable"
    assert call_count == [1]
    assert original.headers["Cache-Control"] == "no-store"
    assert original.headers["Retry-After"] == "10"
    assert "Trading actions are intentionally hidden" in original.get_data(as_text=True)

    current[0] += dashboard.DASHBOARD_READ_FAILURE_COOLDOWN_SECONDS + 1
    assert not dashboard.dashboard_read_circuit_open()
    assert client.get("/").status_code == 503
    assert call_count == [2]


def test_build_endpoint_stays_available_during_dashboard_outage(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "isolated-render-test")
    monkeypatch.setattr(
        dashboard,
        "_DASHBOARD_READ_UNAVAILABLE_UNTIL",
        dashboard.time.monotonic() + 120.0,
    )
    client = dashboard.app.test_client()
    build = client.get("/api/build")
    assert build.status_code == 200
    assert build.is_json
    assert client.get("/").status_code == 503


def test_circuit_never_masks_isolated_test_mode(monkeypatch):
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.setattr(
        dashboard,
        "_DASHBOARD_READ_UNAVAILABLE_UNTIL",
        dashboard.time.monotonic() + 1000.0,
    )
    assert not dashboard.dashboard_read_circuit_open()
