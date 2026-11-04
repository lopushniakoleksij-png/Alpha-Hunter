"""Web-only canonical evidence integrity: mobile availability without signal promotion."""
from datetime import datetime, timedelta, timezone

import pytest
import requests
import app as web


def parent(*, complete=False):
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    return {
        "run_id": "test-web-only-20261104",
        "created_at": stamp,
        "collected_at_utc": stamp,
        "symbol_count": 2,
        "error_count": 0,
        "payload": {
            "run_id": "test-web-only-20261104",
            "_storage_contract": "snapshot-parent-v0.2",
            "validation_identity": {"run_source": "RENDER_CRON"},
            "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
        },
    }


def test_incomplete_canonical_browser_is_usable_with_no_trading_data(monkeypatch):
    p = parent()
    monkeypatch.setenv("RENDER_SERVICE_ID", "web-only-isolated-test")
    monkeypatch.setattr(web, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)

    def rows(table, _params):
        if table == web.SNAPSHOT_TABLE:
            return [p]
        if table == "alpha_hunter_symbol_snapshots":
            return []
        pytest.fail(f"unexpected table {table}")

    monkeypatch.setattr(web, "supabase_get_rows", rows)
    client = web.app.test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["Cache-Control"] == "no-store"
    assert page.headers["X-Alpha-Hunter-Evidence-State"] == "INCOMPLETE"
    assert "LATEST CANONICAL SCAN INCOMPLETE" in page.get_data(as_text=True)
    assert "No trade signals or execution recommendations" in page.get_data(as_text=True)
    assert "Bitget public market prices" in page.get_data(as_text=True)
    assert not web.dashboard_read_circuit_open()

    api = client.get("/api/latest")
    assert api.status_code == 503
    assert api.get_json()["error"] == "canonical_scan_incomplete"
    assert api.get_json()["signals_available"] is False
    assert api.get_json()["trade_permission"] is False
    assert api.headers["Cache-Control"] == "no-store"
    assert api.headers["X-Alpha-Hunter-Evidence-State"] == "INCOMPLETE"
    assert not web.dashboard_read_circuit_open()


def test_recovered_verified_scan_is_visible_without_75_second_delay(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "web-only-isolated-test")
    monkeypatch.setattr(web, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    latest = [False]
    def snapshot():
        if not latest[0]:
            raise web.CanonicalSnapshotIncomplete("synthetic incomplete parent")
        return {"run_id": "completed-source"}
    monkeypatch.setattr(web, "latest_snapshot", snapshot)
    monkeypatch.setattr(web, "latest_test_engine_status", lambda: {"spec_id": "R10", "trade_permission": False})
    monkeypatch.setattr(web, "latest_paper_lifecycle_status", lambda: {})
    monkeypatch.setattr(web, "dashboard_payload", lambda *_args: {
        "source_run_id": "completed-source", "trade_permission": False,
    })
    client = web.app.test_client()
    first = client.get("/api/latest")
    assert first.status_code == 503
    assert first.get_json()["error"] == "canonical_scan_incomplete"
    assert not web.dashboard_read_circuit_open()
    latest[0] = True
    second = client.get("/api/latest")
    assert second.status_code == 200
    assert second.get_json()["source_run_id"] == "completed-source"
    assert second.get_json()["trade_permission"] is False


def test_true_database_outage_still_opens_safety_circuit(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "web-only-isolated-test")
    monkeypatch.setattr(web, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    monkeypatch.setattr(web, "latest_snapshot", lambda: (_ for _ in ()).throw(requests.Timeout("synthetic outage")))
    result = web.app.test_client().get("/")
    assert result.status_code == 503
    assert web.dashboard_read_circuit_open()
    assert result.headers["Cache-Control"] == "no-store"


def test_parent_run_identity_mismatch_is_not_accepted(monkeypatch):
    p = parent()
    p["payload"]["run_id"] = "different-run"
    monkeypatch.setattr(web, "supabase_get_rows", lambda *_args: pytest.fail("must not fetch children"))
    with pytest.raises(web.CanonicalSnapshotIncomplete, match="identity mismatch"):
        web._hydrate_dashboard_snapshot(p, p["payload"])


def test_scanner_error_count_in_parent_blocks_signal_rendering(monkeypatch):
    p = parent()
    p["error_count"] = 1
    monkeypatch.setattr(web, "supabase_get_rows", lambda *_args: pytest.fail("must not fetch children"))
    with pytest.raises(web.CanonicalSnapshotIncomplete, match="scanner reported"):
        web._hydrate_dashboard_snapshot(p, p["payload"])
