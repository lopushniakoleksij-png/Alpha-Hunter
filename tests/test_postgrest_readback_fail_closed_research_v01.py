"""Synthetic PostgREST read-boundary regression; no network or production writes.

A failed/ambiguous read is not evidence of an absent canonical snapshot.
This does not test production RLS, grants, or unknown-COMMIT recovery.
"""
import pytest
import requests
import app as dashboard


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def isolated_read_client(monkeypatch):
    monkeypatch.setattr(dashboard, "SUPABASE_URL", "https://invalid.example")
    monkeypatch.setattr(dashboard, "SUPABASE_KEY", "synthetic-not-a-secret")
    monkeypatch.setattr(dashboard, "SUPABASE_READ_ATTEMPTS", 2)
    monkeypatch.setattr(dashboard, "SUPABASE_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(dashboard.time, "sleep", lambda _: None)


@pytest.mark.parametrize("payload", [
    {"run_id": "synthetic"}, None, "unknown", False, 0,
])
def test_non_array_postgrest_readback_never_means_absent(monkeypatch, payload):
    calls = []
    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse(200, payload)
    monkeypatch.setattr(dashboard.requests, "get", fake_get)
    with pytest.raises(RuntimeError, match="Unexpected Supabase response shape"):
        dashboard.supabase_get_rows("alpha_hunter_snapshots", {"run_id": "eq.synthetic"})
    assert len(calls) == 1
    assert calls[0]["timeout"] > 0


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
def test_nontransient_http_error_is_not_empty_evidence(monkeypatch, status):
    calls = []
    def fake_get(*args, **kwargs):
        calls.append(1)
        return FakeResponse(status, {"message": "not evidence"})
    monkeypatch.setattr(dashboard.requests, "get", fake_get)
    with pytest.raises(requests.HTTPError):
        dashboard.supabase_get_rows("alpha_hunter_snapshots", {"run_id": "eq.synthetic"})
    assert len(calls) == 1


def test_transient_failure_exhaustion_fails_closed_without_write(monkeypatch):
    calls = []
    def fake_get(*args, **kwargs):
        calls.append(1)
        raise requests.ConnectionError("synthetic disconnected read")
    monkeypatch.setattr(dashboard.requests, "get", fake_get)
    monkeypatch.setattr(dashboard.requests, "post",
                        lambda *args, **kwargs: pytest.fail("readback must not POST"))
    with pytest.raises(requests.ConnectionError):
        dashboard.supabase_get_rows("alpha_hunter_snapshots", {"run_id": "eq.synthetic"})
    assert len(calls) == 2


def test_successful_exact_run_read_preserves_payload(monkeypatch):
    row = {"run_id": "synthetic", "symbol_count": 2, "payload": {"run_id": "synthetic"}}
    monkeypatch.setattr(dashboard.requests, "get",
                        lambda *args, **kwargs: FakeResponse(200, [row]))
    assert dashboard.supabase_get_rows(
        "alpha_hunter_snapshots", {"run_id": "eq.synthetic"}
    ) == [row]
