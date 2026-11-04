"""Synthetic PostgREST per-row shape contract: no network, writes or production data."""
import pytest
import requests
import app as dashboard


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def isolated_client(monkeypatch):
    monkeypatch.setattr(dashboard, "SUPABASE_URL", "https://invalid.example")
    monkeypatch.setattr(dashboard, "SUPABASE_KEY", "synthetic")
    monkeypatch.setattr(dashboard, "SUPABASE_READ_ATTEMPTS", 2)
    monkeypatch.setattr(dashboard, "SUPABASE_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(dashboard.time, "sleep", lambda _: None)
    monkeypatch.setattr(dashboard.requests, "post",
                        lambda *args, **kwargs: pytest.fail("read must not write"))


@pytest.mark.parametrize("payload", [
    [None], [False], [0], ["unexpected"], [[]],
    [{"run_id": "synthetic"}, None],
    [None, {"run_id": "synthetic"}],
])
def test_malformed_row_elements_fail_closed_without_retry(monkeypatch, payload):
    calls = []
    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse(payload)
    monkeypatch.setattr(dashboard.requests, "get", fake_get)
    with pytest.raises(RuntimeError, match="Unexpected Supabase response shape"):
        dashboard.supabase_get_rows("alpha_hunter_snapshots", {"run_id": "eq.synthetic"})
    assert len(calls) == 1
    assert calls[0]["timeout"] > 0


@pytest.mark.parametrize("payload", [
    [], [{"run_id": "synthetic"}], [{"run_id": "a"}, {"run_id": "b"}],
])
def test_valid_row_arrays_are_preserved(monkeypatch, payload):
    monkeypatch.setattr(dashboard.requests, "get",
                        lambda *args, **kwargs: FakeResponse(payload))
    assert dashboard.supabase_get_rows(
        "alpha_hunter_snapshots", {"run_id": "eq.synthetic"}
    ) == payload
