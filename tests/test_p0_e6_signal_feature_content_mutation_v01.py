"""P0 E6: atomic success must not hide mutated signal/feature evidence.

Isolated in-memory HTTP only, no database, Docker, scanner or trades.
Unlike simple identity fixtures, both signal and feature arrays must be
POPULATED by the actual SupabaseStorage.save_snapshot serializer.
"""
import json

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


@pytest.mark.parametrize("family,field", [
    ("alpha_hunter_signals", "payload"),
    ("alpha_hunter_signal_features", "source_payload"),
    ("alpha_hunter_signals", "entry_price"),
    ("alpha_hunter_signal_features", "features"),
])
def test_atomic_ack_and_matching_five_family_ids_cannot_hide_content_corruption(family, field):
    """One RPC/5 independent GETs; fail closed before any downstream paper write."""

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
                "Unexpected fallback/downstream write after corrupted readback"
            )
            payload = json.loads(kwargs["data"])
            assert len(payload["p_parent"]) == 1
            assert len(payload["p_children"]) == 1
            assert len(payload["p_signals"]) == 1, "Signal fixture must be populated"
            assert len(payload["p_features"]) == 1, "Feature fixture must be populated"
            assert len(payload["p_readiness"]) == 1
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
            assert params["select"] == "*", "QA must inspect full submitted content"
            assert params["run_id"].startswith("eq.")
            self.gets.append((url, params))
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
                row = rows[0]
                assert field in row, "Requested corruption must affect an actual field"
                if field == "entry_price":
                    assert isinstance(row[field], (int, float)) and row[field] > 0
                    row[field] = row[field] + 500.0
                elif field == "payload":
                    assert isinstance(row[field], dict)
                    row[field]["trade_permission"] = True
                elif field == "source_payload":
                    assert isinstance(row[field], dict)
                    row[field]["last_price"] = 1.0
                else:  # nested feature payload
                    assert isinstance(row[field], dict)
                    row[field]["__QA_content_corrupted__"] = True
            return Response(rows)

    session = Session()
    config = SupabaseConfig(
        url="https://isolated.invalid",
        key="SYNTHETIC_TEST_ONLY",
        atomic_core_scan_writes=True,
        verify_core_scan_readback=True,
        verify_core_scan_content_readback=True,
        max_retries=0,
    )
    snapshot = {
        "version": "synthetic-only-content-mutation",
        "collected_at_utc": "2026-11-20T16:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT",
            "state": "WATCH_SHORT",
            "trade_permission": False,
            "last_price": 65000.0,
            "behaviour": {"volume_ratio": 1.4, "spread_pct": 0.02},
            "timeframes": {
                "1H": {"trend": "BEARISH", "indicators": {"ema_9": 64600.0}},
            },
            "execution_setup": {
                "direction": "SHORT",
                "entry": 65000.0,
                "stop": 65800.0,
                "target": 62800.0,
                "rr": 2.75,
                "checks": {"rr_minimum_met": False},
            },
        }],
    }
    with pytest.raises(SupabaseStorageError, match="content readback mismatch"):
        SupabaseStorage(config, session=session).save_snapshot(snapshot)
    assert len(session.posts) == 1
    assert len(session.gets) == 5
    expected_tables = (
        "alpha_hunter_snapshots",
        "alpha_hunter_symbol_snapshots",
        "alpha_hunter_signals",
        "alpha_hunter_signal_features",
        "alpha_hunter_readiness_observations_v01",
    )
    assert tuple(url.rsplit("/", 1)[-1] for url, _ in session.gets) == expected_tables
    assert len({params["run_id"] for _, params in session.gets}) == 1
