import performance_job


class _Settings:
    url = "https://example.supabase.co"
    key = "service-role-key"
    timeout_seconds = 15


class _Response:
    status_code = 201


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
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": '{"fills_considered":0,"rows_persisted":0,'
                '"order_details_connected":0,"order_detail_failures":0,'
                '"read_only_get":true,"no_order_write_path":true}',
                "stderr": "",
            },
        )(),
    )
    monkeypatch.setattr(
        performance_job.requests,
        "post",
        lambda *args, **kwargs: _Response(),
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
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "returncode": 12,
                "stdout": '{"fills_considered":13,"rows_persisted":0,'
                '"order_details_connected":0,"order_detail_failures":13,'
                '"read_only_get":true,"no_order_write_path":true}',
                "stderr": "",
            },
        )(),
    )
    monkeypatch.setattr(
        performance_job.requests,
        "post",
        lambda *args, **kwargs: _Response(),
    )

    assert performance_job.main() == 0

    captured = capsys.readouterr()
    assert "PERFORMANCE SIGNALS SAVED: 60" in captured.out
    assert "READ-ONLY EXECUTION QUALITY COLLECTION DEGRADED" in captured.err



def test_collector_telemetry_persists_only_sanitized_health(monkeypatch):
    captured = {}

    class _TelemetryResponse:
        status_code = 201

    def fake_post(url, *, headers, data, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["row"] = performance_job.json.loads(data)
        captured["timeout"] = timeout
        return _TelemetryResponse()

    monkeypatch.setattr(performance_job.requests, "post", fake_post)

    performance_job._persist_collector_telemetry(
        _Settings(),
        snapshot={"run_id": "canonical-run-1"},
        snapshot_source="SUPABASE_CANONICAL",
        collector_exists=True,
        bitget_credentials_configured=True,
        subprocess_started=True,
        subprocess_exit_code=4,
        result={
            "fills_considered": 13,
            "order_details_connected": 0,
            "order_detail_failures": 0,
            "rows_persisted": 0,
            "read_only_get": True,
            "no_order_write_path": True,
        },
    )

    row = captured["row"]
    assert row["source_run_id"] == "canonical-run-1"
    assert row["collector_status"] == "DEGRADED"
    assert row["subprocess_exit_code"] == 4
    assert row["bitget_credentials_configured"] is True
    assert row["fills_considered"] == 13
    assert row["rows_persisted"] == 0
    assert row["trade_permission"] is False
    assert row["evidence"]["credential_values_persisted"] is False
    assert row["evidence"]["raw_order_ids_persisted_here"] is False
    assert "BITGET_API_KEY" not in performance_job.json.dumps(row)
    assert "BITGET_SECRET_KEY" not in performance_job.json.dumps(row)


def test_parse_collector_result_tolerates_prefix_noise():
    parsed = performance_job._parse_collector_result(
        'notice before json\n{"fills_considered":13,"rows_persisted":7}\n'
    )
    assert parsed == {"fills_considered": 13, "rows_persisted": 7}
