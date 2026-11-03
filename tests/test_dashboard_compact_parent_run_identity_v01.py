"""Fail-closed compact parent/payload run provenance contract.

No network access: synthetic rows exercise only the read-only dashboard hydrator.
A record from one canonical run must never be decorated with another run's
valid-looking child rows.
"""
from datetime import datetime, timezone

import pytest

import app as dashboard


def _row(run_id):
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol_count": 1,
    }


def _payload(run_id):
    return {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": run_id,
        "symbols": [{"symbol": "BTCUSDT"}],
    }


@pytest.mark.parametrize("parent_id,payload_id", [
    ("canonical-parent-A", "different-run-B"),
    (None, "different-run-B"),
    ("", "different-run-B"),
])
def test_compact_parent_payload_run_mismatch_fails_before_child_fetch(
    monkeypatch, parent_id, payload_id
):
    called = []

    def fake_rows(table, params):
        called.append((table, params))
        return [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}}]

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)

    with pytest.raises(RuntimeError, match="run_id.*mismatch|missing.*run_id"):
        dashboard._hydrate_dashboard_snapshot(_row(parent_id), _payload(payload_id))
    assert called == []


def test_matching_compact_parent_payload_run_uses_parent_child_key(monkeypatch):
    calls = []

    def fake_rows(table, params):
        calls.append((table, params))
        return [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT", "score": 3}}]

    monkeypatch.setattr(dashboard, "supabase_get_rows", fake_rows)
    result = dashboard._hydrate_dashboard_snapshot(
        _row("canonical-parent-A"),
        _payload("canonical-parent-A"),
    )

    assert result["run_id"] == "canonical-parent-A"
    assert result["symbols"] == [{"symbol": "BTCUSDT", "score": 3}]
    assert len(calls) == 1
    assert calls[0][0] == "alpha_hunter_symbol_snapshots"
    assert calls[0][1]["run_id"] == "eq.canonical-parent-A"


def test_legacy_payload_contract_is_preserved(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "supabase_get_rows",
        lambda *_: (_ for _ in ()).throw(AssertionError("legacy must not fetch child rows")),
    )
    legacy = {"_storage_contract": "legacy-full-v0.1", "symbols": [{"symbol": "BTCUSDT"}]}
    result = dashboard._hydrate_dashboard_snapshot(_row("legacy-1"), legacy)
    assert result["run_id"] == "legacy-1"
    assert result["symbols"] == [{"symbol": "BTCUSDT"}]
