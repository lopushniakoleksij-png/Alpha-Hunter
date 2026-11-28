"""E6: concurrent committed receipts must not mask cross-run readback identity.

Synthetic in-memory transport only; no production-equivalent PostgreSQL proof.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock, get_ident
from unittest.mock import Mock

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload
        self.text = ""

    def json(self):
        return self.payload


@pytest.mark.parametrize("corrupted_table", [
    "alpha_hunter_snapshots",
    "alpha_hunter_symbol_snapshots",
    "alpha_hunter_readiness_observations_v01",
])
def test_concurrent_receipts_with_cross_run_readback_fail_closed(monkeypatch, corrupted_table):
    barrier = Barrier(2, timeout=10)
    lock = Lock()
    downstream = Mock(side_effect=AssertionError("downstream paper write"))
    monkeypatch.setattr(SupabaseStorage, "_insert_immutable", downstream)
    monkeypatch.setattr(SupabaseStorage, "_reconcile_paper_stages", downstream)

    class Session:
        def __init__(self):
            self.payloads = {}
            self.posts = []
            self.gets = []

        def post(self, url, **kwargs):
            assert url.endswith("/rpc/alpha_hunter_commit_core_scan_v01")
            payload = json.loads(kwargs["data"])
            with lock:
                self.payloads[get_ident()] = payload
                self.posts.append((url, kwargs["data"]))
            barrier.wait()
            return Response(200, {
                "committed": True,
                "run_id": payload["p_parent"][0]["run_id"],
                "parent_count": len(payload["p_parent"]),
                "symbol_count": len(payload["p_children"]),
                "signal_count": len(payload["p_signals"]),
                "feature_count": len(payload["p_features"]),
                "readiness_count": len(payload["p_readiness"]),
            })

        def get(self, url, **kwargs):
            table = url.rsplit("/", 1)[-1]
            params = kwargs["params"]
            with lock:
                payload = self.payloads[get_ident()]
                self.gets.append((get_ident(), table, dict(params)))
            families = {
                "alpha_hunter_snapshots": "p_parent",
                "alpha_hunter_symbol_snapshots": "p_children",
                "alpha_hunter_signals": "p_signals",
                "alpha_hunter_signal_features": "p_features",
                "alpha_hunter_readiness_observations_v01": "p_readiness",
            }
            columns = params["select"].split(",")
            rows = [
                {column: row.get(column) for column in columns}
                for row in payload[families[table]]
            ]
            if table == corrupted_table:
                # Correct counts and receipts, but one family belongs to another run.
                for row in rows:
                    row["run_id"] = "OTHER_SYNTHETIC_RUN"
            return Response(200, rows)

    session = Session()
    config = SupabaseConfig(
        url="https://synthetic.invalid",
        key="SYNTHETIC_TEST_ONLY",
        atomic_core_scan_writes=True,
        verify_core_scan_readback=True,
        max_retries=0,
    )

    def submit():
        snapshot = {
            "version": "e6-cross-run-identity",
            "collected_at_utc": "2026-11-19T08:00:00+00:00",
            "product_type": "usdt-futures",
            "symbols": [{
                "symbol": "BTCUSDT", "last_price": 65000.0,
                "state": "WATCH", "trade_permission": False,
                "execution_setup": {"direction": None, "rr": None},
            }],
        }
        with pytest.raises(SupabaseStorageError, match="Independent core scan readback mismatch"):
            SupabaseStorage(config, session=session).save_snapshot(snapshot)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)

    assert len(session.posts) == 2
    assert session.posts[0] == session.posts[1]
    assert len(session.gets) == 10
    assert len({worker for worker, _, _ in session.gets}) == 2
    run_id = json.loads(session.posts[0][1])["p_parent"][0]["run_id"]
    assert all(params["run_id"] == "eq." + run_id
               for _, _, params in session.gets)
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url
               for url, _ in session.posts)
    downstream.assert_not_called()
