"""Alpha Hunter V8 phase-5 frontend contract: real Flask SSR, no services or orders."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import app as dashboard


def _sample_snapshot():
    rows = []
    for symbol, direction, status, price in [
        ("BEAMUSDT", "LONG", "WATCH", "0.004314335679928122"),
        ("RSRUSDT", "LONG", "WATCH", "0.0014765977539562157"),
        ("BTCUSDT", "SHORT", "NO_SETUP", "79001.12"),
    ]:
        rows.append({
            "symbol": symbol,
            "last_price": float(price),
            "state": "DIRECTION_EMERGING_" + direction,
            "market_phase": "IGNITION",
            "opportunity_timing": "EARLY",
            "behaviour_score": 4.0,
            "discovery_permission": False,
            "candidate_quality_status": "RESEARCH_ONLY",
            "rejection_reasons": [],
            "v7_trade_ready": False,
            "execution_setup": {
                "direction": direction,
                "entry": float(price),
                "stop": float(price) * (0.91 if direction == "LONG" else 1.09),
                "target": float(price) * (1.15 if direction == "LONG" else 0.85),
                "rr": 1.7,
                "checks": {},
            },
            "intelligence": {"huge_rr_score": 4.0},
            "multi_strategy_engine": {
                "strategies": [{
                    "strategy_id": "S3",
                    "strategy_name": "Trend Pullback",
                    "status": status,
                    "direction": direction,
                    "action": "WAIT_FOR_TRIGGER",
                    "proposed_action": "PLACE_LIMIT",
                    "signal_score": 10.0,
                    "entry": float(price),
                    "stop": float(price) * 0.91,
                    "target": float(price) * 1.15,
                    "rr": 3.82,
                    "persistence": {"state": "NEW", "consecutive_scans": 1},
                    "reasons": ["Waiting for evidence, not executable"],
                }]
            },
        })
    return {
        "run_id": "synthetic_phase_5_never_a_market_scan",
        "collected_at_utc": datetime(2026, 11, 5, 0, 55, tzinfo=timezone.utc).isoformat(),
        "canonical_market_freshness": {"verified": True},
        "universe": {"selected_count": len(rows)},
        "symbols": rows,
        "private_account": {"status": "UNKNOWN"},
        "multi_strategy_summary": {
            "configured_strategy_count": 10,
            "shadow_candidate_count": 0,
            "persistent_continuing_count": 0,
            "total_evaluations": 30,
            "covered_symbol_count": 3,
        },
    }


def _example_dashboard(monkeypatch):
    data = dashboard.dashboard_payload(
        _sample_snapshot(), test_engine={"spec_id": "TEST_ONLY", "verdict": "NOT_PROVEN"},
        paper_lifecycle={},
    )
    assert len(data["strategy_shadow"]) >= 2
    monkeypatch.setattr(dashboard, "bounded_dashboard_payload", lambda: data)
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    response = dashboard.app.test_client().get("/")
    return response


def test_current_flask_dashboard_renders_approved_v8_shell_without_backend_change(monkeypatch):
    response = _example_dashboard(monkeypatch)
    assert response.status_code == 200
    content = response.get_data(as_text=True)
    assert "Alpha Hunter V8" in content
    assert "Underlying engine 7.2" in content
    assert 'class="v8-shell"' in content
    assert 'id="v8-workspace"' in content
    for destination in ("overview", "research", "results", "system"):
        assert f'id="v8-view-{destination}"' in content
        assert f'data-v8-tab="{destination}"' in content
    assert 'id="v8-mobile-cards"' in content
    assert 'class="v8-strategy-table"' in content
    assert 'id="v8-search"' in content
    assert 'id="v8-detail-panel"' in content
    assert "/static/v8.css" in content and "/static/v8.js" in content


def test_research_payload_retains_original_values_and_explicit_unsafe_gate(monkeypatch):
    response = _example_dashboard(monkeypatch)
    body = response.get_data(as_text=True)
    assert "BEAMUSDT" in body
    assert "RSRUSDT" in body
    assert "WAIT_FOR_TRIGGER" in body or "NOT_APPROVED" in body
    assert "WATCH_ONLY" in body
    assert "Raw R:R" in body
    assert "No real-money orders" in body
    assert "Raw shadow intent (not executable)" in body
    assert "score" not in body.lower() or "uncalibrated" in body.lower()


def test_no_public_scan_button_or_ui_post_to_scanner(monkeypatch):
    response = _example_dashboard(monkeypatch)
    page = response.get_data(as_text=True)
    assert 'id="runScanButton"' not in page
    assert 'onclick="runScan()"' not in page
    assert "The protected scanner runs separately" in page
    assert 'aria-label="Refresh dashboard from the latest accepted canonical scan"' in page
    # Backend route deliberately remains unchanged by a presentation-only patch.
    assert "/api/run-scan" in {rule.rule for rule in dashboard.app.url_map.iter_rules()}



def test_phase7_public_scan_endpoint_is_fail_closed_and_cannot_spawn_worker(monkeypatch):
    """No browser or unauthenticated API request may create a second scanner."""
    import copy
    before = copy.deepcopy(dashboard.scan_state)
    def forbidden_worker(*args, **kwargs):
        raise AssertionError("Public web API attempted to launch a scanner worker")
    monkeypatch.setattr(dashboard.threading, "Thread", forbidden_worker)
    monkeypatch.setattr(dashboard, "run_scan_worker", forbidden_worker)
    client = dashboard.app.test_client()
    for headers in ({}, {"Authorization": "Basic YWJjOmRlZg=="}):
        response = client.post("/api/run-scan", json={}, headers=headers)
        assert response.status_code == 403
        assert response.headers["Cache-Control"] == "no-store"
        data = response.get_json()
        assert data["error"] == "manual_web_scanning_disabled"
        assert data["scanner_started"] is False
        assert data["trade_permission"] is False
        assert data["order_path"] == "NONE"
    assert dashboard.scan_state == before



def test_static_assets_served_from_existing_flask_application():
    client = dashboard.app.test_client()
    css = client.get("/static/v8.css")
    script = client.get("/static/v8.js")
    assert css.status_code == 200 and script.status_code == 200
    assert "text/css" in css.content_type
    assert "javascript" in script.content_type
    body = script.get_data(as_text=True)
    assert "[data-v8-section]" in body
    assert "v8-mobile-cards" in body
    assert "No real-money execution" in body
    assert "fetch(" not in body
    assert "/api/run-scan" not in body
    assert "requests" not in body


def test_legacy_critical_routes_and_scientific_permissions_remain_present():
    routes = {rule.rule: set(rule.methods) for rule in dashboard.app.url_map.iter_rules()}
    for route in ("/", "/api/latest", "/api/build", "/api/historical-status",
                  "/api/control-tower", "/control-tower", "/performance",
                  "/api/performance", "/execution-freeze", "/api/run-scan"):
        assert route in routes
    assert "POST" in routes["/api/run-scan"]
    assert "GET" in routes["/api/latest"]


@pytest.mark.parametrize("problem", [
    dashboard.CanonicalSnapshotPublishing("synthetic source publishing"),
    dashboard.CanonicalSnapshotIncomplete("synthetic source incomplete"),
])
def test_web_evidence_failure_still_withholds_current_research(monkeypatch, problem):
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    def fail():
        raise problem
    monkeypatch.setattr(dashboard, "bounded_dashboard_payload", fail)
    client = dashboard.app.test_client()
    page = client.get("/")
    assert page.status_code in (200, 202)
    assert "BEAMUSDT" not in page.get_data(as_text=True)
    api = client.get("/api/latest")
    assert api.status_code == 503
    assert api.get_json()["trade_permission"] is False if isinstance(problem, dashboard.CanonicalSnapshotIncomplete) else api.get_json()["error"] == "canonical_scan_publishing"


def test_v8_recovery_keeps_responsive_navigation_and_safety_boundary(monkeypatch):
    """An incomplete newest scan must still show the V8 terminal shell."""
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0)
    monkeypatch.setattr(
        dashboard, "bounded_dashboard_payload",
        lambda: (_ for _ in ()).throw(
            dashboard.CanonicalSnapshotIncomplete("synthetic incomplete latest scan")
        ),
    )
    client = dashboard.app.test_client()
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.headers["X-Alpha-Hunter-Evidence-State"] == "INCOMPLETE"
    assert 'class="v8-shell"' in html
    assert 'id="v8-workspace"' in html
    assert 'class="v8-bottom-nav"' in html
    assert 'id="v8-view-overview"' in html
    assert 'id="v8-view-research"' in html
    assert 'id="v8-view-results"' in html
    assert 'id="v8-view-system"' in html
    assert 'data-v8-section="research"' in html
    assert 'data-v8-section="overview"' in html
    assert "LATEST CANONICAL SCAN INCOMPLETE" in html
    assert "Current signals withheld" in html
    assert "HISTORICAL ONLY" in html
    assert "/static/v8.js" in html and "/static/v8.css" in html
    assert 'id="runScanButton"' not in html
    assert "Real orders disabled" in html
    result = client.get("/api/latest")
    assert result.status_code == 503
    assert result.get_json()["error"] == "canonical_scan_incomplete"


def test_v8_outage_page_preserves_same_navigation_and_no_trades(monkeypatch):
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0)
    monkeypatch.setattr(
        dashboard, "bounded_dashboard_payload",
        lambda: (_ for _ in ()).throw(RuntimeError("synthetic transport fault")),
    )
    client = dashboard.app.test_client()
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 503
    assert 'id="v8-workspace"' in html
    assert "LIVE DATA TEMPORARILY UNAVAILABLE" in html
    assert "Current signals withheld" in html
    assert "No exchange-order authority" in html or "no exchange-order authority" in html
    assert "Check latest scan" in html
    assert "Enable auto retry" in html


