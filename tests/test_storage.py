from datetime import datetime, timezone

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, build_run_id
from hourly import seconds_until_next_hour


class FakeResponse:
    status_code = 201
    text = ""


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def sample_snapshot():
    return {
        "version": "0.3.0",
        "collected_at_utc": "2026-07-26T18:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "SUIUSDT",
            "state": "WATCH_LONG",
            "trade_permission": False,
            "last_price": 0.75,
            "execution_setup": {"direction": None, "rr": None},
        }],
    }


def test_run_id_is_deterministic():
    first = sample_snapshot()
    second = sample_snapshot()
    assert build_run_id(first) == build_run_id(second)


def test_supabase_writes_parent_and_children():
    session = FakeSession()
    storage = SupabaseStorage(
        SupabaseConfig(url="https://example.supabase.co", key="secret"), session=session
    )
    run_id = storage.save_snapshot(sample_snapshot())
    assert len(run_id) == 32
    assert len(session.calls) == 2
    assert session.calls[0][1]["params"] == {"on_conflict": "run_id"}
    assert session.calls[1][1]["params"] == {"on_conflict": "run_id,symbol"}


def test_seconds_until_next_hour():
    now = datetime(2026, 7, 26, 18, 45, 30, tzinfo=timezone.utc)
    assert seconds_until_next_hour(now) == 870


def test_hourly_lock_prevents_overlap(tmp_path):
    from hourly import acquire_lock, release_lock
    lock = tmp_path / ".lock"
    assert acquire_lock(lock) is True
    assert acquire_lock(lock) is False
    release_lock(lock)
    assert acquire_lock(lock) is True
    release_lock(lock)


def test_env_file_loader(tmp_path, monkeypatch):
    from alpha_hunter.env import load_env_file
    env_file = tmp_path / ".env"
    env_file.write_text('SUPABASE_URL="https://demo.supabase.co"\n# comment\nSUPABASE_SERVICE_ROLE_KEY=test-key\n')
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert load_env_file(env_file) is True
    import os
    assert os.environ["SUPABASE_URL"] == "https://demo.supabase.co"
    assert os.environ["SUPABASE_SERVICE_ROLE_KEY"] == "test-key"
