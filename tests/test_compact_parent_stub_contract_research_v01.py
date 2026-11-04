"""Read-only synthetic compact-parent stub integrity regression."""
import pytest
import app as dashboard


def parent(stubs):
    return {"run_id": "run-test", "symbol_count": 2, "created_at": "2020-01-01T00:00:00Z"}


def payload(stubs):
    value = {"_storage_contract": "snapshot-parent-v0.2", "run_id": "run-test"}
    if stubs is not OMITTED:
        value["symbols"] = stubs
    return value


OMITTED = object()
CHILDREN = [
    {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
    {"symbol": "ETHUSDT", "payload": {"symbol": "ETHUSDT"}},
]


@pytest.mark.parametrize("stubs", [
    OMITTED, None, {}, "BTCUSDT", [],
    [{"symbol": "BTCUSDT"}],
    [{"symbol": "BTCUSDT"}, {"symbol": "BTCUSDT"}],
    [{"symbol": "BTCUSDT"}, {"symbol": ""}],
    [{"symbol": "BTCUSDT"}, {"symbol": None}],
    [{"symbol": "BTCUSDT"}, "ETHUSDT"],
])
def test_invalid_parent_stubs_fail_closed(monkeypatch, stubs):
    calls = []
    def fake_read(table, params):
        calls.append((table, params))
        return CHILDREN
    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_read)
    with pytest.raises(RuntimeError, match=r"(?:parent symbol|parent and child symbol mismatch)"):
        dashboard._hydrate_dashboard_snapshot(parent(stubs), payload(stubs))
    assert len(calls) == 1
    assert calls[0][0] == "alpha_hunter_symbol_snapshots"
    assert calls[0][1]["run_id"] == "eq.run-test"


@pytest.mark.parametrize("stubs", [
    [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
    [{"symbol": "ETHUSDT"}, {"symbol": "BTCUSDT"}],
])
def test_complete_parent_stubs_hydrate(monkeypatch, stubs):
    monkeypatch.setattr(dashboard, "supabase_get_rows", lambda *_: CHILDREN)
    result = dashboard._hydrate_dashboard_snapshot(parent(stubs), payload(stubs))
    assert [item["symbol"] for item in result["symbols"]] == ["BTCUSDT", "ETHUSDT"]


def test_legacy_noncompact_payload_does_not_read_children(monkeypatch):
    monkeypatch.setattr(dashboard, "supabase_get_rows",
                        lambda *_: pytest.fail("legacy must not query children"))
    value = dashboard._hydrate_dashboard_snapshot(
        {"run_id": "legacy"}, {"symbols": [{"symbol": "BTCUSDT"}]})
    assert value["run_id"] == "legacy"
