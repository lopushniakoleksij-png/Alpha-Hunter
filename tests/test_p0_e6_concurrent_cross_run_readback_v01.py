"""E6: concurrent distinct scan identities must not accept cross-run readback.

Synthetic HTTP-only isolation; not authentic private PostgreSQL trigger proof.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def test_concurrent_distinct_run_readback_cross_contamination_fails_closed():
    barrier = Barrier(2, timeout=10)
    lock = Lock()
    posts, reads = [], []

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
            payload = json.loads(kwargs["data"])
            run_id = payload["p_parent"][0]["run_id"]
            with lock:
                posts.append(run_id)
            barrier.wait()
            return Response({
                "committed": True, "run_id": run_id,
                "parent_count": len(payload["p_parent"]),
                "symbol_count": len(payload["p_children"]),
                "signal_count": len(payload["p_signals"]),
                "feature_count": len(payload["p_features"]),
                "readiness_count": len(payload["p_readiness"]),
            })

        def get(self, url, **kwargs):
            params = dict(kwargs["params"])
            with lock:
                reads.append((url, params))
                other = [x for x in posts if x != params["run_id"][3:]]
            if url.endswith("/rest/v1/alpha_hunter_snapshots"):
                assert other, "both distinct RPC identities must exist before readback"
                return Response([{"run_id": other[0]}])
            return Response([])

    config = SupabaseConfig(
        url="https://example.supabase.co", key="SYNTHETIC_TEST_ONLY",
        atomic_core_scan_writes=True, verify_core_scan_readback=True,
        max_retries=0, retry_backoff_seconds=0,
    )
    session = Session()

    def worker(minute):
        snapshot = {
            "version": "e6-cross-run-readback",
            "collected_at_utc": f"2026-11-21T19:{minute}:00+00:00",
            "product_type": "usdt-futures",
            "symbols": [{
                "symbol": "BTCUSDT", "last_price": 65000.0,
                "trade_permission": False, "state": "WATCH",
                "execution_setup": {"direction": None, "rr": None},
            }],
        }
        with pytest.raises(SupabaseStorageError, match="readback"):
            SupabaseStorage(config, session=session).save_snapshot(snapshot)

    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in (pool.submit(worker, "10"), pool.submit(worker, "11")):
            future.result(timeout=15)

    assert len(posts) == 2 and posts[0] != posts[1]
    assert len(reads) == 10
    assert len({url.rsplit("/", 1)[-1] for url, _ in reads}) == 5
    assert {params["run_id"] for _, params in reads} == {"eq." + x for x in posts}
