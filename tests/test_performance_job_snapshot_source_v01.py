import performance_job


class _Settings:
    url = "https://example.supabase.co"
    key = "service-role-key"


def test_performance_job_unpacks_snapshot_source(monkeypatch, capsys):
    snapshot = {
        "run_id": "run-1",
        "collected_at_utc": "2026-09-27T11:23:18+00:00",
        "symbols": [],
    }
    saved = {}

    monkeypatch.setattr(
        performance_job,
        "load_env_file",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        performance_job,
        "load_config",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        performance_job,
        "load_previous_snapshot",
        lambda *args, **kwargs: (snapshot, "SUPABASE_CANONICAL"),
    )
    monkeypatch.setattr(
        performance_job.SupabaseConfig,
        "from_environment",
        lambda config: _Settings(),
    )

    class _Storage:
        def __init__(self, url, key):
            assert url == _Settings.url
            assert key == _Settings.key

        def save_signals(self, received):
            saved["snapshot"] = received
            return 0

    monkeypatch.setattr(performance_job, "PerformanceStorage", _Storage)
    monkeypatch.setattr(
        performance_job.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0})(),
    )

    assert performance_job.main() == 0
    assert saved["snapshot"] is snapshot

    out = capsys.readouterr().out
    assert "PERFORMANCE SNAPSHOT SOURCE: SUPABASE_CANONICAL" in out
    assert "PERFORMANCE SIGNALS SAVED: 0" in out


def test_performance_job_fails_closed_when_no_snapshot(monkeypatch):
    monkeypatch.setattr(
        performance_job,
        "load_env_file",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        performance_job,
        "load_config",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        performance_job,
        "load_previous_snapshot",
        lambda *args, **kwargs: (None, "NONE"),
    )

    try:
        performance_job.main()
    except SystemExit as exc:
        assert str(exc) == "No latest snapshot found"
    else:
        raise AssertionError("performance_job.main() should fail closed")



def test_readonly_execution_quality_failure_is_nonfatal(monkeypatch, capsys):
    snapshot = {
        "run_id": "run-2",
        "collected_at_utc": "2026-09-27T12:23:15+00:00",
        "symbols": [],
    }

    monkeypatch.setattr(
        performance_job,
        "load_env_file",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        performance_job,
        "load_config",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        performance_job,
        "load_previous_snapshot",
        lambda *args, **kwargs: (snapshot, "SUPABASE_CANONICAL"),
    )
    monkeypatch.setattr(
        performance_job.SupabaseConfig,
        "from_environment",
        lambda config: _Settings(),
    )

    class _Storage:
        def __init__(self, url, key):
            pass

        def save_signals(self, received):
            return 60

    monkeypatch.setattr(performance_job, "PerformanceStorage", _Storage)
    monkeypatch.setattr(
        performance_job.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 12})(),
    )

    assert performance_job.main() == 0

    captured = capsys.readouterr()
    assert "PERFORMANCE SIGNALS SAVED: 60" in captured.out
    assert "READ-ONLY EXECUTION QUALITY COLLECTION DEGRADED" in captured.err
