"""Read-only synthetic regression: compact canonical parent/payload run identity.

No network, database writes, production access, or historical evidence changes.
"""
import pytest
import app as dashboard


@pytest.mark.parametrize("parent_id,payload_id", [
    ("parent-a", "other-run"),
    ("parent-a", ""),
    ("parent-a", None),
    ("", "parent-a"),
    (None, "parent-a"),
    (123, "123"),
])
def test_compact_parent_payload_identity_mismatch_fails_before_child_read(
    monkeypatch, parent_id, payload_id,
):
    calls = []
    def forbidden_read(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("invalid identity must not query any child records")
    monkeypatch.setattr(dashboard, "supabase_get_rows", forbidden_read)
    row = {"run_id": parent_id, "symbol_count": 1}
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": payload_id,
        "symbols": [{"symbol": "BTCUSDT"}],
    }
    with pytest.raises(RuntimeError, match="parent/payload run_id mismatch"):
        dashboard._hydrate_dashboard_snapshot(row, payload)
    assert not calls


def test_matching_compact_identity_hydrates_exact_run_only(monkeypatch):
    observed = []
    def read_children(table, params):
        observed.append((table, dict(params)))
        return [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT", "value": 1}}]
    monkeypatch.setattr(dashboard, "supabase_get_rows", read_children)
    row = {"run_id": "synthetic-001", "symbol_count": 1}
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": "synthetic-001",
        "symbols": [{"symbol": "BTCUSDT"}],
    }
    result = dashboard._hydrate_dashboard_snapshot(row, payload)
    assert result["symbols"] == [{"symbol": "BTCUSDT", "value": 1}]
    assert observed == [("alpha_hunter_symbol_snapshots", {
        "select": "symbol,payload",
        "run_id": "eq.synthetic-001",
        "order": "symbol.asc",
        "limit": "2000",
    })]


def test_legacy_noncompact_payload_preserved_without_child_read(monkeypatch):
    monkeypatch.setattr(dashboard, "supabase_get_rows",
                        lambda *args, **kwargs: pytest.fail("legacy should not hydrate"))
    row = {"run_id": "parent-a"}
    payload = {"run_id": "other-run", "symbols": []}
    assert dashboard._hydrate_dashboard_snapshot(row, payload)["run_id"] == "other-run"
