"""Harada E6: distinguish provider-observed no-parent and parent-only failures.

Synthetic HTTP/readback only; never claims authentic private PG17 proof.
"""
import json
import pytest
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


@pytest.mark.parametrize("failure_shape", ["no_parent", "parent_only"])
def test_atomic_success_receipt_cannot_mask_missing_core_evidence(failure_shape):
    calls = {"posts": [], "gets": []}

    class Response:
        status_code = 200
        text = ""
        def __init__(self, value):
            self.value = value
        def json(self):
            return self.value

    class Session:
        def post(self, url, **kwargs):
            assert url.endswith("/rpc/alpha_hunter_commit_core_scan_v01")
            payload = json.loads(kwargs["data"])
            calls["posts"].append((url, kwargs["data"]))
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
            calls["gets"].append((url, dict(kwargs["params"])))
            if failure_shape == "parent_only" and url.endswith("/rest/v1/alpha_hunter_snapshots"):
                return Response([{"run_id": kwargs["params"]["run_id"][3:]}])
            return Response([])

    config = SupabaseConfig(
        url="https://example.supabase.co", key="SYNTHETIC_ONLY",
        atomic_core_scan_writes=True, verify_core_scan_readback=True,
        max_retries=0, retry_backoff_seconds=0,
    )
    snapshot = {
        "version": "e6-failure-shapes",
        "collected_at_utc": "2026-11-21T00:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT", "last_price": 65000.0,
            "trade_permission": False, "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }
    with pytest.raises(SupabaseStorageError, match="readback"):
        SupabaseStorage(config, session=Session()).save_snapshot(snapshot)
    assert len(calls["posts"]) == 1
    assert len(calls["gets"]) == 5
    assert len({url for url, _ in calls["gets"]}) == 5
    run_id = json.loads(calls["posts"][0][1])["p_parent"][0]["run_id"]
    assert all(params["run_id"] == "eq." + run_id for _, params in calls["gets"])
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in calls["posts"])
