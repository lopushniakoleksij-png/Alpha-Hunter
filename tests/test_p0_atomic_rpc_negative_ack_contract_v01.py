"""Harada E2: isolated negative HTTP and acknowledgement contract tests.

Only synthetic responses. No production access or network partition is exercised.
"""
import json

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def config():
    return SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_ONLY",
        atomic_core_scan_writes=True,
        max_retries=2,
        retry_backoff_seconds=0,
    )


def snapshot():
    return {
        "version": "synthetic",
        "collected_at_utc": "2026-11-09T15:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT", "last_price": 60000,
            "state": "WATCH", "trade_permission": False,
            "execution_setup": {"direction": None, "rr": None},
        }],
    }


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload
        self.text = "synthetic"

    def json(self):
        return self.payload


class Session:
    def __init__(self, status, receipt=None):
        self.status = status
        self.receipt = receipt
        self.calls = []

    def post(self, url, **kwargs):
        assert url.endswith("/rpc/alpha_hunter_commit_core_scan_v01")
        self.calls.append((url, json.loads(kwargs["data"])))
        if self.receipt is None:
            return Response(self.status, {"error": "synthetic"})
        request = self.calls[-1][1]
        counts = {
            "parent_count": len(request["p_parent"]),
            "symbol_count": len(request["p_children"]),
            "signal_count": len(request["p_signals"]),
            "feature_count": len(request["p_features"]),
            "readiness_count": len(request["p_readiness"]),
        }
        return Response(self.status, {
            "committed": True,
            "run_id": request["p_parent"][0]["run_id"],
            **counts,
            **self.receipt,
        })


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_nonretryable_http_failure_never_replays_or_falls_back(status):
    session = Session(status)
    with pytest.raises(SupabaseStorageError, match=f"HTTP {status}"):
        SupabaseStorage(config(), session=session).save_snapshot(snapshot())
    assert len(session.calls) == 1


@pytest.mark.parametrize("receipt", [
    {"committed": False},
    {"run_id": "wrong-run-id"},
    {"symbol_count": 0},
    {"symbol_count": True},
    {"readiness_count": -1},
])
def test_mismatched_receipt_fails_closed_without_legacy_fallback(receipt):
    session = Session(200, receipt=receipt)
    with pytest.raises(SupabaseStorageError, match="confirmation did not match"):
        SupabaseStorage(config(), session=session).save_snapshot(snapshot())
    assert len(session.calls) == 1
