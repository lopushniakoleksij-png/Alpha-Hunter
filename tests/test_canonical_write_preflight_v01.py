"""Research-only regression: invalid canonical child identities must fail before parent upsert.

No database or network traffic; all requests are intercepted by FakeSession.
"""
import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        raise AssertionError("invalid canonical batch must never write")


def snapshot(symbols):
    return {
        "version": "0.3.0",
        "collected_at_utc": "2026-11-03T18:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": symbols,
    }


def child(symbol):
    return {
        "symbol": symbol,
        "state": "WATCH_LONG",
        "trade_permission": False,
        "last_price": 1.0,
        "execution_setup": {},
    }


@pytest.mark.parametrize("symbols", [
    [child("BTCUSDT"), child("BTCUSDT")],
    [child("BTCUSDT"), child("")],
    [child("BTCUSDT"), child(None)],
    [child("BTCUSDT"), child(" BTCUSDT ")],
    [child("BTCUSDT"), {"state": "ERROR", "error": "source unavailable"}],
])
def test_preflight_rejects_invalid_child_identity_without_parent_write(symbols):
    session = FakeSession()
    storage = SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="fake"),
        session=session,
    )
    with pytest.raises(SupabaseStorageError, match="canonical.*symbol|duplicate.*symbol"):
        storage.save_snapshot(snapshot(symbols))
    assert session.calls == []


def test_preflight_accepts_unique_symbol_identifiers():
    class GoodResponse:
        status_code = 201
        text = ""

    class GoodSession:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return GoodResponse()

    session = GoodSession()
    storage = SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="fake"),
        session=session,
    )
    result = storage.save_snapshot(snapshot([child("BTCUSDT"), child("ETHUSDT")]))
    assert len(result) == 32
    assert session.calls[0][0].endswith("/alpha_hunter_snapshots")
    assert session.calls[1][0].endswith("/alpha_hunter_symbol_snapshots")
