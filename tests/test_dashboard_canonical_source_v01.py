import app as dashboard


class FakeResponse:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self._rows


def test_latest_snapshot_filters_to_canonical_run_source(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse([{
            "payload": {
                "validation_identity": {
                    "run_source": "RENDER",
                },
                "multi_strategy_summary": {
                    "configured_strategy_count": 10,
                },
            },
        }])

    monkeypatch.setattr(dashboard, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(dashboard, "SUPABASE_KEY", "test")
    monkeypatch.setattr(dashboard, "CANONICAL_RUN_SOURCE", "RENDER")
    monkeypatch.setattr(dashboard.requests, "get", fake_get)

    payload = dashboard.latest_snapshot()

    params = calls[0][1]["params"]
    assert params["payload->validation_identity->>run_source"] == "eq.RENDER"
    assert payload["validation_identity"]["run_source"] == "RENDER"


def test_latest_snapshot_rejects_source_mismatch(monkeypatch):
    def fake_get(url, **kwargs):
        return FakeResponse([{
            "payload": {
                "validation_identity": {
                    "run_source": "GITHUB_REALTIME_HOURLY",
                },
            },
        }])

    monkeypatch.setattr(dashboard, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(dashboard, "SUPABASE_KEY", "test")
    monkeypatch.setattr(dashboard, "CANONICAL_RUN_SOURCE", "RENDER")
    monkeypatch.setattr(dashboard.requests, "get", fake_get)

    try:
        dashboard.latest_snapshot()
    except RuntimeError as exc:
        assert "source mismatch" in str(exc).lower()
    else:
        raise AssertionError("source mismatch must fail closed")


def test_latest_snapshot_rejects_legacy_payload(monkeypatch):
    def fake_get(url, **kwargs):
        return FakeResponse([{"payload": {"version": "0.7.1"}}])

    monkeypatch.setattr(dashboard, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(dashboard, "SUPABASE_KEY", "test")
    monkeypatch.setattr(dashboard, "CANONICAL_RUN_SOURCE", "RENDER")
    monkeypatch.setattr(dashboard.requests, "get", fake_get)

    try:
        dashboard.latest_snapshot()
    except RuntimeError as exc:
        assert "validation identity" in str(exc).lower()
    else:
        raise AssertionError("legacy payload must fail closed")
