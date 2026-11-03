"""Regression: malformed optional repair diagnostics must not crash the dashboard.

Non-production isolated Flask fixture. All Supabase rows are stubbed; no
network access, schema changes, trading or live position modifications.
"""
import pytest
import app as dashboard


@pytest.mark.parametrize("repair_row", [
    {"unresolved_entry_orders": "1", "open_positions_over_24h": 0},
    {"unresolved_entry_orders": -2, "open_positions_over_24h": 0},
    {"unresolved_entry_orders": 0, "open_positions_over_24h": None},
    {"unresolved_entry_orders": 0},
    {"unresolved_entry_orders": True, "open_positions_over_24h": 0},
])
def test_invalid_optional_repair_counts_fail_closed_without_dashboard_outage(monkeypatch, repair_row):
    calls = []

    def fake_read(table, params):
        calls.append(table)
        if table == "alpha_hunter_paper_profitability_status_v09":
            return [{
                "spec_id": "R10", "operational_status": "BLOCKED",
                "trade_permission": False,
                "production_promotion_permitted": False,
                "blockers": [],
            }]
        if table == "alpha_hunter_paper_repair_status_v01":
            return [repair_row]
        raise AssertionError(f"unexpected Supabase call: {table}")

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_read)
    status = dashboard.latest_test_engine_status()

    assert calls == [
        "alpha_hunter_paper_profitability_status_v09",
        "alpha_hunter_paper_repair_status_v01",
    ]
    assert status["spec_id"] == "R10"
    assert status["trade_permission"] is False
    assert status["production_promotion_permitted"] is False
    assert status["operational_status"] == "REVIEW_REQUIRED"
    assert status["repair_status"] == {}
    assert "REPAIR_DIAGNOSTICS_UNAVAILABLE" in status["blockers"]


@pytest.mark.parametrize("repair_row,expected", [
    ({"unresolved_entry_orders": 0, "open_positions_over_24h": 0}, ()),
    ({"unresolved_entry_orders": 2, "open_positions_over_24h": 0},
     ("UNRESOLVED_PAPER_ENTRY_REQUIRES_REPAIR",)),
    ({"unresolved_entry_orders": 0, "open_positions_over_24h": 3},
     ("OPEN_PAPER_POSITIONS_EXCEED_24H",)),
])
def test_valid_repair_counts_preserve_original_classification(monkeypatch, repair_row, expected):
    def fake_read(table, params):
        if table == "alpha_hunter_paper_profitability_status_v09":
            return [{
                "spec_id": "R10", "operational_status": "BLOCKED",
                "trade_permission": False, "production_promotion_permitted": False,
                "blockers": [],
            }]
        if table == "alpha_hunter_paper_repair_status_v01":
            return [repair_row]
        raise AssertionError(table)

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_read)
    status = dashboard.latest_test_engine_status()
    for blocker in expected:
        assert blocker in status["blockers"]
    if expected:
        assert status["operational_status"] == "REVIEW_REQUIRED"
    else:
        assert "REPAIR_DIAGNOSTICS_UNAVAILABLE" not in status["blockers"]
        assert status["operational_status"] == "BLOCKED"
    assert status["repair_status"] == repair_row
