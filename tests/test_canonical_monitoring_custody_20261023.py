"""No network: publication requires a durable current-run position receipt."""
from copy import deepcopy

import pytest

from alpha_hunter.storage import SupabaseStorageError
from test_canonical_snapshot_publication_20261017 import (
    setup_writer, sample_canonical, _parent_states,
)

POSITION = dict(entry_order_id="position-1", decision_id="decision-1",
                symbol="BTCUSDT", direction="LONG")


def install_monitoring(monkeypatch, writer, calls, mutation=None):
    original = writer._select_json
    def select(table, params):
        if table == "alpha_hunter_paper_protection_horizon_open_v09":
            return [deepcopy(POSITION)]
        if table == "alpha_hunter_paper_exit_attempts_v04":
            calls.append(("monitoring_readback",))
            receipt = dict(POSITION, source_run_id=params["source_run_id"][3:],
                           observed_at_utc="2026-10-17T08:40:00Z",
                           outcome="NO_TRIGGER", blockers=[], paper_only=True,
                           exchange_authority=False, trade_permission=False,
                           order_path="NONE")
            rows = [receipt]
            return mutation(rows) if mutation else rows
        return original(table, params)
    monkeypatch.setattr(writer, "_select_json", select)


def test_durable_receipt_precedes_verified_parent(monkeypatch):
    writer, calls = setup_writer(monkeypatch)
    install_monitoring(monkeypatch, writer, calls)
    writer.save_snapshot(sample_canonical())
    assert _parent_states(calls) == ["PENDING", "VERIFIED"]
    read_index = calls.index(("monitoring_readback",))
    assert read_index < max(i for i, c in enumerate(calls)
                            if c[:2] == ("write", "alpha_hunter_snapshots"))


@pytest.mark.parametrize("mutation", [
    lambda rows: [],
    lambda rows: rows * 2,
    *[lambda rows, k=k, v=v: [{**rows[0], k: v}] for k, v in [
        ("source_run_id", "old-run"), ("decision_id", "wrong-decision"),
        ("symbol", "ETHUSDT"), ("direction", "SHORT"),
        ("observed_at_utc", "2026-10-17T08:39:59Z"),
        ("observed_at_utc", "2026-10-17T09:15:01Z"),
        ("observed_at_utc", "2026-10-17T08:40:00"),
        ("outcome", "INPUT_MISSING"), ("outcome", "AMBIGUOUS"),
        ("blockers", ["HORIZON_MONITORING_GAP_EXCEEDED"]),
        ("paper_only", False), ("trade_permission", True),
    ]],
])
def test_successful_reconcile_ack_cannot_replace_durable_evidence(monkeypatch, mutation):
    writer, calls = setup_writer(monkeypatch)
    install_monitoring(monkeypatch, writer, calls, mutation)
    with pytest.raises(SupabaseStorageError, match="durable monitoring evidence"):
        writer.save_snapshot(sample_canonical())
    assert any(c[0] == "reconcile" for c in calls)
    assert _parent_states(calls) == ["PENDING"]


def test_inventory_failure_still_attempts_reconciliation(monkeypatch):
    writer, calls = setup_writer(monkeypatch)
    original = writer._select_json
    def select(table, params):
        if table == "alpha_hunter_paper_protection_horizon_open_v09":
            raise SupabaseStorageError("inventory timeout")
        return original(table, params)
    monkeypatch.setattr(writer, "_select_json", select)
    with pytest.raises(SupabaseStorageError, match="monitoring inventory"):
        writer.save_snapshot(sample_canonical())
    assert any(c[0] == "reconcile" for c in calls)
    assert _parent_states(calls) == ["PENDING"]


def test_real_early_return_without_quotes_cannot_publish(monkeypatch):
    writer, calls = setup_writer(monkeypatch)
    install_monitoring(monkeypatch, writer, calls, lambda rows: [])
    monkeypatch.setattr(writer, "_reconcile_paper_stages",
                        type(writer)._reconcile_paper_stages.__get__(writer))
    with pytest.raises(SupabaseStorageError, match="durable monitoring evidence"):
        writer.save_snapshot(sample_canonical())
    assert _parent_states(calls) == ["PENDING"]
