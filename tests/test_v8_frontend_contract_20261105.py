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



def _synthetic_actionable_rows():
    """Synthetic display-only actions, NEVER sourced from exchange or paper logs."""
    return [
        {
            "symbol": "SYNTHALPHAUSDT",
            "_action": {
                "status": "PLACE_LIMIT_PAPER",
                "direction": "LONG",
                "entry": 0.10488,
                "stop": 0.10374,
                "target": 0.11223,
                "rr": 6.46,
                "distance_pct": 0.09,
                "reason": "Synthetic research rationale. No order authority; "
                          "illustrative geometry only and not a real signal.",
            },
        },
        {
            "symbol": "SYNTHBETAUSDT",
            "_action": {
                "status": "WAIT_FOR_TRIGGER",
                "direction": "SHORT",
                "entry": 121.333333,
                "stop": 126.444444,
                "target": 88.777777,
                "rr": 6.37,
                "distance_pct": 0.28,
                "reason": "Synthetic long explanation intended to validate "
                          "readable iPhone layout without squeezed columns. "
                          "No paper fill or exchange instruction.",
            },
        },
    ]


def test_stage8_paper_queue_has_mobile_card_and_desktop_table_without_value_changes(monkeypatch):
    data = dashboard.dashboard_payload(
        _sample_snapshot(), test_engine={"spec_id":"DISPLAY_TEST","verdict":"NOT_PROVEN"},
        paper_lifecycle={},
    )
    data["actionable"] = _synthetic_actionable_rows()
    monkeypatch.setattr(dashboard, "bounded_dashboard_payload", lambda: data)
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    response = dashboard.app.test_client().get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'class="v8-queue-scroll"' in body
    assert 'class="v8-queue-table"' in body
    assert 'class="v8-queue-cards"' in body
    assert body.count('class="v8-queue-card"') == 2
    assert body.count("SYNTHALPHAUSDT") == 2
    assert body.count("SYNTHBETAUSDT") == 2
    assert "0.10488" in body and "0.10374" in body and "0.11223" in body
    assert "6.46" in body and "0.09%" in body
    assert "Research rationale" in body
    assert "Paper research only · No order authority" in body
    css = dashboard.app.test_client().get("/static/v8.css").get_data(as_text=True)
    assert ".v8-body .v8-queue-table" in css
    assert ".v8-body .v8-queue-scroll{display:none!important}" in css
    assert ".v8-body .v8-queue-cards" in css
    assert 'id="runScanButton"' not in body




def _synthetic_radar_rows():
    """Representative UI rows, not real signals or trade recommendations."""
    return [
        {
            "symbol": "SYNTHRADARUSDT",
            "last_price": 1.223688,
            "_phase": "ACCUMULATION",
            "_timing": "LATE",
            "_behaviour": 6.82,
            "state": "WATCH_LONG",
            "_rr": None,
            "_action": {
                "status": "RESEARCH_ONLY",
                "label": "RESEARCH / WATCH",
                "reason": "Synthetic explanation of a research-only observation; "
                          "no signal or executable permission.",
            },
        },
        {
            "symbol": "SYNTHRADAR2USDT",
            "last_price": 0.001322,
            "_phase": "IGNITION",
            "_timing": "FAIR",
            "_behaviour": 6.30,
            "state": "DIRECTION_EMERGING_LONG",
            "_rr": 0.24,
            "_action": {
                "status": "RETEST_PLAN",
                "label": "BEST RETEST / LIMIT ZONE",
                "reason": "Synthetic long label and long explanatory note to "
                          "detect compressed columns on narrow mobile screens.",
            },
        },
    ]


def test_stage8_radar_mobile_cards_and_raw_research_values(monkeypatch):
    data = dashboard.dashboard_payload(
        _sample_snapshot(),
        test_engine={"spec_id":"DISPLAY_TEST", "operational_status":"REVIEW_REQUIRED",
                     "verdict":"NOT_PROVEN"},
        paper_lifecycle={},
    )
    data["research"] = _synthetic_radar_rows()
    monkeypatch.setattr(dashboard, "bounded_dashboard_payload", lambda: data)
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    response = dashboard.app.test_client().get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'class="v8-radar-scroll"' in html
    assert 'class="v8-radar-table"' in html
    assert 'class="v8-radar-cards"' in html
    assert html.count('class="v8-radar-card"') == 2
    assert html.count("SYNTHRADARUSDT") == 2
    assert html.count("SYNTHRADAR2USDT") == 2
    assert "1.223688" in html and "0.001322" in html
    assert "0.24" in html and "6.82" in html
    assert "BEST RETEST / LIMIT ZONE" in html
    assert "No trading authorisation" in html
    assert "Review Required" in html
    assert "Not Proven" in html
    assert 'title="Status code: REVIEW_REQUIRED"' in html
    css = dashboard.app.test_client().get("/static/v8.css").get_data(as_text=True)
    assert ".v8-body .v8-radar-scroll {display:none!important}" in css
    assert ".v8-body .v8-radar-cards" in css
    assert ".v8-body .action-grid .v8-integrity-metric" in css



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
    assert "viewport-fit=cover" in content
    assert 'id="v8-workspace"' in content
    for destination in ("overview", "research", "results", "system"):
        assert f'id="v8-view-{destination}"' in content
        assert f'data-v8-tab="{destination}"' in content
    assert 'id="v8-mobile-cards"' in content
    assert 'class="v8-strategy-table"' in content
    assert 'id="v8-search"' in content
    assert 'id="v8-detail-panel"' in content
    assert "/static/v8.css" in content and "/static/v8.js" in content


