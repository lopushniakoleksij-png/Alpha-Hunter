"""Synthetic canonical storage read integrity: never accept incomplete child batches."""
import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class Response:
    status_code = 200
    text = ""

    def __init__(self, rows):
        self.rows = rows

    def json(self):
        return self.rows


class Session:
    def __init__(self, children):
        self.children = children
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.children)


def storage_for(children):
    session = Session(children)
    return SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="test-only", max_retries=0),
        session=session,
    ), session


def parent(count=2, run_id="run-A"):
    return {"run_id": run_id, "symbol_count": count, "collected_at_utc": "2026-11-03T16:00:00Z"}


def payload(run_id="run-A"):
    return {"run_id": run_id, "_storage_contract": "snapshot-parent-v0.2",
            "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]}


def child(symbol):
    return {"symbol": symbol, "payload": {"symbol": symbol, "trade_permission": False}}


@pytest.mark.parametrize("children", [
    [], [child("BTCUSDT")],
    [child("BTCUSDT"), child("BTCUSDT")],
    [child("BTCUSDT"), {"symbol": "ETHUSDT", "payload": None}],
    [child("BTCUSDT"), {"symbol": "ETHUSDT", "payload": {"symbol": "OTHERUSDT"}}],
])
def test_incomplete_or_corrupt_child_batch_fails_closed(children):
    storage, _ = storage_for(children)
    with pytest.raises(SupabaseStorageError, match="canonical.*child|canonical.*count"):
        storage._hydrate_snapshot(parent(), payload())


@pytest.mark.parametrize("bad_count", [None, -1, True, "2", 2.0])
def test_invalid_parent_symbol_count_fails_closed(bad_count):
    storage, session = storage_for([child("BTCUSDT"), child("ETHUSDT")])
    with pytest.raises(SupabaseStorageError, match="symbol_count"):
        storage._hydrate_snapshot(parent(bad_count), payload())
    assert session.calls == []


def test_mismatched_parent_payload_run_fails_before_child_read():
    storage, session = storage_for([child("BTCUSDT"), child("ETHUSDT")])
    with pytest.raises(SupabaseStorageError, match="run_id"):
        storage._hydrate_snapshot(parent(), payload("run-B"))
    assert session.calls == []


def test_complete_canonical_batch_preserves_two_symbols():
    storage, session = storage_for([child("BTCUSDT"), child("ETHUSDT")])
    result = storage._hydrate_snapshot(parent(), payload())
    assert [r["symbol"] for r in result["symbols"]] == ["BTCUSDT", "ETHUSDT"]
    assert len(session.calls) == 1
    assert session.calls[0][1]["params"]["run_id"] == "eq.run-A"
