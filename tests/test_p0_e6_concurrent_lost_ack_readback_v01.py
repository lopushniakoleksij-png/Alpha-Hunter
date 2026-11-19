"""E6 isolated concurrent lost-ACK retry followed by failed independent readback.

No real database or network partition; does not certify private PG17.
"""
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock, get_ident

import pytest
import requests

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def test_two_concurrent_lost_ack_retries_fail_closed_on_missing_readback():
    barrier = Barrier(2, timeout=10)
    lock = Lock()
    attempts = defaultdict(list)
    gets = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class Session:
        def post(self, url, **kwargs):
            assert url.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")
            thread = get_ident()
            with lock:
                attempts[thread].append(kwargs["data"])
                count = len(attempts[thread])
            if count == 1:
                barrier.wait()
                raise requests.ConnectionError("synthetic acknowledgement lost")
            body = json.loads(kwargs["data"])
            return Response({
                "committed": True,
                "run_id": body["p_parent"][0]["run_id"],
                "parent_count": len(body["p_parent"]),
                "symbol_count": len(body["p_children"]),
                "signal_count": len(body["p_signals"]),
                "feature_count": len(body["p_features"]),
                "readiness_count": len(body["p_readiness"]),
            })

        def get(self, url, **kwargs):
            with lock:
                gets.append((url, kwargs.get("params", {})))
            return Response([])

    session = Session()
    config = SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_ONLY",
        atomic_core_scan_writes=True,
        verify_core_scan_readback=True,
        max_retries=1,
        retry_backoff_seconds=0,
    )

    def worker():
        snapshot = {
            "version": "isolated-e6-lost-ack",
            "collected_at_utc": "2026-11-19T21:00:00+00:00",
            "product_type": "usdt-futures",
            "symbols": [{
                "symbol": "BTCUSDT",
                "last_price": 65000.0,
                "trade_permission": False,
                "state": "WATCH",
                "execution_setup": {"direction": None, "rr": None},
            }],
        }
        with pytest.raises(SupabaseStorageError, match="readback"):
            SupabaseStorage(config, session=session).save_snapshot(snapshot)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)

    assert len(attempts) == 2
    assert all(len(items) == 2 and items[0] == items[1] for items in attempts.values())
    assert len({items[0] for items in attempts.values()}) == 1
    assert len(gets) == 10  # Five independent readbacks per worker.
    assert len({url.rsplit("/", 1)[-1] for url, _ in gets}) == 5
    run_id = json.loads(next(iter(attempts.values()))[0])["p_parent"][0]["run_id"]
    assert all(params["run_id"] == "eq." + run_id for _, params in gets)
    # Exactly four RPC posts, no partial REST fallback or post-readback retry.
    assert sum(map(len, attempts.values())) == 4
