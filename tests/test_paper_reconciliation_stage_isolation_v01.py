import pytest

import alpha_hunter.storage as storage_module
from alpha_hunter.storage import (
    SupabaseConfig,
    SupabaseStorage,
    SupabaseStorageError,
)


def canonical_snapshot():
    return {
        "run_id": "run-stage-isolation",
        "collected_at_utc": "2026-10-02T23:00:00+00:00",
        "symbols": [
            {
                "symbol": "TESTUSDT",
                "bid_price": 9.9,
                "ask_price": 10.0,
                "bid_size": 1000.0,
                "ask_size": 1000.0,
            }
        ],
    }


def build_storage():
    return SupabaseStorage(
        SupabaseConfig(
            url="https://example.invalid",
            key="service-role-test",
        )
    )


def test_entry_reconciliation_failure_does_not_skip_exit_stage(monkeypatch):
    storage = build_storage()
    exit_commit_called = {"value": False}

    def fake_select(table, params):
        if table == storage_module.PAPER_RECONCILIATION_OPEN_VIEW:
            return [{"order_id": "entry-open", "symbol": "TESTUSDT"}]
        if table == storage_module.PAPER_RECONCILIATION_ATTEMPT_TABLE:
            return []
        if table == storage_module.PAPER_PROTECTION_OPEN_VIEW:
            return [{"entry_order_id": "protected-open", "symbol": "TESTUSDT"}]
        if table == storage_module.PAPER_EXIT_ATTEMPT_TABLE:
            return []
        raise AssertionError(table)

    monkeypatch.setattr(storage, "_select_json", fake_select)
    monkeypatch.setattr(
        storage,
        "_capture_missing_reconciliation_quotes",
        lambda snapshot, rows: {},
    )
    monkeypatch.setattr(
        storage_module,
        "reconcile_open_orders",
        lambda *args, **kwargs: ([{"attempt_id": "a"}], [], [], []),
    )
    monkeypatch.setattr(
        storage,
        "_commit_paper_reconciliation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SupabaseStorageError("entry transaction failed")
        ),
    )
    monkeypatch.setattr(
        storage_module,
        "reconcile_active_protections",
        lambda *args, **kwargs: ([{"attempt_id": "x"}], [], []),
    )

    def exit_commit(*args, **kwargs):
        exit_commit_called["value"] = True

    monkeypatch.setattr(
        storage,
        "_commit_paper_exit_reconciliation",
        exit_commit,
    )

    with pytest.raises(
        SupabaseStorageError,
        match="ENTRY_RECONCILIATION",
    ):
        storage._reconcile_paper_stages(
            canonical_snapshot(),
            "run-stage-isolation",
        )

    assert exit_commit_called["value"] is True


def test_exit_reconciliation_failure_does_not_erase_successful_entry_stage(monkeypatch):
    storage = build_storage()
    entry_commit_called = {"value": False}

    def fake_select(table, params):
        if table in {
            storage_module.PAPER_RECONCILIATION_OPEN_VIEW,
            storage_module.PAPER_PROTECTION_OPEN_VIEW,
        }:
            return []
        if table in {
            storage_module.PAPER_RECONCILIATION_ATTEMPT_TABLE,
            storage_module.PAPER_EXIT_ATTEMPT_TABLE,
        }:
            return []
        raise AssertionError(table)

    monkeypatch.setattr(storage, "_select_json", fake_select)
    monkeypatch.setattr(
        storage,
        "_capture_missing_reconciliation_quotes",
        lambda snapshot, rows: {},
    )
    monkeypatch.setattr(
        storage_module,
        "reconcile_open_orders",
        lambda *args, **kwargs: ([{"attempt_id": "a"}], [], [], []),
    )

    def entry_commit(*args, **kwargs):
        entry_commit_called["value"] = True

    monkeypatch.setattr(storage, "_commit_paper_reconciliation", entry_commit)
    monkeypatch.setattr(
        storage_module,
        "reconcile_active_protections",
        lambda *args, **kwargs: ([{"attempt_id": "x"}], [], []),
    )
    monkeypatch.setattr(
        storage,
        "_commit_paper_exit_reconciliation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SupabaseStorageError("exit transaction failed")
        ),
    )

    with pytest.raises(
        SupabaseStorageError,
        match="EXIT_RECONCILIATION",
    ):
        storage._reconcile_paper_stages(
            canonical_snapshot(),
            "run-stage-isolation",
        )

    assert entry_commit_called["value"] is True


def test_no_quotes_keeps_reconciliation_fail_closed_without_database_calls(monkeypatch):
    storage = build_storage()
    called = {"value": False}

    def unexpected(*args, **kwargs):
        called["value"] = True
        raise AssertionError("database reconciliation should not run")

    monkeypatch.setattr(storage, "_select_json", unexpected)

    snapshot = canonical_snapshot()
    snapshot["symbols"] = [{"symbol": "TESTUSDT"}]
    storage._reconcile_paper_stages(snapshot, snapshot["run_id"])

    assert called["value"] is False
