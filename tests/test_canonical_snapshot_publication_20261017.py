"""Isolated canonical-parent publication regression tests; no production I/O."""
from copy import deepcopy

import pytest
import requests

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
        if table == "alpha_hunter_paper_protection_horizon_open_v09":
            return []
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
        call[2][0]["payload"].get("_canonical_publication_state")
        for call in calls
        if call[0] == "write" and call[1] == "alpha_hunter_snapshots"
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


def _large_canonical_snapshot(count=57):
    row = sample_canonical()
    row["symbols"] = [
        {"symbol": f"TEST{i:03d}USDT", "state": "NEUTRAL",
         "last_price": 100.0 + i, "trade_permission": False,
         "execution_setup": {}}
        for i in range(count)
    ]
    return row


@pytest.mark.parametrize(
    "count,expected_batches",
    [
        (57, [8, 8, 8, 8, 8, 8, 8, 1]),
        # Actual incident 31 Oct 2026: 62 advertised symbol rows / zero children.
        (62, [8, 8, 8, 8, 8, 8, 8, 6]),
    ],
)
def test_large_canonical_write_uses_bounded_idempotent_batches(
    monkeypatch, count, expected_batches,
):
    writer, calls = setup_writer(monkeypatch)
    original_select = writer._select_json

    def select(table, params):
        if table == writer.settings.symbol_table:
            return [
                {"symbol": row["symbol"], "payload": row["payload"]}
                for call in calls
                if call[0] == "write" and call[1] == writer.settings.symbol_table
                for row in call[2]
            ]
        return original_select(table, params)

    monkeypatch.setattr(writer, "_select_json", select)
    writer.save_snapshot(_large_canonical_snapshot(count))
    batches = [
        call[2] for call in calls
        if call[0] == "write" and call[1] == writer.settings.symbol_table
    ]
    assert [len(batch) for batch in batches] == expected_batches
    assert _parent_states(calls) == ["PENDING", "VERIFIED"]
    assert len({row["symbol"] for batch in batches for row in batch}) == count


def test_mid_batch_timeout_keeps_parent_pending_and_never_promotes(monkeypatch):
    writer, calls = setup_writer(monkeypatch)
    original_upsert = writer._upsert
    batches = [0]

    def interrupt(table, rows, on_conflict):
        if table == writer.settings.symbol_table:
            batches[0] += 1
            if batches[0] == 3:
                raise requests.ReadTimeout("synthetic timed-out third chunk")
        return original_upsert(table, rows, on_conflict)

    monkeypatch.setattr(writer, "_upsert", interrupt)
    with pytest.raises(requests.ReadTimeout, match="timed-out third chunk"):
        writer.save_snapshot(_large_canonical_snapshot())

    assert batches == [3]
    assert _parent_states(calls) == ["PENDING"]
    assert [
        len(call[2]) for call in calls
        if call[0] == "write" and call[1] == writer.settings.symbol_table
    ] == [8, 8]
