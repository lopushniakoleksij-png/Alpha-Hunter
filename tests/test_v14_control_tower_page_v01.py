import requests

import app as dashboard_app


def sample_status():
    return {
        "watchdog_status": "WARNING",
        "spec_id": "SEALED-ARCH-V14-FP-20M-20260926",
        "critical_alerts": [],
        "warning_alerts": ["BITGET_ACCOUNT_IDENTITY_UNPINNED"],
        "expected_gates": ["MINIMUM_30_DAY_DURATION_NOT_MET"],
        "operational_status": "PASS",
        "test_days_elapsed": 0.1,
        "minimum_test_days": 30,
        "test_days_remaining": 29.9,
        "completed_paper_trades": 0,
        "minimum_completed_paper_trades": 100,
        "paper_trades_remaining": 100,
        "cadence_integrity_status": "PASS",
        "expected_schedule": "RENDER_CRON_ALIGNED_00_20_40",
        "identity_drift_scans": 0,
        "latest_live_scan_age_seconds": 120,
        "latest_live_scan_at_utc": "2026-09-26T19:23:21+00:00",
        "historical_fill_continuity_conflict": True,
        "account_identity_probe_status": "UNPINNED",
        "database_size_pretty": "1799 MB",
        "live_toast_review_tables": 4,
        "profitability_status": "RUNNING_MINIMUM_DURATION_NOT_MET",
        "verdict": "TEST_RUNNING",
        "earliest_duration_gate_at_utc": "2026-10-26T16:23:25+00:00",
        "cost_scientific_status": "DESCRIPTIVE_OBSERVED_COST_FLOOR_ONLY",
        "cost_next_gate": "FORWARD_DECISION_TO_FILL_BENCHMARK_AND_SLIPPAGE_VALIDATION",
        "post_start_scans": 10,
        "identity_mismatch_scan_count": 0,
        "too_frequent_scan_intervals": 0,
        "excessive_gap_intervals": 0,
        "historical_fill_rows_same_window": 16,
        "legacy_control_plane_status": "FAILED",
    }


def test_control_tower_page_is_phone_first_read_only(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "latest_control_tower_status",
        sample_status,
    )
    monkeypatch.setattr(
        dashboard_app,
        "latest_control_tower_events",
        lambda limit=12: [],
    )

    client = dashboard_app.app.test_client()
    response = client.get("/control-tower")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "V14 Control Tower" in body
    assert "Forward scientific test" in body
    assert "BITGET_ACCOUNT_IDENTITY_UNPINNED" in body
    assert "trade_permission=false" in body
    assert "order_path=NONE" in body
    assert 'name="viewport"' in body


def test_control_tower_api_preserves_no_order_authority(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "latest_control_tower_status",
        sample_status,
    )
    monkeypatch.setattr(
        dashboard_app,
        "latest_control_tower_events",
        lambda limit=12: [],
    )

    client = dashboard_app.app.test_client()
    response = client.get("/api/control-tower")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["paper_only"] is True
    assert payload["trade_permission"] is False
    assert payload["production_promotion_permitted"] is False
    assert payload["order_path"] == "NONE"


def test_control_tower_fails_closed_when_supabase_unavailable(monkeypatch):
    def unavailable():
        raise requests.ConnectionError("database unavailable")

    monkeypatch.setattr(
        dashboard_app,
        "latest_control_tower_status",
        unavailable,
    )

    client = dashboard_app.app.test_client()

    page = client.get("/control-tower")
    assert page.status_code == 503
    assert "LIVE DATA TEMPORARILY UNAVAILABLE" in page.get_data(as_text=True)
    assert "database unavailable" not in page.get_data(as_text=True)

    api = client.get("/api/control-tower")
    assert api.status_code == 503
    payload = api.get_json()
    assert payload["error"] == "control_tower_unavailable"
    assert payload["retry_after_seconds"] == 10
