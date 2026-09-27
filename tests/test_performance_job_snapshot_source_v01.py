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

    monkeypatch.setattr(
        performance_job,
        "_verify_canonical_signal_rows",
        lambda settings, received: {
            "run_id": received["run_id"],
            "expected_count": 0,
            "observed_count": 0,
            "missing_count": 0,
            "unexpected_count": 0,
            "verified": True,
            "write_path": "NONE",
        },
    )
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

    out = capsys.readouterr().out
    assert "PERFORMANCE SNAPSHOT SOURCE: SUPABASE_CANONICAL" in out
    assert "PERFORMANCE SIGNALS VERIFIED: 0/0 write_path=NONE" in out


def test_performance_job_fails_closed_when_no_snapshot_but_collector_still_runs(
    monkeypatch,
):
    collector_called = {"value": False}

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
    monkeypatch.setattr(
        performance_job.SupabaseConfig,
        "from_environment",
        lambda config: _Settings(),
    )

    def fake_run(*args, **kwargs):
        collector_called["value"] = True
        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": '{"fills_considered":0,"rows_persisted":0,'
                '"order_details_connected":0,"order_detail_failures":0,'
                '"read_only_get":true,"no_order_write_path":true}',
                "stderr": "",
            },
        )()

    monkeypatch.setattr(performance_job.subprocess, "run", fake_run)
    monkeypatch.setattr(
        performance_job.requests,
        "post",
        lambda *args, **kwargs: _Response(),
    )

    try:
        performance_job.main()
    except SystemExit as exc:
        assert str(exc) == "No latest snapshot found"
    else:
        raise AssertionError("performance_job.main() should fail closed")

    assert collector_called["value"] is True



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

    monkeypatch.setattr(
        performance_job,
        "_verify_canonical_signal_rows",
        lambda settings, received: {
            "run_id": received["run_id"],
            "expected_count": 60,
            "observed_count": 60,
            "missing_count": 0,
            "unexpected_count": 0,
            "verified": True,
            "write_path": "NONE",
        },
    )
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
    assert "PERFORMANCE SIGNALS VERIFIED: 60/60 write_path=NONE" in captured.out
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



def test_render_cron_identity_is_restored_before_snapshot_load(monkeypatch):
    snapshot = {
        "run_id": "run-render-cron",
        "collected_at_utc": "2026-09-27T15:03:00+00:00",
        "symbols": [],
    }
    observed = {}

    monkeypatch.setenv("RENDER_SERVICE_NAME", "Alpha-Hunter")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("ALPHA_HUNTER_RUN_SOURCE", raising=False)
    monkeypatch.delenv("ALPHA_HUNTER_RUNTIME_ROLE", raising=False)

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
        performance_job.SupabaseConfig,
        "from_environment",
        lambda config: _Settings(),
    )

    def fake_load_previous_snapshot(config_path, config, cloud_settings=None):
        observed["run_source"] = performance_job.os.getenv(
            "ALPHA_HUNTER_RUN_SOURCE"
        )
        observed["runtime_role"] = performance_job.os.getenv(
            "ALPHA_HUNTER_RUNTIME_ROLE"
        )
        observed["cloud_settings"] = cloud_settings
        return snapshot, "SUPABASE_CANONICAL"

    monkeypatch.setattr(
        performance_job,
        "load_previous_snapshot",
        fake_load_previous_snapshot,
    )

    monkeypatch.setattr(
        performance_job,
        "_verify_canonical_signal_rows",
        lambda settings, received: {
            "run_id": received["run_id"],
            "expected_count": 0,
            "observed_count": 0,
            "missing_count": 0,
            "unexpected_count": 0,
            "verified": True,
            "write_path": "NONE",
        },
    )
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
    assert observed["run_source"] == "RENDER_CRON"
    assert observed["runtime_role"] == "RENDER_CRON"
    assert isinstance(observed["cloud_settings"], _Settings)


def test_explicit_runtime_identity_is_not_overwritten(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_NAME", "Alpha-Hunter")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("ALPHA_HUNTER_RUN_SOURCE", "EXPLICIT_SOURCE")
    monkeypatch.setenv("ALPHA_HUNTER_RUNTIME_ROLE", "EXPLICIT_ROLE")

    assert performance_job._align_render_cron_identity() == "RENDER_CRON"
    assert performance_job.os.getenv("ALPHA_HUNTER_RUN_SOURCE") == "EXPLICIT_SOURCE"
    assert performance_job.os.getenv("ALPHA_HUNTER_RUNTIME_ROLE") == "EXPLICIT_ROLE"



def test_canonical_signal_verification_is_get_only(monkeypatch):
    snapshot = {
        "run_id": "run-read-only",
        "symbols": [{"symbol": "BTCUSDT"}],
    }
    captured = {}

    monkeypatch.setattr(
        performance_job,
        "extract_signal_rows",
        lambda received: [{"signal_id": "sig-1"}],
    )

    class _GetResponse:
        status_code = 200

        def json(self):
            return [{"signal_id": "sig-1"}]

    def fake_get(url, *, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _GetResponse()

    monkeypatch.setattr(performance_job.requests, "get", fake_get)

    result = performance_job._verify_canonical_signal_rows(
        _Settings(),
        snapshot,
    )

    assert result["verified"] is True
    assert result["expected_count"] == 1
    assert result["observed_count"] == 1
    assert result["write_path"] == "NONE"
    assert captured["url"].endswith("/rest/v1/alpha_hunter_signals")
    assert captured["params"]["run_id"] == "eq.run-read-only"


def test_performance_job_has_no_signal_write_path():
    source = performance_job.Path(performance_job.__file__).read_text(
        encoding="utf-8"
    )
    assert "PerformanceStorage" not in source
    assert ".save_signals(" not in source
    assert (
        'requests.post(\n        f"{settings.url}/rest/v1/alpha_hunter_signals"'
        not in source
    )
