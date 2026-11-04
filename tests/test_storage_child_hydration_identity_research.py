"""Offline compact child hydration identity regression (research only)."""

from types import SimpleNamespace

import pytest

from alpha_hunter.storage import (
    PARENT_STORAGE_CONTRACT,
    SupabaseConfig,
    SupabaseStorage,
    SupabaseStorageError,
)


def hydrate(rows):
    storage = SupabaseStorage.__new__(SupabaseStorage)
    storage.settings = SupabaseConfig(url="https://example.invalid", key="test-only")
    storage.request_with_retry = lambda *args, **kwargs: SimpleNamespace(
        status_code=200, json=lambda: rows
    )
    return storage._hydrate_snapshot(
        {"run_id": "run-1", "collected_at_utc": "2026-11-04T00:00:00Z"},
        {"_storage_contract": PARENT_STORAGE_CONTRACT, "symbols": []},
    )


def test_valid_child_identity_preserved():
    assert hydrate([{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT", "score": 3}}])["symbols"] == [
        {"symbol": "BTCUSDT", "score": 3}
    ]


@pytest.mark.parametrize("rows", [
    [None],
    [{"symbol": "BTCUSDT", "payload": None}],
    [{"symbol": "BTCUSDT", "payload": {"symbol": "ETHUSDT"}}],
    [{"symbol": "BTCUSDT", "payload": {}}],
    [{"symbol": "", "payload": {"symbol": ""}}],
    [{"symbol": 42, "payload": {"symbol": 42}}],
    [
        {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
        {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
    ],
])
def test_malformed_or_mismatched_child_fails_closed(rows):
    with pytest.raises(SupabaseStorageError):
        hydrate(rows)


def test_legacy_snapshot_does_not_query_children():
    storage = SupabaseStorage.__new__(SupabaseStorage)
    storage.request_with_retry = lambda *a, **k: pytest.fail("unexpected request")
    payload = {"symbols": [{"symbol": "BTCUSDT"}]}
    assert storage._hydrate_snapshot({"run_id": "legacy"}, payload)["symbols"] == payload["symbols"]
