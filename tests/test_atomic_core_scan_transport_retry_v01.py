"""Harada E2/E3: transport-level mock contract tests for opt-in atomic core RPC.

The server's database commit is emulated. These tests DO NOT provide real
network-fault or authentic production-trigger evidence. PostgreSQL 17's
separate-session lost-response and concurrency tests provide server-side QA.
"""
import json

import pytest
import requests

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class QAResponse:
    def __init__(self, payload):
        self.status_code = 200
        self.payload = payload
        self.text = ""

    def json(self):
        return self.payload


class CommittedButResponseLostSession:
    """Pretend server accepted first request, but caller lost its response."""

    def __init__(self, *, exception_factory, lose_all=False):
        self.exception_factory = exception_factory
        self.lose_all = lose_all
        self.calls = []
        self.first_committed_payload = None

    def post(self, url, **kwargs):
        assert url.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")
        assert kwargs["headers"]["Prefer"] == "return=representation"
        request = json.loads(kwargs["data"])
        self.calls.append((url, request))
        if self.first_committed_payload is None:
            # This models the server commit, NOT actual PostgreSQL execution.
            self.first_committed_payload = request
            raise self.exception_factory("QA connection dropped after simulated commit")
        if self.lose_all:
            raise self.exception_factory("QA repeat acknowledgement lost")
        result = {
            "committed": True,
            "run_id": request["p_parent"][0]["run_id"],
            "parent_count": len(request["p_parent"]),
            "symbol_count": len(request["p_children"]),
            "signal_count": len(request["p_signals"]),
            "feature_count": len(request["p_features"]),
            "readiness_count": len(request["p_readiness"]),
        }
        return QAResponse(result)


def sample_snapshot():
    return {
        "version": "isolated-transport-contract",
        "collected_at_utc": "2026-11-08T12:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT",
            "last_price": 65000.0,
            "trade_permission": False,
            "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }


def atomic_config():
    return SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        max_retries=1,
        retry_backoff_seconds=0,
    )


@pytest.mark.parametrize("exception_factory", [requests.ConnectionError, requests.Timeout])
def test_same_run_id_and_identical_payload_after_ambiguous_transport_failure(exception_factory):
    session = CommittedButResponseLostSession(exception_factory=exception_factory)
    run_id = SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())

    assert len(session.calls) == 2
    first_url, first_request = session.calls[0]
    second_url, second_request = session.calls[1]
    assert first_url == second_url
    assert first_request == second_request
    assert first_request == session.first_committed_payload
    assert first_request["p_parent"][0]["run_id"] == run_id
    assert first_request["p_readiness"][0]["run_id"] == run_id
    assert all(not row["trade_permission"] for row in first_request["p_children"])
    assert all(not row["trade_permission"] for row in first_request["p_readiness"])


@pytest.mark.parametrize("exception_factory", [requests.ConnectionError, requests.Timeout])
def test_exhausted_ambiguous_ack_retries_fail_closed_without_legacy_upsert(exception_factory):
    session = CommittedButResponseLostSession(exception_factory=exception_factory, lose_all=True)
    with pytest.raises(SupabaseStorageError, match="after 2 attempts"):
        SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())

    assert len(session.calls) == 2
    assert session.calls[0] == session.calls[1]
    # A transport error is AMBIGUOUS: caller cannot assume rollback or commit.
    # No independent REST family fallback must run.
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.calls)


class TransientHttpFailureSession:
    """Simulate an ambiguous gateway response; no actual network is contacted."""

    def __init__(self, *, status_code, fail_all=False):
        self.status_code = status_code
        self.fail_all = fail_all
        self.calls = []

    def post(self, url, **kwargs):
        request = json.loads(kwargs["data"])
        self.calls.append((url, request))
        if self.fail_all or len(self.calls) == 1:
            response = QAResponse({"error": "synthetic gateway failure"})
            response.status_code = self.status_code
            response.text = "synthetic gateway failure"
            return response
        return QAResponse({
            "committed": True,
            "run_id": request["p_parent"][0]["run_id"],
            "parent_count": len(request["p_parent"]),
            "symbol_count": len(request["p_children"]),
            "signal_count": len(request["p_signals"]),
            "feature_count": len(request["p_features"]),
            "readiness_count": len(request["p_readiness"]),
        })


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
def test_atomic_rpc_retryable_http_status_preserves_exact_identity(status_code):
    session = TransientHttpFailureSession(status_code=status_code)
    run_id = SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 2
    assert session.calls[0] == session.calls[1]
    assert session.calls[0][1]["p_parent"][0]["run_id"] == run_id
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.calls)


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
def test_atomic_rpc_exhausted_retryable_http_status_fails_closed(status_code):
    session = TransientHttpFailureSession(status_code=status_code, fail_all=True)
    with pytest.raises(SupabaseStorageError, match=f"HTTP {status_code}"):
        SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 2
    assert session.calls[0] == session.calls[1]
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.calls)
