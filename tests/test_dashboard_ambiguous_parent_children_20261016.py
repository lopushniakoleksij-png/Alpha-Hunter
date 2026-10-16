"""Fail-closed recovery for a parent committed without its compact child rows.

2026-10-16 live incident: canonical parent reported 60 symbols, 0 children.
This test deliberately never executes SQL or changes production test data.
"""
import pytest
import app as dashboard


def make_parent(symbols):
    return {
        "run_id": "isolated-run",
        "symbol_count": len(symbols),
        "payload": {
            "_storage_contract": "snapshot-parent-v0.2",
            "validation_identity": {"run_source": "RENDER_CRON"},
            "symbols": [{"symbol": name} for name in symbols],
        },
    }


def test_ambiguous_parent_committed_with_zero_children_fails_closed(monkeypatch):
    row = make_parent(["BTCUSDT", "ETHUSDT"])
    monkeypatch.setattr(dashboard, "supabase_get_rows", lambda table, params: [])
    with pytest.raises(RuntimeError, match="Incomplete compact canonical snapshot child evidence"):
        dashboard._hydrate_dashboard_snapshot(row, row["payload"])


def test_partial_child_write_fails_closed(monkeypatch):
    row = make_parent(["BTCUSDT", "ETHUSDT"])
    monkeypatch.setattr(
        dashboard,
        "supabase_get_rows",
        lambda table, params: [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}}],
    )
    with pytest.raises(RuntimeError, match="Incomplete compact canonical snapshot child evidence"):
        dashboard._hydrate_dashboard_snapshot(row, row["payload"])


@pytest.mark.parametrize("children", [
    [{"symbol": "BTCUSDT", "payload": {"symbol": "ETHUSDT"}}],
    [{"symbol": "ETHUSDT", "payload": {"symbol": "ETHUSDT"}}],
    [{"symbol": "BTCUSDT", "payload": "not-a-dict"}],
])
def test_wrong_child_evidence_never_substituted_for_parent(monkeypatch, children):
    row = make_parent(["BTCUSDT"])
    monkeypatch.setattr(dashboard, "supabase_get_rows", lambda table, params: children)
    with pytest.raises(RuntimeError):
        dashboard._hydrate_dashboard_snapshot(row, row["payload"])


def test_matching_parent_child_rows_hydrate_successfully(monkeypatch):
    row = make_parent(["BTCUSDT", "ETHUSDT"])
    children = [
        {"symbol": "ETHUSDT", "payload": {"symbol": "ETHUSDT", "last_price": 200}},
        {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT", "last_price": 100}},
    ]
    monkeypatch.setattr(dashboard, "supabase_get_rows", lambda table, params: children)
    result = dashboard._hydrate_dashboard_snapshot(row, row["payload"])
    assert [x["symbol"] for x in result["symbols"]] == ["BTCUSDT", "ETHUSDT"]


def test_incomplete_snapshot_endpoint_is_retryable_503(monkeypatch):
    row = make_parent(["BTCUSDT"])
    def fake_rows(table, params):
        if table == dashboard.SNAPSHOT_TABLE:
            return [row]
        if table == "alpha_hunter_symbol_snapshots":
            return []
        pytest.fail(f"unexpected read: {table}")
    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    assert dashboard.app.test_client().get("/").status_code == 503
    assert dashboard.app.test_client().get("/api/latest").get_json()["error"] == "live_data_unavailable"
