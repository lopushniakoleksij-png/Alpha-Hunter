"""Harada E6: concurrent identical atomic submissions remain identity-stable.

Isolated in-memory HTTP mock only. Does not certify private PG17 trigger
concurrency, advisory locking, or production persistence.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage


def test_two_concurrent_atomic_writers_preserve_identical_run_and_payload():
    barrier = Barrier(2, timeout=10)
    lock = Lock()

    class Response:
        status_code = 200
        text = ""

        def __init__(self, receipt):
            self.receipt = receipt

        def json(self):
            return self.receipt

    class RecordingSession:
        def __init__(self):
            self.requests = []

        def post(self, url, **kwargs):
            assert url.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")
            payload = json.loads(kwargs["data"])
            with lock:
                self.requests.append((url, kwargs["data"]))
            barrier.wait()
            return Response({
                "committed": True,
                "run_id": payload["p_parent"][0]["run_id"],
                "parent_count": len(payload["p_parent"]),
                "symbol_count": len(payload["p_children"]),
                "signal_count": len(payload["p_signals"]),
                "feature_count": len(payload["p_features"]),
                "readiness_count": len(payload["p_readiness"]),
            })

    session = RecordingSession()
    config = SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        max_retries=0,
    )
    snapshot = {
        "version": "isolated-concurrency-contract",
        "collected_at_utc": "2026-11-19T08:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT",
            "last_price": 65000.0,
            "trade_permission": False,
            "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }

    def submit():
        return SupabaseStorage(config, session=session).save_snapshot(snapshot)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        run_ids = [f.result(timeout=15) for f in futures]

    assert run_ids[0] == run_ids[1]
    assert len(session.requests) == 2
    assert session.requests[0] == session.requests[1]
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.requests)
    payload = json.loads(session.requests[0][1])
    assert payload["p_parent"][0]["run_id"] == run_ids[0]
    assert all(row["trade_permission"] is False for row in payload["p_children"])
    assert all(row["trade_permission"] is False for row in payload["p_readiness"])


def test_concurrent_atomic_receipts_with_missing_independent_readback_fail_closed():
    """Two matching RPC receipts cannot override missing independently read rows."""
    import pytest
    from alpha_hunter.storage import SupabaseStorageError

    barrier = Barrier(2, timeout=10)
    lock = Lock()

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Session:
        def __init__(self):
            self.posts = []
            self.gets = []

        def post(self, url, **kwargs):
            payload = json.loads(kwargs["data"])
            with lock:
                self.posts.append((url, kwargs["data"]))
            barrier.wait()
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
            with lock:
                self.gets.append((url, dict(kwargs.get("params", {}))))
            return Response([])  # Missing parent even though RPC claims committed.

    session = Session()
    config = SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        verify_core_scan_readback=True,
        max_retries=0,
    )

    def submit():
        snapshot = {
            "version": "isolated-concurrency-readback",
            "collected_at_utc": "2026-11-19T08:00:00+00:00",
            "product_type": "usdt-futures",
            "symbols": [{
                "symbol": "BTCUSDT",
                "last_price": 65000.0,
                "trade_permission": False,
                "state": "WATCH",
                "execution_setup": {"direction": None, "rr": None},
            }],
        }
        with pytest.raises(SupabaseStorageError):
            SupabaseStorage(config, session=session).save_snapshot(snapshot)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)

    assert len(session.posts) == 2
    assert session.posts[0] == session.posts[1]
    assert len(session.gets) == 10  # Five independent family reads per writer.
    expected_tables = {
        "alpha_hunter_snapshots",
        "alpha_hunter_symbol_snapshots",
        "alpha_hunter_signals",
        "alpha_hunter_signal_features",
        "alpha_hunter_readiness_observations_v01",
    }
    for table in expected_tables:
        assert sum(url.endswith("/rest/v1/" + table) for url, _ in session.gets) == 2
    run_id = json.loads(session.posts[0][1])["p_parent"][0]["run_id"]
    assert all(params["run_id"] == "eq." + run_id for _, params in session.gets)
    assert all(params["limit"] in {"1", "2"} for _, params in session.gets)
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.posts)
    assert len(session.posts) == 2  # No legacy fallback after failed readback.
