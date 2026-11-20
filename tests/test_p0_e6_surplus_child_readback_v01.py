"""E6 isolated negative: independently observed surplus child must fail closed.

No production DB, real orders, or private trigger graph are exercised.
"""
import json

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def test_atomic_receipt_with_surplus_symbol_row_rejects_independent_readback():
    class Response:
        status_code = 200
        text = ""

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    class Session:
        def __init__(self):
            self.posts = []
            self.gets = []

        def post(self, url, **kwargs):
            assert url.endswith("/rpc/alpha_hunter_commit_core_scan_v01")
            payload = json.loads(kwargs["data"])
            self.posts.append(payload)
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
            params = kwargs["params"]
            self.gets.append((url, dict(params)))
            payload = self.posts[0]
            tables = {
                "alpha_hunter_snapshots": ("p_parent", ("run_id",)),
                "alpha_hunter_symbol_snapshots": ("p_children", ("run_id", "symbol")),
                "alpha_hunter_signals": ("p_signals", ("run_id", "signal_id", "symbol")),
                "alpha_hunter_signal_features": ("p_features", ("run_id", "signal_id", "symbol")),
                "alpha_hunter_readiness_observations_v01": ("p_readiness", ("run_id", "symbol")),
            }
            table = url.rsplit("/", 1)[-1]
            key, columns = tables[table]
            rows = [{col: row.get(col) for col in columns} for row in payload[key]]
            if table == "alpha_hunter_symbol_snapshots":
                rows.append({"run_id": payload["p_parent"][0]["run_id"], "symbol": "UNEXPECTEDUSDT"})
            return Response(rows)

    session = Session()
    config = SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        verify_core_scan_readback=True,
        max_retries=0,
    )
    snapshot = {
        "version": "isolated-surplus-readback",
        "collected_at_utc": "2026-11-20T05:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT",
            "last_price": 65000.0,
            "trade_permission": False,
            "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }
    with pytest.raises(SupabaseStorageError, match="readback mismatch"):
        SupabaseStorage(config, session=session).save_snapshot(snapshot)
    assert len(session.posts) == 1
    assert len(session.gets) == 5
    assert all(params["run_id"].startswith("eq.") for _, params in session.gets)
    assert all(params["limit"] in {"1", "2"} for _, params in session.gets)
