"""Harada E3: lost RPC acknowledgement followed by parent-only readback.

Isolated synthetic HTTP fault injection, not an authentic PG17 transaction test.
"""
import json

import pytest
import requests

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def test_lost_ack_retry_receipt_parent_only_readback_fails_closed():
    posts, gets = [], []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class Session:
        def post(self, url, **kwargs):
            assert url.endswith("/rpc/alpha_hunter_commit_core_scan_v01")
            posts.append(kwargs["data"])
            if len(posts) == 1:
                raise requests.ConnectionError("synthetic lost acknowledgement after possible commit")
            payload = json.loads(kwargs["data"])
            return Response({
                "committed": True,
                "run_id": payload["p_parent"][0]["run_id"],
                "parent_count": len(payload["p_parent"]),
                "symbol_count": len(payload["p_children"]),
                "signal_count": len(payload["p_signals"]),
                "feature_count": len(payload["p_features"]),
                "readiness_count": len(payload["p_readiness"]),
            })

        def get(self, url, **kwargs):
            params = dict(kwargs["params"])
            gets.append((url, params))
            if url.endswith("/rest/v1/alpha_hunter_snapshots"):
                return Response([{"run_id": params["run_id"][3:]}])
            return Response([])

    config = SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_ONLY",
        atomic_core_scan_writes=True,
        verify_core_scan_readback=True,
        max_retries=1,
        retry_backoff_seconds=0,
    )
    snapshot = {
        "version": "e3-lost-ack-parent-only",
        "collected_at_utc": "2026-11-21T07:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT", "last_price": 65000.0,
            "trade_permission": False, "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }
    with pytest.raises(SupabaseStorageError, match="readback"):
        SupabaseStorage(config, session=Session()).save_snapshot(snapshot)

    assert len(posts) == 2
    assert posts[0] == posts[1], "lost ACK retry must preserve identical transaction payload"
    assert len(gets) == 5
    assert len({url for url, _ in gets}) == 5
    run_id = json.loads(posts[0])["p_parent"][0]["run_id"]
    assert all(params["run_id"] == "eq." + run_id for _, params in gets)

