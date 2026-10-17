"""Isolated canonical-parent publication regression tests; no production I/O."""
from copy import deepcopy

import pytest

import app as dashboard
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def sample_canonical():
    return {
        "version": "0.3.0",
        "collected_at_utc": "2026-10-17T08:40:00+00:00",
        "product_type": "usdt-futures",
        "validation_identity": {"run_source": "RENDER_CRON"},
        "symbols": [{
            "symbol": "BTCUSDT",
            "state": "WATCH",
            "trade_permission": False,
            "last_price": 70000.0,
            "execution_setup": {"direction": None, "rr": None},
        }, {
            "symbol": "ETHUSDT",
            "state": "WATCH",
            "trade_permission": False,
            "last_price": 2000.0,
            "execution_setup": {"direction": None, "rr": None},
        }],
    }


def setup_writer(monkeypatch, child_mode="complete", parent_mode="complete",
                 reconciliation_error=None):
    storage = SupabaseStorage(SupabaseConfig(
        url="https://isolated.example.supabase.co", key="test-only",
    ))
    calls = []
    persisted = {}

    def upsert(table, rows, on_conflict):
        saved = deepcopy(rows)
        calls.append(("write", table, saved))
        if table == storage.settings.snapshot_table:
            persisted.update(saved[0])

    def select(table, params):
        calls.append(("read", table, deepcopy(params)))
        if table == storage.settings.symbol_table:
            if child_mode == "empty":
                return []
            if child_mode == "partial":
                return [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}}]
            if child_mode == "mismatch":
                return [
                    {"symbol": "BTCUSDT", "payload": {"symbol": "ETHUSDT"}},
                    {"symbol": "ETHUSDT", "payload": {"symbol": "ETHUSDT"}},
                ]
            return [
                {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
                {"symbol": "ETHUSDT", "payload": {"symbol": "ETHUSDT"}},
            ]
        if table == storage.settings.snapshot_table:
            if parent_mode == "missing":
                return []
            return [deepcopy(persisted)]
        pytest.fail(f"unexpected select: {table}")

    def reconcile(snapshot, run_id):
        calls.append(("reconcile", run_id))
        if reconciliation_error:
            raise SupabaseStorageError(reconciliation_error)

    monkeypatch.setattr(storage, "_upsert", upsert)
    monkeypatch.setattr(storage, "_insert_immutable", lambda *a, **kw: None)
    monkeypatch.setattr(storage, "_select_json", select)
    monkeypatch.setattr(storage, "_reconcile_paper_stages", reconcile)
    return storage, calls


def _parent_states(calls):
    return [
        rows[0]["payload"].get("_canonical_publication_state")
        for action, table, rows in calls
        if action == "write" and table == "alpha_hunter_snapshots"
    ]


def test_canonical_parent_is_pending_until_reconciliation_and_readback(monkeypatch):
    writer, calls = setup_writer(monkeypatch)
    run_id = writer.save_snapshot(sample_canonical())
    assert len(run_id) == 32
    assert _parent_states(calls) == ["PENDING", "VERIFIED"]
    first_parent_index = next(
        i for i, row in enumerate(calls)
        if row[0] == "write" and row[1] == "alpha_hunter_snapshots"
    )
    child_write_index = next(
        i for i, row in enumerate(calls)
        if row[0] == "write" and row[1] == "alpha_hunter_symbol_snapshots"
    )
    reconcile_index = next(i for i, row in enumerate(calls) if row[0] == "reconcile")
    child_read_index = next(
        i for i, row in enumerate(calls)
        if row[0] == "read" and row[1] == "alpha_hunter_symbol_snapshots"
    )
    last_parent_write_index = max(
        i for i, row in enumerate(calls)
        if row[0] == "write" and row[1] == "alpha_hunter_snapshots"
    )
    assert first_parent_index < child_write_index < reconcile_index < child_read_index
    assert child_read_index < last_parent_write_index
    assert calls[-1][0:2] == ("read", "alpha_hunter_snapshots")


@pytest.mark.parametrize("mode", ["empty", "partial", "mismatch"])
def test_missing_or_corrupt_child_evidence_never_publishes(monkeypatch, mode):
    writer, calls = setup_writer(monkeypatch, child_mode=mode)
    with pytest.raises(SupabaseStorageError, match="incomplete child evidence"):
        writer.save_snapshot(sample_canonical())
    assert _parent_states(calls) == ["PENDING"]


def test_unconfirmed_reconciliation_never_publishes(monkeypatch):
    writer, calls = setup_writer(
        monkeypatch, reconciliation_error="ambiguous paper monitoring write",
    )
    with pytest.raises(SupabaseStorageError, match="ambiguous paper monitoring"):
        writer.save_snapshot(sample_canonical())
    assert _parent_states(calls) == ["PENDING"]


def test_missing_final_parent_readback_fails_closed(monkeypatch):
    writer, calls = setup_writer(monkeypatch, parent_mode="missing")
    with pytest.raises(SupabaseStorageError, match="confirmed parent readback"):
        writer.save_snapshot(sample_canonical())
    assert _parent_states(calls) == ["PENDING", "VERIFIED"]


def test_pending_parent_never_hydrates_even_if_all_children_exist(monkeypatch):
    row = {
        "run_id": "pending-run",
        "symbol_count": 2,
        "payload": {
            "_storage_contract": "snapshot-parent-v0.2",
            "_canonical_publication_state": "PENDING",
            "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
        },
    }
    monkeypatch.setattr(
        dashboard, "supabase_get_rows",
        lambda *a, **kw: pytest.fail("pending must fail before child query"),
    )
    with pytest.raises(RuntimeError, match="publication is unverified"):
        dashboard._hydrate_dashboard_snapshot(row, row["payload"])
    storage = SupabaseStorage(SupabaseConfig(url="https://x.invalid", key="test"))
    with pytest.raises(SupabaseStorageError, match="publication is not verified"):
        storage._hydrate_snapshot(row, row["payload"])


def test_pending_canonical_snapshot_endpoint_keeps_trading_hidden(monkeypatch):
    row = {
        "run_id": "pending-run",
        "symbol_count": 1,
        "payload": {
            "_storage_contract": "snapshot-parent-v0.2",
            "_canonical_publication_state": "PENDING",
            "validation_identity": {"run_source": "RENDER_CRON"},
            "symbols": [{"symbol": "BTCUSDT"}],
        },
    }
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.setattr(dashboard, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0.0)
    monkeypatch.setattr(
        dashboard, "supabase_get_rows",
        lambda table, params: [row] if table == dashboard.SNAPSHOT_TABLE else [],
    )
    response = dashboard.app.test_client().get("/")
    assert response.status_code == 503
    assert "Trading actions are intentionally hidden" in response.get_data(as_text=True)
