"""E6 QA-only regression: matching row identities cannot mask parent/readiness corruption."""
import json

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


@pytest.mark.parametrize("family,field,bad_value", [
    ("alpha_hunter_snapshots", "symbol_count", 999),
    ("alpha_hunter_readiness_observations_v01", "reference_price", 1.0),
])
def test_atomic_receipt_with_mutated_non_symbol_family_fails_closed(family, field, bad_value):
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
                "No downstream or sequential fallback writes allowed"
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
            if table == family:
                assert len(rows) == 1
                rows[0][field] = bad_value
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
        "version": "isolated-parent-readiness-content-mutation",
        "collected_at_utc": "2026-11-20T13:00:00+00:00",
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
