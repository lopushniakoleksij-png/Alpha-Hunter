"""Harada E6: concurrent readback transport failures fail closed independently.

In-memory HTTP simulation only; no private PostgreSQL trigger proof.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock, get_ident

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def test_concurrent_receipts_cannot_bypass_distinct_readback_transport_failures():
    barrier = Barrier(2, timeout=10)
    lock = Lock()

    class Response:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self.payload = payload
            self.text = text

        def json(self):
            if isinstance(self.payload, Exception):
                raise self.payload
            return self.payload

    class Session:
        def __init__(self):
            self.posts = []
            self.gets = []
            self.worker_modes = {}

        def post(self, url, **kwargs):
            assert url.endswith("/rpc/alpha_hunter_commit_core_scan_v01")
            body = json.loads(kwargs["data"])
            with lock:
                self.posts.append((url, kwargs["data"]))
            barrier.wait()
            return Response(200, {
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
                self.gets.append((get_ident(), url, dict(kwargs.get("params", {}))))
                mode = self.worker_modes[get_ident()]
            if mode == "http_503":
                return Response(503, {"error": "temporary unavailable"}, "unavailable")
            return Response(200, ValueError("malformed JSON"), "{broken")

    session = Session()
    config = SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        verify_core_scan_readback=True,
        max_retries=0,
    )

    def submit(mode):
        with lock:
            session.worker_modes[get_ident()] = mode
        snapshot = {
            "version": "e6-readback-transport-failure",
            "collected_at_utc": "2026-11-19T08:00:00+00:00",
            "product_type": "usdt-futures",
            "symbols": [{
                "symbol": "BTCUSDT", "last_price": 65000.0,
                "trade_permission": False, "state": "WATCH",
                "execution_setup": {"direction": None, "rr": None},
            }],
        }
        with pytest.raises(SupabaseStorageError):
            SupabaseStorage(config, session=session).save_snapshot(snapshot)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, mode) for mode in ("http_503", "bad_json")]
        for future in futures:
            future.result(timeout=15)

    assert len(session.posts) == 2
    assert session.posts[0] == session.posts[1]
    assert len(session.gets) == 2
    assert all(url.endswith("/rest/v1/alpha_hunter_snapshots")
               for _, url, _ in session.gets)
    run_id = json.loads(session.posts[0][1])["p_parent"][0]["run_id"]
    assert all(params["run_id"] == "eq." + run_id
               for _, _, params in session.gets)
    assert len({worker for worker, _, _ in session.gets}) == 2
    # No legacy REST fallback or downstream paper writes.
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url
               for url, _ in session.posts)
