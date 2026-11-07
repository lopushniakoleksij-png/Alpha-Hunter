"""Opt-in core-scan RPC contract tests (mock-only; no database access).

A passing result does NOT prove PostgreSQL trigger rollback or latency.
The SQL migration requires isolated DB integration tests before enablement.
"""
import json
from pathlib import Path

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self.payload = payload
        self.text = text

    def json(self):
        return self.payload


class RPCSession:
    def __init__(self, status_code=200, mutate=None):
        self.status_code = status_code
        self.mutate = mutate
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.status_code != 200:
            return FakeResponse(self.status_code, text="isolated simulated error")
        request = json.loads(kwargs["data"])
        result = {
            "committed": True,
            "run_id": request["p_parent"][0]["run_id"],
            "parent_count": len(request["p_parent"]),
            "symbol_count": len(request["p_children"]),
            "signal_count": len(request["p_signals"]),
            "feature_count": len(request["p_features"]),
            "readiness_count": len(request["p_readiness"]),
        }
        if self.mutate is not None:
            self.mutate(result)
        return FakeResponse(payload=result)


def sample_snapshot():
    return {
        "version": "isolated-rpc-contract",
        "collected_at_utc": "2026-11-07T08:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT",
            "last_price": 70000.0,
            "trade_permission": False,
            "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }


def config(**updates):
    return SupabaseConfig(
        url="https://example.supabase.co",
        key="FAKE_TEST_KEY",
        max_retries=0,
        retry_backoff_seconds=0,
        atomic_core_scan_writes=True,
        **updates,
    )


def test_atomic_flag_defaults_off():
    assert SupabaseConfig(url="https://example.supabase.co", key="dummy").atomic_core_scan_writes is False


def test_atomic_rpc_replaces_five_core_writes_and_checks_receipt():
    session = RPCSession()
    run_id = SupabaseStorage(config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 1
    url, args = session.calls[0]
    assert url.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")
    payload = json.loads(args["data"])
    assert payload["p_parent"][0]["run_id"] == run_id
    assert len(payload["p_children"]) == 1
    assert len(payload["p_readiness"]) == 1
    assert all(row["trade_permission"] is False for row in payload["p_readiness"])
    assert set(payload) == {
        "p_parent", "p_children", "p_signals", "p_features", "p_readiness"
    }


def test_rpc_failure_fails_closed_without_rest_fallback():
    session = RPCSession(status_code=500)
    with pytest.raises(SupabaseStorageError, match="atomic core scan RPC failed"):
        SupabaseStorage(config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 1
    assert "/rpc/alpha_hunter_commit_core_scan_v01" in session.calls[0][0]


def test_rpc_incomplete_receipt_is_rejected():
    session = RPCSession(mutate=lambda result: result.update(readiness_count=0))
    with pytest.raises(SupabaseStorageError, match="confirmation did not match"):
        SupabaseStorage(config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 1


def test_atomic_sql_candidate_has_non_escalating_permissions_and_required_fields():
    sql = (
        Path(__file__).resolve().parents[1]
        / "ops/sql/atomic_core_scan_rpc_candidate_v01.sql"
    ).read_text()
    assert "security invoker" in sql.lower()
    assert "set search_path = ''" in sql.lower()
    assert "to service_role" in sql.lower()
    assert "from public, anon, authenticated" in sql.lower()
    for table in (
        "alpha_hunter_snapshots",
        "alpha_hunter_symbol_snapshots",
        "alpha_hunter_signals",
        "alpha_hunter_signal_features",
        "alpha_hunter_readiness_observations_v01",
    ):
        assert "insert into public." + table in sql.lower()
    assert sql.lower().count("on conflict") >= 5
    assert sql.lower().count("do nothing") >= 5
    assert sql.lower().count("persisted content mismatch") >= 5
    for field in ("trade_permission", "features", "source_payload", "error_count"):
        assert field in sql.lower()
