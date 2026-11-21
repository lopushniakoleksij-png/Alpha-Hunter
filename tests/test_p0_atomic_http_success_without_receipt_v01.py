"""Harada E2: HTTP success without a verifiable atomic receipt must fail closed.

Synthetic transport only; does not certify production PostgreSQL triggers.
"""
import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class MissingReceiptResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.text = body

    def json(self):
        import json
        return json.loads(self.text)


class MissingReceiptSession:
    def __init__(self, status, body):
        self.status, self.body = status, body
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs["data"]))
        return MissingReceiptResponse(self.status, self.body)


@pytest.mark.parametrize("status,body", [
    (200, ""),
    (200, "not-json"),
    (204, ""),
    (200, "null"),
    (200, "[]"),
])
def test_http_success_without_valid_atomic_receipt_never_falls_back(status, body):
    session = MissingReceiptSession(status, body)
    config = SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        max_retries=1,
        retry_backoff_seconds=0,
    )
    snapshot = {
        "version": "isolated-missing-receipt",
        "collected_at_utc": "2026-11-10T03:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT", "last_price": 65000.0,
            "trade_permission": False, "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }
    with pytest.raises(SupabaseStorageError):
        SupabaseStorage(config, session=session).save_snapshot(snapshot)
    assert len(session.calls) == 1
    assert session.calls[0][0].endswith(
        "/rest/v1/rpc/alpha_hunter_commit_core_scan_v01"
    )
