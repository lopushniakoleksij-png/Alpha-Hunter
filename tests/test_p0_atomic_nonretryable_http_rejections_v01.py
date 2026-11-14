"""Harada E2: non-retryable HTTP rejections must fail closed (isolated mock).

No network, database, production schema or real orders are used.
"""
import json

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class RejectedAtomicSession:
    def __init__(self, status):
        self.status = status
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs["data"]))
        class Response:
            status_code = self.status
            text = "synthetic rejection"
        return Response()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_atomic_rpc_nonretryable_http_rejection_never_replays_or_falls_back(status):
    session = RejectedAtomicSession(status)
    config = SupabaseConfig(
        url="https://example.invalid",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        max_retries=3,
        retry_backoff_seconds=0,
    )
    snapshot = {
        "version": "qa-rejection-only",
        "collected_at_utc": "2026-11-14T00:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT", "last_price": 65000.0,
            "trade_permission": False, "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }
    with pytest.raises(SupabaseStorageError, match=f"HTTP {status}"):
        SupabaseStorage(config, session=session).save_snapshot(snapshot)
    assert len(session.calls) == 1
    url, body = session.calls[0]
    assert url.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")
    payload = json.loads(body)
    assert payload["p_parent"][0]["run_id"] == snapshot["run_id"]
    assert payload["p_children"][0]["trade_permission"] is False
