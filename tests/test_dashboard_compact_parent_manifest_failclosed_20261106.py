"""Synthetic compact parent identity checks; no network or production writes."""
import pytest
import app as dashboard


def _parent():
    return {
        "run_id": "synthetic-run",
        "symbol_count": 1,
        "payload": {
            "_storage_contract": "snapshot-parent-v0.2",
            "run_id": "synthetic-run",
            "symbols": [{"symbol": "BTCUSDT"}],
        },
    }


@pytest.mark.parametrize("manifest", [None, {}, "BTCUSDT"])
def test_compact_parent_without_identity_manifest_fails_closed(monkeypatch, manifest):
    row = _parent()
    if manifest is None:
        del row["payload"]["symbols"]
    else:
        row["payload"]["symbols"] = manifest
    reads = []

    def fake_rows(table, params):
        reads.append((table, params))
        return [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}}]

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    with pytest.raises(RuntimeError, match="symbol manifest is missing"):
        dashboard._hydrate_dashboard_snapshot(row, row["payload"])
    # Malformed parent evidence must fail before a remote child read.
    assert reads == []


def test_valid_compact_parent_manifest_still_hydrates(monkeypatch):
    row = _parent()
    monkeypatch.setattr(
        dashboard, "supabase_get_rows",
        lambda table, params: [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT", "last_price": 1}}],
    )
    result = dashboard._hydrate_dashboard_snapshot(row, row["payload"])
    assert result["symbols"] == [{"symbol": "BTCUSDT", "last_price": 1}]


@pytest.mark.parametrize("count", [0, -1, 2001, True, False, "1", 1.0, [], {}])
def test_invalid_parent_count_rejected_without_child_query(monkeypatch, count):
    row = _parent()
    row["symbol_count"] = count
    reads = []
    monkeypatch.setattr(dashboard, "supabase_get_rows", lambda *args, **kwargs: reads.append(args) or [])
    with pytest.raises(RuntimeError, match="symbol_count is invalid"):
        dashboard._hydrate_dashboard_snapshot(row, row["payload"])
    assert reads == []


def test_absent_parent_count_uses_valid_manifest_length(monkeypatch):
    row = _parent()
    del row["symbol_count"]
    reads = []
    def fake_rows(table, params):
        reads.append((table, params))
        return [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}}]
    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    result = dashboard._hydrate_dashboard_snapshot(row, row["payload"])
    assert result["symbols"] == [{"symbol": "BTCUSDT"}]
    assert len(reads) == 1
