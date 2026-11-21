"""E6 isolated QA: matching identities do not certify persisted child content.

Synthetic HTTP only. No private SQL, production database or paper admissions.
"""
import json

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def test_atomic_success_with_mutated_symbol_payload_fails_closed():
    class Response:
        status_code = 200
        text = ""

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class Session:
        def __init__(self):
            self.posts = []
            self.gets = []

        def post(self, url, **kwargs):
            assert url.endswith("/rpc/alpha_hunter_commit_core_scan_v01"), (
                "Unexpected downstream or legacy write after corrupt readback"
            )
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
            assert kwargs["params"]["select"] == "*"
            self.gets.append((url, kwargs["params"]))
            mapping = {
                "alpha_hunter_snapshots": "p_parent",
                "alpha_hunter_symbol_snapshots": "p_children",
                "alpha_hunter_signals": "p_signals",
                "alpha_hunter_signal_features": "p_features",
                "alpha_hunter_readiness_observations_v01": "p_readiness",
            }
            table = url.rsplit("/", 1)[-1]
            rows = json.loads(json.dumps(self.posts[0][mapping[table]]))
            if table == "alpha_hunter_symbol_snapshots":
                assert len(rows) == 1
                rows[0]["payload"]["last_price"] = 1.0  # Same identity; corrupted evidence.
            return Response(rows)

    session = Session()
    config = SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        verify_core_scan_readback=True,
        verify_core_scan_content_readback=True,
        max_retries=0,
    )
    snapshot = {
        "version": "isolated-content-mutation",
        "collected_at_utc": "2026-11-20T10:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT",
            "last_price": 65000.0,
            "trade_permission": False,
            "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }
    with pytest.raises(SupabaseStorageError, match="content readback mismatch"):
        SupabaseStorage(config, session=session).save_snapshot(snapshot)
    assert len(session.posts) == 1
    assert len(session.gets) == 5
    assert all(params["run_id"].startswith("eq.") for _, params in session.gets)