def test_stage6_mobile_public_research_layout_and_private_boundary(monkeypatch):
    content = _example_dashboard(monkeypatch).get_data(as_text=True)
    assert 'class="v8-runtime-note v8-build-meta" data-v8-section="system"' in content
    assert 'class="panel v8-private-boundary"' in content
    assert "Private account information" in content
    assert "Bitget Open Positions" not in content
    css = dashboard.app.test_client().get("/static/v8.css").get_data(as_text=True)
    assert ".v8-body .top h1" in css
    assert "#v8-view-system > .v8-trust-panel {order:20}" in css


def test_stage6_never_put_synthetic_private_account_fields_in_public_html(monkeypatch):
    snapshot = _sample_snapshot()
    snapshot["private_account"] = {
        "status": "CONNECTED",
        "open_positions": [{
            "symbol": "PRIVATE_CANARY_PAIR_842",
            "hold_side": "LONG",
            "total": "PRIVATE_CANARY_SIZE_842",
            "open_price_avg": "PRIVATE_CANARY_ENTRY_842",
            "mark_price": "PRIVATE_CANARY_MARK_842",
            "unrealized_pl": "PRIVATE_CANARY_PNL_842",
            "leverage": 7,
        }],
    }
    result = dashboard.dashboard_payload(
        snapshot, test_engine={"spec_id":"TEST_ONLY","verdict":"NOT_PROVEN"},
        paper_lifecycle={},
    )
    assert result["positions"][0]["symbol"] == "PRIVATE_CANARY_PAIR_842"
    assert "private_account" in result["snapshot"]
    monkeypatch.setattr(dashboard, "bounded_dashboard_payload", lambda: result)
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    response = dashboard.app.test_client().get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "PRIVATE_CANARY_" not in html
    assert "Bitget Open Positions" not in html
    assert "Personal Bitget account positions" in html
    api = dashboard.app.test_client().get("/api/latest")
    assert api.status_code == 200
    api_payload = api.get_json()
    assert "private_account" not in api_payload["snapshot"]
    assert api_payload["positions"] == []
    assert api_payload["account_status"] == "PRIVATE"
    assert "PRIVATE_CANARY_" not in api.get_data(as_text=True)


def test_stage6_public_reference_prices_secondary_disclosure(monkeypatch):
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    monkeypatch.setattr(dashboard, "bounded_dashboard_payload", lambda: (
        _ for _ in ()
    ).throw(dashboard.CanonicalSnapshotIncomplete("synthetic incomplete")))
    content = dashboard.app.test_client().get("/").get_data(as_text=True)
    assert '<details class="v8-market-reference">' in content
    assert "<summary>Public exchange reference prices" in content
    assert "Not Alpha Hunter signals" in content
    assert 'id="public-market-list"' in content
    assert 'id="v8-scan-warning"' in content


def test_v8_product_transparency_is_present_on_healthy_and_recovery_pages(monkeypatch):
    healthy = _example_dashboard(monkeypatch).get_data(as_text=True)
    assert 'id="v8-trust-title"' in healthy
    assert 'id="v8-copy-view-link"' in healthy
    assert 'id="v8-share-feedback"' in healthy
    assert 'id="v8-share-manual"' in healthy
    assert "Paper results and shadow scores are not verified live returns" in healthy
    assert "independent security certification" in healthy
    assert "Real-money order authority is disabled" in healthy
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    monkeypatch.setattr(
        dashboard, "bounded_dashboard_payload",
        lambda: (_ for _ in ()).throw(
            dashboard.CanonicalSnapshotIncomplete("synthetic blocked latest scan")
        ),
    )
    blocked = dashboard.app.test_client().get("/").get_data(as_text=True)
    assert 'id="v8-trust-title"' in blocked
    assert 'id="v8-copy-view-link"' in blocked
    assert "Historical records never replace incomplete" in blocked


def test_v8_share_link_drops_query_parameters_and_never_fetches(monkeypatch):
    _example_dashboard(monkeypatch)
    js = dashboard.app.test_client().get("/static/v8.js").get_data(as_text=True)
    assert 'location.origin + location.pathname + "#v8-" + activeView' in js
    assert 'navigator.clipboard.writeText(safeUrl)' in js
    assert 'manualShare.select()' in js
    assert "location.search" not in js
    assert "fetch(" not in js


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
    assert 'data-v8-retry-ms="60000"' in html
    assert "every 60 seconds" in html
    assert "viewport-fit=cover" in html
    assert 'class="card v8-recovery-card"' in html
    assert 'id="v8-scan-warning"' in html
    assert '<details class="v8-recovery-details">' in html
    assert "<summary>Recovery and retry details</summary>" in html
    assert "The scanner reported a canonical run" in html
    assert "Alpha Hunter signals are withheld" in html
    assert "Current signals withheld" in html
    assert 'class="v8-report-link"' in html
    assert "View historical performance report" in html
    assert "Report may be unavailable during a source outage" in html
    assert "<h1>Market intelligence</h1>" in html
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
    assert 'data-v8-retry-ms="75000"' in html
    assert "every 75 seconds" in html
    assert "viewport-fit=cover" in html
    assert 'id="v8-scan-warning"' in html
    assert "Recovery and retry details" in html
    assert "You can refresh saved evidence now" in html
    assert "Current signals withheld" in html
    assert "No exchange-order authority" in html or "no exchange-order authority" in html
    assert "Check latest scan" in html
    assert "Enable auto retry" in html
    assert 'class="v8-report-link"' in html
    assert "Open existing performance report (may be unavailable)" not in html


