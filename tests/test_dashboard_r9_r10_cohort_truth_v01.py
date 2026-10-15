"""Dashboard-only R9/R10 scientific cohort separation regression.

No live Supabase, Bitget, scanner, order engine or scientific data mutation.
"""
import app as dashboard


R10 = {
    "spec_id": "SEALED-ARCH-V14R10-EXEC-PAPER-24H-20261005",
    "real_scans_since_registration": 649,
    "completed_paper_trades": 1,
    "minimum_completed_paper_trades": 100,
    "test_days_elapsed": 9.01,
    "minimum_test_days": 30,
    "profitability_status": "BLOCKED_ADMISSION_HALTED",
    "operational_status": "BLOCKED",
    "verdict": "BLOCKED_ADMISSION_HALTED",
    "blockers": ["VALIDATED_EXECUTION_COST_MODEL_MISSING", "SUCCESSOR_INTEGRITY_FAILURE"],
    "trade_permission": False,
}
R9 = {
    "spec_id": "SEALED-ARCH-V14R9-EXEC-PAPER-24H-20261004",
    "real_scans_since_registration": 796,
    "completed_paper_trades": 0,
    "identity_drift_scans": 738,
    "test_days_elapsed": 11.06,
    "profitability_status": "BLOCKED_ADMISSION_HALTED",
}


def fake_rows(table, params):
    assert params == {"select": "*", "limit": "1"}
    if table == "alpha_hunter_paper_profitability_status_v10":
        return [dict(R10)]
    if table == "alpha_hunter_paper_profitability_status_v09":
        return [dict(R9)]
    if table == "alpha_hunter_paper_repair_status_v01":
        return [{"unresolved_entry_orders": 0, "open_positions_over_24h": 0}]
    raise AssertionError(f"unexpected source: {table}")


def test_r10_is_primary_and_historical_r9_is_separate(monkeypatch):
    calls = []
    def spy(table, params):
        calls.append(table)
        return fake_rows(table, params)
    monkeypatch.setattr(dashboard, "supabase_get_rows", spy)
    got = dashboard.latest_test_engine_status()
    assert got["spec_id"] == R10["spec_id"]
    assert got["real_scans_since_registration"] == 649
    assert got["completed_paper_trades"] == 1
    assert got["verdict"] == "BLOCKED_ADMISSION_HALTED"
    assert got["historical_r9"]["real_scans_since_registration"] == 796
    assert got["historical_r9"]["identity_drift_scans"] == 738
    assert got["cohort_role"] == "CURRENT_R10_SUCCESSOR"
    assert got["trade_permission"] is False
    assert calls == [
        "alpha_hunter_paper_profitability_status_v10",
        "alpha_hunter_paper_profitability_status_v09",
        "alpha_hunter_paper_repair_status_v01",
    ]


def test_unavailable_r10_never_inherits_r9_scans_or_completions(monkeypatch):
    def missing_successor(table, params):
        if table == "alpha_hunter_paper_profitability_status_v10":
            return []
        return fake_rows(table, params)
    monkeypatch.setattr(dashboard, "supabase_get_rows", missing_successor)
    got = dashboard.latest_test_engine_status()
    assert got["verdict"] == "R10_STATUS_UNAVAILABLE"
    assert got["operational_status"] == "REVIEW_REQUIRED"
    assert "SUCCESSOR_STATUS_UNAVAILABLE" in got["blockers"]
    assert "real_scans_since_registration" not in got
    assert "completed_paper_trades" not in got
    assert got["historical_r9"]["real_scans_since_registration"] == 796
    assert got["trade_permission"] is False
    assert got["order_path"] == "NONE"


def test_mislabeled_r10_source_fails_closed(monkeypatch):
    def swapped(table, params):
        if table == "alpha_hunter_paper_profitability_status_v10":
            return [dict(R9)]
        return fake_rows(table, params)
    monkeypatch.setattr(dashboard, "supabase_get_rows", swapped)
    got = dashboard.latest_test_engine_status()
    assert got["spec_id"] == "R10_STATUS_UNAVAILABLE"
    assert got["verdict"] == "R10_STATUS_UNAVAILABLE"
    assert "completed_paper_trades" not in got


def test_html_renders_distinct_r10_and_r9_cohorts_without_combining(monkeypatch):
    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    status = dashboard.latest_test_engine_status()
    data = dashboard.dashboard_payload(
        {
            "run_id": "test-snapshot",
            "symbols": [],
            "collected_at_utc": "2026-10-15T14:43:40+00:00",
            "private_account": {"open_positions": []},
        },
        status,
        {"valid_completed_trades": 32},
    )
    monkeypatch.setattr(dashboard, "dashboard_view_data", lambda: data)
    page = dashboard.app.test_client().get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "R10 Successor (Current)" in html
    assert "R10 qualified completions" in html
    assert "1/100" in html
    assert "R9 Historical" in html
    assert "R9 scans: 796" in html
    assert "identity-drift scans: 738" in html
    assert "NOT current or mergeable with R10" in html
    assert "BLOCKED_ADMISSION_HALTED" in html


def test_missing_r10_renders_unavailable_not_fake_zero(monkeypatch):
    def missing_successor(table, params):
        if table == "alpha_hunter_paper_profitability_status_v10":
            return []
        return fake_rows(table, params)
    monkeypatch.setattr(dashboard, "supabase_get_rows", missing_successor)
    status = dashboard.latest_test_engine_status()
    data = dashboard.dashboard_payload(
        {"run_id": "test", "symbols": [], "private_account": {"open_positions": []}},
        status,
        {},
    )
    monkeypatch.setattr(dashboard, "dashboard_view_data", lambda: data)
    html = dashboard.app.test_client().get("/").get_data(as_text=True)
    assert "R10_STATUS_UNAVAILABLE" in html
    assert "R10 qualified completions" in html
    assert "Unavailable" in html
    assert "R9 scans: 796" in html
    assert "SUCCESSOR_STATUS_UNAVAILABLE" in html
